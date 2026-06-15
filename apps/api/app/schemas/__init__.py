"""Pydantic API contracts (request/response DTOs)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ---- Doctor discovery ----
class DoctorOut(BaseModel):
    id: uuid.UUID
    full_name: str
    specialty: str
    city: str | None = None
    locality: str | None = None
    languages: list[str] = []
    consult_fee: float
    consult_type: str
    gender: str | None = None
    is_verified: bool
    rating: float

    class Config:
        from_attributes = True


class DoctorSearchQuery(BaseModel):
    q: str | None = None
    specialty: str | None = None
    city: str | None = None
    language: str | None = None
    gender: str | None = None
    max_fee: float | None = None
    consult_type: str | None = None
    page: int = 1
    page_size: int = 20


# ---- Triage ----
class TriageRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(..., description="Patient symptom text (or transcribed voice)")
    language: str = "en"


class TriageResponse(BaseModel):
    session_id: str
    reply: str
    follow_up_questions: list[str] = []
    urgency: str  # routine | soon | urgent | emergency
    recommended_specialty: str | None = None
    consultation_type: str | None = None  # online | offline | either
    is_emergency: bool = False
    disclaimer: str


# ---- Booking ----
class BookingRequest(BaseModel):
    doctor_id: uuid.UUID
    scheduled_at: datetime
    consult_type: str = "offline"
    notes: str | None = None


class BookingOut(BaseModel):
    id: uuid.UUID
    doctor_id: uuid.UUID
    scheduled_at: datetime
    status: str
    consult_type: str

    class Config:
        from_attributes = True
