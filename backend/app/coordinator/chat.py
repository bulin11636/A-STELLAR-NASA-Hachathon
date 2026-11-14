"""Route-scoped durable chat. Idempotency claims prevent duplicate paid calls."""
from datetime import datetime, timezone
import json
from app.api.errors import ApiProblem
from app.contracts.chat import ChatHistory, ChatResponse
from app.coordinator.attempts import AttemptStore, payload_hash


class RouteChat:
    def __init__(self, agent):
        self.agent=agent
        self.store=agent.planning.store

    def _attempts(self, route_id):
        return AttemptStore(self.store.root/'requests'/'chat'/route_id,'chat')

    def _parse(self, route_id, request_id):
        def parse(data, expected_hash):
            response = ChatResponse.model_validate(data)
            if response.route_id != route_id or response.message_id != request_id:
                raise ValueError('Chat identity mismatch')
            if expected_hash and payload_hash({'message':response.user_message}) != expected_hash:
                raise ValueError('Chat input mismatch')
            if (response.result is None) != (response.metadata is None):
                raise ValueError('Incomplete chat revision')
            if response.result:
                stored = self.store.get(response.result.route_id)
                if stored.result != response.result or stored.metadata != response.metadata or stored.metadata.parent_route_id != route_id:
                    raise ValueError('Chat revision mismatch')
            return response
        return parse

    def status(self, route_id, request_id):
        self.store.get(route_id)
        directory = self.store.root/'chat'/route_id
        return self._attempts(route_id).status(request_id,self._parse(route_id,request_id),
            response_path=directory/(request_id+'.json'),legacy_claim=directory/(request_id+'.claim'))

    def send(self, route_id, request, *, retry_attempt=None):
        stored = self.store.get(route_id)
        directory = self.store.root/'chat'/route_id
        attempts = self._attempts(route_id)
        if not attempts.paths(request.request_id)[0].exists():
            previous = attempts.cached(directory/(request.request_id+'.json'),self._parse(route_id,request.request_id),None)
            if previous and previous.user_message != request.message:
                raise ApiProblem(409,'CHAT_REQUEST_CONFLICT','This message ID was already used for different text.')
        def respond():
            recent=[{'user':item.user_message[:180],'assistant':item.assistant_message[:120]}
                    for item in self.history(route_id).messages[-2:]]
            answer,revised,usage=self.agent.respond(stored,request.message,recent_dialogue=recent)
            return ChatResponse(message_id=request.request_id,route_id=route_id,created_at=datetime.now(timezone.utc),
                user_message=request.message,assistant_message=answer,result=revised.result if revised else None,
                metadata=revised.metadata if revised else None,usage=usage)
        return attempts.execute(request.request_id,{'message':request.message},respond,
            self._parse(route_id,request.request_id),retry_attempt=retry_attempt,
            response_path=directory/(request.request_id+'.json'),legacy_claim=directory/(request.request_id+'.claim'))

    def history(self, route_id):
        messages=[]; visited=set()
        # Bound ancestry to avoid unbounded route/grid loading on a long session.
        while route_id and route_id not in visited and len(visited)<12:
            visited.add(route_id)
            stored=self.store.get(route_id)
            directory=self.store.root/'chat'/route_id
            for path in sorted(directory.glob('*.json'))[-40:]:
                if path.stat().st_size>2_000_000:
                    raise ApiProblem(500,'CHAT_RECORD_INVALID','A stored chat record exceeds its size limit.')
                try:
                    messages.append(ChatResponse.model_validate_json(path.read_text()))
                except Exception:
                    raise ApiProblem(500,'CHAT_RECORD_INVALID','A stored chat record failed validation.') from None
            route_id=stored.metadata.parent_route_id
        messages.sort(key=lambda m:m.created_at)
        return ChatHistory(messages=messages[-40:])
