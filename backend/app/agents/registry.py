import inspect

from app.agents.base import Worker
from app.contracts.workers import AGENT_IDS, AgentId


class WorkerRegistry:
    """Explicit authored workers only: no dynamic imports, eval or LLM code."""

    def __init__(self):
        self._workers: dict[AgentId, Worker] = {}

    def register(self, worker: Worker) -> None:
        if worker.agent_id not in AGENT_IDS:
            raise ValueError("Worker is not in the agent allowlist.")
        if worker.agent_id in self._workers:
            raise ValueError("Worker is already registered.")
        if not inspect.iscoroutinefunction(worker.run):
            raise TypeError("Worker.run must be async for bounded dispatch.")
        self._workers[worker.agent_id] = worker

    def get(self, agent_id: AgentId) -> Worker | None:
        if agent_id not in AGENT_IDS:
            raise ValueError("Unknown agent ID.")
        return self._workers.get(agent_id)

    @property
    def registered_ids(self) -> tuple[AgentId, ...]:
        return tuple(agent for agent in AGENT_IDS if agent in self._workers)
