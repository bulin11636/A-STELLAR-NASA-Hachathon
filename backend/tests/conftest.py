"""Keep ordinary tests independent of the developer's private runtime config."""
import pytest


@pytest.fixture(scope='session')
def runtime_env_file(tmp_path_factory):
    env_file=tmp_path_factory.mktemp('offline-runtime')/'empty-runtime.env'
    env_file.write_text('',encoding='utf-8')
    return env_file


@pytest.fixture(autouse=True)
def offline_runtime(runtime_env_file,monkeypatch):
    monkeypatch.setenv('A_STELLAR_ENV_FILE',str(runtime_env_file))
    monkeypatch.setenv('A_STELLAR_ROUTING_MODE','mock')
    monkeypatch.setenv('A_STELLAR_A0_MODE','deterministic')
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
