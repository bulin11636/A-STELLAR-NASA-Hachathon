# Specialist agents

The web application combines a mission coordinator with explicitly registered
Python scientific workers. These workers are not separate deployed microservices
and do not each make their own language-model calls. The frontend presents short
domain labels; full public role names and stable internal IDs remain available
in the contracts and traces.

## Responsibilities

| Internal ID | Public role | Current contribution |
| --- | --- | --- |
| A0 | Mission Orchestration and Route Planning Coordinator | Interprets intent, selects optional tools and explains host-computed routes |
| A1 | Surface Traversability and Terrain Hazard Agent | Mandatory DEM coverage, terrain masks, slope-based costs and native checks |
| A2 | Thermal Environment and Exposure Context Agent | Configured prototype thermal context; calibrated temperature limits remain unavailable |
| A3 | Radiation Exposure and Mission Dose Assessment Agent | Explicit configured duration/rate scenarios; not a spatial hazard layer |
| A4 | Geological Context and Science Opportunity Agent | Source-backed science places and optional geology associations |
| A5 | Surface Obstacle Context | Merged into the terrain specialist; retained as an explicit assessment entry |
| A6 | Rover Traverse and Observation Evidence Agent | Historical rover places, traverse context and bounded observation references |

The terrain planner derives its mandatory inputs directly from the approved DEM.
Legacy standalone terrain/thermal previews are not automatically substituted for
that validated planning grid. Contextual science and rover outputs do not
implicitly become calibrated terrain-risk costs.

## Selection and execution

`RouteAgent` advertises a capability catalog. Terrain analysis is mandatory;
thermal, radiation, geology/science and rover context are optional unless the
selected mission profile, explicit required analyses or a scenario budget makes
the relevant analysis required. Required analyses
cannot be skipped by a model decision.

With configured optional workers, agentic actions can make a selection request
and a final proposal request. The host validates both. With no configured optional
worker, selection can be omitted. Deterministic mode uses Python selection and
makes no model requests. Advanced Plan and Ask A0 contains a plan action followed
by a separate chat action after the base record is stored and verified.

The trace distinguishes configuration, selection, execution, result quality,
application, reason and limitations. A ready file is not automatically a selected
analysis; a selected analysis is not automatically successful or applicable.
Missing, stale and incompatible inputs remain explicit. Numerical workers do not
invoke additional models.

## Trusted data bindings

`A_STELLAR_EVIDENCE_PROFILE` selects a trusted local JSON profile using the
`RuntimeProfile` contract in `backend/app/coordinator/profiles.py`. Its fields are:

- `scope`: mission, region, ROI and dataset-version context.
- `radiation_scenario`: a documented dose-equivalent scenario JSON.
- `evidence_manifest`: a verified source snapshot manifest.
- `geology_report` and `observation_report`: optional reports requiring the manifest.
- `a1_config` and `a2_config`: explicit standalone-adapter configurations.

Relative paths resolve from the profile/config file, not the shell directory.
Scopes and provenance must agree; the host does not silently rebind an old scenario
to a new dataset version. Docker profiles need container-visible input paths and
writable output paths. A single compatible verified snapshot can also be discovered
under the DEM's sibling `evidence/` directory; ambiguous candidates are not guessed.

Inspect `/api/v1/a0/capabilities` and the result's `specialist_trace` to see what
is actually configured and used. Do not infer worker activation from a visible
map layer: presentation and scientific analysis have separate availability rules.

## Scientific boundaries

- Thermal visual mosaics are stretched/blended image products, not calibrated
  thermometry, thermal inertia or validated EVA thermal constraints.
- Radiation uses an explicitly configured historical constant-rate scenario and
  its uncertainty description. It does not model solar events, suit shielding,
  organ dose or a calibrated future Jezero environment.
- Regional geology has source-scale and offset limitations. Its associations and
  science points are context, not an automatic target-value ranking.
- Rover history documents past operations. It does not validate astronaut
  traversability or provide complete contemporary imagery.
- Surface-obstacle context remains merged into terrain assessment; it is not a
  separately running worker that can be treated as missing by renumbering agents.

Required missing analyses or failed scenarios keep mission limitations visible.
Partial risk can summarize assessed weighted factors, while complete risk and
mission gates retain their own requirements. See [architecture](architecture.md).

## Walking and exposure assumptions

Walking is the only supported mission mode. An explicit speed permits an estimate:

```text
travel minutes = projected route distance / speed / 60
total minutes = travel minutes + dwell per intermediate visit * visit count
```

This is an engineering estimate, not a recommended Mars walking speed. Start/goal
dwell, rest, slope-dependent speed, suit/load and physiology are excluded.
Without speed, time remains unknown. A supplied exposure duration overrides the
walking estimate for a configured radiation scenario; without either, dose stays
unknown. A radiation budget is a scenario input, not a default NASA/medical limit.

Chat revisions preserve typed mission assumptions and recompute their applicable
results. Changing speed, scenario budget or versioned mission profile requires a
new typed plan; free text cannot override those fields. Unknown place names require
clarification or explicit coordinates rather than invented locations.

## Implementing an extension

1. Define bounded inputs and typed outputs with scope, units, provenance, evidence
   references, uncertainty and an honest unavailable state.
2. Implement an async authored worker compatible with `app.agents.base.Worker`.
3. Register it through `WorkerRegistry`; update the closed IDs/schemas if adding
   a genuinely new specialist, rather than dynamically importing model-selected code.
4. Bind trusted sources, enforce execution limits and test failure isolation.
5. Classify the result as context, a mission scenario, or a separately validated
   routing constraint. A map preview alone is not a routing cost.
6. Expose a spatial layer only when its artifact and display extent exist.

The optional LangGraph experiment uses the packaged coordinator `SKILL.md` and
separate CLI/sample inputs. It is not a prerequisite for the public web route
pipeline. Keep its runtime instruction asset when cleaning project documentation.
