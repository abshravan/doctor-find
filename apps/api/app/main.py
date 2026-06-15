"""DoctorFind API entrypoint — modular monolith (see docs/03-system-architecture.md)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routers import appointments, doctors, health, triage
from app.core.config import settings

app = FastAPI(
    title="DoctorFind API",
    version=__version__,
    description="AI Healthcare Navigator for India — discovery, triage, booking, voice.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten per environment in prod
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(triage.router)
app.include_router(doctors.router)
app.include_router(appointments.router)


@app.get("/", tags=["meta"])
async def root() -> dict:
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "disclaimer": "Informational navigation only — not medical diagnosis.",
    }
