"""A0 route tool adapter. Model proposals never change hard terrain policy."""
import hashlib
from pathlib import Path
import re
from uuid import uuid4

from app.api.errors import ApiProblem
from app.contracts.api import PlanRouteRequest
from app.coordinator.metered import MeteredProvider
from app.coordinator.specialists import SpecialistRouter, sum_usage
from app.planning.service import ROLES


class RouteAgent:
    def __init__(self, settings, planning, provider=None):
        self.settings, self.planning = settings, planning
        self.provider = provider or MeteredProvider(settings, settings.usage_root)
        self.evidence = None
        self.evidence_failure = False
        try:
            self._configure_evidence()
        except Exception:
            self.evidence_failure = True  # no paths or exception text in model/UI context

        self.specialists=SpecialistRouter(self)

    def _configure_evidence(self):
        if self.settings.evidence_profile:
            from app.coordinator.profiles import load_profile
            self.evidence = load_profile(self.settings.evidence_profile)
            return
        # One verified local snapshot can be discovered; multiple releases require
        # explicit profile selection. This never downloads or writes into raw inputs.
        if self.planning.grid is None:
            return
        roots=list((self.planning.grid.source_path.parent/'evidence').glob('jezero-evidence-*/manifest.json'))
        if len(roots)!=1:
            return
        from app.evidence.preview import prepare_dataset
        from app.agents.a4 import Worker as ScienceWorker
        from app.agents.a6 import Worker as RoverWorker
        from app.agents.registry import WorkerRegistry
        from app.contracts.workers import WorkerContext
        from types import SimpleNamespace
        dataset=prepare_dataset(roots[0],output_root=self.planning.store.root.parent/'evidence-normalized')
        registry=WorkerRegistry()
        registry.register(ScienceWorker(dataset)); registry.register(RoverWorker(dataset))
        self.evidence=SimpleNamespace(registry=registry,scope=WorkerContext(mission_id='a0-context',region_id='jezero',
            roi_id=dataset.roi.roi_id,dataset_version=dataset.dataset_version),input_hashes={'manifest':hashlib.sha256(roots[0].read_bytes()).hexdigest()})

    def catalog(self):
        return self.specialists.catalog()

    def _summarize(self, outputs, traces):
        by_id={r.agent_id:r for r in outputs}
        ready=traces[0].configured
        evidence=[{'id':'A1','status':'ready' if ready else 'unavailable','kind':'observed' if ready else 'unavailable',
            'facts':{'terrain_policy':'DEM slope/masks; unknown cells blocked'}}]
        workers=[];pois=[]
        for trace in traces[1:]:
            result=by_id.get(trace.agent_id)
            usable=trace.application!='none'
            status=result.status if result else 'unassessed' if not trace.selected else 'unavailable'
            kind=result.data_kind if result else 'unavailable'
            facts={}
            if trace.agent_id=='A3' and trace.selected and result is None: facts['duration_pending']='The host evaluates the scenario after A* supplies walking duration.'
            if usable and hasattr(result,'pois'):
                pois=[{'id':p.id,'name_hint':p.rationale[:96],'longitude':p.longitude,'latitude':p.latitude} for p in result.pois]
                facts['science_sites']=len(pois)
            if usable and hasattr(result,'stops'): facts['historical_stops']=len(result.stops)
            if usable and hasattr(result,'dose_estimate_usv'):
                facts.update(dose_estimate_usv=result.dose_estimate_usv,constraint_status=result.constraint_status)
            evidence.append({'id':trace.agent_id,'status':status if usable else 'unavailable','kind':kind,'facts':facts})
            workers.append(dict(agent_id=trace.agent_id,requested=trace.selected,status=status,evidence_kind=kind,
                dataset_ids=result.dataset_ids if result else [],artifact_ids=[],warnings=list(trace.limitations),
                unassessed_constraints=[ROLES[trace.agent_id][0]]))
        return evidence,workers,pois,{r.agent_id:r.model_dump(mode='json') for r in outputs}

    def snapshot(self, request, *, action_id, stored=None, message='', advanced_context=None):
        traces,selection_usage=self.specialists.choose(request,message,action_id=action_id,
            route_id=stored.result.route_id if stored else None,advanced_context=advanced_context)
        mission=request.mission
        duration=mission.exposure_duration_min if mission else None
        if duration is None and stored and stored.metadata.assessment:
            duration=stored.metadata.assessment.radiation_duration_min
        # A3 uses an explicit duration now, or the computed candidate duration
        # after A*. No guessed duration is sent to a radiation worker.
        only=None if stored or duration is not None else ('A2','A4','A6')
        outputs,traces=self.specialists.run(traces,duration_min=duration,
            radiation_budget_usv=mission.radiation_budget_usv if mission else None,only=only)
        evidence,workers,pois,raw=self._summarize(outputs,traces)
        pois.sort(key=lambda p:(p['longitude']-request.start.longitude)**2+(p['latitude']-request.start.latitude)**2)
        words={word.casefold() for word in re.findall(r'[A-Za-z]{4,}',message)}-{'visit','first','before','after','route','please','this','that','sample','site','documented','context','historical'}
        pois.sort(key=lambda p:not (p['id'].casefold() in message.casefold() or bool(words & set(re.findall(r'[a-z]{4,}',p.get('name_hint','').casefold())))))
        snapshot={'request':request.model_dump(mode='json',exclude_none=True),'evidence':evidence,'places':pois[:6]}
        if self.planning.grid:
            profile=self.planning.grid.profile
            snapshot['policy']={'slope_threshold_deg':profile.slope_threshold_deg,'terrain_weight':profile.terrain_weight,
                'assessment':'terrain_only','required_stop_order':'fixed'}
        if stored:
            snapshot['route_facts']={'distance_m':stored.result.metrics.distance_m,'waypoints':len(request.waypoints)}
        if advanced_context is not None:
            snapshot['advanced_context']=advanced_context.model_dump(mode='json')
            snapshot['request'].pop('waypoints',None)
        return snapshot,workers,pois,raw,traces,outputs,selection_usage

    def evidence_descriptions(self, outputs):
        descriptions={}
        for result in outputs:
            if result.status not in ('ready','partial') or not result.provenance_ref or not result.dataset_ids: continue
            worker=self.evidence.registry.get(result.agent_id) if self.evidence else None
            scenario=getattr(worker,'scenario',None)
            source=getattr(scenario,'source',None) or getattr(getattr(worker,'config',None),'source',None)
            urls=[str(source.source_url)] if source else []
            for field in ('pois','stops'):
                for item in getattr(result,field,[]):
                    url=str(item.source.source_url)
                    if url not in urls: urls.append(url)
            acquired=getattr(result,'data_timestamp',None) or getattr(result,'observed_at',None)
            descriptions[result.agent_id]=dict(dataset_ids=result.dataset_ids,source_urls=urls[:12],
                dataset_version=self.evidence.scope.dataset_version,acquisition_time=acquired.isoformat() if acquired else None,
                observation_period=scenario.source_observation_period if scenario else None,
                route_coverage_fraction=1.0 if result.agent_id=='A3' and result.dose_estimate_usv is not None else None,
                uncertainty=scenario.uncertainty_description if scenario else 'Context does not establish route-risk coverage or current hazard applicability.')
        return descriptions

    def evidence_applicability(self):
        states={}
        if self.evidence:
            for agent_id in ('A2','A3'):
                worker=self.evidence.registry.get(agent_id)
                scenario=getattr(worker,'scenario',None)
                config=getattr(worker,'config',None)
                scope=self.evidence.scope
                if scenario and (scenario.region_id,scenario.roi_id,scenario.dataset_version)!=(scope.region_id,scope.roi_id,scope.dataset_version):
                    states[agent_id]='incompatible'
                elif config is not None and hasattr(config,'matches') and not config.matches(scope):
                    states[agent_id]='incompatible'
        return states

    def finalize(self, request, distance, traces, outputs):
        from app.planning.assessment import walking_assessment
        assessment=walking_assessment(request,distance)
        later,traces=self.specialists.run(traces,duration_min=assessment.radiation_duration_min,
            radiation_budget_usv=request.mission.radiation_budget_usv if request.mission else None,only=('A3',))
        by_id={r.agent_id:r for r in outputs}
        by_id.update({r.agent_id:r for r in later})
        radiation=by_id.get('A3')
        if radiation and any(t.agent_id=='A3' and t.application=='dose_scenario' for t in traces):
            assessment=assessment.model_copy(update=dict(dose_estimate_usv=radiation.dose_estimate_usv,
                dose_uncertainty_usv=radiation.dose_uncertainty_usv,radiation_constraint_status=radiation.constraint_status))
        unknown=[];failed=[]
        for trace in traces:
            if not trace.required or trace.agent_id=='A1': continue
            result=by_id.get(trace.agent_id)
            if trace.agent_id=='A3' and assessment.radiation_constraint_status=='fail': failed.append(trace.agent_id)
            elif trace.execution_state not in ('succeeded','cached') or trace.agent_id=='A2' or (
                trace.agent_id=='A3' and (not result or result.dose_estimate_usv is None or
                    request.mission and request.mission.radiation_budget_usv is not None and assessment.radiation_constraint_status=='unknown')):
                unknown.append(trace.agent_id)
        assessment=assessment.model_copy(update={'required_unassessed':unknown,'required_failed':failed})
        evidence,workers,_,raw=self._summarize(list(by_id.values()),traces)
        return dict(assessment=assessment,specialist_trace=traces,workers=workers,evidence=evidence,private_evidence=raw,
            evidence_descriptions=self.evidence_descriptions(list(by_id.values())),evidence_applicability=self.evidence_applicability())

    def plan(self, request, *, request_id=None):
        grid=self.planning.prepare_grid(request)
        action_id=request_id or uuid4().hex
        message='Plan the supplied route and required waypoint order.'
        snapshot,workers,_,raw,traces,outputs,selection_usage=self.snapshot(request,action_id=action_id,message=message)
        context={'workers':workers,'evidence':snapshot['evidence'],'private_evidence':raw}
        if self.settings.enabled:
            decision,usage=self.provider.decide(snapshot,message,force_plan=True)
            if (decision.mode is not None and decision.mode!=request.mode) or (decision.waypoints is not None and decision.waypoints!=request.waypoints):
                raise ApiProblem(503,'A0_INVALID_PROPOSAL','A0 proposed changes to explicit route inputs; no replan was executed.')
            context.update(commentary=decision.message,evidence_ids=decision.citations,usage=sum_usage(selection_usage,usage).model_dump())
        return self.planning.plan(request,agent_context=context,prepared_grid=grid,
            assessment_builder=lambda distance:self.finalize(request,distance,traces,outputs))

    def _save_chat_evidence(self, route_id, action_id, raw, traces):
        from app.coordinator.attempts import save_json
        traces=[t.model_copy(update={'artifact_id':route_id+':chat:'+action_id+':'+t.agent_id})
            if t.agent_id in raw else t for t in traces]
        try:
            save_json(self.planning.store.root/'requests'/'chat'/route_id/(action_id+'.evidence'),
                dict(specialist_trace=[t.model_dump(mode='json') for t in traces],results=raw))
        except OSError:
            raise ApiProblem(503,'A0_EVIDENCE_STORAGE_UNAVAILABLE','Selected evidence could not be stored; no final model request was sent.',retry_safe=True) from None
        return traces

    def respond(self, stored, message, *, recent_dialogue=None, advanced_context=None, request_id=None):
        request=stored.metadata.request
        if advanced_context is not None: advanced_context.require_parent(request)
        action_id=request_id or uuid4().hex
        snapshot,workers,pois,raw,traces,outputs,selection_usage=self.snapshot(request,stored=stored,message=message,
            action_id=action_id,advanced_context=advanced_context)
        traces=self._save_chat_evidence(stored.result.route_id,action_id,raw,traces)
        if not self.settings.enabled:
            summary=stored.metadata.rationale.summary if stored.metadata.rationale else 'This route was computed by deterministic terrain A*.'
            return summary+' Live A0 chat is disabled; use the ordered waypoint editor to revise this route.',None,None,traces
        if recent_dialogue: snapshot['recent_dialogue']=recent_dialogue
        decision,decision_usage=self.provider.decide(snapshot,message)
        usage=sum_usage(selection_usage,decision_usage)
        if advanced_context is not None and not advanced_context.allow_supported_revision:
            return decision.message+' Explanation only: this request does not permit route revisions; the route is unchanged.',None,usage,traces
        if decision.action=='answer': return decision.message,None,usage,traces
        if decision.waypoints is not None:
            allowed=[request.start,request.goal,*request.waypoints,*pois]
            supplied_text=message+' '+' '.join(turn['user'] for turn in (recent_dialogue or []))
            supplied=[(float(a),float(b)) for a,b in re.findall(r'(-?\d+(?:\.\d+)?)\s*[,，]\s*(-?\d+(?:\.\d+)?)',supplied_text)]
            coordinates=[(p['longitude'],p['latitude']) if isinstance(p,dict) else (p.longitude,p.latitude) for p in allowed]+supplied
            if any(not any(abs(p.longitude-x)<1e-7 and abs(p.latitude-y)<1e-7 for x,y in coordinates) for p in decision.waypoints):
                raise ApiProblem(422,'UNRESOLVED_WAYPOINT','A0 proposed an unrecognized place. Specify longitude,latitude or a known place ID.')
        if request.mission_profile is not None and decision.mode is not None and decision.mode!=request.mode:
            raise ApiProblem(422,'PROFILE_OBJECTIVE_MISMATCH','Change the versioned mission profile through a new plan; chat cannot override its objective.')
        revised=PlanRouteRequest.model_validate({**request.model_dump(),'mode':decision.mode or request.mode,
            'waypoints':decision.waypoints if decision.waypoints is not None else request.waypoints})
        if revised==request:
            return decision.message+' The current route already uses those preferences; its ID is unchanged.',None,usage,traces
        result=self.planning.plan(revised,agent_context={'commentary':decision.message,'evidence_ids':decision.citations,
            'usage':usage.model_dump(),'workers':workers,'evidence':snapshot['evidence'],'private_evidence':raw},parent_route_id=stored.result.route_id,
            assessment_builder=lambda distance:self.finalize(revised,distance,traces,outputs))
        record=self.planning.store.get(result.route_id)
        return decision.message,record,usage,record.metadata.specialist_trace
