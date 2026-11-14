"""Policy-gated agentic A0 graph; no generated code or implicit planner."""
import asyncio
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from time import monotonic
from typing import TypedDict
from uuid import uuid4

from app.coordinator.contracts import AgentLimits, AuditEvent, Evidence, MissionReport, MissionRequest, Proposal
from app.coordinator.policy import deterministic_proposal, rejection
from app.coordinator.providers import DecisionProvider
from app.coordinator.tools import ToolBox, required_tools

SKILL_PATH = Path(__file__).parent/'skills/mission-coordinator/SKILL.md'


@dataclass
class Runtime:
    request: MissionRequest
    directory: Path
    deadline: float
    run_id: str
    skill: str
    evidence: list[Evidence] = field(default_factory=list)
    audit: list[AuditEvent] = field(default_factory=list)
    artifacts: dict[str,str] = field(default_factory=dict)
    calls: int = 0
    model_calls: int = 0
    decision_calls: int = 0
    rounds: int = 0
    fallback: bool = False
    proposal: Proposal | None = None
    stop: str | None = None
    report: MissionReport | None = None

    def record(self, event: str, **details):
        self.audit.append(AuditEvent(sequence=len(self.audit)+1,event=event,details=details))


class AgentState(TypedDict):
    runtime: Runtime


class MissionAgent:
    def __init__(self, toolbox: ToolBox, provider: DecisionProvider | None = None, limits: AgentLimits | None = None):
        self.toolbox, self.provider = toolbox, provider
        self.limits = AgentLimits.model_validate(limits.model_dump()) if limits else AgentLimits()

    def _graph(self):
        # Optional extra: existing FastAPI startup never imports LangGraph.
        from langgraph.graph import END, START, StateGraph
        graph = StateGraph(AgentState)
        graph.add_node('inspect',self._inspect)
        graph.add_node('plan',self._plan)
        graph.add_node('policy',self._policy)
        graph.add_node('execute',self._execute)
        graph.add_node('evaluate',self._evaluate)
        graph.add_node('report',self._report)
        graph.add_edge(START,'inspect')
        graph.add_conditional_edges('inspect',lambda s:'report' if s['runtime'].stop else 'plan',{'plan':'plan','report':'report'})
        graph.add_edge('plan','policy')
        graph.add_conditional_edges('policy',lambda s:'report' if s['runtime'].stop else 'execute',{'execute':'execute','report':'report'})
        graph.add_edge('execute','evaluate')
        graph.add_edge('evaluate','policy')
        graph.add_edge('report',END)
        return graph.compile()

    async def run(self, request: MissionRequest, output_root: Path) -> MissionReport:
        # Revalidate caller-supplied/copied values before any tool execution.
        request = MissionRequest.model_validate(request.model_dump())
        run_id = uuid4().hex
        skill = SKILL_PATH.read_text(encoding='utf-8')
        runtime = Runtime(request=request,directory=output_root.resolve()/run_id,
                          deadline=monotonic()+self.limits.mission_timeout_s,run_id=run_id,skill=skill)
        from langsmith import tracing_context
        # Audit stays local even if a developer has global LangSmith tracing set.
        with tracing_context(enabled=False):
            state = await self._graph().ainvoke({'runtime':runtime},config={'recursion_limit':64,'callbacks':[]})
        return state['runtime'].report

    def _remaining(self, runtime):
        return runtime.deadline-monotonic()

    async def _inspect(self, state):
        rt = state['runtime']
        if not self.toolbox.matches(rt.request):
            rt.stop='scope_mismatch'
            rt.record('mission_rejected',reason=rt.stop)
        else:
            rt.calls=1
            rt.evidence.append(Evidence(evidence_id='e0001',tool='inspect_capabilities',agent_id=None,status='ready',
                                        data_kind='metadata',facts={'configured_agents':len(self.toolbox.registry.registered_ids),
                                                                   'validated_planner':False},dataset_ids=[],limitations=['metadata_not_scientific_evidence']))
            rt.record('tool_completed',tool='inspect_capabilities',evidence_id='e0001')
        return state

    async def _plan(self, state):
        return await self._propose(state,'plan')

    async def _evaluate(self, state):
        return await self._propose(state,'evaluate')

    async def _propose(self, state, phase):
        rt = state['runtime']
        if rt.stop:
            return state
        if self._remaining(rt) <= 0:
            rt.stop='mission_deadline'
            return state
        if rt.decision_calls >= self.limits.max_replans+2:
            rt.stop='decision_budget'
            return state
        rt.decision_calls+=1
        if self.provider is None or rt.fallback:
            rt.proposal=deterministic_proposal(rt.request,rt.evidence,self.limits.max_tool_calls-rt.calls)
        else:
            snapshot={'mission':rt.request.model_dump(mode='json'),
                      'capabilities':[c.model_dump() for c in self.toolbox.capabilities()],
                      'evidence':[e.model_dump() for e in rt.evidence],
                      'remaining_tool_calls':self.limits.max_tool_calls-rt.calls,
                      'remaining_replans':max(0,self.limits.max_replans-max(0,rt.rounds-1))}
            if self.provider.name == 'openai':
                rt.model_calls+=1
            try:
                output=await asyncio.wait_for(self.provider.propose(phase,snapshot,rt.skill),
                                               timeout=min(self.limits.model_timeout_s,self._remaining(rt)))
                rt.proposal=Proposal.model_validate(output.model_dump() if isinstance(output,Proposal) else output)
            except asyncio.TimeoutError:
                rt.fallback=True
                rt.record('deterministic_fallback',reason='model_timeout')
            except Exception:
                # Never log model/API exceptions, credentials or response bodies.
                rt.fallback=True
                rt.record('deterministic_fallback',reason='invalid_proposal_or_provider_failure')
            if rt.fallback:
                rt.proposal=deterministic_proposal(rt.request,rt.evidence,self.limits.max_tool_calls-rt.calls)
        rt.record('proposal',phase=phase,action=rt.proposal.action,tools=','.join(rt.proposal.tools),
                  rationale=rt.proposal.rationale,authoritative=False,
                  origin='deterministic' if self.provider is None or rt.fallback else self.provider.name)
        return state

    async def _policy(self, state):
        rt=state['runtime']
        if rt.stop:
            return state
        if self._remaining(rt)<=0:
            rt.stop='mission_deadline'
            return state
        reason=rejection(rt.proposal,rt.request,rt.evidence,rt.calls,rt.rounds,self.limits)
        if reason:
            rt.record('proposal_rejected',reason=reason)
            rt.fallback=True
            rt.proposal=deterministic_proposal(rt.request,rt.evidence,self.limits.max_tool_calls-rt.calls)
            reason=rejection(rt.proposal,rt.request,rt.evidence,rt.calls,rt.rounds,self.limits)
            if reason:
                rt.stop='execution_budget'
                rt.record('mission_stopped',reason=rt.stop)
                return state
        if rt.proposal.action=='finish':
            rt.stop='finished'
        return state

    async def _execute(self, state):
        rt=state['runtime']
        if self._remaining(rt)<=0:
            rt.stop='mission_deadline'
            return state
        rt.rounds+=1
        rt.calls+=len(rt.proposal.tools)
        rt.record('tools_started',tools=','.join(rt.proposal.tools),round=rt.rounds)
        started=monotonic()
        try:
            evidence,artifacts=await asyncio.wait_for(self.toolbox.execute(rt.proposal.tools,rt.request,
                rt.directory/'artifacts',len(rt.evidence)+1,min(self.limits.tool_timeout_s,self._remaining(rt))),
                timeout=max(0.001,self._remaining(rt)))
            rt.evidence.extend(evidence)
            rt.artifacts.update(artifacts)
            for entry in evidence:
                rt.record('tool_completed',tool=entry.tool,evidence_id=entry.evidence_id,status=entry.status,
                          data_kind=entry.data_kind,batch_elapsed_ms=round((monotonic()-started)*1000,3))
        except asyncio.TimeoutError:
            rt.stop='mission_deadline'
            rt.record('mission_stopped',reason=rt.stop)
        except Exception:
            rt.stop='tool_execution_failure'
            rt.record('mission_stopped',reason=rt.stop)
        return state

    async def _report(self, state):
        rt=state['runtime']
        by_tool={e.tool:e for e in rt.evidence}
        unmet=[]
        for tool in required_tools(rt.request):
            entry=by_tool.get(tool)
            if entry is None or entry.status in ('unavailable','failed'):
                unmet.append(f'{tool}:unavailable_or_not_executed')
        if 'route' in rt.request.objectives:
            if rt.request.start is None: unmet.append('route:start_missing')
            if rt.request.goal_point is None: unmet.append('route:goal_missing')
            unmet.append('route:validated_grid_masks_transforms_planner_and_validator_required')
        if 'radiation' in rt.request.objectives:
            if rt.request.context.parameters.eva_duration_min is None: unmet.append('radiation:duration_missing')
            if rt.request.context.parameters.radiation_budget_usv is None: unmet.append('radiation:budget_unknown')
        if rt.stop=='scope_mismatch': unmet.append('mission:scope_mismatch')
        if rt.stop=='tool_execution_failure': unmet.append('mission:tool_execution_failure')
        scientific=[e for e in rt.evidence if e.data_kind in ('observed','scenario') and e.status in ('ready','partial')]
        constraint_failed=any(e.facts.get('constraint_status')=='fail' and e.data_kind in ('observed','scenario') for e in scientific)
        if rt.stop=='mission_deadline': status='timed_out'
        elif rt.stop in ('execution_budget','decision_budget'): status='budget_exhausted'
        elif rt.stop=='tool_execution_failure' or 'route' in rt.request.objectives or constraint_failed or not scientific: status='blocked'
        elif unmet or any(e.data_kind!='observed' or e.status!='ready' for e in scientific): status='partial'
        else: status='complete'
        if constraint_failed: unmet.append('constraint:failed_in_returned_evidence_scope')
        rt.record('mission_completed',status=status,stop_reason=rt.stop)
        limits=['No validated planner/candidate is configured; no computed or astronaut-safe route is produced.',
                'Scenario/mock/prototype evidence never establishes physical safety; unknown constraints remain unknown.',
                'Final findings are constructed from typed tool facts, not model-authored claims.',
                'Native blocking worker threads may continue after cooperative timeout; no late result is promoted.']
        rt.report=MissionReport(run_id=rt.run_id,request=rt.request,
            requested_provider=self.provider.name if self.provider else 'deterministic',
            provider_model=getattr(self.provider,'model',None),limits=self.limits,capabilities=self.toolbox.capabilities(),
            fallback_used=rt.fallback,
            skill_sha256=hashlib.sha256(rt.skill.encode()).hexdigest(),status=status,
            route_status='unavailable' if 'route' in rt.request.objectives else 'not_requested',
            summary=f'Mission {status}: {len(scientific)} usable evidence results; {len(unmet)} unmet requirements. No safety determination.',
            evidence=rt.evidence,unmet_requirements=unmet,limitations=limits,tool_calls=rt.calls,model_calls=rt.model_calls,
            decision_calls=rt.decision_calls,replans=max(0,rt.rounds-1),audit=rt.audit,artifact_index=rt.artifacts,
            input_hashes=self.toolbox.input_hashes)
        rt.directory.mkdir(parents=True,exist_ok=True)
        await asyncio.to_thread((rt.directory/'report.json').write_text,rt.report.model_dump_json(indent=2),encoding='utf-8')
        return state
