"""Regional scale must retain native hazards, exact stops and durable geometry."""
import json

import numpy as np
import pytest

from app.api.errors import ApiProblem
from app.planning.grid import load_grid, transform_point
from app.planning.service import PlanningService
from app.planning.validation import validate_native_polyline
from app.coordinator.route_agent import RouteAgent
from app.coordinator.settings import AgentSettings
from app.coordinator.metered import MeteredProvider
from test_planning import fixture_profile, request_for


def regional_profile(tmp_path, z=None):
    path = fixture_profile(tmp_path, np.zeros((154,164)) if z is None else z)
    raw = json.loads(path.read_text())
    raw.update(window=[1,1,10,10], limits={"max_grid_cells":1000,"max_expanded_nodes":1000,"max_elapsed_seconds":5})
    path.write_text(json.dumps(raw))
    return path


def test_region_uses_whole_source_under_memory_limit_and_validates_native(tmp_path):
    service = PlanningService('computed',regional_profile(tmp_path),tmp_path/'routes')
    base = service.grid
    goal = base.wire(*(transform_point(base.transform,(140.5,130.5))))
    request = request_for(base).model_copy(update={'goal':goal})
    result = service.plan(request)
    stored = service.store.get(result.route_id)
    assert result.route[0] == request.start and result.route[-1] == goal
    assert stored.metadata.grid.width*stored.metadata.grid.height <= 1000
    assert stored.metadata.grid.planning_resolution_m == (120,180)
    private = json.loads((service.store.root/result.route_id/'provenance.json').read_text())
    assert private['inventory']['source_window'] == [1,1,162,152]
    report = json.loads((service.store.root/result.route_id/'validation.json').read_text())
    assert report['native_validation']['status'] == 'passed'
    assert report['native_validation']['touched_native_cells'] > 100
    assert any('narrow native corridors' in fact for fact in stored.metadata.rationale.facts)


def test_native_hazard_and_nodata_cannot_be_averaged_away(tmp_path):
    z = np.zeros((154,164)); z[60,60]=1000; z[100,100]=-9999
    path = regional_profile(tmp_path,z)
    g = load_grid(path,window=(1,1,162,152),resolution_factor=6)
    assert g.blocked[59//6,58//6] or g.blocked[59//6,60//6]
    assert g.unknown[99//6,99//6]
    assert not g.allowed[-1,:].any(), 'Partial blocks remain unknown'
    # Bypass the aggregated masks to test the independent source validator.
    # This one native-pixel segment touches the central-difference hazard.
    from affine import Affine
    transform = Affine(*g.inventory['source_transform'])
    with pytest.raises(ApiProblem,match='native terrain'):
        validate_native_polyline(g,[transform_point(transform,(58.5,60.5)),transform_point(transform,(59.5,60.5))])


def test_disabling_adaptation_preserves_explicit_limit(tmp_path):
    path = regional_profile(tmp_path)
    raw = json.loads(path.read_text()); raw['adaptive_resolution']=False; path.write_text(json.dumps(raw))
    service = PlanningService('computed',path,tmp_path/'routes')
    request = request_for(service.grid)
    request = request.model_copy(update={'goal':service.grid.wire(*(transform_point(service.grid.transform,(140.5,130.5))))})
    with pytest.raises(ApiProblem) as error:
        service.plan(request)
    assert error.value.code == 'PLANNING_LIMIT_EXCEEDED'


def test_disconnected_crop_widens_without_a_second_model_call(tmp_path):
    import httpx
    from test_route_agent import decision, model_response
    z = np.zeros((50,50)); z[10:36,20]=1000
    path = fixture_profile(tmp_path,z)
    raw = json.loads(path.read_text()); raw['window']=[12,15,18,12]; path.write_text(json.dumps(raw))
    service = PlanningService('computed',path,tmp_path/'routes')
    settings = AgentSettings(enabled=True,api_key='synthetic-only')
    provider = MeteredProvider(settings,tmp_path/'usage',httpx.MockTransport(lambda req:httpx.Response(200,json=model_response(decision()))))
    agent = RouteAgent(settings,service,provider)
    request = request_for(service.grid,a=(5,2),b=(5,15))
    result = agent.plan(request)
    stored = service.store.get(result.route_id)
    assert stored.metadata.grid.width == 48 and stored.metadata.grid.height == 48
    assert any('full-source retry' in fact for fact in stored.metadata.rationale.facts)
    assert stored.metadata.planner.expanded_nodes <= stored.metadata.policy.limits.max_expanded_nodes
    assert provider.totals()['attempts'] == 1
