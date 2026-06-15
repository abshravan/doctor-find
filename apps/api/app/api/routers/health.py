"""Liveness/readiness probes."""

from fastapi import APIRouter

from app import __version__

router = APIRouter(tags=["meta"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "doctorfind-api", "version": __version__}
