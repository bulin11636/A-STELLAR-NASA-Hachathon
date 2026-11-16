# Documentation

The [project README](../README.md) introduces the mission workflow, features,
agent architecture and extension directions. These guides describe how to run,
understand and verify the current implementation.

| Guide | Use it for |
| --- | --- |
| [Development setup](setup.md) | Python/Vite environments, native startup and local checks |
| [Docker runtime](docker.md) | Build/run commands, external configuration, datasets and persistent state |
| [Datasets](datasets.md) | Required terrain data, optional sources, acquisition and provenance |
| [Architecture](architecture.md) | Production data flow, route computation, assessment and persistence |
| [Specialist agents](agents.md) | Tool selection, typed worker results, scientific limits and extensions |
| [API](api.md) | Endpoints, request shapes, stored metadata and retry/recovery semantics |
| [Verification](verification.md) | Offline tests, browser workflows, real data and Docker acceptance |
| [Map coordinates and registration](map-registration.md) | Coordinate conversion, demo overlays and independent feature controls |
| [Provider troubleshooting](provider-troubleshooting.md) | Application/provider limits, proposal errors and diagnostics |
| [SI disclosure metadata](si-disclosure.json) | Confirmed SI tool use, scientific-data distinctions and demo narration credit |

Runtime schemas are available from FastAPI at `/docs` and `/openapi.json`.
Generated frontend contracts live in `frontend/src/types/`. Source manifests and
scientific verification records remain in `data/samples/`; test fixtures remain
in `data/fixtures/`. They are separate from presentation and development history.
