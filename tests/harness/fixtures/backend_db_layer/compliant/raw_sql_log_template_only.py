"""v1.3.1 S13 — pre-v1.3.0 false positive: the docstring contains
'INSERT failed because of …' as natural prose. The regex matched it.
The AST-aware scan must NOT fire here because no string literal in the
file is a real SQL query.

Pretend-path: backend/src/services/runner.py
"""


def run(operation):
    # If something fails: "INSERT failed because of permissions" — a
    # log message, not a query. Pre-v1.3.0 the regex matched this line.
    return operation
