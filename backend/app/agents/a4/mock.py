from app.contracts.workers import ScienceResult, WorkerContext


class MockScienceWorker:
    agent_id = "A4"

    async def run(self, context: WorkerContext) -> ScienceResult:
        return ScienceResult(
            status="unavailable", data_kind="mock",
            warnings=["MOCK A4: No source-verified Jezero science POIs or scoring rubric are configured. Empty POIs mean unavailable data, not no science value."],
        )
