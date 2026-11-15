"""A0 route tool adapter. Model proposals never change hard terrain policy."""
import asyncio
from pathlib import Path
import re
from uuid import uuid4

from app.api.errors import ApiProblem
from app.contracts.api import PlanRouteRequest
from app.coordinator.dispatcher import AgentDispatcher
from app.coordinator.metered import MeteredProvider
from app.planning.service import ROLES


class RouteAgent:
    def __init__(self, settings, planning, provider=None):
        self.settings, self.planning = settings, planning
        self.provider = provider or MeteredProvider(settings, settings.usage_root)
        self.evidence = None
        self.evidence_failure = False
        if settings.enabled:
            try:
                self._configure_evidence()
            except Exception:
                self.evidence_failure = True  # no paths or exception text in model/UI context

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
            roi_id=dataset.roi.roi_id,dataset_version=dataset.dataset_version))

    def collect(self):
        ready=self.planning.ready
        evidence=[{'id':'A1','status':'ready' if ready else 'unavailable',
                   'kind':'observed' if ready else 'unavailable','facts':{'terrain_policy':'DEM slope/masks; unknown cells blocked'}}]
        workers=[]; pois=[]
        outputs=[]
        if self.evidence:
            context=self.evidence.scope.model_copy(update={'mission_id':'route-'+uuid4().hex})
            report=asyncio.run(AgentDispatcher(self.evidence.registry,timeout_seconds=8).run(context,('A2','A3','A4','A6')))
            outputs=report.results
        for agent in ['A2','A3','A4','A6']:
            result=next((r for r in outputs if r.agent_id==agent),None)
            status=result.status if result else 'unavailable'
            kind=result.data_kind if result else 'unavailable'
            facts={}
            if result and hasattr(result,'pois'):
                pois=[{'id':p.id,'name_hint':p.rationale[:96],'longitude':p.longitude,'latitude':p.latitude} for p in result.pois]
                facts['science_sites']=len(pois)
            if result and hasattr(result,'stops'): facts['historical_stops']=len(result.stops)
            if result and hasattr(result,'dose_estimate_usv'):
                facts.update(dose_estimate_usv=result.dose_estimate_usv,constraint_status=result.constraint_status)
            evidence.append({'id':agent,'status':status,'kind':kind,'facts':facts})
            workers.append(dict(agent_id=agent,requested=bool(result),status=status,evidence_kind=kind,
                dataset_ids=result.dataset_ids if result else [],artifact_ids=[],
                warnings=['Context only; not fused into terrain costs.']+([] if result else ['Worker inputs are unconfigured or unavailable.']),
                unassessed_constraints=[ROLES[agent][0]]))
        raw={result.agent_id:result.model_dump(mode='json') for result in outputs}
        return evidence,workers,pois,raw

    def snapshot(self, request, *, stored=None, message=''):
        evidence,workers,pois,raw=self.collect()
        pois.sort(key=lambda p:(p['longitude']-request.start.longitude)**2+(p['latitude']-request.start.latitude)**2)
        words={word.casefold() for word in re.findall(r'[A-Za-z]{4,}',message)}-{'visit','first','before','after','route','please','this','that','sample','site','documented','context','historical'}
        pois.sort(key=lambda p:not (p['id'].casefold() in message.casefold() or bool(words & set(re.findall(r'[a-z]{4,}',p.get('name_hint','').casefold())))))
        snapshot={'request':request.model_dump(mode='json'),'evidence':evidence,'places':pois[:6]}
        if self.planning.grid:
            profile=self.planning.grid.profile
            snapshot['policy']={'slope_threshold_deg':profile.slope_threshold_deg,'terrain_weight':profile.terrain_weight,
                'assessment':'terrain_only','required_stop_order':'fixed'}
        if stored:
            snapshot['route_facts']={'distance_m':stored.result.metrics.distance_m,
                'waypoints':len(request.waypoints),'rationale':stored.metadata.rationale.summary if stored.metadata.rationale else 'Terrain-only A* result.'}
        return snapshot,workers,pois,raw

    def plan(self, request):
        if not self.settings.enabled:
            return self.planning.plan(request)
        grid=self.planning.prepare_grid(request)  # reject invalid coverage before a paid request
        snapshot,workers,_,raw=self.snapshot(request)
        decision,usage=self.provider.decide(snapshot,'Plan the supplied route and required waypoint order.',force_plan=True)
        if (decision.mode is not None and decision.mode!=request.mode) or (decision.waypoints is not None and decision.waypoints!=request.waypoints):
            raise ApiProblem(503,'A0_INVALID_PROPOSAL','A0 proposed changes to explicit route inputs; no replan was executed.')
        context={'commentary':decision.message,'evidence_ids':decision.citations,'usage':usage.model_dump(),'workers':workers,
                 'evidence':snapshot['evidence'],'private_evidence':raw}
        return self.planning.plan(request,agent_context=context,prepared_grid=grid)

    def respond(self, stored, message, *, recent_dialogue=None, advanced_context=None):
        request=stored.metadata.request
        if advanced_context is not None:
            advanced_context.require_parent(request)
        if not self.settings.enabled:
            summary=stored.metadata.rationale.summary if stored.metadata.rationale else 'This route was computed by deterministic terrain A*.'
            return summary+' Live A0 chat is disabled; use the ordered waypoint editor to revise this route.',None,None
        snapshot,workers,pois,raw=self.snapshot(request,stored=stored,message=message)
        if recent_dialogue:
            snapshot['recent_dialogue']=recent_dialogue
        if advanced_context is not None:
            snapshot['advanced_context']=advanced_context.model_dump(mode='json')
            # The typed context already carries these exact parent stops.
            # Keep one authoritative list in the bounded model input.
            snapshot['request'].pop('waypoints',None)
        decision,usage=self.provider.decide(snapshot,message)
        if advanced_context is not None and not advanced_context.allow_supported_revision:
            return decision.message+' Explanation only: this request does not permit route revisions; the route is unchanged.',None,usage
        if decision.action=='answer':
            return decision.message,None,usage
        if decision.waypoints is not None:
            allowed=[request.start,request.goal,*request.waypoints,*pois]
            supplied_text=message+' '+' '.join(turn['user'] for turn in (recent_dialogue or []))
            supplied=[(float(a),float(b)) for a,b in re.findall(r'(-?\d+(?:\.\d+)?)\s*[,，]\s*(-?\d+(?:\.\d+)?)',supplied_text)]
            coordinates=[(p['longitude'],p['latitude']) if isinstance(p,dict) else (p.longitude,p.latitude) for p in allowed]+supplied
            if any(not any(abs(p.longitude-x)<1e-7 and abs(p.latitude-y)<1e-7 for x,y in coordinates) for p in decision.waypoints):
                raise ApiProblem(422,'UNRESOLVED_WAYPOINT','A0 proposed an unrecognized place. Specify longitude,latitude or a known place ID.')
        revised=PlanRouteRequest.model_validate({**request.model_dump(),
            'mode':decision.mode or request.mode,'waypoints':decision.waypoints if decision.waypoints is not None else request.waypoints})
        if revised==request:
            return decision.message+' The current route already uses those preferences; its ID is unchanged.',None,usage
        result=self.planning.plan(revised,agent_context={'commentary':decision.message,'evidence_ids':decision.citations,
            'usage':usage.model_dump(),'workers':workers,'evidence':snapshot['evidence'],'private_evidence':raw},parent_route_id=stored.result.route_id)
        return decision.message,self.planning.store.get(result.route_id),usage
