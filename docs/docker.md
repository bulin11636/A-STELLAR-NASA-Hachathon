# Docker runtime

The multi-stage Dockerfile builds the React frontend and serves it with FastAPI
on one origin. Raw datasets, private `.env` files, local environments, test output
and application state are excluded from the image by the build-context allowlist.

## Requirements

Use Docker Engine/Desktop with Compose v2 and Linux container support. On Windows,
Docker Desktop can use the WSL 2 backend; enable integration for the distribution
when running commands from WSL. Intel and AMD x86-64 hosts can use the same
`linux/amd64` image. The launcher also needs a local Python 3.10+ interpreter.

Prepare the required [dataset](datasets.md) and copy `.env.example` to a private
runtime file. The default planning profile expects
`M20_JezeroCrater_CTXDEM_20m.tif` directly inside the supplied dataset directory.
Run the launcher as an unprivileged host user.

## Build and start

From the repository root, Bash / WSL:

```bash
python scripts/run_docker.py \
  --env-file "$PWD/.env" \
  --dataset-dir /absolute/path/to/dataset \
  --mode agentic
```

PowerShell, with paths replaced for the local machine:

```powershell
python scripts/run_docker.py --env-file .env --dataset-dir C:\data\jezero --mode agentic
```

Open **http://localhost:8080**. The default action executes `docker compose up -d
--build`; it rebuilds changed application layers and updates the service. Build
caches may be reused. You do not need a separate Vite server in this mode.

Agentic mode requires the user's configured backend API credential and provider
access. Use `--mode deterministic` for computed terrain planning without live
model calls; its conversation/revision support is narrower. No credentials are
needed at image-build time.

## Input and runtime options

| Option | Purpose |
| --- | --- |
| `--env-file PATH` | Private runtime configuration, mounted read-only |
| `--dataset-dir PATH` | Scientific input root, mounted read-only at `/datasets` |
| `--planning-profile PATH` | Approved profile; defaults to the tracked CTX example |
| `--mode agentic` or `deterministic` | Select model-assisted or offline host planning |
| `--port 8081` | Choose another localhost HTTP port |
| `--project-name NAME` | Isolate a separate application/state instance |
| `--no-build` | Reuse an existing image rather than build it |
| `--dry-run` | Validate inputs and display the Compose command without starting Docker |

The profile's `dem` must be dataset-relative and resolve inside the mounted root.
Source identity, units and coordinates still require validation for another DEM.
Evidence profiles must use container-visible input paths and writable output
paths. The standard image does not include every optional geology dependency or
the ignored native geology cache; see [dataset limitations](datasets.md).

For a prebuilt image, first pull its approved version, set `A_STELLAR_IMAGE` to
that exact image/tag, and run the launcher with `--no-build`. No public image/tag
is assumed by the default local-build setup.

## Configuration precedence

The launcher passes mount paths through its environment and explicitly prevents
Compose from interpolating the private runtime file. The backend reads the
read-only file as data; it is not sourced as shell code.

Native startup uses process environment over the selected runtime file. In
Compose, the launcher-selected mode and fixed container paths override matching
file values: routing is computed, data are `/datasets`, the profile is
`/run/a-stellar/planning.json`, persistent state is under `/var/lib/a-stellar`, and
the production frontend is `/app/frontend/dist`. Other settings, such as model
configuration and trusted evidence bindings, come from the runtime file.

Restart after runtime configuration changes. Recreating with `--action up` is
appropriate when a bind-mounted file was replaced atomically or mount inputs
changed. Do not put the API credential in build arguments or the Dockerfile.

## Persistent state and lifecycle

A project-scoped named volume stores routes, evidence artifacts, chat messages
and application request/accounting state. Ordinary restart, rebuild and `down`
retain it. Deleting the volume deletes those records; back it up before removal.
Application/provider limits are distinct and do not reset just because the
container restarts.

Use the same env/dataset/project arguments with an action:

```bash
python scripts/run_docker.py --env-file .env --dataset-dir /path/to/dataset --action status
python scripts/run_docker.py --env-file .env --dataset-dir /path/to/dataset --action logs
python scripts/run_docker.py --env-file .env --dataset-dir /path/to/dataset --action restart
python scripts/run_docker.py --env-file .env --dataset-dir /path/to/dataset --action down
```

The service binds to localhost, drops Linux capabilities and runs as a non-root
user. On POSIX hosts the launcher uses the host UID/GID so private files can remain
readable without loosening their permissions. Keep a consistent UID when reusing
state. Windows uses the launcher's non-root fallback identity.

## Readiness and verification

- `/api/v1/health` checks process liveness.
- `/api/v1/ready` checks usable local planning configuration, storage and the
  required local credential configuration for the selected mode.
- Neither endpoint makes a model request, verifies provider credit or certifies
  NASA map alignment. The container health check uses readiness.

Run `python scripts/verify_docker.py --synthetic` for isolated image acceptance,
or use `--dataset-dir /path/to/dataset` for real terrain data. The verifier tests
its own project and state; see [verification](verification.md) for scope and reports.
