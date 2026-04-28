# v1.3.0 S17 (S-CV2) — `from . import x` (single-dot bare imports
# common in __init__.py re-exports) must NOT fire Q18.no-relative-
# import-backend. Pre-v1.3.0 false positive.
from . import sibling  # noqa: F401
