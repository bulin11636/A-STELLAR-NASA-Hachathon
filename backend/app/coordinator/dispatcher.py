import asyncio
import logging
import math
from time import monotonic

from pydantic import Field, SerializeAsAny

from app.agents.registry import WorkerRegistry
from app.contracts.api import ContractModel, NonNegative
from app.contracts.workers import (
    AGENT_IDS, RESULT_TYPES, AgentId, WorkerContext, WorkerResult, WorkerStatus,
)

logger = logging.getLogger(__name__)


class WorkerTrace(ContractModel):
    agent_id: AgentId
    status: WorkerStatus
    elapsed_ms: NonNegative


class DispatchReport(ContractModel):
    results: list[SerializeAsAny[WorkerResult]] = Field(default_factory=list)
    trace: list[WorkerTrace] = Field(default_factory=list)


class AgentDispatcher:
    def __init__(self, registry: WorkerRegistry, timeout_seconds: float = 2.0):
        if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 30:
            raise ValueError("Worker timeout must be finite and in (0, 30] seconds.")
        self.registry = registry
        self.timeout_seconds = timeout_seconds

    async def run(self, context: WorkerContext, agents: tuple[AgentId, ...]) -> DispatchReport:
        if len(agents) > len(AGENT_IDS) or len(set(agents)) != len(agents) or any(agent not in AGENT_IDS for agent in agents):
            raise ValueError("Select each allowlisted worker at most once.")

        async def call(agent_id: AgentId):
            started = monotonic()
            worker = self.registry.get(agent_id)
            result_type = RESULT_TYPES[agent_id]
            if worker is None:
                result = result_type(
                    status="unavailable", data_kind="unavailable",
                    warnings=[f"{agent_id} is not registered; its inputs and constraints are unknown."],
                )
            else:
                try:
                    output = await asyncio.wait_for(worker.run(context), timeout=self.timeout_seconds)
                    if not isinstance(output, result_type) or output.agent_id != agent_id:
                        raise TypeError("Worker returned an incompatible specialized schema.")
                    # Revalidate copied/mutated Pydantic values before fusion.
                    result = result_type.model_validate(output.model_dump())
                except asyncio.TimeoutError:
                    result = result_type(
                        status="failed", data_kind="unavailable",
                        warnings=[f"{agent_id} timed out; no measurements or constraints are inferred."],
                    )
                except Exception:
                    logger.exception("Worker %s failed", agent_id)
                    result = result_type(
                        status="failed", data_kind="unavailable",
                        warnings=[f"{agent_id} failed; no measurements or constraints are inferred."],
                    )
            return result, WorkerTrace(agent_id=agent_id, status=result.status, elapsed_ms=(monotonic() - started) * 1000)

        calls = await asyncio.gather(*(call(agent) for agent in agents))
        return DispatchReport(results=[item[0] for item in calls], trace=[item[1] for item in calls])
