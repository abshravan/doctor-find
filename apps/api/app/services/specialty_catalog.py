"""Specialty catalog used to GROUND the triage LLM's routing (anti-hallucination).

The LLM may only choose a specialty from this catalog, and the finalizer coerces
anything off-catalog back to "General Physician". This is the lightweight, reliable
form of RAG grounding for routing; semantic doctor retrieval via pgvector is layered
on top in the discovery path (see docs/04 + docs/05).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

CANONICAL_SPECIALTIES: list[str] = [
    "General Physician",
    "Cardiology",
    "Dermatology",
    "Orthopedics",
    "Pediatrics",
    "Gynecology",
    "ENT",
    "Gastroenterology",
    "Neurology",
    "Psychiatry",
    "Ophthalmology",
    "Dentistry",
    "Pulmonology",
    "Endocrinology",
    "Urology",
]


async def get_specialty_catalog(db=None) -> list[str]:
    """Return live specialty names from the DB, falling back to the canonical list."""
    if db is None:
        return list(CANONICAL_SPECIALTIES)
    try:
        from sqlalchemy import select

        from app.models import Specialty

        rows = (await db.execute(select(Specialty.name))).scalars().all()
        return list(rows) if rows else list(CANONICAL_SPECIALTIES)
    except Exception as exc:  # noqa: BLE001 — DB may be unavailable in some contexts
        logger.warning("Specialty catalog DB fetch failed, using canonical: %s", exc)
        return list(CANONICAL_SPECIALTIES)
