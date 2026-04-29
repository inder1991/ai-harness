"""Sprint 4 / S4.2 — node-backend pack tests.

Each violation fixture must produce >= 1 ERROR with the matching rule id.
Each compliant fixture must produce zero ERRORs.

Note: tests run the check as a subprocess via _helpers (matches the
Python-pack pattern). Each check lives at
`.harness/checks/node-backend/<name>.py`, so the check_name passed to
_helpers includes the subdir.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "harness"))

from _helpers import assert_check_fires, assert_check_silent  # noqa: E402

FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures/node-backend"


@pytest.mark.parametrize(
    "check,fixture,rule,pretend",
    [
        # node_logging
        ("node-backend/node_logging", "template_in_logger.ts",
         "NQ16.no-template-in-logger", "backend/src/services/x.ts"),
        ("node-backend/node_logging", "console_log_in_spine.ts",
         "NQ16.no-console-log-in-spine", "backend/src/services/x.ts"),
        # node_async_correctness
        ("node-backend/node_async_correctness", "uses_axios.ts",
         "NQ7.no-axios-outside-wrapper", "backend/src/api/x.ts"),
        ("node-backend/node_async_correctness", "execsync_in_async.ts",
         "NQ7.no-execsync-in-async", "backend/src/api/x.ts"),
        # node_db_layer
        ("node-backend/node_db_layer", "raw_queryraw.ts",
         "NQ8.queryraw-outside-analytics", "backend/src/api/x.ts"),
        # node_validation_contracts
        ("node-backend/node_validation_contracts", "lax_request_schema.ts",
         "NQ10.request-needs-strict", "backend/src/api/x.ts"),
        ("node-backend/node_validation_contracts", "mutable_response_schema.ts",
         "NQ10.response-needs-readonly", "backend/src/api/x.ts"),
        # node_testing
        ("node-backend/node_testing", "live_llm_in_test.test.ts",
         "NQ9.no-live-llm-in-tests", "tests/x.test.ts"),
        ("node-backend/node_testing", "raw_fetch_in_test.test.ts",
         "NQ9.no-raw-fetch-in-tests", "tests/x.test.ts"),
        # node_security_routes
        ("node-backend/node_security_routes", "unauth_post_route.ts",
         "NQ13.mutating-route-needs-auth", "backend/src/routes/users.ts"),
        # node_storage_isolation
        ("node-backend/node_storage_isolation", "fs_outside_storage.ts",
         "NQ8.fs-outside-storage-boundary", "backend/src/api/x.ts"),
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
    "fixture_dir,rule",
    [
        ("dev_in_runtime", "NQ11.runtime-needs-dev"),
        ("runtime_in_dev", "NQ11.dev-shouldnt-be-runtime"),
    ],
)
def test_dependency_policy_fires(fixture_dir: str, rule: str) -> None:
    assert_check_fires(
        check_name="node-backend/node_dependency_policy",
        target=FIXTURE_ROOT / "violation" / fixture_dir,
        expected_rule=rule,
        pretend_path=f"{fixture_dir}/package.json",
    )


@pytest.mark.parametrize(
    "check,fixture,pretend",
    [
        ("node-backend/node_logging", "structured_logger.ts",
         "backend/src/services/x.ts"),
        ("node-backend/node_async_correctness", "wrapper_uses_axios.ts",
         "src/lib/http.ts"),
        ("node-backend/node_async_correctness", "exec_in_sync.ts",
         "backend/src/utils/sh.ts"),
        ("node-backend/node_db_layer", "analytics_uses_queryraw.ts",
         "db/analytics.ts"),
        ("node-backend/node_validation_contracts", "strict_request_schema.ts",
         "backend/src/api/x.ts"),
        ("node-backend/node_testing", "mocked_test.test.ts",
         "tests/x.test.ts"),
        ("node-backend/node_security_routes", "auth_post_route.ts",
         "backend/src/routes/users.ts"),
        ("node-backend/node_storage_isolation", "storage_uses_fs.ts",
         "backend/src/storage/loader.ts"),
    ],
)
def test_compliant_fixture_silent(check: str, fixture: str, pretend: str) -> None:
    assert_check_silent(
        check_name=check,
        target=FIXTURE_ROOT / "compliant" / fixture,
        pretend_path=pretend,
    )


def test_dependency_policy_clean_package_silent() -> None:
    assert_check_silent(
        check_name="node-backend/node_dependency_policy",
        target=FIXTURE_ROOT / "compliant" / "clean_package",
        pretend_path="clean_package/package.json",
    )


def test_ts_parser_handles_jsx_decorators_and_js() -> None:
    """The wrapper supports .ts/.tsx/.js/.jsx (S0.1 ADR acceptance criterion)."""
    sys.path.insert(0, str(REPO_ROOT / ".harness/checks/node-backend"))
    from _ts_parser import parse, supported_suffixes  # noqa: E402

    assert ".ts" in supported_suffixes()
    assert ".tsx" in supported_suffixes()
    assert ".js" in supported_suffixes()
    assert ".jsx" in supported_suffixes()

    # Decorator (NestJS-style) — must parse without error in TS grammar.
    sample_ts = REPO_ROOT / "tests/harness/fixtures/node-backend/violation/uses_axios.ts"
    ast = parse(sample_ts)
    assert not ast.has_errors()
    imports = list(ast.find(("import_statement",)))
    assert len(imports) == 1
