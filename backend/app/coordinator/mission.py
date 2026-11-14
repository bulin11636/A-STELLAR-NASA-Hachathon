from uuid import uuid4

from app.agents.a3 import MockRadiationWorker
from app.agents.registry import WorkerRegistry
from app.agents.a6 import MockRoverTraverseWorker
from app.agents.a4 import MockScienceWorker
from app.contracts.api import PlanRouteRequest, PlanRouteResponse, RouteMetrics
from app.contracts.workers import AGENT_IDS, WorkerContext
from app.coordinator.dispatcher import AgentDispatcher, DispatchReport


def default_registry() -> WorkerRegistry:
    registry = WorkerRegistry()
    for worker in (MockRadiationWorker(), MockScienceWorker(), MockRoverTraverseWorker()):
        registry.register(worker)
    # A1/A2 prototype adapters require explicit source/context configuration.
    # Keep the public endpoint on the existing mock registry.
    return registry


class MissionCoordinator:
    def __init__(self, dispatcher: AgentDispatcher):
        self.dispatcher = dispatcher

    async def run_workers(self, context: WorkerContext) -> DispatchReport:
        return await self.dispatcher.run(context, AGENT_IDS)

    async def plan_mock_route(self, request: PlanRouteRequest) -> PlanRouteResponse:
        report = await self.run_workers(WorkerContext(
            mission_id=f"demo-{uuid4().hex}", region_id="jezero",
            roi_id="jezero-roi-pending", dataset_version="unconfigured",
        ))
        warnings = [
            "Demonstration route only. No terrain or astronaut safety evaluation performed.",
            "Coordinate convention not validated against a shared Jezero DEM ROI. Mock integration only.",
        ]
        for result in report.results:
            warnings.extend(result.warnings)
        # Registry readiness never promotes this path to computed. A validated
        # canonical metric grid, planner and route validator are later stages.
        return PlanRouteResponse(
            route_id=f"demo-jezero-{uuid4().hex}", mode=request.mode, source="mock",
            route=[request.start, *request.waypoints, request.goal], metrics=RouteMetrics(), warnings=warnings,
        )
