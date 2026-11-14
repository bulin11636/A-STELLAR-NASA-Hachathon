"""Run `python -m app.coordinator.demo` from backend/ to inspect B0 outputs."""
import asyncio

from app.contracts.workers import WorkerContext
from app.coordinator.dispatcher import AgentDispatcher
from app.coordinator.mission import MissionCoordinator, default_registry


async def main():
    coordinator = MissionCoordinator(AgentDispatcher(default_registry()))
    report = await coordinator.run_workers(WorkerContext(
        mission_id="b0-example", region_id="jezero", roi_id="jezero-roi-pending",
        dataset_version="unconfigured",
    ))
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
