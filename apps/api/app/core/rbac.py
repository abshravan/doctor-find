"""Role-Based Access Control. Full permission matrix in docs/03-system-architecture.md."""

from enum import Enum

from fastapi import Depends, Header, HTTPException, status

from app.core.security import decode_token


class Role(str, Enum):
    PATIENT = "patient"
    DOCTOR = "doctor"
    CLINIC_ADMIN = "clinic_admin"
    RECEPTIONIST = "receptionist"
    PLATFORM_ADMIN = "platform_admin"


# Coarse permission matrix (resource:action -> allowed roles).
PERMISSIONS: dict[str, set[Role]] = {
    "doctor:read": set(Role),  # everyone can discover doctors
    "appointment:create": {Role.PATIENT, Role.RECEPTIONIST, Role.CLINIC_ADMIN},
    "appointment:read_own": set(Role),
    "clinic:manage": {Role.CLINIC_ADMIN, Role.PLATFORM_ADMIN},
    "availability:manage": {Role.DOCTOR, Role.CLINIC_ADMIN, Role.RECEPTIONIST},
    "platform:admin": {Role.PLATFORM_ADMIN},
}


async def current_principal(authorization: str | None = Header(default=None)) -> dict:
    """Decode bearer token into a principal {sub, role}. Stubbed for scaffold."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_token(token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from exc
    return {"sub": payload["sub"], "role": Role(payload.get("role", "patient"))}


def require(permission: str):
    """Dependency factory enforcing a permission."""

    async def _dep(principal: dict = Depends(current_principal)) -> dict:
        allowed = PERMISSIONS.get(permission, set())
        if principal["role"] not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires {permission}")
        return principal

    return _dep
