# Docker runtime

The multi-stage image builds the React UI and serves it with the FastAPI API on
one origin. Scientific data and credentials are runtime inputs. The build-context
allowlist includes only application source, frontend build inputs and runtime
dependency metadata. The image does not include datasets, `.env` files, local
environments, test output or route records.

## Start

Install Docker Engine/Desktop with Compose v2. In WSL, enable Docker Desktop's
integration for the selected distribution. Run these commands from the repository
root as your regular user:

```bash
python scripts/run_docker.py \
  --env-file /absolute/path/to/private.env \
  --dataset-dir /absolute/path/to/dataset
```

Open `http://127.0.0.1:8080`. The default planning profile selects
`M20_JezeroCrater_CTXDEM_20m.tif` relative to the supplied dataset directory.
Use `--planning-profile /path/to/profile.json` for another supported profile;
its `dem` must be relative to the dataset root and resolve inside it.

The private runtime file uses the same assignment syntax as native startup.
Supply `OPENAI_API_KEY` for the default agentic mode. Model settings and optional
trusted evidence bindings can be configured there. An evidence profile must use
container-visible paths such as `/datasets/...`; a single verified snapshot
under the DEM's sibling `evidence/` directory is also discoverable automatically.
No credential value is passed as a command-line argument or Compose build input.

For offline terrain planning, add `--mode deterministic`. For another HTTP port,
add `--port 8081`. Use `--dry-run` to validate mount inputs without starting Docker,
and `--no-build` to reuse an existing image.

## Configuration and persistence

The launcher passes paths to Compose through its process environment. It does
not source, print or ask Compose to interpolate the private runtime file.
The backend reads that file through a read-only mount.

Native startup precedence is process environment over the selected runtime file.
In Compose, the launcher-selected A0 mode and fixed container paths override
matching values in the file: routing is computed, datasets are `/datasets`, the
profile is `/run/a-stellar/planning.json`, routes/chat/evidence are under
`/var/lib/a-stellar`, and the production UI is `/app/frontend/dist`.
Other backend settings, including the model and optional evidence profile, come
from the runtime file. Restart the container to reload changed configuration.

Dataset, profile and runtime-file mounts are read-only. A project-scoped named
volume stores routes, their validation/provenance artifacts, chat messages and
application counters. Ordinary `down`, rebuild and restart operations retain it.
Removing the volume deletes those records; make a backup before doing so.

On POSIX hosts the launcher uses the host user's UID/GID so private `0600` files
remain readable without changing their permissions. The image also has a
non-root default UID of 10001 for direct use. The state-volume root is sticky and
writable; application subdirectories belong to the runtime user. Keep the same
UID when reusing a state volume. The launcher rejects root execution.
The service binds to localhost and drops all Linux capabilities.

Use the same input arguments with `--action status`, `logs`, `restart` or `down`:

```bash
python scripts/run_docker.py --env-file /path/to/private.env \
  --dataset-dir /path/to/dataset --action logs
```

Stop/status/log operations remain available if an input file was removed.
Changing a bind-mounted file by atomic replacement can require container
recreation (`--action up`) rather than a process restart.

## Verification

`GET /api/v1/health` is process liveness. `GET /api/v1/ready` returns HTTP 200 only
when the local planning configuration is usable and agentic mode has a key;
otherwise it returns HTTP 503 with boolean checks. Neither endpoint makes a
provider request, verifies provider access, or certifies NASA map registration.
The image health check uses readiness.

The automated backend checks cover production assets, API routing/error/cache
boundaries, missing DEM/profile, missing credentials, external-file precedence,
portable source paths and secret-free launcher arguments. The regional and
browser verifiers exercise the production UI/API, durable records and real DEM.
See [regional verification](regional-verification.md).

Actual image build, bind permissions, named-volume initialization and restart
acceptance still require an available Docker engine. They have not been run in
the current WSL distribution because Docker Desktop integration is disabled.

The packaging follows Docker's [multi-stage build](https://docs.docker.com/build/building/multi-stage/)
and [Compose service/mount](https://docs.docker.com/reference/compose-file/services/) documentation.
