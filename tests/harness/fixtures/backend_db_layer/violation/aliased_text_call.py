"""v1.3.1 S15 — `sa.text(...)` (aliased import) must fire
Q8.text-call-outside-analytics. Pre-v1.3.0 only matched bare `text(...)`
Name calls (S-DB5).

Pretend-path: backend/src/services/report.py
"""
import sqlalchemy as sa


def query():
    return sa.text("SELECT 1")
