"""Booking endpoints. Booking is a DETERMINISTIC workflow (no LLM in the
critical path) — see docs/04 'deterministic vs agentic'. WhatsApp confirmations
and reminders are dispatched via Temporal/queue (see docs/06, docs/12)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import require
from app.db.session import get_db
from app.models import Doctor
from app.schemas import BookingOut, BookingRequest
from app.services.booking import (
    create_appointment,
    emit_appointment_requested,
    start_reminder_workflow,
)

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.post("", response_model=BookingOut, status_code=201)
async def book_appointment(
    payload: BookingRequest,
    db: AsyncSession = Depends(get_db),
    principal: dict = Depends(require("appointment:create")),
    idempotency_key: str | None = Header(default=None),
) -> BookingOut:
    """Create an appointment with idempotency. Emits domain event + starts reminder workflow.

    Idempotency: provide `Idempotency-Key` header to ensure the same request always
    returns the same result (important for retry-safety). If omitted, a new key is
    generated.

    Event-driven: on success, emits AppointmentRequestedEvent (for analytics/audit)
    and starts a Temporal reminder workflow (sends WhatsApp reminders at 24h and 2h
    before the appointment, with voice fallback).
    """
    if not idempotency_key:
        import uuid

        idempotency_key = str(uuid.uuid4())

    # Create the appointment (idempotent)
    appt, is_new = await create_appointment(
        patient_id=str(principal["sub"]),
        doctor_id=str(payload.doctor_id),
        scheduled_at=payload.scheduled_at,
        consult_type=payload.consult_type,
        idempotency_key=idempotency_key,
        db=db,
        notes=payload.notes,
    )

    if is_new:
        # Emit event for audit + analytics (sent to event sink, logged by the service)
        await emit_appointment_requested(appt, idempotency_key)

        # Get doctor details for the reminder workflow
        doctor = await db.get(Doctor, payload.doctor_id)
        if not doctor:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Doctor not found"
            )

        # Start the reminder workflow (best-effort; failures logged by the service)
        _ = await start_reminder_workflow(appt, doctor.full_name)

    return BookingOut(
        id=appt.id,
        doctor_id=appt.doctor_id,
        scheduled_at=appt.scheduled_at,
        status=appt.status.value,
        consult_type=appt.consult_type.value,
    )
