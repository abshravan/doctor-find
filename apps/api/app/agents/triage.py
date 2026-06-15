"""AI Symptom Navigator / Triage Agent (docs/04-ai-agent-design.md).

Two layers:
  * `navigate()` — a fully DETERMINISTIC, dependency-free implementation (emergency
    detection + keyword routing). It is the safe fallback and runs with zero API keys.
  * `run_triage()` — the orchestrator. It ALWAYS runs the deterministic emergency
    pre-filter first, then attempts the real LangGraph + LLM navigation
    (`triage_graph.run_graph`). If the LLM path is unavailable (no keys, missing
    libs, provider errors), it falls back to `navigate()`.

Design invariants:
  * Emergency red-flags are checked DETERMINISTICALLY before any LLM reasoning.
  * Output is ALWAYS structured (urgency + specialty + consult type).
  * A disclaimer is ALWAYS attached. The agent navigates; it never diagnoses.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

DISCLAIMER_EN = (
    "I'm an AI navigator, not a doctor, and this is not a medical diagnosis. "
    "For medical advice, please consult a qualified doctor. "
    "If this is an emergency, call 112 (or 108 for ambulance) immediately."
)

# Red-flag patterns -> immediate emergency escalation. Keep conservative (high recall).
EMERGENCY_PATTERNS = [
    r"chest pain", r"can'?t breathe", r"difficulty breathing", r"shortness of breath",
    r"unconscious", r"not breathing", r"severe bleeding", r"stroke", r"slurred speech",
    r"face droop", r"seizure", r"fainted", r"blue lips", r"severe (chest|abdominal) pain",
    # Self-harm / suicidality — keep broad (high recall is the goal here).
    r"suicid", r"self[- ]harm", r"overdose", r"(harm|hurt|kill)(ing)? myself",
    r"end(ing)? my life", r"want to die",
]

# Naive keyword -> specialty routing. Replace with retrieval + LLM (Phase 4).
SPECIALTY_HINTS: dict[str, list[str]] = {
    "Cardiology": ["palpitation", "heart", "bp", "blood pressure"],
    "Dermatology": ["rash", "skin", "acne", "itch", "hair fall"],
    "ENT": ["ear", "throat", "nose", "sinus", "tonsil"],
    "Orthopedics": ["knee", "back pain", "joint", "fracture", "shoulder"],
    "Pediatrics": ["child", "baby", "infant", "kid"],
    "Gynecology": ["period", "pregnan", "menstrual", "pcos"],
    "Gastroenterology": ["stomach", "acidity", "vomit", "diarrhea", "constipation"],
    "General Physician": [],  # default
}


def _is_emergency(text: str) -> bool:
    t = text.lower()
    return any(re.search(p, t) for p in EMERGENCY_PATTERNS)


def _route_specialty(text: str) -> str:
    t = text.lower()
    for specialty, hints in SPECIALTY_HINTS.items():
        if any(h in t for h in hints):
            return specialty
    return "General Physician"


def emergency_result() -> dict:
    """Canonical emergency-escalation response (deterministic, never from an LLM)."""
    return {
        "reply": (
            "This sounds like it may be a medical emergency. "
            "Please call 112 (or 108 for an ambulance) or go to the nearest "
            "emergency room right now."
        ),
        "follow_up_questions": [],
        "urgency": "emergency",
        "recommended_specialty": "Emergency Medicine",
        "consultation_type": "offline",
        "is_emergency": True,
        "disclaimer": DISCLAIMER_EN,
    }


def navigate(message: str, language: str = "en") -> dict:
    """Return a structured triage result. Deterministic + safe by construction."""
    if _is_emergency(message):
        return emergency_result()

    specialty = _route_specialty(message)
    return {
        "reply": (
            f"Thanks for sharing. Based on what you described, a {specialty} "
            "may be the right specialist to help. I can help you find and book one."
        ),
        "follow_up_questions": [
            "How long have you had these symptoms?",
            "On a scale of 1–10, how severe is it?",
            "Do you prefer an online or in-clinic consultation?",
        ],
        "urgency": "routine",
        "recommended_specialty": specialty,
        "consultation_type": "either",
        "is_emergency": False,
        "disclaimer": DISCLAIMER_EN,
    }


async def run_triage(
    message: str,
    language: str = "en",
    history: list[dict[str, str]] | None = None,
    db: Any = None,
) -> dict:
    """Orchestrate triage: deterministic emergency pre-filter, then LLM navigation.

    1. ALWAYS run the deterministic emergency check first. If it fires, return the
       escalation immediately — the LLM is never consulted for emergencies.
    2. Otherwise build the grounded specialty catalog and run the LangGraph + LLM
       pipeline for empathetic, structured navigation.
    3. On ANY failure (no API keys, langgraph/provider libs missing, provider errors),
       fall back to the deterministic `navigate()` so the endpoint never fails closed.
    """
    if _is_emergency(message):
        return emergency_result()

    from app.services.specialty_catalog import get_specialty_catalog

    catalog = await get_specialty_catalog(db)
    try:
        from app.agents.triage_graph import run_graph

        return await run_graph(message, language, history or [], catalog)
    except Exception as exc:  # noqa: BLE001 — degrade gracefully to deterministic
        logger.warning("LLM triage path unavailable; using deterministic fallback: %s", exc)
        return navigate(message, language)
