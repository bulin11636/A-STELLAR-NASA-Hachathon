"""A0 deterministic coordinator; no graph or model imports or network calls."""
from datetime import datetime, timezone
from collections import OrderedDict
from pathlib import Path
import os
from time import monotonic
from uuid import uuid4
from app.api.errors import ApiProblem
from app.contracts.api import COORDINATE_SYSTEM, PlanRouteRequest, PlanRouteResponse, PlanningInfo, Region, RouteMetrics
from app.contracts.routes import RouteMetadata, StoredRouteResponse
from app.contracts.agent_names import PUBLIC_AGENT_NAMES
from app.planning.grid import load_grid, grid_for_request, regional_grid, source_bounds, digest, VERSION
from app.planning.store import RouteStore, write_json

REPO = Path(__file__).resolve().parents[3]
ROLES = {
    'A0': (PUBLIC_AGENT_NAMES['A0'], 'Validate mission inputs and available data, dispatch registered analysis tools, request deterministic fusion/planning/validation, preserve provenance, persist results and explain unmet requirements.'),
    'A1': (PUBLIC_AGENT_NAMES['A1'], 'Derive slope and supported terrain descriptors from a DEM; supply metric costs, coverage, unknown and blocked masks. Optical obstacle analysis requires aligned imagery.'),
    'A2': (PUBLIC_AGENT_NAMES['A2'], 'Describe day/night thermal observations, units, times and coverage. Calibrated constraints require separate validation.'),
    'A3': (PUBLIC_AGENT_NAMES['A3'], 'Evaluate explicitly configured dose scenarios against a mission duration and user-supplied budget, retaining assumptions and uncertainty.'),
    'A4': (PUBLIC_AGENT_NAMES['A4'], 'Associate source-attributed sampling POIs with regional geology, retain ambiguity and explain scientific relevance. Priority scoring requires a documented rubric.'),
    'A6': (PUBLIC_AGENT_NAMES['A6'], 'Normalize historical rover positions and segments, compute supported proximity measures and attach verified observation references. Historical traversal does not establish astronaut safety.'),
}
WARNINGS = [
    'Research terrain-only route; the 15 degree default is a configurable demo policy, not a certified safety threshold.',
    'Thermal, radiation and optical safety constraints remain unassessed; any science/rover evidence is contextual and does not reduce terrain cost.',
    'Distance is native projected planar polyline length including validated endpoint connectors, not terrain-following 3D or ground distance.',
    'NASA imagery displays the M20 DEM route as a visual demo overlay.',
    'Source elevation units are explicitly asserted by the host profile; source identity and calibration are not publisher-certified.',
]


class PlanningService:
    def __init__(self, mode='mock', profile=None, output_root=None, dataset_root=None, *, allow_synthetic_registration=False):
        if mode not in ('mock','computed'):
            raise ValueError('A_STELLAR_ROUTING_MODE must be mock or computed')
        self.mode = mode
        self.profile_path = profile
        self.dataset_root = dataset_root
        self.allow_synthetic_registration=allow_synthetic_registration
        self.store = RouteStore(output_root or REPO/'data/processed/routes')
        self.grid = None
        self.failure = None
        self._regional_grid = None
        self._policy_grids = OrderedDict()
        self._regional_example = None
        self._regional_example_checked = False
        if mode == 'computed':
            try:
                if not profile:
                    raise ValueError('Planning profile missing')
                self.grid = load_grid(profile, dataset_root=dataset_root)
            except Exception as exc:
                # Keep private diagnostic locally; never disclose paths in public errors.
                self.failure = exc

    @classmethod
    def from_env(cls):
        return cls(os.getenv('A_STELLAR_ROUTING_MODE','mock'),os.getenv('A_STELLAR_PLANNING_PROFILE'),os.getenv('A_STELLAR_ROUTE_STORE'))

    @property
    def ready(self):
        if self.mode == 'mock':
            return True
        if self.grid is None:
            return False
        try:
            self.grid.ensure_unchanged()
            return bool(self.grid.allowed.any())
        except (OSError, ApiProblem):
            return False

    def describe_region(self):
        ready = self.ready
        planning = None
        if self.mode == 'computed' and ready:
            g = self.grid
            example = None
            # Match the inspected CTX demo window and the verifier's cells.
            # Coordinates come from the loaded DEM, not the unverified basemap.
            if (g.profile.roi_id == 'ctx-jezero-demo-128-v1'
                    and g.profile.window == (1210, 2440, 128, 128)
                    and g.allowed[20, 20] and g.allowed[100, 100]):
                example = PlanRouteRequest(region_id='jezero', coordinate_system=COORDINATE_SYSTEM,
                    start=g.wire(*g.center((20, 20))), goal=g.wire(*g.center((100, 100))), mode='shortest')
            planning = PlanningInfo(roi_id=g.profile.roi_id, bounds=g.bounds.model_dump(),
                resolution_m=g.metadata.planning_resolution_m, example_request=example,
                regional_example_request=self.regional_example(),
                source_bounds=source_bounds(g).model_dump(), dynamic_windowing=g.profile.dynamic_windowing,
                max_grid_cells=g.profile.limits.max_grid_cells)
        return Region(routing_mode=self.mode, routing_available=ready, planning=planning)

    def regional_example(self):
        """Advertise explicit DEM-derived crater-scale demo stops, without a model call."""
        if self._regional_example_checked:
            return self._regional_example
        self._regional_example_checked = True
        if not self.grid.profile.dynamic_windowing or not self.grid.profile.adaptive_resolution:
            return None
        from app.contracts.api import MarsCoordinate
        import numpy as np
        # Fixed Jezero demonstration targets; other source footprints must
        # contain both targets rather than inventing coverage or endpoints.
        bounds = source_bounds(self.grid)
        targets = [MarsCoordinate(longitude=77.1,latitude=18.15),MarsCoordinate(longitude=77.9,latitude=18.75)]
        if any(not (bounds.west < p.longitude < bounds.east and bounds.south < p.latitude < bounds.north) for p in targets):
            return None
        try:
            g = self._regional_grid or regional_grid(self.profile_path,self.grid,self.dataset_root)
            self._regional_grid = g
            points = []
            allowed = g.allowed
            for target in targets:
                r,c = g.cell(target)
                candidates = [(rr,cc) for rr in range(max(0,r-5),min(allowed.shape[0],r+6))
                    for cc in range(max(0,c-5),min(allowed.shape[1],c+6)) if allowed[rr,cc]]
                if not candidates:
                    return None
                x,y = g.xy(target)
                cell = min(candidates,key=lambda rc: np.linalg.norm(np.subtract(g.center(rc),(x,y))))
                points.append(g.wire(*g.center(cell)))
            self._regional_example = PlanRouteRequest(region_id='jezero',coordinate_system=COORDINATE_SYSTEM,
                start=points[0],goal=points[1],mode='shortest')
        except (ApiProblem,ValueError,OSError):
            return None
        return self._regional_example

    def prepare_grid(self, request):
        if self.grid is None:
            raise ApiProblem(503,'PLANNING_UNAVAILABLE','Computed routing requires a validated planning profile and DEM.')
        from app.planning.policies import configure_grid
        if request.mission_profile is not None:
            expected='shortest' if request.mission_profile=='fastest' else 'safest'
            if request.mode!=expected:
                raise ApiProblem(422,'PROFILE_OBJECTIVE_MISMATCH','Use the terrain objective advertised for the selected mission profile.')
        policy_base=configure_grid(self.grid,request)
        cache_key=policy_base.profile.model_dump_json()
        cached=self._policy_grids.get(cache_key)
        try:
            self.grid.ensure_unchanged()
            g=grid_for_request(self.profile_path,policy_base,request,self.dataset_root,cached)
            g.ensure_unchanged()
            if g.inventory.get('resolution_factor',1) > 1:
                self._policy_grids[cache_key]=g
                self._policy_grids.move_to_end(cache_key)
                while len(self._policy_grids)>2: self._policy_grids.popitem(last=False)
        except OSError:
            raise ApiProblem(503,'PLANNING_UNAVAILABLE','A configured source or profile is no longer readable.') from None
        allowed=g.allowed
        for point in [request.start,*request.waypoints,request.goal]:
            if not allowed[g.cell(point)]:
                raise ApiProblem(400,'ENDPOINT_NOT_TRAVERSABLE','A route stop is blocked or unknown.')
        return g

    def plan(self, request, *, agent_context=None, parent_route_id=None, prepared_grid=None, assessment_builder=None):
        if self.grid is None:
            if isinstance(self.failure, ApiProblem):
                raise self.failure
            raise ApiProblem(503,'PLANNING_UNAVAILABLE','Computed routing requires a readable, verified planning profile and DEM.')
        import numpy as np
        from app.planning.search import SearchProblem
        from app.planning.solver import solve_route
        from app.planning.validation import validate_native_polyline
        g = prepared_grid or self.prepare_grid(request)
        try:
            g.ensure_unchanged()
        except OSError:
            raise ApiProblem(503,'PLANNING_UNAVAILABLE','A configured source or profile is no longer readable.') from None
        limits = g.profile.limits
        started = monotonic()
        widened = False
        try:
            solution = solve_route(g,request,limits.max_expanded_nodes,limits.max_elapsed_seconds)
        except SearchProblem as error:
            full_h,full_w = g.inventory['source_shape']
            full_window = (1,1,full_w-2,full_h-2)
            if error.code != 'NO_PATH' or not g.profile.dynamic_windowing or tuple(g.inventory['source_window']) == full_window:
                raise
            wider = regional_grid(self.profile_path,g,self.dataset_root)
            wider.ensure_unchanged()
            # Conservative aggregation may exclude a traversable native endpoint.
            # Keep the original NO_PATH result rather than mislabeling its coordinates.
            allowed = wider.allowed
            if any(not allowed[wider.cell(p)] for p in [request.start,*request.waypoints,request.goal]):
                raise error
            remaining = limits.max_elapsed_seconds-(monotonic()-started)
            if remaining <= 0 or error.expanded_nodes >= limits.max_expanded_nodes:
                raise ApiProblem(503,'PLANNING_LIMIT_EXCEEDED','No search budget remains for a wider terrain footprint.') from None
            solution = solve_route(wider,request,limits.max_expanded_nodes-error.expanded_nodes,remaining)
            solution.search.expanded += error.expanded_nodes
            solution.search.elapsed_ms += error.elapsed_ms
            g = wider
            if request.mission_profile is None and request.resolution_profile is None: self._regional_grid=wider
            widened = True
        points,route,search = solution.points,solution.route,solution.search
        distance,touched = solution.distance,solution.touched
        arrays = g.arrays()
        dx,dy = g.metadata.planning_resolution_m
        stops = [request.start,*request.waypoints,request.goal]
        factor = g.inventory.get('resolution_factor',1)
        native_validation = validate_native_polyline(g,points) if factor > 1 else None
        from app.planning.assessment import walking_assessment
        context = dict(agent_context or {})
        if assessment_builder is not None: context.update(assessment_builder(distance))
        assessment = context.get('assessment') or walking_assessment(request,distance)
        warnings = list(WARNINGS)
        if assessment.required_unassessed: warnings.append('Required analyses remain unassessed: '+', '.join(assessment.required_unassessed)+'. This is a provisional terrain route.')
        if assessment.required_failed: warnings.append('Required scenario checks failed: '+', '.join(assessment.required_failed)+'. The route does not meet those scenario requirements.')
        route_id = 'route-'+uuid4().hex
        from app.planning.policies import selected_profile, POLICY_VERSION
        from app.planning.risk_assessment import enrich_risk_assessment
        traces=context.get('specialist_trace',[])
        assessment=enrich_risk_assessment(assessment,selected_profile(request),traces,
            grid=g,touched=touched,route_id=route_id,request=request,evidence_descriptions=context.get('evidence_descriptions'),evidence_applicability=context.get('evidence_applicability'))
        if assessment.hard_gate_status!='pass': warnings.extend(assessment.gate_reasons)
        applied=dict(version=POLICY_VERSION,mission_profile_id=assessment.mission_profile.profile_id,
            mission_profile_version=assessment.mission_profile.version,legacy_objective=request.mission_profile is None,
            resolution_profile=request.resolution_profile or ('standard' if request.mission_profile else 'legacy'),
            minimum_native_factor=g.profile.min_resolution_factor,actual_native_factor=factor,
            actual_cell_size_m=g.metadata.planning_resolution_m,source_cell_size_m=g.metadata.source_resolution,
            terrain_weight=0.0 if request.mode=='shortest' else g.profile.terrain_weight,limits=limits.model_dump(mode='json'))
        from app.contracts.routes import AppliedPlanningPolicy
        applied=AppliedPlanningPolicy.model_validate(applied).model_dump(mode='json')
        legs=[dict(index=i+1,distance_m=d,travel_time_min=d/request.mission.speed_m_s/60 if request.mission and request.mission.speed_m_s is not None and assessment.time else None,
            stop_time_min=request.mission.stop_minutes_per_waypoint if request.mission and i<len(request.waypoints) else 0)
            for i,d in enumerate(solution.leg_distances)]
        from app.planning.registration import registration_for_route
        registration=registration_for_route(g,route,dataset_root=self.dataset_root,allow_synthetic=self.allow_synthetic_registration)
        registration=registration.model_copy(update={'evidence_id':route_id+':provenance#registration'})
        from app.planning.registration import control_snapshot
        controls_text=control_snapshot(g,registration,dataset_root=self.dataset_root)
        result = PlanRouteResponse(route_id=route_id,mode=request.mode,source='computed',route=route,
            metrics=RouteMetrics(distance_m=distance,estimated_time_min=assessment.time.total_min if assessment.time else None), warnings=warnings)
        def build(folder):
            np.savez_compressed(folder/'grid.npz', **arrays)
            write_json(folder/'validation.json',dict(cells=search.cells,touched_cells=touched,metric_polyline=points,
                validated_wire_polyline=[p.model_dump() for p in route],source_hash=g.source_hash,grid_id=g.metadata.grid_id,
                native_validation=native_validation))
            write_json(folder/'provenance.json',dict(source_path=str(g.source_path),inventory=g.inventory,
                profile=g.profile.model_dump(),source_hash=g.source_hash,specialist_evidence=context.get('evidence',[]),
                specialist_results=context.get('private_evidence',{}),registration=registration.model_dump(mode='json'),
                assessment=assessment.model_dump(mode='json'),planning_policy=applied,legs=legs,registration_controls_text=controls_text))
            artifacts = {role:dict(artifact_id=route_id+':'+role,sha256=digest(folder/name)) for role,name in
                [('grid','grid.npz'),('validation','validation.json'),('provenance','provenance.json')]}
            gridmeta = g.metadata.model_copy(update={'mask_artifact_ids':{k:route_id+':grid#'+k for k in ['coverage','unknown','blocked']}})
            workers = [dict(agent_id=k,public_name=ROLES[k][0],responsibility=ROLES[k][1],requested=k=='A1',
                status='ready' if k=='A1' else 'unassessed',evidence_kind='observed' if k=='A1' else 'unavailable',
                dataset_ids=[g.profile.dataset_id] if k=='A1' else [],artifact_ids=[route_id+':grid'] if k=='A1' else [],
                warnings=['Optical obstacles are unassessed.'] if k=='A1' else ['Not invoked; no validated constraint supplied.'],
                unassessed_constraints=['optical obstacles'] if k=='A1' else [ROLES[k][0]]) for k in ['A1','A2','A3','A4','A6']]
            for observed in context.get('workers',[]):
                for index, worker in enumerate(workers):
                    if worker['agent_id']==observed['agent_id'] and worker['agent_id']!='A1':
                        workers[index]={**worker,**observed}
                        if observed['agent_id'] in context.get('private_evidence',{}):
                            workers[index]['artifact_ids']=[route_id+':provenance#'+observed['agent_id']]
            facts = [f'Computed {len(stops)-1} ordered route leg(s), including {len(request.waypoints)} required waypoint(s).',
                f'Projected planar distance: {distance:.2f} m; objective: {request.mode}.',
                f'Grid: {g.metadata.width} by {g.metadata.height} cells at {dx:g} by {dy:g} m.',
                f'Unknown cells are impassable; slope threshold is {g.profile.slope_threshold_deg:g} degrees (research policy).']
            if widened:
                facts.append('The initial crop was disconnected; a full-source retry shared the original node/time budget without another model call.')
            if factor > 1:
                facts.extend([f'Regional search uses conservative {factor} by {factor} native-cell blocks; any blocked or unknown constituent blocks traversal.',
                    f'Independently checked {native_validation["touched_native_cells"]} touched native cells after planning.',
                    'Optimality applies to the aggregated search graph; narrow native corridors can be excluded.'])
            rationale = dict(summary='A* computed a terrain-only route using '+('projected distance' if request.mode=='shortest' else 'terrain-weighted distance')+' cost and the requested stop order.',
                facts=facts,limitations=list(warnings),model_commentary=context.get('commentary'),evidence_ids=context.get('evidence_ids',[]))
            traces=[t.model_copy(update={'artifact_id':route_id+(':grid' if t.agent_id=='A1' else ':provenance#'+t.agent_id)})
                if t.agent_id=='A1' or t.agent_id in context.get('private_evidence',{}) else t for t in context.get('specialist_trace',[])]
            metadata = RouteMetadata(route_id=route_id,created_at=datetime.now(timezone.utc),request=request,
                coordinator=dict(public_name=ROLES['A0'][0],responsibility=ROLES['A0'][1],implementation_version='python-a0-v1'),
                scope=dict(roi_id=g.profile.roi_id,dataset_version=g.source_hash,bounds=g.bounds),
                sources=[dict(dataset_id=g.profile.dataset_id,source_url=g.profile.source_url,input_filename=g.source_path.name,
                    sha256=g.source_hash,instrument=g.profile.instrument,mission=g.profile.mission,acquisition_time=g.profile.acquisition_time,
                    provenance_record_id=route_id+':provenance')],grid=gridmeta,
                policy=dict(policy_id='terrain-research-v1',slope_threshold_deg=g.profile.slope_threshold_deg,
                    endpoint_rule='Exact endpoints; closed-cell segment intersections including corner touches; no smoothing.',
                    cost_formula='edge_length_m * mean(1 + weight*(slope_deg/threshold_deg)^2); endpoint connectors use endpoint cell penalty',
                    parameters={'weight':0.0 if request.mode=='shortest' else g.profile.terrain_weight},limits=limits),
                planner=dict(implementation_version='astar-v1',heuristic='Euclidean metric distance; minimum penalty is one',
                    objective_cost=float(search.cost),objective_units='terrain-weighted metres' if request.mode=='safest' else 'm',
                    expanded_nodes=search.expanded,elapsed_ms=search.elapsed_ms,distance_convention='Native projected planar polyline including endpoint connectors'),
                validation=dict(validator_version='closed-cell-native-v2' if factor > 1 else 'closed-cell-box-v1',checks=['source version unchanged','all segments inside ROI',
                    'all touched cells covered, known and allowed','no blocked diagonal corners','exact endpoints','emitted wire geometry revalidated']
                    + (['conservative native-cell aggregation','independent native source segment re-read'] if factor > 1 else []),
                    control_fixture_ids=['native-sphere-eqc-analytic-v1'],tolerances={'wire_metric_roundtrip_m':1e-5},map_alignment=registration.map_alignment),
                workers=workers,artifacts=artifacts,warnings=warnings,rationale=rationale,
                specialist_trace=traces,assessment=assessment,planning_policy=applied,legs=legs,registration=registration,
                usage=context.get('usage'),parent_route_id=parent_route_id)
            return StoredRouteResponse(result=result,metadata=metadata)
        return self.store.publish(route_id,build).result
