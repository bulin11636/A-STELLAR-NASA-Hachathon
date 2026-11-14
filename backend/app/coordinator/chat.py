"""Route-scoped durable chat. Idempotency claims prevent duplicate paid calls."""
from datetime import datetime, timezone
import json
import os
from app.api.errors import ApiProblem
from app.contracts.chat import ChatHistory, ChatResponse


class RouteChat:
    def __init__(self, agent):
        self.agent=agent
        self.store=agent.planning.store

    def send(self, route_id, request):
        stored=self.store.get(route_id)
        directory=self.store.root/'chat'/route_id
        directory.mkdir(parents=True,exist_ok=True)
        path=directory/(request.request_id+'.json')
        claim=directory/(request.request_id+'.claim')
        if path.is_file():
            previous=ChatResponse.model_validate_json(path.read_text())
            if previous.user_message!=request.message:
                raise ApiProblem(409,'CHAT_REQUEST_CONFLICT','The message ID was already used for different text.')
            return previous
        try:
            with claim.open('x') as stream:
                stream.write('claimed')
        except FileExistsError:
            raise ApiProblem(409,'CHAT_MESSAGE_IN_PROGRESS','This message was already submitted. Reload its history; do not automatically submit another paid request.')
        # Claims intentionally survive failure/restart: unknown API usage is not
        # retried by replaying the same message ID.
        recent=[{'user':item.user_message[:180],'assistant':item.assistant_message[:120]}
                for item in self.history(route_id).messages[-2:]]
        answer,revised,usage=self.agent.respond(stored,request.message,recent_dialogue=recent)
        response=ChatResponse(message_id=request.request_id,route_id=route_id,created_at=datetime.now(timezone.utc),
            user_message=request.message,assistant_message=answer,result=revised.result if revised else None,
            metadata=revised.metadata if revised else None,usage=usage)
        temporary=path.with_suffix('.tmp')
        with temporary.open('x',encoding='utf-8') as stream:
            stream.write(response.model_dump_json(indent=2)); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary,path)
        return response

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
