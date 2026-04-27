# v1.3.0 S1+S11 — aliased import slips literal-name regex pre-v1.3.0;
# ImportTracker resolves it.
import requests as r  # noqa: F401


def fetch():
    return r.get("https://example.com")
