"""AI Symptom Navigator endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.agents import triage as triage_agent
from app.schemas import TriageRequest, TriageResponse

router = APIRouter(prefix="/triage", tags=["triage"])


@router.post("", response_model=TriageResponse)
async def navigate_symptoms(payload: TriageRequest) -> TriageResponse:
    """Patient enters symptoms (voice-transcribed or text). Returns urgency,
    recommended specialty, consult type, follow-ups, and a mandatory disclaimer.

    Safety: emergency red-flags are detected deterministically and short-circuit
    to 112/108 escalation. See docs/07-ai-safety-compliance.md.
    """
    result = triage_agent.navigate(payload.message, payload.language)
    return TriageResponse(
        session_id=payload.session_id or str(uuid.uuid4()),
        **result,
    )
