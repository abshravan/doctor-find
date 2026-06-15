"""Temporal activity definitions (deterministic, idempotent, small units of work).

Activities are simple, pure functions that Temporal orchestrates. Each can be retried,
compensated, or parallelized. They abstract away I/O (DB, APIs) so the workflow graph
stays readable.

See docs/03 (event-driven architecture) and docs/12 (Temporal choice rationale).
"""

from __future__ import annotations

import logging

from temporalio import activity

logger = logging.getLogger(__name__)


# --- Notification activities ---


@activity.defn
async def send_whatsapp_reminder(
    patient_id: str, appointment_id: str, doctor_name: str, scheduled_at: str
) -> dict:
    """Send a WhatsApp reminder. Returns {sent: bool, message_id: str, error?: str}.

    Implementation: call Gupshup WhatsApp API (or Twilio for intl fallback).
    """
    try:
        # TODO: wire Gupshup API
        logger.info(
            "WhatsApp reminder queued for patient=%s appt=%s doc=%s",
            patient_id,
            appointment_id,
            doctor_name,
        )
        return {"sent": True, "message_id": f"msg_{appointment_id[:8]}"}
    except Exception as exc:  # noqa: BLE001
        logger.exception("WhatsApp send failed: %s", exc)
        return {"sent": False, "error": str(exc)}


@activity.defn
async def place_reminder_call(
    patient_id: str, appointment_id: str, doctor_name: str, scheduled_at: str
) -> dict:
    """Place a voice call reminder (fallback to WhatsApp failure).

    Implementation: call Exotel or LiveKit to initiate the call; route to Voice
    Receptionist Agent to confirm/reschedule.
    """
    try:
        # TODO: wire Exotel voice API
        logger.info(
            "Voice reminder call queued for patient=%s appt=%s",
            patient_id,
            appointment_id,
        )
        return {"placed": True, "call_id": f"call_{appointment_id[:8]}"}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Voice call placement failed: %s", exc)
        return {"placed": False, "error": str(exc)}


# --- Appointment state checks ---


@activity.defn
async def is_appointment_cancelled(appointment_id: str) -> bool:
    """Check if the appointment was cancelled since the reminder was scheduled.

    Prevents sending reminders for dead appointments (common abort condition in
    the workflow).
    """
    try:
        # TODO: query DB
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("Appointment status check failed: %s", exc)
        return False
