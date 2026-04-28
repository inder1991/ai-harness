"""v1.3.1 S13 — pre-v1.3.0 fired Q8.raw-sql-unjustified on the docstring
"INSERT failed because of …" because the regex walked the source line by
line. The AST-aware scan correctly fires on the actual query string but
NOT the docstring (which lives in a separate Constant). This fixture
exercises the remaining true-positive path: an actual query as a
string literal.

Pretend-path: backend/src/services/report.py
"""

QUERY = "INSERT INTO orders (id) VALUES (1)"
