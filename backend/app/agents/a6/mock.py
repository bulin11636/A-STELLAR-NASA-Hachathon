from app.contracts.workers import RoverTraverseResult, WorkerContext


class MockRoverTraverseWorker:
    agent_id = "A6"

    async def run(self, context: WorkerContext) -> RoverTraverseResult:
        return RoverTraverseResult(
            status="unavailable", data_kind="mock",
            warnings=["MOCK A6: No verified rover track is loaded. Proximity is unknown. Historical rover traversal is not evidence of astronaut safety."],
        )
