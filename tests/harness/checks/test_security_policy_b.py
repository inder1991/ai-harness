"""H.1c.2 — security_policy_b check tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

CHECK = "security_policy_b"
FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures" / CHECK


@pytest.mark.parametrize(
    "fixture_name,expected_rule",
    [
        ("post_no_auth.py", "Q13.route-needs-auth"),
        ("post_no_rate_limit.py", "Q13.route-needs-rate-limit"),
        ("post_no_csrf.py", "Q13.route-needs-csrf"),
        # v1.3.0 S9 — substring decoy `NoCsrfProtectNeeded` no longer
        # passes the CSRF check.
        ("csrf_substring_decoy.py", "Q13.route-needs-csrf"),
    ],
)
def test_violation_fires(fixture_name: str, expected_rule: str) -> None:
    assert_check_fires(
        check_name=CHECK,
        target=FIXTURE_ROOT / "violation" / fixture_name,
        expected_rule=expected_rule,
        pretend_path="backend/src/api/routes_v4.py",
    )


@pytest.mark.parametrize(
    "fixture_name",
    [
        "post_full_protection.py",
        # v1.3.0 S8 — Annotated[T, Depends(f)] satisfies auth.
        "annotated_depends_auth.py",
        # v1.3.0 S9 — FastAPI(middleware=[...]) constructor exempts CSRF.
        "global_csrf_constructor.py",
        # v1.3.0 S10 — module-Constant route path resolved + checked.
        "route_path_constant.py",
    ],
)
def test_compliant_silent(fixture_name: str) -> None:
    assert_check_silent(
        check_name=CHECK,
        target=FIXTURE_ROOT / "compliant" / fixture_name,
        pretend_path="backend/src/api/routes_v4.py",
    )
