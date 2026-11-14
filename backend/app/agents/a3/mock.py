from app.contracts.workers import RadiationResult, WorkerContext


class MockRadiationWorker:
    agent_id = "A3"

    async def run(self, context: WorkerContext) -> RadiationResult:
        return RadiationResult(
            status="unavailable", data_kind="mock",
            duration_min=context.parameters.eva_duration_min,
            budget_usv=context.parameters.radiation_budget_usv,
            warnings=["MOCK A3: No validated ionizing-dose model is configured. Dose and budget compliance are unknown; no spatial radiation map is supplied."],
        )
