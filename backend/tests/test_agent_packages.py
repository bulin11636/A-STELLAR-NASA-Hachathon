"""Package boundaries and synthetic standalone adapters, not raster validation."""
import asyncio
import importlib
import inspect
import json
from pathlib import Path
import subprocess
import sys
import threading

import pytest
from pydantic import ValidationError

from app.agents.a1 import TraversabilityConfig, Worker as A1
from app.agents.a2 import ThermalConfig, Worker as A2
from app.agents.a3 import Worker as A3
from app.agents.a4 import Worker as A4
from app.agents.a6 import Worker as A6
from app.agents.registry import WorkerRegistry
from app.contracts.workers import AGENT_IDS, WorkerContext
from app.coordinator.dispatcher import AgentDispatcher
from app.evidence.models import EvidenceDataset, PREVIEW_ROI


def context(**changes):
    return WorkerContext(**{'mission_id':'package-test','region_id':'jezero','roi_id':PREVIEW_ROI.roi_id,
                            'dataset_version':'synthetic-v1',**changes})


def common(tmp_path):
    return dict(roi_id=PREVIEW_ROI.roi_id,dataset_version='synthetic-v1',point={'longitude':77.4,'latitude':18.4},
                source={'dataset_id':'synthetic-source','source_url':'https://example.com/synthetic',
                        'mission':'synthetic','instrument':'synthetic'},provenance_ref='synthetic-source.json',
                output_root=tmp_path/'output')


def a1_config(tmp_path, **changes):
    dem=tmp_path/'synthetic-dem.tif'; dem.write_bytes(b'synthetic only, not a GeoTIFF')
    return TraversabilityConfig(**{**common(tmp_path),'dem_path':dem,'radius_m':10.0,'tile_size_m':1.0,**changes})


def a2_config(tmp_path, **changes):
    day,night=tmp_path/'day.tif',tmp_path/'night.tif'
    day.write_bytes(b'synthetic only'); night.write_bytes(b'synthetic only')
    return ThermalConfig(**{**common(tmp_path),'day_path':day,'night_path':night,**changes})


def test_every_agent_exports_the_shared_async_worker_entry_point():
    for agent_id in AGENT_IDS:
        package=importlib.import_module(f'app.agents.{agent_id.lower()}')
        assert package.Worker.agent_id==agent_id
        assert inspect.iscoroutinefunction(package.Worker.run)


def test_packages_import_without_loading_optional_scientific_dependencies():
    code='''import sys
class NoScientificImports:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'rasterio','numpy','fiona','shapely','pyproj'}:
            raise AssertionError('Unexpected optional dependency import: '+fullname)
sys.meta_path.insert(0,NoScientificImports())
from app.agents import a1,a2,a3,a4,a6
from app.main import create_app
assert all(hasattr(module,'Worker') for module in [a1,a2,a3,a4,a6])
create_app()
'''
    result=subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr


def test_all_five_packages_dispatch_typed_unavailable_outputs_without_configured_data():
    dataset=EvidenceDataset(dataset_version='synthetic-v1',roi=PREVIEW_ROI,stops=[],segments=[],pois=[],
                            dataset_ids=[],warnings=['Synthetic empty dataset.'],provenance_ref='synthetic.json',artifact_ref='vectors.json')
    registry=WorkerRegistry()
    for worker in (A1(),A2(),A3(),A4(dataset),A6(dataset)):
        registry.register(worker)
    report=asyncio.run(AgentDispatcher(registry).run(context(),AGENT_IDS))
    assert registry.registered_ids==AGENT_IDS
    assert tuple(r.agent_id for r in report.results)==AGENT_IDS
    assert all(r.status=='unavailable' and r.warnings for r in report.results)


@pytest.mark.parametrize('factory,config_factory',[(A1,a1_config),(A2,a2_config)])
def test_mismatched_context_does_not_execute_the_prototype(tmp_path,monkeypatch,factory,config_factory):
    worker=factory(config_factory(tmp_path))
    def unexpected(*args): raise AssertionError('Prototype should not execute.')
    monkeypatch.setattr(worker,'_analyze',unexpected)
    result=asyncio.run(worker.run(context(dataset_version='other')))
    assert result.status=='unavailable' and not result.artifacts
    assert not (tmp_path/'output').exists()


@pytest.mark.parametrize('changes',[{'radius_m':0.0},{'tile_size_m':-1.0},{'max_slope_deg':90.0},
                                    {'radius_m':float('nan')},{'provenance_ref':''}])
def test_a1_invalid_configuration_is_rejected(tmp_path,changes):
    with pytest.raises(ValidationError): a1_config(tmp_path,**changes)


def test_missing_input_files_remain_unknown_without_running_prototypes(tmp_path,monkeypatch):
    for worker in (A1(a1_config(tmp_path,dem_path=tmp_path/'missing.tif')),
                   A2(a2_config(tmp_path,night_path=tmp_path/'missing.tif'))):
        def unexpected(*args): raise AssertionError('Missing inputs should not execute.')
        monkeypatch.setattr(worker,'_analyze',unexpected)
        result=asyncio.run(worker.run(context()))
        assert result.status=='unavailable' and not result.artifacts


def test_a1_offloads_blocking_work_and_isolates_simultaneous_artifacts(tmp_path,monkeypatch):
    import numpy as np
    worker=A1(a1_config(tmp_path))
    event_loop_thread=threading.get_ident()
    def synthetic(directory):
        assert threading.get_ident()!=event_loop_thread
        directory.mkdir(parents=True)
        path=directory/'synthetic.npy'; np.save(path,np.zeros((2,2)))
        return {'status':'complete','grid_file_path':str(path),'safety_summary':{'total_tiles':4}}
    monkeypatch.setattr(worker,'_analyze',synthetic)
    async def both(): return await asyncio.gather(worker.run(context()),worker.run(context()))
    first,second=asyncio.run(both())
    assert first.artifacts['prototype_slope_grid']!=second.artifacts['prototype_slope_grid']
    for result in (first,second):
        assert result.status=='partial' and result.data_kind=='scenario'
        assert result.grid_id is result.risk_ref is result.hard_block_ref is result.unknown_ref is None
        assert result.slope_ref is result.geospatial_metadata_ref is None
        report=json.loads(Path(result.artifacts['prototype_report']).read_text())
        assert report['planning_ready'] is False and report['configuration']['dataset_version']=='synthetic-v1'
        assert Path(report['prototype_result']['grid_file_path']).is_file()


def test_a1_rejects_external_grid_references(tmp_path,monkeypatch):
    worker=A1(a1_config(tmp_path))
    outside=tmp_path/'outside.npy'; outside.write_bytes(b'synthetic')
    monkeypatch.setattr(worker,'_analyze',lambda directory:{'status':'complete','grid_file_path':str(outside)})
    result=asyncio.run(worker.run(context()))
    assert result.status=='failed' and not result.artifacts
    assert outside.read_bytes()==b'synthetic'


def test_a2_prototype_values_are_never_promoted_to_calibrated_observations(tmp_path,monkeypatch):
    worker=A2(a2_config(tmp_path))
    event_loop_thread=threading.get_ident()
    def synthetic():
        assert threading.get_ident()!=event_loop_thread
        return {'status':'complete','day_temperature_c':-42.0,'material_prediction':'Synthetic heuristic'}
    monkeypatch.setattr(worker,'_analyze',synthetic)
    result=asyncio.run(worker.run(context()))
    assert result.status=='partial' and result.data_kind=='scenario' and result.constraint_status=='unknown'
    assert result.observed_at is result.observation_unit is result.thermal_raster_ref is None
    report=json.loads(Path(result.artifacts['prototype_report']).read_text())
    assert report['planning_ready'] is False and report['prototype_result']['day_temperature_c']==-42.0


@pytest.mark.parametrize('factory,config_factory',[(A1,a1_config),(A2,a2_config)])
def test_missing_optional_dependencies_are_explicit(tmp_path,monkeypatch,factory,config_factory):
    worker=factory(config_factory(tmp_path))
    def missing(*args): raise ImportError('private installation path')
    monkeypatch.setattr(worker,'_analyze',missing)
    result=asyncio.run(worker.run(context()))
    assert result.status=='unavailable' and 'raster' in result.warnings[0]
    assert 'private installation path' not in result.model_dump_json()


def test_malformed_prototype_outputs_are_isolated_by_dispatcher(tmp_path,monkeypatch):
    worker=A2(a2_config(tmp_path))
    monkeypatch.setattr(worker,'_analyze',lambda:{'status':'complete','day_temperature_c':float('nan')})
    registry=WorkerRegistry(); registry.register(worker)
    report=asyncio.run(AgentDispatcher(registry).run(context(),('A2',)))
    assert report.results[0].status=='failed' and not report.results[0].artifacts
