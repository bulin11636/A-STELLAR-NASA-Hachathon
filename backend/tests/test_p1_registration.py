"""Synthetic controls verify the gate machinery, never real NASA registration."""
import hashlib
import json
from pathlib import Path

import pytest
from app.planning.grid import load_grid
from app.planning.registration import validate_controls
from app.planning.synthetic_fixtures import inputs, controls
from app.planning.service import PlanningService
from test_planning import request_for


def prepared(tmp_path):
    path=inputs(tmp_path);grid=load_grid(path);report=controls(grid,tmp_path)
    request=request_for(grid,a=(10,10),b=(70,80))
    return grid,report,request


def test_independent_control_scope_and_synthetic_production_guard(tmp_path):
    grid,path,request=prepared(tmp_path)
    assert validate_controls(grid,path,[request.start,request.goal]).map_alignment=='unverified'
    result=validate_controls(grid,path,[request.start,request.goal],allow_synthetic=True)
    assert result.map_alignment=='verified' and result.synthetic
    assert len(result.residuals)==4 and all(r.passed for r in result.residuals)
    outside=grid.wire(*grid.center((0,0)))
    assert validate_controls(grid,path,[outside,request.goal],allow_synthetic=True).map_alignment=='unverified'


@pytest.mark.parametrize('change',['source','latitude','radius','duplicate','collinear','dem_offset','wmts_offset','asset','matrix','capability_resolution'])
def test_wrong_or_insufficient_controls_never_verify(tmp_path,change):
    grid,path,request=prepared(tmp_path);body=json.loads(path.read_text())
    if change=='source': body['source_sha256']='0'*64
    if change=='latitude': body['latitude_type']='planetocentric'
    if change=='radius': body['semi_major_m']=3396160.0
    if change=='duplicate': body['observations'][1]['control_id']=body['observations'][0]['control_id']
    if change=='collinear':
        for i,o in enumerate(body['observations']):
            wire=grid.wire(*grid.center((20,10+i*10)));o['wire']=wire.model_dump();o['dem_pixel']=[11.5+i*10,21.5]
    if change=='dem_offset': body['observations'][0]['dem_pixel'][0]+=10
    if change=='wmts_offset': body['observations'][0]['wmts_coordinate'][1]+=.01
    if change=='asset': (tmp_path/'synthetic-measurements.json').write_text('tampered')
    if change=='matrix': body['observations'][0]['wmts_matrix_id']='missing'
    if change=='capability_resolution':
        p=tmp_path/'synthetic-capabilities.xml';p.write_text(p.read_text().replace('65536','256').replace('32768','128'))
        body['capabilities_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    path.write_text(json.dumps(body))
    result=validate_controls(grid,path,[request.start,request.goal],allow_synthetic=True)
    assert result.map_alignment=='unverified' and result.reasons


def test_registration_persists_with_route_and_retrieval_without_sources(tmp_path):
    grid,control_path,request=prepared(tmp_path)
    p=tmp_path/'profile.json';body=json.loads(p.read_text());body['registration_controls']=control_path.name;p.write_text(json.dumps(body))
    service=PlanningService('computed',p,tmp_path/'routes',allow_synthetic_registration=True)
    result=service.plan(request)
    record=service.store.get(result.route_id)
    assert record.metadata.validation.map_alignment=='verified'
    assert record.metadata.registration.evidence_id==result.route_id+':provenance#registration'
    control_path.unlink()
    fresh=PlanningService('computed',p,tmp_path/'routes')
    assert fresh.store.get(result.route_id)==record
    new=fresh.store.get(fresh.plan(request).route_id)
    assert new.metadata.validation.map_alignment=='unverified'
