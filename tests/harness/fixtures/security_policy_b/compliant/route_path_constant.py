"""v1.3.0 S10 — route path declared via Name reference to a module constant.

Pre-v1.3.0 _route_decorator_info required ast.Constant(str); a Name
reference like `router.post(API_USERS_ROOT)` was silently ignored
(S-B5 false negative — the route went unchecked entirely).

Pretend-path: backend/src/api/routes_v4.py
"""
from fastapi import APIRouter, Depends, Request
from fastapi_csrf_protect import CsrfProtect
from slowapi import Limiter
from slowapi.util import get_remote_address

API_USERS_ROOT = "/api/v4/users"

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


def require_user() -> dict:
    return {}


@router.post(API_USERS_ROOT)
@limiter.limit("10/minute")
async def create_user(
    request: Request,
    payload: dict,
    user=Depends(require_user),
    csrf_protect: CsrfProtect = Depends(),
) -> dict:
    return {"ok": True}
