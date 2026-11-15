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
        if stored.result != response or expected_hash and payload_hash(stored.metadata.request.model_dump(mode='json',exclude_none=True)) != expected_hash:
            raise ValueError('Plan response and request disagree')
        return response

    def plan(self, request, request_id, retry_attempt=None):
        payload=request.model_dump(mode='json',exclude_none=True)
        # The short-lived v1 contract defaulted an omitted profile to balanced.
        # Alias only a proven completed v1 response; never reinterpret new inputs
        # or execute a legacy failed/unknown request under different policy.
        if request.mission_profile is None and request.resolution_profile is None:
            cached=self.attempts.cached(self.attempts.paths(request_id)[1],self.parse,None)
            if cached is not None:
                old=self.agent.planning.store.get(cached.route_id).metadata
                if old.assessment and old.assessment.mission_profile and old.assessment.mission_profile.version.endswith('-v1'):
                    candidate={**payload,'mission_profile':'balanced'}
                    if candidate==old.request.model_dump(mode='json',exclude_none=True): payload=candidate
        return self.attempts.execute(request_id,payload,
            lambda: self.agent.plan(request,request_id=request_id),self.parse,retry_attempt=retry_attempt)

    def status(self, request_id):
        return self.attempts.status(request_id,self.parse)
