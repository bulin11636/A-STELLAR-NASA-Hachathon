"""Deterministic gates; no model text can relax these checks."""
from app.coordinator.contracts import Proposal
from app.coordinator.tools import DESCRIPTIONS, required_tools


def rejection(proposal: Proposal, request, evidence, calls, rounds, limits) -> str | None:
    known = {e.evidence_id for e in evidence}
    attempted = {e.tool for e in evidence}
    if any(key not in known for key in proposal.evidence_ids):
        return 'unknown_evidence_reference'
    if proposal.action == 'finish':
        if any(tool not in attempted for tool in required_tools(request)):
            return 'premature_finish'
        return None
    if calls + len(proposal.tools) > limits.max_tool_calls:
        return 'tool_budget_exceeded'
    if rounds >= limits.max_replans + 1:
        return 'replan_budget_exceeded'
    if any(tool not in DESCRIPTIONS for tool in proposal.tools):
        return 'unsupported_tool'
    if any(tool in attempted for tool in proposal.tools):
        return 'duplicate_tool_call'
    if 'validate_route' in proposal.tools:
        return 'validated_route_candidate_unavailable'
    return None


def deterministic_proposal(request, evidence, remaining: int) -> Proposal:
    attempted = {e.tool for e in evidence}
    pending = [tool for tool in required_tools(request) if tool not in attempted]
    workers = [tool for tool in pending if tool != 'plan_route']
    selected = (workers or pending)[:max(0, remaining)]
    return Proposal(action='execute' if selected else 'finish', tools=selected,
                    rationale='Deterministic selection of outstanding mission requirements.',
                    evidence_ids=[e.evidence_id for e in evidence])
