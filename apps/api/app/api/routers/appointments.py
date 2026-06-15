"""Booking endpoints. Booking is a DETERMINISTIC workflow (no LLM in the
critical path) — see docs/04 'deterministic vs agentic'. WhatsApp confirmations
and reminders are dispatched via Temporal/queue (see docs/06, docs/12)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import require
from app.db.session import get_db
from app.models import Appointment, AppointmentStatus, ConsultType
from app.schemas import BookingOut, BookingRequest

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.post("", response_model=BookingOut, status_code=201)
async def create_appointment(
    payload: BookingRequest,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require("appointment:create")),
) -> BookingOut:
    appt = Appointment(
        patient_id=principal["sub"],
        doctor_id=payload.doctor_id,
        scheduled_at=payload.scheduled_at,
        consult_type=ConsultType(payload.consult_type),
        status=AppointmentStatus.requested,
        notes=payload.notes,
    )
    db.add(appt)
    await db.commit()
    await db.refresh(appt)
    # TODO: emit `appointment.requested` event -> WhatsApp confirm + reminder workflow
    return BookingOut(
        id=appt.id,
        doctor_id=appt.doctor_id,
        scheduled_at=appt.scheduled_at,
        status=appt.status.value,
        consult_type=appt.consult_type.value,
    )
