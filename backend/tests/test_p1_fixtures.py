"""Shared fixtures must remain typed, complete, deterministic and explicitly synthetic."""
import importlib.util
import json
from pathlib import Path

from app.contracts.policies import PolicyCatalog
from app.contracts.routes import StoredRouteResponse

ROOT=Path(__file__).resolve().parents[2]
FIXTURES=ROOT/'data/fixtures/p1'


def test_p1_matrix_validates_and_never_scores_missing_factors():
    files=list(FIXTURES.glob('*.json'))
    assert len(files)==19
    for file in files:
        if file.name=='policies.json':
            assert len(PolicyCatalog.model_validate_json(file.read_text()).profiles)==4
            continue
        record=StoredRouteResponse.model_validate_json(file.read_text())
        a=record.metadata.assessment
        assert len(a.risk_factors)==6 and a.score_scale=='0..100'
        if a.hard_gate_status!='pass': assert a.risk_score is None
        assert 0<=a.assessment_confidence<=100
        if 'verified-alignment-synthetic' in file.name:
            assert record.metadata.registration.synthetic and record.metadata.validation.map_alignment=='verified'
        else: assert record.metadata.validation.map_alignment=='unverified'


def test_p1_export_is_reproducible_with_no_model_configuration(tmp_path):
    spec=importlib.util.spec_from_file_location('export_p1',ROOT/'scripts/export_p1_fixtures.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    first,second=tmp_path/'first',tmp_path/'second'
    assert module.export(first)==module.export(second)
    for file in first.glob('*.json'):
        assert file.read_bytes()==(second/file.name).read_bytes(),file.name
        assert file.read_bytes()==(FIXTURES/file.name).read_bytes(),file.name
