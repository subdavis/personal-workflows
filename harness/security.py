"""Bearer-token auth for webhook endpoints."""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from .config import get_settings


def require_bearer(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency enforcing ``Authorization: Bearer <WEBHOOK_BEARER_TOKEN>``."""
    expected = f"Bearer {get_settings().webhook_bearer_token}"
    if authorization is None or not secrets.compare_digest(authorization, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing bearer token",
        )
