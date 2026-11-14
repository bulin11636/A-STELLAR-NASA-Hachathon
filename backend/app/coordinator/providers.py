"""Structured decision providers. Live OpenAI access is explicit and optional."""
import json
import os
from typing import Protocol

from app.coordinator.contracts import Proposal
from app.coordinator.tools import DESCRIPTIONS


class DecisionProvider(Protocol):
    name: str
    async def propose(self, phase: str, state: dict, instructions: str) -> dict: ...


class ScriptedProvider:
    name = 'scripted'

    def __init__(self, proposals: list[dict]):
        self.proposals = list(proposals)
        self.cursor = 0

    async def propose(self, phase: str, state: dict, instructions: str) -> dict:
        if self.cursor >= len(self.proposals):
            raise ValueError('Script exhausted.')
        proposal = self.proposals[self.cursor]
        self.cursor += 1
        return proposal


def proposal_schema() -> dict:
    # Supported strict function schema; stronger bounds are enforced locally.
    return {'type':'object', 'additionalProperties':False,
            'properties':{'action':{'type':'string','enum':['execute','finish']},
                          'tools':{'type':'array','items':{'type':'string','enum':list(DESCRIPTIONS)}},
                          'rationale':{'type':'string'},
                          'evidence_ids':{'type':'array','items':{'type':'string'}}},
            'required':['action','tools','rationale','evidence_ids']}


class OpenAIProvider:
    name = 'openai'

    def __init__(self, model: str | None, api_key: str | None = None, transport=None):
        self.model = model
        self._api_key = api_key if api_key is not None else os.environ.get('OPENAI_API_KEY')
        self._transport = transport  # HTTP mock transport for tests, not a model-selected endpoint.

    async def propose(self, phase: str, state: dict, instructions: str) -> dict:
        if not self.model or not self._api_key:
            raise ValueError('Live provider not configured.')
        import httpx
        payload = {'model':self.model, 'store':False, 'parallel_tool_calls':False,
                   'input':[{'role':'developer','content':instructions},
                            {'role':'user','content':json.dumps({'phase':phase,'state':state},allow_nan=False)}],
                   'tools':[{'type':'function','name':'propose_mission_action',
                             'description':'Propose a mission action for host policy validation; does not execute tools.',
                             'parameters':proposal_schema(),'strict':True}],
                   'tool_choice':{'type':'function','name':'propose_mission_action'},
                   'max_output_tokens':1200}
        async with httpx.AsyncClient(transport=self._transport, follow_redirects=False, timeout=60) as client:
            async with client.stream('POST','https://api.openai.com/v1/responses',json=payload,
                                     headers={'Authorization':f'Bearer {self._api_key}'}) as response:
                response.raise_for_status()
                parts, length = [], 0
                async for part in response.aiter_bytes():
                    length += len(part)
                    if length > 2_000_000:
                        raise ValueError('Model response too large.')
                    parts.append(part)
        body = json.loads(b''.join(parts))
        if body.get('status') != 'completed':
            raise ValueError('Incomplete model response.')
        outputs = body.get('output',[])
        if any(content.get('type') == 'refusal' for output in outputs for content in output.get('content',[])):
            raise ValueError('Model declined request.')
        calls = [output for output in outputs if output.get('type') == 'function_call']
        if len(calls) != 1 or calls[0].get('name') != 'propose_mission_action':
            raise ValueError('Unexpected model tool call.')
        proposal = Proposal.model_validate_json(calls[0]['arguments'])
        return proposal.model_dump()
