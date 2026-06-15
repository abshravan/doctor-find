"""Tests for the booking service (idempotency, event emission, workflow orchestration)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models import Appointment, AppointmentStatus, Clinic, ConsultType, Doctor, Specialty
from app.services.booking import create_appointment, emit_appointment_requested


@pytest.fixture
async def doctor_fixture(db: AsyncSession) -> Doctor:
    """Create a test doctor + clinic."""
    sp = Specialty(name="Orthopedics", slug="orthopedics")
    db.add(sp)
    await db.flush()

    clinic = Clinic(name="Test Clinic", city="Pune", locality="Test")
    db.add(clinic)
    await db.flush()

    doctor = Doctor(
        clinic_id=clinic.id,
        full_name="Dr. Test",
        specialty_id=sp.id,
        languages="en,hi",
        consult_fee=500,
        consult_type=ConsultType.both,
    )
    db.add(doctor)
    await db.commit()
    return doctor


async def test_create_appointment_basic(db: AsyncSession, doctor_fixture: Doctor):
    patient_id = str(uuid.uuid4())
    scheduled_at = datetime.now(timezone.utc) + timedelta(days=7)

    appt, is_new = await create_appointment(
        patient_id=patient_id,
        doctor_id=str(doctor_fixture.id),
        scheduled_at=scheduled_at,
        consult_type="offline",
        idempotency_key="key-1",
        db=db,
    )

    assert is_new is True
    assert appt.patient_id == uuid.UUID(patient_id)
    assert appt.doctor_id == doctor_fixture.id
    assert appt.status == AppointmentStatus.requested


async def test_create_appointment_idempotency(db: AsyncSession, doctor_fixture: Doctor):
    """Retry the same request; should return the same appointment (idempotent)."""
    patient_id = str(uuid.uuid4())
    scheduled_at = datetime.now(timezone.utc) + timedelta(days=7)
    key = "idempotent-key-1"

    appt1, is_new1 = await create_appointment(
        patient_id=patient_id,
        doctor_id=str(doctor_fixture.id),
        scheduled_at=scheduled_at,
        consult_type="offline",
        idempotency_key=key,
        db=db,
    )
    assert is_new1 is True

    appt2, is_new2 = await create_appointment(
        patient_id=patient_id,
        doctor_id=str(doctor_fixture.id),
        scheduled_at=scheduled_at,
        consult_type="offline",
        idempotency_key=key,
        db=db,
    )
    assert is_new2 is False
    assert appt2.id == appt1.id


async def test_emit_appointment_requested_event(db: AsyncSession, doctor_fixture: Doctor):
    """Verify that emitting the event produces the correct structure."""
    patient_id = str(uuid.uuid4())
    scheduled_at = datetime.now(timezone.utc) + timedelta(days=7)

    appt, _ = await create_appointment(
        patient_id=patient_id,
        doctor_id=str(doctor_fixture.id),
        scheduled_at=scheduled_at,
        consult_type="offline",
        idempotency_key="key-2",
        db=db,
    )

    event = await emit_appointment_requested(appt, "key-2")

    assert event.event_type.value == "appointment.requested"
    assert event.appointment_id == str(appt.id)
    assert event.patient_id == patient_id
    assert event.doctor_id == str(doctor_fixture.id)
    assert event.idempotency_key == "key-2"


@pytest.fixture
async def db():
    """Create a test DB session."""
    async with SessionLocal() as session:
        yield session
