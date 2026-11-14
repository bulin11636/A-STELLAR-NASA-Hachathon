"""Fixed tool surface. Models never choose paths, datasets or worker arguments."""
import asyncio
from pathlib import Path

from app.agents.registry import WorkerRegistry
from app.contracts.workers import RadiationResult, RoverTraverseResult, ScienceResult, SurfaceResult, ThermalResult, WorkerContext
from app.coordinator.contracts import Capability, Evidence, MissionRequest, ToolName
from app.coordinator.dispatcher import AgentDispatcher

TOOL_AGENTS = {'analyze_terrain': 'A1', 'analyze_thermal': 'A2', 'estimate_radiation': 'A3',
               'find_science_sites': 'A4', 'inspect_rover_history': 'A6'}
OBJECTIVE_TOOLS = {'terrain': ['analyze_terrain'], 'thermal': ['analyze_thermal'],
                   'radiation': ['estimate_radiation'], 'science': ['find_science_sites'],
                   'rover_history': ['inspect_rover_history'], 'route': ['analyze_terrain', 'plan_route']}
DESCRIPTIONS = {
    'inspect_capabilities': 'Inspect server-configured workers and limitations; metadata, not scientific evidence.',
    'analyze_terrain': 'A1 terrain prototype. No canonical planning grid or validated geometry is currently supplied.',
    'analyze_thermal': 'A2 thermal prototype. DN heuristics are not calibrated temperatures or EVA constraints.',
    'estimate_radiation': 'A3 explicitly configured dose-equivalent scenario; needs supplied duration and optional budget.',
    'find_science_sites': 'A4 source-attributed science sites and optional regional geology; priorities may be unranked.',
    'inspect_rover_history': 'A6 historical rover observations and metric proximity; never proof of safe terrain.',
    'plan_route': 'Planning prerequisite gate only. No validated planner is configured; returns unavailable.',
    'validate_route': 'Unavailable until a genuine computed candidate and independent route validator exist.',
}


def required_tools(request: MissionRequest) -> list[str]:
    return list(dict.fromkeys(tool for objective in request.objectives for tool in OBJECTIVE_TOOLS[objective]))


class ToolBox:
    def __init__(self, registry: WorkerRegistry, scope: WorkerContext, readiness: dict[str, str] | None = None,
                 input_hashes: dict[str, str] | None = None):
        self.registry, self.scope = registry, scope
        self.readiness = readiness or {}
        self.input_hashes = dict(input_hashes or {})

    def matches(self, request: MissionRequest) -> bool:
        actual, expected = request.context, self.scope
        return (actual.region_id, actual.roi_id, actual.dataset_version) == (expected.region_id, expected.roi_id, expected.dataset_version)

    def capabilities(self) -> list[Capability]:
        result = []
        for tool, description in DESCRIPTIONS.items():
            agent = TOOL_AGENTS.get(tool)
            configured = self.registry.get(agent) is not None if agent else tool == 'inspect_capabilities'
            readiness = self.readiness.get(agent, 'unavailable') if configured and agent else ('metadata' if configured else 'unavailable')
            result.append(Capability(tool=tool, agent_id=agent, configured=configured, readiness=readiness, description=description))
        return result

    async def execute(self, tools: list[ToolName], request: MissionRequest, directory: Path,
                      first_id: int, timeout_s: float) -> tuple[list[Evidence], dict[str, str]]:
        if not self.matches(request):
            raise ValueError('Mission scope mismatch.')
        agents = tuple(TOOL_AGENTS[t] for t in tools if t in TOOL_AGENTS)
        dispatched = await AgentDispatcher(self.registry, timeout_seconds=timeout_s).run(request.context, agents)
        outputs = {result.agent_id: result for result in dispatched.results}
        evidence, artifacts = [], {}
        for index, tool in enumerate(tools, first_id):
            evidence_id = f'e{index:04}'
            if tool in TOOL_AGENTS:
                result = outputs[TOOL_AGENTS[tool]]
                usable = (result.status in ('ready','partial') and result.data_kind in ('observed','scenario')
                          and bool(result.provenance_ref) and bool(result.dataset_ids))
                facts = {'provenance_available': bool(result.provenance_ref)}
                if isinstance(result, RadiationResult):
                    facts.update(dose_estimate_usv=result.dose_estimate_usv if usable else None,
                                 dose_uncertainty_usv=result.dose_uncertainty_usv if usable else None,
                                 constraint_status=result.constraint_status if usable else 'unknown',
                                 constraint_scope='scenario' if usable and result.data_kind == 'scenario' else 'unavailable')
                elif isinstance(result, ScienceResult):
                    facts.update(poi_count=len(result.pois) if usable else None,
                                 ranked_poi_count=sum(p.priority is not None for p in result.pois) if usable else None, geology_attached=bool(result.geology_ref))
                elif isinstance(result, RoverTraverseResult):
                    facts.update(stop_count=len(result.stops) if usable else None, nearest_track_distance_m=result.nearest_track_distance_m if usable else None)
                elif isinstance(result, SurfaceResult):
                    facts['canonical_planning_ready'] = False
                elif isinstance(result, ThermalResult):
                    facts.update(constraint_status=result.constraint_status if usable else 'unknown', calibrated_thermal_ready=False)
                limits = [f'evidence_kind:{result.data_kind}']
                if result.status != 'ready':
                    limits.append('incomplete_evidence')
                if not usable:
                    limits.append('no_usable_source_grounded_measurement')
                # No worker-authored prose is inserted into the model context.
                entry = Evidence(evidence_id=evidence_id, tool=tool, agent_id=result.agent_id,
                                 status=result.status if usable or result.status in ('unavailable','failed') else 'unavailable',
                                 data_kind=result.data_kind, facts=facts, dataset_ids=[x[:160] for x in result.dataset_ids[:8]], limitations=limits)
                directory.mkdir(parents=True, exist_ok=True)
                path = directory / f'{evidence_id}.json'
                await asyncio.to_thread(path.write_text, result.model_dump_json(indent=2), encoding='utf-8')
                artifacts[evidence_id] = str(path.resolve())
            elif tool == 'plan_route':
                entry = Evidence(evidence_id=evidence_id, tool=tool, agent_id=None, status='unavailable', data_kind='unavailable',
                                 facts={'canonical_grid_ready': False, 'planner_configured': False, 'candidate_available': False},
                                 dataset_ids=[], limitations=['validated_grid_masks_transforms_and_planner_required'])
            else:
                raise ValueError('Tool not executable in this phase.')
            evidence.append(entry)
        return evidence, artifacts
