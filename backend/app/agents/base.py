from typing import Protocol

from app.contracts.workers import AgentId, WorkerContext, WorkerResult


class Worker(Protocol):
    agent_id: AgentId

    async def run(self, context: WorkerContext) -> WorkerResult:
        """Cooperative async work; offload blocking I/O/compute explicitly."""
        ...
