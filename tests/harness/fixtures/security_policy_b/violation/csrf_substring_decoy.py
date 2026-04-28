"""v1.3.0 S9 — pre-v1.3.0 substring `'CsrfProtect' in ast.dump(ann)`
accepted any annotation with that substring, including
`NoCsrfProtectNeeded`. The structural Name match in v1.3.0 correctly
flags this route as missing CSRF.

Pretend-path: backend/src/api/routes_v4.py
"""
from fastapi import APIRouter, Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


class NoCsrfProtectNeeded:
    """Decoy class whose name contains 'CsrfProtect' as a substring."""


def require_user() -> dict:
    return {}


@router.post("/api/v4/decoys")
@limiter.limit("1/minute")
async def create_decoy(
    request: Request,
    payload: dict,
    user=Depends(require_user),
    fake: NoCsrfProtectNeeded = NoCsrfProtectNeeded(),
) -> dict:
    return {"ok": True}
