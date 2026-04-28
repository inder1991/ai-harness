"""v1.3.1 S15 — `self.cursor.execute(...)` (attribute-chain receiver)
must fire Q8.execute-quarantine. Pre-v1.3.0 only matched bare `cursor`
Name receivers (S-DB4).

Pretend-path: backend/src/services/migrate.py
"""


class Migrator:
    def __init__(self, cursor):
        self.cursor = cursor

    def run(self, sql):
        self.cursor.execute(sql)
