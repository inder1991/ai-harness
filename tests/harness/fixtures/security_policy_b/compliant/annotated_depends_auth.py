"""v1.3.0 S8 — Annotated[T, Depends(f)] auth pattern (FastAPI 0.95+).

Pre-v1.3.0 _has_auth_dep only matched the legacy `arg = Depends(f)`
default-value form. This file is the modern idiomatic style.

Pretend-path: backend/src/api/routes_v4.py
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi_csrf_protect import CsrfProtect
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


def require_user() -> dict:
    return {}


@router.post("/api/v4/orders")
@limiter.limit("5/minute")
async def create_order(
    request: Request,
    user: Annotated[dict, Depends(require_user)],
    csrf_protect: CsrfProtect = Depends(),
) -> dict:
    return {"ok": True}
