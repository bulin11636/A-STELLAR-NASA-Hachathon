"""Release assets pin the tested image and contain only deployment inputs."""
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('package_release', ROOT / 'scripts/package_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
IMAGE = 'ghcr.io/bulin11636/a-stellar-nasa-hachathon'
DIGEST = 'sha256:' + 'a' * 64
REVISION = 'b' * 40


def source(tmp_path):
    root = tmp_path / 'source'; root.mkdir()
    for name in (*release.FILES, 'compose.yaml', 'frontend/package.json', 'backend/pyproject.toml'):
        target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    (root / 'frontend/package.json').write_text(json.dumps({'version': '0.1.0'}))
    (root / 'backend/pyproject.toml').write_text('version = "0.1.0"\n')
    (root / '.env').write_text('OPENAI_API_KEY=must-never-be-packaged')
    (root / 'data/raw').mkdir(); (root / 'data/raw/private.tif').write_bytes(b'private scientific input')
    return root


def test_bundle_pins_image_and_excludes_private_inputs(tmp_path):
    root = source(tmp_path); output = tmp_path / 'output'
    metadata = release.package('v0.1.0', IMAGE, DIGEST, REVISION, output, root)
    archive = output / 'a-stellar-v0.1.0-deploy.zip'
    with zipfile.ZipFile(archive) as bundle:
        assert set(bundle.namelist()) == set(release.FILES) | {'compose.yaml', 'README.md', 'release.json'}
        assert all(b'must-never-be-packaged' not in bundle.read(name) for name in bundle.namelist())
        compose = bundle.read('compose.yaml').decode()
        assert '    image: ' + IMAGE + '@' + DIGEST in compose
        assert 'build:' not in compose and 'a-stellar:local' not in compose
        assert json.loads(bundle.read('release.json')) == metadata
        assert 'http://localhost:8080' in bundle.read('README.md').decode()
    for line in (output / 'SHA256SUMS').read_text().splitlines():
        expected, filename = line.split('  ')
        assert hashlib.sha256((output / filename).read_bytes()).hexdigest() == expected
    assert metadata['revision'] == REVISION and metadata['platform'] == 'linux/amd64'


@pytest.mark.parametrize('tag', ['main', 'v01.0.0', 'v0.1', '../v0.1.0', 'v0.1.0; echo x', 'v0.1.0-rc.01', 'v1.0.0'])
def test_invalid_or_mismatched_versions_are_rejected(tag, tmp_path):
    with pytest.raises(ValueError):
        release.version(tag, source(tmp_path))


def test_prerelease_uses_matching_base_package_version(tmp_path):
    assert release.version('v0.1.0-rc.1', source(tmp_path)) == '0.1.0-rc.1'


@pytest.mark.parametrize('image,digest,revision', [
    ('ghcr.io/Owner/Image', DIGEST, REVISION),
    (IMAGE, 'sha256:incomplete', REVISION),
    (IMAGE, DIGEST, 'main'),
])
def test_unpinned_or_invalid_image_identity_is_rejected(tmp_path, image, digest, revision):
    with pytest.raises(ValueError):
        release.package('v0.1.0', image, digest, revision, tmp_path / 'output', source(tmp_path))


def test_extracted_bundle_launches_without_a_source_checkout(tmp_path):
    output = tmp_path / 'output'
    release.package('v0.1.0', IMAGE, DIGEST, REVISION, output, source(tmp_path))
    extracted = tmp_path / 'deployment'
    with zipfile.ZipFile(output / 'a-stellar-v0.1.0-deploy.zip') as bundle:
        bundle.extractall(extracted)
    runtime = extracted / '.env'; runtime.write_text('')
    dataset = tmp_path / 'dataset'; dataset.mkdir()
    profile = json.loads((extracted / 'data/samples/a0-planning-profile.example.json').read_text())
    (dataset / profile['dem']).touch()
    result = subprocess.run([sys.executable, str(extracted / 'scripts/run_docker.py'),
        '--env-file', str(runtime), '--dataset-dir', str(dataset), '--no-build',
        '--mode', 'deterministic', '--dry-run'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert str(extracted / 'compose.yaml') in result.stdout
    assert '--build' not in result.stdout
