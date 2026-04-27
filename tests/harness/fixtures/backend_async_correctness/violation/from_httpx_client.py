# v1.3.0 — `from httpx import Client; Client()` must fire Q7.no-sync-httpx.
from httpx import Client


def make():
    return Client()
