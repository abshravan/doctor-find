"""SQLAlchemy ORM models. Full schema + DDL in docs/05-database-design.md.

Only a representative subset is modeled here for the scaffold (users, clinics,
doctors, specialties, appointments). Extend per the Phase 5 design.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, time

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class ConsultType(str, enum.Enum):
    online = "online"
    offline = "offline"
    both = "both"


class AppointmentStatus(str, enum.Enum):
    requested = "requested"
    confirmed = "confirmed"
    cancelled = "cancelled"
    completed = "completed"
    no_show = "no_show"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(30), default="patient", index=True)
    preferred_language: Mapped[str] = mapped_column(String(10), default="en")


class Specialty(Base):
    __tablename__ = "specialties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)


class Clinic(Base, TimestampMixin):
    __tablename__ = "clinics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(160), index=True)
    city: Mapped[str] = mapped_column(String(80), index=True)
    locality: Mapped[str | None] = mapped_column(String(120), index=True)
    address: Mapped[str | None] = mapped_column(Text)

    doctors: Mapped[list[Doctor]] = relationship(back_populates="clinic")


class Doctor(Base, TimestampMixin):
    __tablename__ = "doctors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clinics.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(120), index=True)
    specialty_id: Mapped[int] = mapped_column(ForeignKey("specialties.id"), index=True)
    gender: Mapped[str | None] = mapped_column(String(10))
    languages: Mapped[str] = mapped_column(String(120), default="en")  # csv; normalize in Phase 5
    consult_fee: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    consult_type: Mapped[ConsultType] = mapped_column(
        Enum(ConsultType), default=ConsultType.offline
    )
    is_verified: Mapped[bool] = mapped_column(default=False)
    rating: Mapped[float] = mapped_column(Numeric(2, 1), default=0)

    clinic: Mapped[Clinic | None] = relationship(back_populates="doctors")
    specialty: Mapped[Specialty] = relationship()


class Availability(Base):
    __tablename__ = "availability"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    doctor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("doctors.id"), index=True)
    weekday: Mapped[int] = mapped_column(Integer)  # 0=Mon
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)


class Appointment(Base, TimestampMixin):
    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    doctor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("doctors.id"), index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus), default=AppointmentStatus.requested, index=True
    )
    consult_type: Mapped[ConsultType] = mapped_column(Enum(ConsultType))
    notes: Mapped[str | None] = mapped_column(Text)
