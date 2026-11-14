"""Launch Docker Compose with external configuration; never source an env file."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

REPO = Path(__file__).resolve().parents[1]


def existing_path(value, *, directory=False):
    path = Path(value).expanduser().resolve()
    if not (path.is_dir() if directory else path.is_file()):
        raise ValueError("A required input directory/file does not exist.")
    return path


def deployment(args):
    env_file = Path(args.env_file).expanduser().resolve()
    datasets = Path(args.dataset_dir).expanduser().resolve()
    profile = Path(args.planning_profile).expanduser().resolve()
    if args.action in ('up','restart'):
        existing_path(env_file)
        existing_path(datasets,directory=True)
        existing_path(profile)
        definition = json.loads(profile.read_text())
        dem = Path(definition['dem'])
        if dem.is_absolute() or '..' in dem.parts or not dem.parts or '\\' in str(dem):
            raise ValueError("Use a dataset-relative DEM path in the Docker planning profile.")
        source = existing_path(datasets / dem)
        if not source.is_relative_to(datasets):
            raise ValueError("The DEM must resolve inside the mounted dataset directory.")
    if not 1 <= args.port <= 65535:
        raise ValueError("The HTTP port must be between 1 and 65535.")
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', args.project_name):
        raise ValueError("The Compose project name must use lowercase letters, digits, underscores or hyphens.")
    env = dict(os.environ)
    env.update(A_STELLAR_HOST_ENV_FILE=str(env_file), A_STELLAR_HOST_DATASET_DIR=str(datasets),
        A_STELLAR_HOST_PLANNING_PROFILE=str(profile), A_STELLAR_HTTP_PORT=str(args.port),
        A_STELLAR_CONTAINER_A0_MODE=args.mode,
        A_STELLAR_RUNTIME_UID=str(os.getuid() if hasattr(os,'getuid') else 10001),
        A_STELLAR_RUNTIME_GID=str(os.getgid() if hasattr(os,'getgid') else 10001))
    if env['A_STELLAR_RUNTIME_UID'] == '0':
        raise ValueError("Launch the application as an unprivileged host user.")
    # Compose must not interpret the private runtime file for interpolation.
    # The application reads its read-only mounted bytes itself.
    command = ['docker', 'compose', '--env-file', os.devnull, '--project-directory', str(REPO),
        '-f', str(REPO / 'compose.yaml'), '--project-name', args.project_name]
    return command, env


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--env-file', required=True, help='Private runtime env file mounted read-only')
    result.add_argument('--dataset-dir', required=True, help='Read-only dataset root with the selected DEM')
    result.add_argument('--planning-profile', default=str(REPO / 'data/samples/a0-planning-profile.example.json'))
    result.add_argument('--port', type=int, default=8080)
    result.add_argument('--project-name', default='a-stellar')
    result.add_argument('--mode', choices=['agentic', 'deterministic'], default='agentic')
    result.add_argument('--action', choices=['up', 'status', 'logs', 'restart', 'down'], default='up')
    result.add_argument('--no-build', action='store_true', help='Reuse an existing image')
    result.add_argument('--dry-run', action='store_true', help='Validate inputs and show the command without Docker')
    return result


def main():
    cli = parser()
    args = cli.parse_args()
    try:
        command, env = deployment(args)
    except (OSError, ValueError, KeyError, TypeError):
        cli.error('Invalid deployment inputs: check paths, relative DEM, JSON profile, project name and port. Input contents were not logged.')
    actions = {'up': ['up', '-d'] + ([] if args.no_build else ['--build']), 'status': ['ps'],
        'logs': ['logs', '--tail', '100', 'app'], 'restart': ['restart', 'app'], 'down': ['down']}
    command += actions[args.action]
    if args.dry_run:
        print(shlex.join(command))
        print(f'Input paths validated. UI: http://127.0.0.1:{args.port}; A0 mode: {args.mode}.')
        return
    try:
        completed = subprocess.run(command, env=env, cwd=REPO, check=False)
    except FileNotFoundError:
        cli.exit(1, 'Docker Compose is unavailable. Install Docker or enable Docker Desktop WSL integration.\n')
    raise SystemExit(completed.returncode)


if __name__ == '__main__':
    main()
