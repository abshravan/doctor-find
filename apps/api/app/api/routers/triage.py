"""AI Symptom Navigator endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import triage as triage_agent
from app.db.session import get_db
from app.schemas import TriageRequest, TriageResponse

router = APIRouter(prefix="/triage", tags=["triage"])


@router.post("", response_model=TriageResponse)
async def navigate_symptoms(
    payload: TriageRequest,
    db: AsyncSession = Depends(get_db),
) -> TriageResponse:
    """Patient enters symptoms (voice-transcribed or text). Returns urgency,
    recommended specialty, consult type, follow-ups, and a mandatory disclaimer.

    Pipeline (docs/04): deterministic emergency pre-filter -> LangGraph + LLM
    navigation (specialty grounded against the live catalog) -> deterministic
    fallback if the LLM is unavailable. Emergency red-flags short-circuit to
    112/108 escalation and never reach the LLM. See docs/07-ai-safety-compliance.md.
    """
    result = await triage_agent.run_triage(payload.message, payload.language, db=db)
    return TriageResponse(
        session_id=payload.session_id or str(uuid.uuid4()),
        **result,
    )
