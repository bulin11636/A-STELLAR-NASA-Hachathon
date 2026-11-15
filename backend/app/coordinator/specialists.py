"""Bounded specialist selection, versioned in-process caching and safe traces."""
import asyncio
from collections import OrderedDict
import json
import re
from pathlib import Path
from threading import Lock
from uuid import uuid4

from app.api.errors import ApiProblem
from app.contracts.assessment import SpecialistSelection, SpecialistTrace
from app.contracts.routes import Usage
from app.coordinator.attempts import payload_hash, save_json
from app.coordinator.dispatcher import AgentDispatcher

OPTIONAL = ('A2','A3','A4','A6')
PURPOSES = {'A2':'Thermal context; calibrated limits unavailable.', 'A3':'Configured constant-rate dose scenario; no spatial avoidance model.',
    'A4':'Science-site context and explicit waypoint suggestions.', 'A6':'Historical rover context; not proof of safe terrain.'}


def sum_usage(*values):
    values=[v for v in values if v is not None]
    if not values: return None
    first=values[0]
    if any(v.model!=first.model or v.price_version!=first.price_version for v in values):
        raise ApiProblem(503,'A0_PROVIDER_ERROR','Incompatible usage records cannot be combined.')
    fields=('calls','input_tokens','cached_input_tokens','output_tokens','reasoning_tokens','estimated_cost_usd')
    return Usage(model=first.model,price_version=first.price_version,**{key:sum(getattr(v,key) for v in values) for key in fields})


class SpecialistRouter:
    def __init__(self, agent):
        self.agent=agent
        self._cache=OrderedDict()
        self._lock=Lock()

    def catalog(self):
        evidence=self.agent.evidence
        return [dict(agent_id=a,configured=bool(evidence and evidence.registry.get(a)),purpose=PURPOSES[a]) for a in OPTIONAL]

    def choose(self, request, message, *, action_id, route_id=None, advanced_context=None):
        if not re.fullmatch(r'[A-Za-z0-9_-]{16,64}',action_id):
            raise ApiProblem(422,'VALIDATION_ERROR','The request identifier is malformed.')
        catalog=self.catalog()
        required=set(request.mission.required_analyses if request.mission else [])
        if request.mission and request.mission.radiation_budget_usv is not None: required.add('A3')
        selection,usage=None,None
        if self.agent.settings.enabled and any(item['configured'] for item in catalog):
            folder=self.agent.planning.store.root/'requests'/('plans' if route_id is None else 'chat')
            if route_id is not None: folder=folder/route_id
            path=folder/(action_id+'.selection')
            identity=payload_hash(dict(request=request.model_dump(mode='json',exclude_none=True),message=message,
                advanced_context=advanced_context.model_dump(mode='json') if advanced_context else None,
                capabilities=catalog,input_hashes=getattr(self.agent.evidence,'input_hashes',{})))
            if path.exists():
                try:
                    if path.is_symlink() or path.stat().st_size>32768: raise ValueError('Invalid checkpoint')
                    data=json.loads(path.read_text())
                    if data['input_hash']!=identity: raise ValueError('Selection input mismatch')
                    selection=SpecialistSelection.model_validate(data['selection'])
                    usage=Usage.model_validate(data['usage'])
                except (OSError,ValueError,KeyError):
                    raise ApiProblem(500,'A0_SELECTION_RECORD_INVALID','The saved tool decision failed validation; no new model call was made.') from None
            else:
                selection,usage=self.agent.provider.select_specialists(catalog,request,message,advanced_context=advanced_context)
                try:
                    save_json(path,dict(input_hash=identity,selection=selection.model_dump(mode='json'),usage=usage.model_dump(mode='json')))
                except OSError:
                    raise ApiProblem(503,'A0_SELECTION_STORAGE_ERROR','The tool decision could not be saved. Its outcome is uncertain; do not automatically retry.',outcome_unknown=True) from None
        choices={c.agent_id:c for c in selection.choices} if selection else {}
        from app.planning.service import ROLES
        traces=[SpecialistTrace(agent_id='A1',public_name=ROLES['A1'][0],configured=self.agent.planning.ready,selected=True,required=True,
            selection_source='host_policy',selection_reason='Terrain coverage, slope policy and native route checks are mandatory.',
            execution_state='succeeded' if self.agent.planning.ready else 'unavailable',data_kind='observed' if self.agent.planning.ready else 'unavailable',
            dataset_ids=[self.agent.planning.grid.profile.dataset_id] if self.agent.planning.grid else [],
            result_status='ready' if self.agent.planning.ready else 'unavailable',application='terrain_cost',limitations=['Optical obstacles and non-terrain environmental constraints remain unassessed.'])]
        for capability in catalog:
            a=capability['agent_id']; configured=capability['configured']; choice=choices.get(a)
            selected=a in required or bool(choice and choice.selected and configured)
            if a in required: reason='User-required analysis; the host cannot skip it.'
            elif not configured: reason='No compatible worker is configured for this dataset scope.'
            elif choice: reason=choice.reason if not choice.selected or configured else 'Unavailable tool was not executed.'
            else: reason='Optional analysis was not selected in deterministic mode.'
            traces.append(SpecialistTrace(agent_id=a,public_name=ROLES[a][0],configured=configured,selected=selected,required=a in required,
                selection_source='user_requirement' if a in required else 'a0' if choice else 'deterministic',selection_reason=reason,
                execution_state='not_requested' if not selected else 'unavailable',data_kind='unavailable',application='none',
                limitations=[PURPOSES[a]]))
        return traces,usage

    def run(self, traces, *, duration_min=None, radiation_budget_usv=None, only=None):
        evidence=self.agent.evidence
        selected=[t.agent_id for t in traces if t.selected and t.agent_id!='A1' and (only is None or t.agent_id in only)]
        if not selected: return [],traces
        outputs={}; cached=set(); missing=[]
        if evidence:
            parameters=evidence.scope.parameters.model_copy(update={'eva_duration_min':duration_min,'radiation_budget_usv':radiation_budget_usv})
            context=evidence.scope.model_copy(update={'mission_id':'route-'+uuid4().hex,'parameters':parameters})
            fingerprint=getattr(evidence,'input_hashes',{})
            base=dict(scope=context.model_dump(mode='json',exclude={'mission_id'}),inputs=fingerprint)
            for a in selected:
                worker=evidence.registry.get(a)
                stats=[]
                config=getattr(worker,'config',None)
                if config:
                    for name in ('dem_path','day_path','night_path'):
                        path=getattr(config,name,None)
                        if path is not None:
                            try:
                                stat=Path(path).stat();stats.append((name,stat.st_size,stat.st_mtime_ns))
                            except OSError:stats.append((name,None,None))
                key=payload_hash({**base,'agent':a,'input_stats':stats})
                with self._lock:
                    result=self._cache.get(key)
                    if result is not None: self._cache.move_to_end(key)
                if result is None: missing.append((a,key))
                else: outputs[a]=result; cached.add(a)
            if missing:
                report=asyncio.run(AgentDispatcher(evidence.registry,timeout_seconds=8).run(context,tuple(a for a,_ in missing)))
                for (a,key),result in zip(missing,report.results):
                    outputs[a]=result
                    if result.status in ('ready','partial'):
                        with self._lock:
                            self._cache[key]=result
                            while len(self._cache)>128: self._cache.popitem(last=False)
        updated=[]
        for trace in traces:
            if trace.agent_id not in selected: updated.append(trace); continue
            result=outputs.get(trace.agent_id)
            usable=bool(result and result.status in ('ready','partial') and result.data_kind in ('observed','scenario') and result.provenance_ref and result.dataset_ids)
            state='cached' if usable and trace.agent_id in cached else 'succeeded' if usable else 'failed' if result and result.status=='failed' else 'unavailable'
            application='dose_scenario' if usable and trace.agent_id=='A3' and result.dose_estimate_usv is not None else 'context_only' if usable else 'none'
            limitations=list(trace.limitations)
            if trace.agent_id=='A3' and duration_min is None:
                limitations.append('No explicit exposure duration or computable walking time is available.')
            elif not usable and result is not None:
                limitations.append('The selected worker supplied no applicable evidence for this scope; inspect the private audit record.')
            updated.append(trace.model_copy(update=dict(limitations=list(dict.fromkeys(limitations)),execution_state=state,data_kind=result.data_kind if result else 'unavailable',application=application,
                result_status=result.status if result else None,
                constraint_status=getattr(result,'constraint_status','unknown') if usable else 'unknown',
                dataset_ids=result.dataset_ids if result else [])))
        return list(outputs.values()),updated
