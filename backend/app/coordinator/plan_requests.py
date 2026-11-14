"""Optional computed-route idempotency without changing the planning body."""
from app.contracts.api import PlanRouteResponse
from app.coordinator.attempts import AttemptStore, payload_hash


class PlanRequests:
    def __init__(self, agent):
        self.agent = agent
        self.attempts = AttemptStore(agent.planning.store.root/'requests'/'plans','plan')

    def parse(self, data, expected_hash):
        response = PlanRouteResponse.model_validate(data)
        stored = self.agent.planning.store.get(response.route_id)
        if stored.result != response or expected_hash and payload_hash(stored.metadata.request.model_dump(mode='json')) != expected_hash:
            raise ValueError('Plan response and request disagree')
        return response

    def plan(self, request, request_id, retry_attempt=None):
        return self.attempts.execute(request_id,request.model_dump(mode='json'),
            lambda: self.agent.plan(request),self.parse,retry_attempt=retry_attempt)

    def status(self, request_id):
        return self.attempts.status(request_id,self.parse)
