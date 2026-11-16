# Releases and container packages

The **Release** GitHub Actions workflow publishes two related outputs:

- A GitHub Release with a deployment ZIP, `release.json` and `SHA256SUMS`.
- A versioned GHCR image at `ghcr.io/bulin11636/a-stellar-nasa-hachathon:0.1.0`.

The first version is `v0.1.0`. Images target `linux/amd64`: Windows/Intel and
WSL/AMD x86-64 PCs use the same Linux image through Docker Desktop/Engine.
The Docker image contains the production frontend and backend. Scientific data,
private runtime configuration and persistent application state are external.

## Publish a version

Publishing runs on GitHub's runner, so the publisher's CPU and local Python
environment do not determine the image. From an up-to-date, clean `main`:

```bash
git switch main
git pull --ff-only origin main
git tag -a v0.1.0 -m "A-STELLAR v0.1.0"
git push origin v0.1.0
```

The tag must point to a commit already in `main`, and its base version must match
both `frontend/package.json` and `backend/pyproject.toml`. For a later release,
update both versions and the frontend lockfile first. Supported prereleases use
`-alpha.N`, `-beta.N` or `-rc.N`, for example `v0.1.0-rc.1`.

The workflow validates the tag, runs the reusable backend/frontend/Docker CI,
builds the release image and performs isolated Docker acceptance on that exact
image. It pushes the tested image, packages a deployment bundle pinned to the
registry digest, then creates the GitHub Release. Application model calls are
disabled during these checks.

The workflow uses GitHub's built-in `GITHUB_TOKEN` with job-scoped
`contents: write` and `packages: write`. It needs no OpenAI credential or Docker
Hub account. Repository/organization policy must permit Actions package writes.
An existing package may need this repository added under its Actions access.

Follow **Actions → Release** or use:

```bash
gh run list --workflow release.yml --branch v0.1.0
gh release view v0.1.0
```

For a failed run, correct the reported permission/infrastructure issue and rerun
the failed jobs. Manual dispatch must select the existing version tag, for
example `gh workflow run release.yml --ref v0.1.0`. Published version tags should
remain fixed; use a new version for application changes. Images receive exact
version tags; no floating `latest` alias is maintained.

## Download and run

Download and extract `a-stellar-v0.1.0-deploy.zip` from the release. This is a
small deployment kit with the launcher, acquisition utility, public example
configuration, source manifest and a Compose file pinned to the release image.
It can run independently of a source checkout. GitHub also supplies source
archives for developers who want the full project.

Install Docker with Compose v2 and a local Python 3.10+ interpreter. Copy
`.env.example` to `.env`, configure it, and supply the Jezero DEM. The extracted
README includes the exact image digest and commands. For a source checkout:

```bash
docker pull ghcr.io/bulin11636/a-stellar-nasa-hachathon:0.1.0
export A_STELLAR_IMAGE=ghcr.io/bulin11636/a-stellar-nasa-hachathon:0.1.0
python scripts/run_docker.py --env-file .env --dataset-dir /absolute/path/to/dataset --no-build --mode agentic
```

PowerShell in a source checkout:

```powershell
docker pull ghcr.io/bulin11636/a-stellar-nasa-hachathon:0.1.0
$env:A_STELLAR_IMAGE = "ghcr.io/bulin11636/a-stellar-nasa-hachathon:0.1.0"
python scripts/run_docker.py --env-file .env --dataset-dir C:\data\jezero --no-build --mode agentic
```

Open http://localhost:8080. Use `--mode deterministic` with an empty runtime file
for acceptance without model generation. The extracted deployment ZIP already
selects its digest-pinned image, so it does not need `A_STELLAR_IMAGE`.

Verify the downloaded assets using `sha256sum -c SHA256SUMS` in Bash/WSL, or
`Get-FileHash -Algorithm SHA256 .\a-stellar-v0.1.0-deploy.zip` in PowerShell and
compare the result with `SHA256SUMS`. `release.json` records the exact commit,
image tag, image digest and platform.

## Private access and public distribution

Repository and package visibility are separate settings. Initially retain the
repository's access controls. For a private package, the tester needs package
read permission and a GitHub classic personal access token with `read:packages`.
Run `docker login ghcr.io` and enter the GitHub username and token at its prompt.
Keep registry credentials separate from the application's model API credential.

When the owner is ready for public distribution:

1. Change the repository visibility under **Repository Settings → General →
   Danger Zone → Change repository visibility**.
2. Open the owner's **Packages → a-stellar-nasa-hachathon → Package settings**
   and change the package visibility to **Public**.
3. Test the release link in a signed-out browser and pull the image using a
   Docker client without registry credentials.

A public GHCR image supports anonymous pulls. Publishing an image does not
automatically make the package public. GitHub documents
[GHCR authentication and access](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

## Tester acceptance

Use a separate `--project-name release-acceptance` and an unused port when
another deployment is running. Confirm the UI loads, create an ordered route,
inspect the briefing, and ask a route question. Restart the deployment and
confirm the route and chat remain available. Use the same dataset, runtime file
and project arguments with `--action down` to stop this acceptance instance.
The named volume retains its records.

Build and deployment details are in [Docker runtime](docker.md); scientific
inputs are in [datasets](datasets.md). The release workflow builds on GitHub's
[container publishing](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images)
and [reusable workflow](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)
facilities.
