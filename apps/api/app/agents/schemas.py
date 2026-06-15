"""Structured-output schemas for AI agents.

Using a constrained schema is a core hallucination-mitigation technique (docs/04):
the model can only emit these fields, and `recommended_specialty` is further coerced
to the live catalog in `triage_graph.finalize_decision`.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, Field


class Urgency(str, enum.Enum):
    routine = "routine"
    soon = "soon"
    urgent = "urgent"
    # `emergency` is intentionally absent: it is decided ONLY by the deterministic
    # red-flag pre-filter, never by the LLM. See docs/07-ai-safety-compliance.md.


class ConsultPreference(str, enum.Enum):
    online = "online"
    offline = "offline"
    either = "either"


class TriageDecision(BaseModel):
    """The LLM's structured navigation output (NOT a diagnosis)."""

    reply: str = Field(..., description="Short, empathetic reply to the patient (their language).")
    follow_up_questions: list[str] = Field(
        default_factory=list,
        description="0-3 clarifying questions to refine the navigation.",
    )
    urgency: Urgency = Field(..., description="How soon they should seek care.")
    recommended_specialty: str = Field(
        ...,
        description="Specialty to see. MUST be chosen from the provided catalog only.",
    )
    consultation_type: ConsultPreference = Field(
        ..., description="Suggested consultation mode."
    )
    rationale: str | None = Field(
        default=None, description="Brief internal rationale (not shown verbatim to patient)."
    )
