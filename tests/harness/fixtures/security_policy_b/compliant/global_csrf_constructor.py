"""v1.3.0 S9 — CSRF middleware via FastAPI(middleware=[...]) constructor.

Pre-v1.3.0 _module_has_csrf_middleware only matched
`app.add_middleware(...)` calls; the constructor pattern was missed
and every per-route check fired (S-B4 false positive).

Pretend-path: backend/src/api/routes_v4.py
"""
from fastapi import APIRouter, Depends, FastAPI, Request
from slowapi import Limiter
from slowapi.middleware import Middleware
from slowapi.util import get_remote_address

from somelib import CsrfMiddleware

app = FastAPI(middleware=[Middleware(CsrfMiddleware)])
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


def require_user() -> dict:
    return {}


@router.post("/api/v4/refunds")
@limiter.limit("3/minute")
async def issue_refund(
    request: Request,
    user=Depends(require_user),
) -> dict:
    return {"ok": True}
