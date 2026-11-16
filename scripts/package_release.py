"""Create an allowlisted deployment bundle for a versioned GHCR image."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TAG = re.compile(r'v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-(alpha|beta|rc)\.(0|[1-9]\d*))?')
FILES = (
    '.env.example', 'scripts/run_docker.py', 'scripts/acquire_verified_products.py',
    'data/samples/a0-planning-profile.example.json', 'data/samples/download-manifest.json',
    'docs/si-disclosure.json',
)


def version(tag, root=ROOT):
    if not TAG.fullmatch(tag):
        raise ValueError('Use vMAJOR.MINOR.PATCH, optionally followed by -alpha.N, -beta.N or -rc.N.')
    base = tag[1:].split('-')[0]
    frontend = json.loads((root / 'frontend/package.json').read_text())['version']
    backend = re.search(r'^version\s*=\s*"([^"]+)"', (root / 'backend/pyproject.toml').read_text(), re.M).group(1)
    if frontend != base or backend != base:
        raise ValueError('The tag must match both frontend and backend package versions.')
    return tag[1:]


def package(tag, image, digest, revision, output, root=ROOT):
    release_version = version(tag, root)
    if not re.fullmatch(r'ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+', image):
        raise ValueError('Expected a lowercase GHCR owner/image name.')
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest) or not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise ValueError('Expected a registry SHA-256 digest and a full Git commit SHA.')
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    pinned = image + '@' + digest
    source = 'https://github.com/' + image.removeprefix('ghcr.io/')
    metadata = dict(version=tag, revision=revision, platform='linux/amd64',
                    image=image + ':' + release_version, image_digest=pinned, source=source)
    instructions = f'''# A-STELLAR {tag}

This deployment bundle runs the prebuilt Linux image on Intel/AMD x86-64 PCs,
including Windows with Docker Desktop and WSL 2. Install Docker Compose v2 and
Python 3.10+ locally, then extract this ZIP before running commands.

Source and full documentation: {source}/tree/{tag}

## Prepare inputs

Copy `.env.example` to a private `.env` and configure it for agentic mode.
For deterministic mode, an empty `.env` file is sufficient. Your configuration,
datasets and persistent application state stay outside the image.

Use an existing dataset directory or download the required terrain product:

```bash
python scripts/acquire_verified_products.py a1-ctx-jezero-dem-20m
```

The command stores the DEM under `data/raw/dem/`. Downloads require network
access. Optional scientific inputs are described in the source dataset guide.

## Pull and run

```bash
docker pull {pinned}
python scripts/run_docker.py --env-file .env --dataset-dir data/raw/dem --no-build --mode deterministic
```

Open http://localhost:8080. Replace `data/raw/dem` with your existing dataset
directory if appropriate. Use `--mode agentic` for model-assisted planning.
This bundle's Compose file pins the published image digest and has no build step.

For a private package, first authenticate to ghcr.io using your GitHub username
and a classic personal access token with `read:packages`, through
`docker login ghcr.io`. A public package can be pulled anonymously. Registry
authentication is separate from the application model API credential.

## Lifecycle

Use the same env-file, dataset-dir and project-name arguments for every action.
`--action status`, `--action logs`, `--action restart` and `--action down` control
the deployment. Routes and chats remain in its named Docker volume across
restart and recreation. Use a separate `--project-name` for an isolated acceptance
run; back up existing state before changing versions.

## Provenance

- Version: `{tag}`
- Source revision: `{revision}`
- Container: `{pinned}`
- Platform: `linux/amd64`
- SI usage: `docs/si-disclosure.json`; the source repository contains data credits.

`release.json` records this identity. `SHA256SUMS` checks the downloaded ZIP and
metadata against the release assets.
'''
    compose = (root / 'compose.yaml').read_text()
    build = '    build:\n      context: .\n'
    default = '    image: ${A_STELLAR_IMAGE:-a-stellar:local}'
    if compose.count(build) != 1 or compose.count(default) != 1:
        raise ValueError('Compose layout changed; review release bundle generation.')
    compose = compose.replace(build, '').replace(default, '    image: ' + pinned)
    archive = output / ('a-stellar-' + tag + '-deploy.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for name in FILES:
            path = root / name
            if path.is_symlink():
                raise ValueError('Release inputs must be regular files.')
            bundle.write(path, name)
        bundle.writestr('compose.yaml', compose)
        bundle.writestr('README.md', instructions)
        bundle.writestr('release.json', json.dumps(metadata, indent=2) + '\n')
    manifest = output / 'release.json'
    manifest.write_text(json.dumps(metadata, indent=2) + '\n')
    (output / 'SHA256SUMS').write_text(''.join(
        hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n'
        for p in (archive, manifest)))
    (output / 'release-notes.md').write_text(f'''A-STELLAR {tag} packages the Mars planning workspace for Docker.

- Download `a-stellar-{tag}-deploy.zip`, extract it and follow its README.
- Image: `{image}:{release_version}` (`linux/amd64`).
- Exact tested image: `{pinned}`.
- Source revision: `{revision}`.
- Inputs: external Jezero DEM and private runtime configuration.
- Backend, frontend and isolated Docker acceptance run before publication.

See the [release guide]({source}/blob/{tag}/docs/releases.md) for Windows/WSL
instructions and package access. Repository and package visibility are managed
separately by the owner.
''')
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--check-version', action='store_true')
    parser.add_argument('--image')
    parser.add_argument('--digest')
    parser.add_argument('--revision')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'data/processed/release')
    args = parser.parse_args()
    try:
        if args.check_version:
            print(version(args.tag))
        else:
            if not all((args.image, args.digest, args.revision)):
                parser.error('--image, --digest and --revision are required for packaging.')
            print(json.dumps(package(args.tag, args.image, args.digest, args.revision, args.output_dir), indent=2))
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
