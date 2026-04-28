# v1.3.0 S7 — wrapper file is allowed to set timeout=None as the
# legitimate "default the consumer overrides" sentinel.
import httpx


async def make(timeout=None):
    async with httpx.AsyncClient(timeout=timeout) as c:
        return c
