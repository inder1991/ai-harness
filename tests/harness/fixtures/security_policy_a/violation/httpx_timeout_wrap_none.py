# v1.3.0 S7 — `httpx.Timeout(None)` wraps an unbounded wait; pre-v1.3.0
# the regex-only scan only matched literal `timeout=None` and missed this.
import httpx


async def fetch():
    async with httpx.AsyncClient(timeout=httpx.Timeout(None)) as c:
        return await c.get("https://example.com")
