"""Seed sample specialties, clinics, and doctors for local dev.

Run: python -m app.scripts.seed   (requires DB up + tables created)
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db.session import Base, SessionLocal, engine
from app.models import Clinic, ConsultType, Doctor, Specialty

SPECIALTIES = [
    ("General Physician", "general-physician"),
    ("Cardiology", "cardiology"),
    ("Dermatology", "dermatology"),
    ("Orthopedics", "orthopedics"),
    ("Pediatrics", "pediatrics"),
    ("Gynecology", "gynecology"),
    ("ENT", "ent"),
    ("Gastroenterology", "gastroenterology"),
]


async def seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as db:
        # specialties
        existing = {s.slug for s in (await db.execute(select(Specialty))).scalars()}
        slug_to_id: dict[str, int] = {}
        for name, slug in SPECIALTIES:
            if slug not in existing:
                sp = Specialty(name=name, slug=slug)
                db.add(sp)
                await db.flush()
                slug_to_id[slug] = sp.id
        await db.commit()

        # refresh ids
        for sp in (await db.execute(select(Specialty))).scalars():
            slug_to_id[sp.slug] = sp.id

        if (await db.execute(select(Clinic))).first():
            print("Already seeded.")
            return

        clinic = Clinic(name="Sunrise Clinic", city="Pune", locality="Kothrud",
                        address="FC Road, Pune")
        db.add(clinic)
        await db.flush()

        doctors = [
            Doctor(clinic_id=clinic.id, full_name="Dr. Asha Rao",
                   specialty_id=slug_to_id["dermatology"], gender="female",
                   languages="en,hi,mr", consult_fee=500, consult_type=ConsultType.both,
                   is_verified=True, rating=4.6),
            Doctor(clinic_id=clinic.id, full_name="Dr. Vikram Singh",
                   specialty_id=slug_to_id["orthopedics"], gender="male",
                   languages="en,hi", consult_fee=700, consult_type=ConsultType.offline,
                   is_verified=True, rating=4.4),
            Doctor(clinic_id=clinic.id, full_name="Dr. Neha Kulkarni",
                   specialty_id=slug_to_id["general-physician"], gender="female",
                   languages="en,hi,mr", consult_fee=400, consult_type=ConsultType.both,
                   is_verified=True, rating=4.8),
        ]
        db.add_all(doctors)
        await db.commit()
        print(f"Seeded {len(doctors)} doctors at {clinic.name}.")


if __name__ == "__main__":
    asyncio.run(seed())
