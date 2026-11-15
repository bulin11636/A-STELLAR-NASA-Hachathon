"""Native startup selects this checkout and probes local readiness only."""
import importlib.util
import json
from pathlib import Path

import pytest
from test_planning import fixture_profile

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('run_backend',ROOT/'scripts/run_backend.py')
launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)


def arguments(tmp_path):
    profile=fixture_profile(tmp_path)
    runtime=tmp_path/'private.env'; runtime.write_text('OPENAI_API_KEY=synthetic-private-value\nA_STELLAR_DATASET_DIR=/old/source\n')
    return launcher.parser().parse_args(['--dataset-dir',str(tmp_path),'--profile',str(profile),'--env-file',str(runtime),
        '--state-dir',str(tmp_path/'state'),'--mode','deterministic','--check'])


def test_local_check_never_starts_the_provider_or_uses_an_old_checkout(tmp_path,monkeypatch):
    args=arguments(tmp_path)
    monkeypatch.setenv('A_STELLAR_STATIC_DIR','/old/frontend/dist')
    monkeypatch.setenv('PYTHONPATH','/old/backend')
    env=launcher.configuration(args)
    result=launcher.check_configuration(env)
    assert result==dict(ready=True,checks=dict(planning=True,storage=True,model_credentials=True),mode='deterministic',provider_access_verified=False)
    assert env['PYTHONPATH']==str(ROOT/'backend') and env['A_STELLAR_STATIC_DIR']==''
    assert env['A_STELLAR_DATASET_DIR']==str(tmp_path)
    assert 'synthetic-private-value' not in json.dumps(result)
    assert not (tmp_path/'state/a0-model-usage/a0-usage.sqlite3').exists()


@pytest.mark.parametrize('field,value',[('port',0),('port',65536),('dataset_dir',Path('/missing-source')),('env_file',Path('/missing-private-file'))])
def test_invalid_inputs_are_rejected_without_reading_secrets(tmp_path,field,value):
    args=arguments(tmp_path);setattr(args,field,value)
    with pytest.raises(ValueError): launcher.configuration(args)
