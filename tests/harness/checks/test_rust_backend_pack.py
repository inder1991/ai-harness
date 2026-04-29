"""Sprint 4 / S4.4 — rust-backend starter pack tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures/rust-backend"


@pytest.mark.parametrize(
    "check,fixture,rule,pretend",
    [
        ("rust-backend/rust_http_wrapper", "uses_reqwest.rs",
         "RQ7.no-reqwest-outside-wrapper", "src/handlers/users.rs"),
        ("rust-backend/rust_db_quarantine", "raw_sqlx_query.rs",
         "RQ8.raw-sql-outside-adapter", "src/handlers/users.rs"),
        ("rust-backend/rust_error_handling", "unwrap_in_spine.rs",
         "RQ12.no-unwrap-in-spine", "src/handlers/users.rs"),
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
        ("rust-backend/rust_http_wrapper", "wrapper_uses_reqwest.rs",
         "src/http/client.rs"),
        ("rust-backend/rust_db_quarantine", "adapter_sqlx_query.rs",
         "src/db/users.rs"),
        ("rust-backend/rust_error_handling", "clean_handler.rs",
         "src/handlers/config.rs"),
    ],
)
def test_compliant_fixture_silent(check: str, fixture: str, pretend: str) -> None:
    assert_check_silent(
        check_name=check,
        target=FIXTURE_ROOT / "compliant" / fixture,
        pretend_path=pretend,
    )


def test_test_files_exempt_from_unwrap_check() -> None:
    """tests/ paths and *_test.rs files are exempt from RQ12."""
    assert_check_silent(
        check_name="rust-backend/rust_error_handling",
        target=FIXTURE_ROOT / "violation" / "unwrap_in_spine.rs",
        pretend_path="src/users_test.rs",
    )
