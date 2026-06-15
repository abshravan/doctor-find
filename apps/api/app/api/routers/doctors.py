"""Doctor discovery endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import Clinic, Doctor, Specialty
from app.schemas import DoctorOut, DoctorSearchQuery

router = APIRouter(prefix="/doctors", tags=["doctors"])


@router.get("", response_model=list[DoctorOut])
async def search_doctors(
    query: DoctorSearchQuery = Depends(),
    db: AsyncSession = Depends(get_db),
) -> list[DoctorOut]:
    """Search & filter doctors by specialty, city, language, gender, fee, consult type.

    For semantic symptom→doctor matching, this is augmented with pgvector retrieval
    (see docs/04 and docs/05). This endpoint covers the structured-filter path.
    """
    stmt = (
        select(Doctor, Specialty, Clinic)
        .join(Specialty, Doctor.specialty_id == Specialty.id)
        .join(Clinic, Doctor.clinic_id == Clinic.id, isouter=True)
    )

    if query.specialty:
        stmt = stmt.where(Specialty.slug == query.specialty.lower())
    if query.city:
        stmt = stmt.where(Clinic.city.ilike(f"%{query.city}%"))
    if query.gender:
        stmt = stmt.where(Doctor.gender == query.gender)
    if query.max_fee is not None:
        stmt = stmt.where(Doctor.consult_fee <= query.max_fee)
    if query.language:
        stmt = stmt.where(Doctor.languages.ilike(f"%{query.language}%"))
    if query.q:
        stmt = stmt.where(Doctor.full_name.ilike(f"%{query.q}%"))

    stmt = stmt.limit(query.page_size).offset((query.page - 1) * query.page_size)

    rows = (await db.execute(stmt)).all()
    return [
        DoctorOut(
            id=d.id,
            full_name=d.full_name,
            specialty=s.name,
            city=c.city if c else None,
            locality=c.locality if c else None,
            languages=[x.strip() for x in (d.languages or "").split(",") if x.strip()],
            consult_fee=float(d.consult_fee),
            consult_type=d.consult_type.value,
            gender=d.gender,
            is_verified=d.is_verified,
            rating=float(d.rating),
        )
        for d, s, c in rows
    ]
