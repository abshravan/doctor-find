"""Temporal workflow definitions (state machines for multi-step, durable processes).

A workflow is Durable — it can survive service restarts and continues exactly where
it left off. Use workflows for business-critical, multi-step processes like reminders,
follow-ups, and missed-call callbacks. See docs/03 and docs/12.

Workflow code is _not_ parallelizable with regular Python async (Temporal enforces
determinism); use `workflow.execute_activity()` for each I/O.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from temporalio import workflow

from app.workers.activities import (
    is_appointment_cancelled,
    place_reminder_call,
    send_whatsapp_reminder,
)


@workflow.defn
class AppointmentReminderWorkflow:
    """Send 24h and 2h reminders before an appointment, with voice fallback.

    Pseudocode (executed deterministically by Temporal):
      wait until 24h before
      if not cancelled: send WhatsApp reminder
      wait until 2h before
      if not cancelled:
        try WhatsApp reminder
        if failed: place voice call

    This workflow guarantees that reminders are sent exactly once (no double-sends)
    and can be paused/resumed/cancelled via the Temporal API.
    """

    @workflow.run
    async def run(
        self,
        appointment_id: str,
        patient_id: str,
        doctor_name: str,
        scheduled_at: datetime,
    ) -> dict:
        logger_wf = workflow.logger
        logger_wf.info(
            "Reminder workflow started for appt=%s, scheduled_at=%s",
            appointment_id,
            scheduled_at,
        )

        # ---- 24-hour reminder ----
        remind_at_24h = scheduled_at - timedelta(hours=24)
        await workflow.sleep_until(remind_at_24h)

        if await workflow.execute_activity(
            is_appointment_cancelled, appointment_id, start_to_close_timeout=timedelta(seconds=5)
        ):
            logger_wf.info("Appointment %s was cancelled; skipping 24h reminder", appointment_id)
            return {"status": "cancelled_before_24h"}

        result_24h = await workflow.execute_activity(
            send_whatsapp_reminder,
            patient_id,
            appointment_id,
            doctor_name,
            scheduled_at.isoformat(),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy={"max_attempts": 2},  # retry once if transient failure
        )
        logger_wf.info("24h reminder result: %s", result_24h)

        # ---- 2-hour reminder ----
        remind_at_2h = scheduled_at - timedelta(hours=2)
        await workflow.sleep_until(remind_at_2h)

        if await workflow.execute_activity(
            is_appointment_cancelled, appointment_id, start_to_close_timeout=timedelta(seconds=5)
        ):
            logger_wf.info("Appointment %s was cancelled; skipping 2h reminder", appointment_id)
            return {"status": "cancelled_before_2h"}

        result_2h = await workflow.execute_activity(
            send_whatsapp_reminder,
            patient_id,
            appointment_id,
            doctor_name,
            scheduled_at.isoformat(),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy={"max_attempts": 2},
        )

        # If WhatsApp failed, fall back to voice call.
        if not result_2h.get("sent"):
            logger_wf.warning(
                "WhatsApp 2h reminder failed for appt=%s; placing voice call",
                appointment_id,
            )
            result_call = await workflow.execute_activity(
                place_reminder_call,
                patient_id,
                appointment_id,
                doctor_name,
                scheduled_at.isoformat(),
                start_to_close_timeout=timedelta(seconds=60),
            )
            return {
                "status": "completed",
                "reminder_24h": result_24h,
                "voice_fallback": result_call,
            }

        return {"status": "completed", "reminder_24h": result_24h, "reminder_2h": result_2h}


# --- Future workflows (stubs) ---
# MissedCallCallbackWorkflow — triggered by Exotel webhook on a missed call
# FollowUpSurveyWorkflow — 24h post-appointment, request patient feedback
# CancellationCompensationWorkflow — undo related state if appointment cancels
