"""v1.3.0 S4 — STDLIB_FIRST_PARTY now derives from sys.stdlib_module_names.

Pre-v1.3.0 the set was hand-maintained and missed tomllib (3.11+),
which the check itself imports. Using sys.stdlib_module_names guarantees
the list stays in sync with whatever Python the consumer is running.

Closes audit finding S-DP4.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from dependency_policy import STDLIB_FIRST_PARTY  # noqa: E402


def test_tomllib_is_stdlib():
    """tomllib lives in stdlib since Python 3.11. Pre-v1.3.0 the
    hand-maintained set didn't list it, so any backend file importing
    tomllib was flagged as Q11.spine-import-unlisted."""
    assert "tomllib" in STDLIB_FIRST_PARTY


def test_zoneinfo_is_stdlib():
    """zoneinfo since Python 3.9."""
    assert "zoneinfo" in STDLIB_FIRST_PARTY


def test_graphlib_is_stdlib():
    """graphlib since Python 3.9."""
    assert "graphlib" in STDLIB_FIRST_PARTY


def test_first_party_namespaces_present():
    """Backend/frontend namespace shortcuts must remain accepted."""
    for name in ("backend", "src", "tests", "frontend"):
        assert name in STDLIB_FIRST_PARTY


def test_classic_modules_still_covered():
    """Regression: every module in the pre-v1.3.0 hardcoded set must
    still be in the auto-derived set."""
    legacy = {
        "asyncio", "json", "logging", "os", "re", "sys", "typing", "pathlib",
        "datetime", "collections", "functools", "itertools", "uuid", "enum",
        "dataclasses", "abc", "hashlib", "math", "io", "time", "random",
        "subprocess", "shutil", "tempfile", "argparse", "warnings", "string",
        "operator", "copy", "secrets", "base64", "hmac", "urllib", "concurrent",
        "contextlib", "inspect", "pickle", "struct", "weakref", "csv",
    }
    missing = legacy - STDLIB_FIRST_PARTY
    assert not missing, f"runtime stdlib set lost {missing}"
