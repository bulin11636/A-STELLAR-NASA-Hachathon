"""Production HTTP boundaries and secret-free deployment configuration."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.planning.service import PlanningService
from app.coordinator.settings import AgentSettings
from test_planning import fixture_profile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('run_docker',ROOT/'scripts/run_docker.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_production_assets_api_errors_and_cache_boundaries(tmp_path):
    ui = tmp_path/'ui'; (ui/'assets').mkdir(parents=True)
    (ui/'index.html').write_text('<html>production shell</html>')
    (ui/'assets/app-test.js').write_text('console.log("build")')
    # API paths remain reserved even if an accidental static file exists there.
    (ui/'api/v1').mkdir(parents=True); (ui/'api/v1/private').write_text('must not leak')
    planning = PlanningService(output_root=tmp_path/'routes')
    with TestClient(create_app(planning=planning,static_dir=ui)) as client:
        root = client.get('/')
        assert root.status_code == 200 and 'production shell' in root.text
        assert root.headers['cache-control'] == 'no-cache'
        asset = client.get('/assets/app-test.js')
        assert asset.status_code == 200 and 'immutable' in asset.headers['cache-control']
        assert client.get('/api/v1/health').json()['status'] == 'ok'
        assert client.get('/api/v1/private').json()['error']['code'] == 'NOT_FOUND'
        assert client.get('/assets/missing.js').status_code == 404
        assert client.get('/.env').status_code == 404
        assert client.get('/api/v1/ready').status_code == 200


def test_readiness_distinguishes_missing_source_and_key_without_a_paid_call(tmp_path):
    broken = PlanningService('computed',tmp_path/'missing.json',tmp_path/'routes')
    with TestClient(create_app(planning=broken)) as client:
        response = client.get('/api/v1/ready')
        assert response.status_code == 503 and response.json()['checks']['planning'] is False
        assert str(tmp_path) not in response.text
        assert client.get('/api/v1/health').status_code == 200
    working = PlanningService('computed',fixture_profile(tmp_path),tmp_path/'routes')
    agent = SimpleNamespace(planning=working,settings=AgentSettings(enabled=True,api_key=None))
    with TestClient(create_app(planning=working,route_agent=agent)) as client:
        response = client.get('/api/v1/ready')
        assert response.status_code == 503
        assert response.json()['checks'] == {'planning':True,'storage':True,'model_credentials':False}


def test_explicit_static_configuration_requires_a_build(tmp_path):
    with pytest.raises(ValueError,match='index.html'):
        create_app(planning=PlanningService(),static_dir=tmp_path)


def deployment_args(tmp_path):
    runtime = tmp_path/'private.env'; runtime.write_text('OPENAI_API_KEY=synthetic-secret-$NOT_INTERPOLATED\n')
    dataset = tmp_path/'dataset'; dataset.mkdir(); (dataset/'dem.tif').touch()
    profile = tmp_path/'profile.json'; profile.write_text(json.dumps({'dem':'dem.tif'}))
    return launcher.parser().parse_args(['--env-file',str(runtime),'--dataset-dir',str(dataset),'--planning-profile',str(profile),'--dry-run'])


def test_external_env_bytes_are_not_executed_or_interpolated(tmp_path,monkeypatch):
    monkeypatch.setattr(launcher.os,'getuid',lambda:1000,raising=False)
    monkeypatch.setattr(launcher.os,'getgid',lambda:1000,raising=False)
    args = deployment_args(tmp_path)
    command,env = launcher.deployment(args)
    assert command[command.index('--env-file')+1] == launcher.os.devnull
    assert env['A_STELLAR_HOST_ENV_FILE'] == args.env_file
    assert env['A_STELLAR_RUNTIME_UID'] == '1000'
    assert 'synthetic-secret' not in json.dumps(command)+json.dumps(env)
    # Stop/log operations must remain possible after an input was removed.
    Path(args.env_file).unlink(); args.action = 'down'
    launcher.deployment(args)


@pytest.mark.parametrize('dem',['../escape.tif','/absolute/dem.tif','folder\\dem.tif'])
def test_nonportable_or_escaping_source_paths_are_rejected(tmp_path,dem,monkeypatch):
    monkeypatch.setattr(launcher.os,'getuid',lambda:1000,raising=False)
    args = deployment_args(tmp_path)
    Path(args.planning_profile).write_text(json.dumps({'dem':dem}))
    with pytest.raises(ValueError): launcher.deployment(args)
