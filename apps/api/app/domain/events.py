"""Event types emitted by the domain. Used for event sourcing + saga orchestration
(Temporal workflows, notification dispatch, analytics).

Convention: namespace.event_name, immutable schema, version field for evolution.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class EventType(str, Enum):
    appointment_requested = "appointment.requested"
    appointment_confirmed = "appointment.confirmed"
    appointment_cancelled = "appointment.cancelled"
    appointment_completed = "appointment.completed"
    appointment_no_show = "appointment.no_show"

    reminder_scheduled = "reminder.scheduled"
    reminder_sent = "reminder.sent"
    reminder_failed = "reminder.failed"

    call_initiated = "call.initiated"
    call_completed = "call.completed"


class DomainEvent(BaseModel):
    """Base event — all events are versioned, timestamped, and idempotent."""

    event_type: EventType
    event_id: str = Field(default_factory=lambda: str(UUID(int=0)))  # override on emit
    version: int = 1
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
    aggregate_id: str  # the patient or appointment ID at the root of the change


class AppointmentRequestedEvent(DomainEvent):
    event_type: EventType = EventType.appointment_requested
    appointment_id: str
    patient_id: str
    doctor_id: str
    scheduled_at: datetime
    consult_type: str
    idempotency_key: str


class ReminderScheduledEvent(DomainEvent):
    event_type: EventType = EventType.reminder_scheduled
    appointment_id: str
    patient_id: str
    remind_at: datetime
    channel: str  # whatsapp, sms, voice
    attempt: int = 1  # 1st or 2nd reminder
