import asyncio

import pytest
from pydantic import ValidationError

from app.agents.registry import WorkerRegistry
from app.contracts.workers import (
    MissionParameters, RadiationResult, SciencePOI, ScienceResult, SurfaceResult,
    WorkerContext,
)
from app.coordinator.dispatcher import AgentDispatcher
from app.coordinator.mission import MissionCoordinator, default_registry


def context():
    return WorkerContext(mission_id="test-mission", region_id="jezero", roi_id="synthetic-only", dataset_version="test-v1")


def test_sheng_mocks_and_absent_sam_workers_are_honest():
    registry = default_registry()
    assert registry.registered_ids == ("A3", "A4", "A6")
    report = asyncio.run(MissionCoordinator(AgentDispatcher(registry)).run_workers(context()))
    assert [result.agent_id for result in report.results] == ["A1", "A2", "A3", "A4", "A6"]
    assert all(result.status == "unavailable" and result.warnings for result in report.results)
    assert all(not result.dataset_ids and not result.artifacts for result in report.results)
    radiation, science, rover = report.results[2:]
    assert radiation.data_kind == science.data_kind == rover.data_kind == "mock"
    assert radiation.dose_estimate_usv is None and radiation.constraint_status == "unknown"
    assert science.pois == []
    assert rover.nearest_track_distance_m is None and rover.stops == []
    assert "dose_estimate_usv" in report.model_dump()["results"][2]


def test_mission_inputs_are_validated_before_dispatch():
    with pytest.raises(ValidationError):
        WorkerContext(mission_id="", region_id="jezero", roi_id="x", dataset_version="v1")
    for invalid in (-1, float("nan"), "20", True):
        with pytest.raises(ValidationError):
            MissionParameters(eva_duration_min=invalid)
    assert MissionParameters(eva_duration_min=0).eva_duration_min == 0


def test_registry_rejects_unknown_duplicate_and_blocking_workers():
    class Unknown:
        agent_id = "A0"
        async def run(self, ctx):
            pass

    class Blocking:
        agent_id = "A1"
        def run(self, ctx):
            pass

    registry = default_registry()
    with pytest.raises(ValueError):
        registry.register(Unknown())
    with pytest.raises(ValueError):
        registry.register(registry.get("A3"))
    with pytest.raises(TypeError):
        registry.register(Blocking())
    with pytest.raises(ValueError):
        registry.get("__import__")


def test_partial_success_failure_timeout_and_missing_results_are_isolated():
    class Partial:
        agent_id = "A4"
        async def run(self, ctx):
            return ScienceResult(status="partial", data_kind="observed", warnings=["No complete ROI coverage."])

    class Broken:
        agent_id = "A3"
        async def run(self, ctx):
            raise RuntimeError("private dataset token")

    class Slow:
        agent_id = "A6"
        async def run(self, ctx):
            await asyncio.sleep(1)

    registry = WorkerRegistry()
    for worker in (Partial(), Broken(), Slow()):
        registry.register(worker)
    report = asyncio.run(AgentDispatcher(registry, timeout_seconds=.01).run(context(), ("A4", "A3", "A6", "A1")))
    assert [result.status for result in report.results] == ["partial", "failed", "failed", "unavailable"]
    assert "timed out" in report.results[2].warnings[0]
    assert "private dataset token" not in report.model_dump_json()
    assert len(report.trace) == 4 and all(item.elapsed_ms >= 0 for item in report.trace)


def test_wrong_return_schema_and_mutated_results_are_not_accepted():
    class Wrong:
        agent_id = "A4"
        async def run(self, ctx):
            return SurfaceResult(status="unavailable", data_kind="unavailable", warnings=["Unavailable"])

    registry = WorkerRegistry()
    registry.register(Wrong())
    report = asyncio.run(AgentDispatcher(registry).run(context(), ("A4",)))
    assert report.results[0].status == "failed"


def test_dispatch_policy_rejects_invalid_actions_and_timeouts():
    dispatcher = AgentDispatcher(default_registry())
    for actions in (("A3", "A3"), ("eval",)):
        with pytest.raises(ValueError):
            asyncio.run(dispatcher.run(context(), actions))
    for timeout in (0, -1, float("inf"), float("nan"), 31):
        with pytest.raises(ValueError):
            AgentDispatcher(default_registry(), timeout_seconds=timeout)


def test_output_provenance_and_unknown_radiation_invariants():
    for kwargs in (
        {"status": "ready", "data_kind": "mock", "warnings": ["Mock"]},
        {"status": "unavailable", "data_kind": "mock", "warnings": []},
        {"status": "ready", "data_kind": "observed", "dataset_ids": []},
        {"status": "partial", "data_kind": "observed", "artifacts": {"x": "file.tif"}, "warnings": ["Incomplete"]},
    ):
        with pytest.raises(ValidationError):
            ScienceResult(**kwargs)
    with pytest.raises(ValidationError):
        RadiationResult(status="unavailable", data_kind="unavailable", warnings=["No model"], dose_estimate_usv=0)
    with pytest.raises(ValidationError):
        RadiationResult(status="partial", data_kind="scenario", warnings=["Scenario"], dose_estimate_usv=1)
    with pytest.raises(ValidationError):
        SciencePOI(id="poi", longitude=77, latitude=18, category="sample", rationale="Example", priority=.5)
