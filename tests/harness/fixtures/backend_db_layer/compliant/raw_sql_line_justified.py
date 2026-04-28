"""v1.3.1 S14 — `# RAW-SQL-JUSTIFIED:` on the immediately-preceding
line silences this finding. Pre-v1.3.0 the file-scope check let any
single token anywhere silence every SQL warning forever (S-DB3).

Pretend-path: backend/src/storage/analytics.py
"""


def query():
    # RAW-SQL-JUSTIFIED: cohort aggregation cannot use SQLModel safely.
    return "SELECT COUNT(*) FROM incidents"
