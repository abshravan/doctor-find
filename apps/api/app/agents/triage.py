"""AI Symptom Navigator / Triage Agent (scaffold).

This is a SAFE, deterministic-first stub of the agent designed in
docs/04-ai-agent-design.md. It demonstrates the contract and the critical safety
behaviors (emergency red-flag detection + mandatory disclaimer) WITHOUT calling an
LLM, so the scaffold runs with no API keys. Swap `_llm_navigate` for a real
LangGraph + Gemini implementation following Phase 4.

Design principles enforced here:
  * Emergency red-flags are checked DETERMINISTICALLY before any LLM reasoning.
  * Output is ALWAYS structured (urgency + specialty + consult type).
  * A disclaimer is ALWAYS attached. The agent navigates; it never diagnoses.
"""

from __future__ import annotations

import re

DISCLAIMER_EN = (
    "I'm an AI navigator, not a doctor, and this is not a medical diagnosis. "
    "For medical advice, please consult a qualified doctor. "
    "If this is an emergency, call 112 (or 108 for ambulance) immediately."
)

# Red-flag patterns -> immediate emergency escalation. Keep conservative (high recall).
EMERGENCY_PATTERNS = [
    r"chest pain", r"can'?t breathe", r"difficulty breathing", r"shortness of breath",
    r"unconscious", r"not breathing", r"severe bleeding", r"stroke", r"slurred speech",
    r"face droop", r"suicid", r"self[- ]harm", r"overdose", r"seizure", r"fainted",
    r"blue lips", r"severe (chest|abdominal) pain",
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


def navigate(message: str, language: str = "en") -> dict:
    """Return a structured triage result. Deterministic + safe by construction."""
    if _is_emergency(message):
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


# --- Real LLM hook (to implement per docs/04) ---
async def _llm_navigate(message: str, language: str, history: list[dict]) -> dict:  # noqa: ARG001
    """Placeholder for the LangGraph + Gemini implementation.

    Must: ground specialty routing in DB, force structured output, keep the
    deterministic emergency check as a pre-filter, and never omit the disclaimer.
    """
    raise NotImplementedError("Wire up LangGraph + Gemini per docs/04-ai-agent-design.md")
