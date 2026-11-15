"""Route-scoped durable chat. Idempotency claims prevent duplicate paid calls."""
from datetime import datetime, timezone
import json
from app.api.errors import ApiProblem
from app.contracts.chat import ChatHistory, ChatRequest, ChatResponse
from app.coordinator.attempts import AttemptStore, payload_hash, save_json


class RouteChat:
    def __init__(self, agent):
        self.agent=agent
        self.store=agent.planning.store

    def _attempts(self, route_id):
        return AttemptStore(self.store.root/'requests'/'chat'/route_id,'chat')

    @staticmethod
    def _payload(request):
        return request.model_dump(mode='json', exclude={'request_id'}, exclude_none=True)

    def _input_path(self, route_id, request_id):
        attempts = self._attempts(route_id)
        attempts.paths(request_id)  # validate before constructing a private path
        return attempts.root / (request_id + '.input')

    def _saved_payload(self, route_id, request_id, message):
        path = self._input_path(route_id, request_id)
        if not path.exists():
            return {'message': message}  # old successful records remain readable
        if path.is_symlink() or path.stat().st_size > 32768:
            raise ValueError('Invalid stored chat input')
        request = ChatRequest.model_validate_json(path.read_text())
        if request.request_id != request_id or request.message != message:
            raise ValueError('Chat input identity mismatch')
        return self._payload(request)

    def _parse(self, route_id, request_id):
        def parse(data, expected_hash):
            response = ChatResponse.model_validate(data)
            if response.route_id != route_id or response.message_id != request_id:
                raise ValueError('Chat identity mismatch')
            original_payload=self._saved_payload(route_id, request_id, response.user_message)
            if expected_hash and payload_hash(original_payload) != expected_hash:
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
            if previous and payload_hash(self._saved_payload(route_id, request.request_id, previous.user_message)) != payload_hash(self._payload(request)):
                raise ApiProblem(409,'CHAT_REQUEST_CONFLICT','This message ID was already used with different input.')
        def respond():
            save_json(self._input_path(route_id, request.request_id), request.model_dump(mode='json', exclude_none=True))
            recent=[{'user':item.user_message[:180],'assistant':item.assistant_message[:120]}
                    for item in self.history(route_id).messages[-2:]]
            answer,revised,usage=self.agent.respond(stored,request.message,recent_dialogue=recent, advanced_context=request.advanced_context)
            return ChatResponse(message_id=request.request_id,route_id=route_id,created_at=datetime.now(timezone.utc),
                user_message=request.message,assistant_message=answer,result=revised.result if revised else None,
                metadata=revised.metadata if revised else None,usage=usage)
        return attempts.execute(request.request_id,self._payload(request),respond,
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
