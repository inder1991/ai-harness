"""Sprint 4 / S4.4 — go-backend starter pack tests.

3 checks × violation/compliant fixtures. Mirrors test_node_backend_pack.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures/go-backend"


@pytest.mark.parametrize(
    "check,fixture,rule,pretend",
    [
        ("go-backend/go_http_wrapper", "uses_net_http.go",
         "GQ7.no-net-http-outside-wrapper", "internal/handlers/users.go"),
        ("go-backend/go_db_quarantine", "raw_db_call.go",
         "GQ8.raw-sql-outside-adapter", "internal/handlers/users.go"),
        ("go-backend/go_error_handling", "discarded_err.go",
         "GQ12.no-discarded-error", "internal/handlers/users.go"),
        ("go-backend/go_error_handling", "panic_on_err.go",
         "GQ12.no-panic-on-error", "internal/handlers/users.go"),
    ],
)
def test_violation_fixture_fires(check: str, fixture: str, rule: str, pretend: str) -> None:
    assert_check_fires(
        check_name=check,
        target=FIXTURE_ROOT / "violation" / fixture,
        expected_rule=rule,
        pretend_path=pretend,
    )


@pytest.mark.parametrize(
    "check,fixture,pretend",
    [
        ("go-backend/go_http_wrapper", "wrapper_imports_net_http.go",
         "pkg/httpclient/client.go"),
        ("go-backend/go_db_quarantine", "adapter_db_call.go",
         "pkg/dbadapter/users.go"),
        ("go-backend/go_error_handling", "clean_handler.go",
         "internal/handlers/clean.go"),
    ],
)
def test_compliant_fixture_silent(check: str, fixture: str, pretend: str) -> None:
    assert_check_silent(
        check_name=check,
        target=FIXTURE_ROOT / "compliant" / fixture,
        pretend_path=pretend,
    )


def test_test_files_exempt_from_error_handling() -> None:
    """*_test.go files don't fire GQ12 — test code can `_ = err` legitimately."""
    assert_check_silent(
        check_name="go-backend/go_error_handling",
        target=FIXTURE_ROOT / "violation" / "discarded_err.go",
        pretend_path="internal/handlers/users_test.go",
    )
