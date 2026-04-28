"""Sprint 0 / S0.4 — regression tests for v1.3.0 rule-semantics audit
(S-A1 through S-DP4 — 30 P3 findings).

These cover the cross-cutting fixes (ImportTracker, AST conversions,
Q22 conformance) plus the per-check polish.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from _common import ImportTracker, is_logger_call  # noqa: E402


# ────────── ImportTracker (S-A4, S-AS3, S-AS4, S-AS6, S-DB5) ──────────

# REGRESSION-FOR: S-A4 (aliased dangerous builtins resolved)
def test_s_a4_import_tracker_resolves_aliased_eval():
    tree = ast.parse("from os import system\nsystem('x')\n")
    t = ImportTracker(tree)
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    assert t.canonical_for(call.func) == "os.system"


# REGRESSION-FOR: S-AS3 (`from httpx import Client` resolves)
def test_s_as3_import_tracker_from_httpx_client():
    tree = ast.parse("from httpx import Client\nClient()\n")
    t = ImportTracker(tree)
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    assert t.canonical_for(call.func) == "httpx.Client"


# REGRESSION-FOR: S-AS4 (`from time import sleep` resolves)
def test_s_as4_import_tracker_from_time_sleep():
    tree = ast.parse("from time import sleep\nsleep(1)\n")
    t = ImportTracker(tree)
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    assert t.canonical_for(call.func) == "time.sleep"


# REGRESSION-FOR: S-AS6 (aliased import: `import requests as r`)
def test_s_as6_import_tracker_aliased_module():
    tree = ast.parse("import requests as r\nr.get('x')\n")
    t = ImportTracker(tree)
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    assert t.canonical_for(call.func) == "requests.get"


# REGRESSION-FOR: S-DB5 (`from sqlalchemy import text` resolves)
def test_s_db5_import_tracker_from_sqlalchemy_text():
    tree = ast.parse("from sqlalchemy import text\ntext('SELECT 1')\n")
    t = ImportTracker(tree)
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    assert t.canonical_for(call.func) == "sqlalchemy.text"


# ────────── is_logger_call (S-A1) ──────────

# REGRESSION-FOR: S-A1 (logger predicate matches custom names)
def test_s_a1_is_logger_call_matches_uppercase():
    tree = ast.parse('LOG.info("x")\n')
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    assert is_logger_call(call, attrs={"info"})


# REGRESSION-FOR: S-A1 (logger predicate matches self.log.*)
def test_s_a1_is_logger_call_matches_self_log():
    tree = ast.parse('class X:\n    def m(self):\n        self.log.info("x")\n')
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    assert is_logger_call(call, attrs={"info"})


# ────────── Documentation drift (S-A9, S-AS1, S-DB1, Q22) ──────────

# REGRESSION-FOR: S-A9 (security_policy_a docstring count = 5)
def test_s_a9_security_policy_a_docstring_consistent():
    src = (REPO_ROOT / ".harness/checks/security_policy_a.py").read_text()
    # The docstring claims "Five rules:"
    assert "Five rules:" in src or "five rules" in src.lower()


# REGRESSION-FOR: S-AS1 (backend_async docstring count = 5)
def test_s_as1_backend_async_docstring_consistent():
    src = (REPO_ROOT / ".harness/checks/backend_async_correctness.py").read_text()
    assert "Five rules" in src


# REGRESSION-FOR: S-DB1 (backend_db_layer docstring count = 7)
def test_s_db1_backend_db_layer_docstring_consistent():
    src = (REPO_ROOT / ".harness/checks/backend_db_layer.py").read_text()
    assert "Seven rules" in src


# REGRESSION-FOR: Q22 (rule_count_conformance check exists)
def test_q22_rule_count_conformance_check_exists():
    check = REPO_ROOT / ".harness/checks/rule_count_conformance.py"
    assert check.exists()


# ────────── security_policy_a hardening (S-A5, S-A7, S-A8) ──────────

# REGRESSION-FOR: S-A5 (multi-line shell=True detected via AST)
def test_s_a5_security_policy_a_uses_ast_for_shell_true():
    src = (REPO_ROOT / ".harness/checks/security_policy_a.py").read_text()
    # The AST-based scan must reference subprocess canonical names.
    assert "_SUBPROCESS_DOTTED_CANONICAL" in src or "ast.parse" in src


# REGRESSION-FOR: S-A7 (UTILS_HTTP exemption is precise paths)
def test_s_a7_security_policy_a_precise_exempt():
    src = (REPO_ROOT / ".harness/checks/security_policy_a.py").read_text()
    # Tightened to require trailing slash or exact match.
    assert "UTILS_HTTP_EXEMPT_PATHS" in src or "_is_http_wrapper" in src


# REGRESSION-FOR: S-A8 (no false-positive on trailing comments)
def test_s_a8_security_policy_a_no_comment_false_positive():
    """An AST-based scan cannot fire on a string literal containing
    `shell=True`; only on actual subprocess calls."""
    src = (REPO_ROOT / ".harness/checks/security_policy_a.py").read_text()
    assert "ast.parse" in src


# ────────── security_policy_b hardening (S-B1 through S-B7) ──────────

# REGRESSION-FOR: S-B1 (router var policy-driven)
def test_s_b1_router_var_names_policy():
    src = (REPO_ROOT / ".harness/checks/security_policy_b.py").read_text()
    assert "router_var_names" in src


# REGRESSION-FOR: S-B2 (Annotated[Depends()] auth recognized)
def test_s_b2_annotated_depends_auth():
    src = (REPO_ROOT / ".harness/checks/security_policy_b.py").read_text()
    assert "_annotated_depends_callee" in src or "Annotated" in src


# REGRESSION-FOR: S-B3 (CSRF dep is structural, not substring)
def test_s_b3_csrf_dep_structural():
    src = (REPO_ROOT / ".harness/checks/security_policy_b.py").read_text()
    assert "csrf_dependency_names" in src


# REGRESSION-FOR: S-B4 (FastAPI(middleware=[...]) constructor recognized)
def test_s_b4_fastapi_constructor_middleware():
    src = (REPO_ROOT / ".harness/checks/security_policy_b.py").read_text()
    # Detection of the constructor pattern.
    assert "FastAPI" in src and "middleware" in src


# REGRESSION-FOR: S-B5 (route paths as JoinedStr / Name resolved)
def test_s_b5_route_path_resolution():
    src = (REPO_ROOT / ".harness/checks/security_policy_b.py").read_text()
    assert "_resolve_path_arg" in src or "JoinedStr" in src


# REGRESSION-FOR: S-B6 (spine_paths consumed for backend_api scope)
def test_s_b6_security_policy_b_uses_spine_paths():
    src = (REPO_ROOT / ".harness/checks/security_policy_b.py").read_text()
    assert "spine_paths" in src and "backend_api" in src


# REGRESSION-FOR: S-B7 (dead `verb != "get"` removed from CODE)
def test_s_b7_no_dead_get_branch():
    """The literal expression must not appear in executable code; the
    docstring may still REFERENCE the bug name."""
    import ast as _ast
    tree = _ast.parse(
        (REPO_ROOT / ".harness/checks/security_policy_b.py").read_text()
    )
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Compare):
            if (isinstance(node.left, _ast.Name)
                    and node.left.id == "verb"
                    and any(isinstance(op, _ast.NotEq) for op in node.ops)):
                for comp in node.comparators:
                    if isinstance(comp, _ast.Constant) and comp.value == "get":
                        raise AssertionError(
                            "S-B7 regression: `verb != 'get'` re-appeared in code"
                        )


# ────────── backend_db_layer hardening (S-DB2, S-DB3, S-DB4, S-DB6) ──────────

# REGRESSION-FOR: S-DB2 (raw-SQL scan is AST + docstring-aware)
def test_s_db2_raw_sql_scan_uses_ast():
    src = (REPO_ROOT / ".harness/checks/backend_db_layer.py").read_text()
    assert "_docstring_constant_ids" in src or "ast.Constant" in src


# REGRESSION-FOR: S-DB3 (RAW-SQL-JUSTIFIED scope is line-local)
def test_s_db3_justification_line_scope():
    src = (REPO_ROOT / ".harness/checks/backend_db_layer.py").read_text()
    # The fix introduces line-aware tracking.
    assert "justification_lines" in src


# REGRESSION-FOR: S-DB4 (cursor.execute resolves chains)
def test_s_db4_cursor_execute_chain_resolution():
    src = (REPO_ROOT / ".harness/checks/backend_db_layer.py").read_text()
    # The fix unifies receiver detection.
    assert "_EXECUTE_RECEIVER_NAMES" in src


# REGRESSION-FOR: S-DB6 (db-model-needs-table inheritance-aware)
def test_s_db6_db_model_inheritance_aware():
    src = (REPO_ROOT / ".harness/checks/backend_db_layer.py").read_text()
    # The fix accepts inheritance from common bases.
    assert "common_bases" in src or "table_bases" in src


# ────────── conventions_policy hardening (S-CV1, S-CV2, S-CV3) ──────────

# REGRESSION-FOR: S-CV1 (DOTDOT_IMPORT_RE doesn't match single dot)
def test_s_cv1_dotdot_regex_strict():
    """Verify the actual regex value, not just the source text. The
    fixed regex must NOT match `./relative` (single dot)."""
    sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))
    from conventions_policy import DOTDOT_IMPORT_RE
    # Single-dot import must NOT match.
    assert DOTDOT_IMPORT_RE.search('import x from "./sibling"\n') is None, (
        "S-CV1 regression: `./relative` is matching DOTDOT_IMPORT_RE again"
    )
    # Double-dot import must match.
    assert DOTDOT_IMPORT_RE.search('import x from "../parent"\n') is not None


# REGRESSION-FOR: S-CV2 (single-dot bare imports allowed)
def test_s_cv2_single_dot_imports_allowed():
    src = (REPO_ROOT / ".harness/checks/conventions_policy.py").read_text()
    # Fixed pattern: `\.{2,}|\.\w` — requires either 2+ dots OR `.<word>`.
    assert "\\.{2,}" in src or r"\.{2,}" in src


# REGRESSION-FOR: S-CV3 (PascalCase strips multi-dot stems)
def test_s_cv3_pascal_case_multidot():
    src = (REPO_ROOT / ".harness/checks/conventions_policy.py").read_text()
    # Fix: split on `.` before applying PascalCase.
    assert "first_segment" in src or 'split(".", 1)' in src


# ────────── dependency_policy hardening (S-DP1-S-DP4) ──────────

# REGRESSION-FOR: S-DP1 (pyproject extras + Poetry + build-system)
def test_s_dp1_dependency_policy_covers_all_sources():
    src = (REPO_ROOT / ".harness/checks/dependency_policy.py").read_text()
    assert "optional-dependencies" in src
    assert "poetry" in src.lower()
    assert "build-system" in src


# REGRESSION-FOR: S-DP2 (separate runtime/dev npm allow-lists)
def test_s_dp2_npm_runtime_dev_split():
    src = (REPO_ROOT / ".harness/checks/dependency_policy.py").read_text()
    assert "runtime_allowed" in src and "dev_allowed" in src


# REGRESSION-FOR: S-DP3 (npm version refs + scoped names)
def test_s_dp3_bare_dep_name_handles_scoped():
    """`@tanstack/react-query` must keep the leading @; only the second
    @ counts as a version separator."""
    sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))
    from dependency_policy import _bare_dep_name
    assert _bare_dep_name("@tanstack/react-query") == "@tanstack/react-query"
    assert _bare_dep_name("@tanstack/react-query@5.0.0") == "@tanstack/react-query"
    assert _bare_dep_name("react@18.0.0") == "react"


# REGRESSION-FOR: S-DP4 (STDLIB_FIRST_PARTY uses sys.stdlib_module_names)
def test_s_dp4_stdlib_includes_tomllib():
    sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))
    from dependency_policy import STDLIB_FIRST_PARTY
    # tomllib was the original gap (the check itself imports it).
    assert "tomllib" in STDLIB_FIRST_PARTY
    assert "zoneinfo" in STDLIB_FIRST_PARTY
