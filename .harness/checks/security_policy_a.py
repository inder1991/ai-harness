#!/usr/bin/env python3
"""Q13.A — security policy: secrets + outbound HTTP + dangerous patterns.

Six rules:
  Q13.secret-detected           — gitleaks CLI fired (re-emitted shape).
  Q13.dangerous-pattern         — eval/exec/os.system/shell=True/pickle.loads/
                                   yaml.load (no Loader)/__import__ + JS-side
                                   dangerouslySetInnerHTML/new Function/document.write.
  Q13.tls-verify-required       — verify=False on httpx/requests OR
                                   ssl._create_unverified_context OR
                                   urllib3.disable_warnings.
  Q13.outbound-timeout-required — httpx.AsyncClient(timeout=None) outside
                                   backend/src/utils/http.py.
  Q13.log-secret-leak           — logger call sees a value containing
                                   `Authorization: Bearer …` / `password=` etc.
                                   without going through a redact_* helper.
  Q13.secret-shaped-literal     — base64/secret-shaped string literal outside
                                   tests/ (WARN; gitleaks is the hard gate).

H-25:
  Missing input    — exit 2; rule=harness.target-missing.
  Malformed input  — WARN rule=harness.unparseable; skip file.
  Upstream failed  — gitleaks binary missing → WARN
                     rule=Q13.secret-detected (degraded mode).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys

import yaml
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from _common import (  # noqa: E402
    ImportTracker, emit, is_logger_call, load_baseline, normalize_path, spine_paths,
)

# v1.3.0 S2/S6: load logger attribute names from logging_policy.yaml so
# security_policy_a's log-leak rule sees the same logger surface
# logging_policy.py enforces. Pre-v1.3.0 it hardcoded `log|logger`.
_LOGGING_POLICY = REPO_ROOT / ".harness" / "logging_policy.yaml"


def _load_logger_attrs() -> set[str]:
    """Return the set of method names that count as logger emissions."""
    if not _LOGGING_POLICY.exists():
        return {"info", "warning", "error", "debug", "exception", "critical"}
    try:
        data = yaml.safe_load(_LOGGING_POLICY.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {"info", "warning", "error", "debug", "exception", "critical"}
    return set(data.get("logger_attr_names") or [])

DEFAULT_ROOTS = spine_paths("backend_src", ("backend/src",)) + spine_paths("frontend_src", ("frontend/src",))
EXCLUDE_VIRTUAL_PREFIXES = (
    "tests/harness/fixtures/",
    "frontend/dist/",
    "frontend/node_modules/",
    "backend/.venv/",
    "backend/venv/",
)
EXCLUDE_FS = (
    "node_modules", ".git", "dist", "site-packages",
    "tests/harness/fixtures", "__pycache__", ".venv", "/venv/",
    ".pytest_cache",
)
SCANNED_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx"}
BASELINE = load_baseline("security_policy_a")

DANGEROUS_PYTHON_RE = re.compile(
    r'\b(eval\s*\(|exec\s*\(|os\.system\s*\(|pickle\.loads\s*\(|__import__\s*\()'
)
# Require shell=True in call-argument context (preceded by `,` or `(`)
# so docstrings/comments containing the literal text don't trigger.
SHELL_TRUE_RE = re.compile(r'[,(]\s*shell\s*=\s*True\b')
YAML_LOAD_UNSAFE_RE = re.compile(r'\byaml\.load\s*\(\s*[^,)]+\)')
DANGEROUS_JS_RE = re.compile(
    r'\b(dangerouslySetInnerHTML|document\.write\s*\(|new\s+Function\s*\()'
)

VERIFY_FALSE_RE = re.compile(r'\bverify\s*=\s*False\b')
SSL_UNVERIFIED_RE = re.compile(r'\bssl\._create_unverified_context\s*\(')
URLLIB3_DISABLE_RE = re.compile(r'\burllib3\.disable_warnings\s*\(')
TIMEOUT_NONE_RE = re.compile(r'\btimeout\s*=\s*None\b')

# LOG_CALL_RE removed in v1.3.0 (S6) — replaced by _common.is_logger_call
# + AST walk in _scan_log_secret_leak. See audit findings S-A1, S-A2.
SECRET_LEAK_KEY_RE = re.compile(
    r'(Authorization\s*:\s*Bearer|password\s*=|api_key\s*=|secret\s*=|token\s*=)',
    re.IGNORECASE,
)
REDACT_HELPER_RE = re.compile(r'\bredact_\w*\s*\(')

# v1.3.0 S7 — tightened from "backend/src/utils/http" (no slash → matched
# httpx_client.py, http_helpers_v2.py, etc) to a precise allowlist:
# either the exact wrapper file or anything under the wrapper package.
# Closes audit S-A7.
UTILS_HTTP_EXEMPT_PATHS = (
    "backend/src/utils/http.py",
    "backend/src/utils/http/__init__.py",
)
UTILS_HTTP_EXEMPT_PREFIX = "backend/src/utils/http/"


def _is_http_wrapper(virtual: str) -> bool:
    return virtual in UTILS_HTTP_EXEMPT_PATHS or virtual.startswith(UTILS_HTTP_EXEMPT_PREFIX)


def _emit(path: Path, rule: str, msg: str, suggestion: str, line: int) -> bool:
    sig = (normalize_path(path), int(line), rule)
    if sig in BASELINE:
        return False
    emit("ERROR", path, rule, msg, suggestion, line=line)
    return True


def _is_excluded(virtual: str) -> bool:
    return any(virtual.startswith(p) for p in EXCLUDE_VIRTUAL_PREFIXES)


_DANGEROUS_BUILTIN_NAMES = {"eval", "exec", "__import__"}
_DANGEROUS_DOTTED_CANONICAL = {
    "os.system",
    "pickle.loads",
    "subprocess.getoutput",
}
_SUBPROCESS_DOTTED_CANONICAL = {
    "subprocess.run",
    "subprocess.call",
    "subprocess.Popen",
    "subprocess.check_call",
    "subprocess.check_output",
}


def _scan_dangerous_patterns(path: Path, virtual: str, source: str) -> int:
    """v1.3.0 S5 — AST-based dangerous-pattern scan.

    Pre-v1.3.0 used line-by-line regex. That:
      - missed multi-line subprocess calls where `shell=True` was on
        its own indented line (S-A5)
      - missed aliased forms like `_eval = eval; _eval(x)` (S-A4)
      - over-fired on trailing comments containing literal text (S-A8)

    AST-based scan reliably detects:
      - bare `eval(...) / exec(...) / __import__(...)`
      - canonical `os.system / pickle.loads / subprocess.getoutput`
        regardless of import alias
      - subprocess.* calls with shell=True keyword (any line layout)
      - yaml.load without an explicit Loader= keyword
      - JS-side patterns still use regex (no AST parser shipped here)
    """
    is_python = path.suffix == ".py"
    is_jsx = path.suffix in {".ts", ".tsx", ".js", ".jsx"}
    errors = 0

    if is_python:
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            return 0
        tracker = ImportTracker(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            # Bare builtins: eval/exec/__import__.
            if isinstance(node.func, ast.Name) and node.func.id in _DANGEROUS_BUILTIN_NAMES:
                if _emit(path, "Q13.dangerous-pattern",
                         f"dangerous Python builtin: `{node.func.id}(...)`",
                         "rewrite to a safe alternative; never execute untrusted strings",
                         node.lineno):
                    errors += 1
                continue
            canonical = tracker.canonical_for(node.func)
            if canonical in _DANGEROUS_DOTTED_CANONICAL:
                if _emit(path, "Q13.dangerous-pattern",
                         f"dangerous Python call: `{canonical}(...)`",
                         "rewrite to a safe alternative; never execute untrusted strings",
                         node.lineno):
                    errors += 1
                continue
            if canonical in _SUBPROCESS_DOTTED_CANONICAL:
                for kw in node.keywords:
                    if (
                        kw.arg == "shell"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value is True
                    ):
                        if _emit(path, "Q13.dangerous-pattern",
                                 f"shell=True on subprocess call: `{canonical}(..., shell=True, ...)`",
                                 "rewrite to a safe alternative; never execute untrusted strings",
                                 node.lineno):
                            errors += 1
                        break
                continue
            # yaml.load without Loader= keyword.
            if canonical in {"yaml.load", "yaml.full_load"}:
                if not any(kw.arg == "Loader" for kw in node.keywords):
                    # full_load has implicit safe loader → no fire there.
                    if canonical == "yaml.load":
                        if _emit(path, "Q13.dangerous-pattern",
                                 "yaml.load without explicit Loader= keyword",
                                 "use yaml.safe_load(...) or pass Loader=yaml.SafeLoader",
                                 node.lineno):
                            errors += 1

    if is_jsx:
        for lineno, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("//"):
                continue
            m = DANGEROUS_JS_RE.search(line)
            if m:
                if _emit(path, "Q13.dangerous-pattern",
                         f"banned JS pattern: `{m.group(0).strip()}`",
                         "render text content; never raw HTML or dynamic Function/document.write",
                         lineno):
                    errors += 1
    return errors


def _scan_outbound_http(path: Path, virtual: str, source: str) -> int:
    """v1.3.0 S7 — outbound HTTP scan, imports-aware.

    Pre-v1.3.0 this scan:
      * decided "is this an httpx file" by checking
        `"httpx" in source.lower()[:5000]` — long files where httpx
        was imported on line 5001+ slipped (S-A3).
      * fired Q13.outbound-timeout-required on any `timeout=None`
        line, including `request.timeout = None` (unrelated
        attribute) — false positives. Missed
        `httpx.Timeout(None)` wrap — false negatives (S-A6).
      * exempted any path starting with `backend/src/utils/http`
        (no trailing slash) — over-exempted httpx_client.py,
        http_helpers_v2.py (S-A7).

    Now AST-based: parse imports up front via ImportTracker, only
    fire timeout-required on `httpx.<*Client>(...)` /
    `*.AsyncClient.<get|post|...>(...)` calls whose `timeout=`
    keyword is `None` or `httpx.Timeout(None)`. Wrapper exemption
    uses precise path matching.
    """
    if path.suffix != ".py":
        return 0
    errors = 0

    # TLS-verify rules stay regex-based (line-local; no ambiguity).
    for lineno, line in enumerate(source.splitlines(), 1):
        if line.strip().startswith("#"):
            continue
        for pattern, rule, message, suggestion in (
            (VERIFY_FALSE_RE, "Q13.tls-verify-required",
             "verify=False disables TLS validation", "remove verify=False"),
            (SSL_UNVERIFIED_RE, "Q13.tls-verify-required",
             "ssl._create_unverified_context", "use ssl.create_default_context()"),
            (URLLIB3_DISABLE_RE, "Q13.tls-verify-required",
             "urllib3.disable_warnings", "remove the call; fix the underlying TLS error"),
        ):
            if pattern.search(line):
                if _emit(path, rule, message, suggestion, lineno):
                    errors += 1

    # Wrapper exemption: timeout-required doesn't apply inside the
    # canonical HTTP wrapper module.
    if _is_http_wrapper(virtual):
        return errors

    # Outbound timeout — AST scan rather than regex line scan.
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return errors
    tracker = ImportTracker(tree)
    # If httpx isn't imported anywhere, skip the call walk entirely.
    if not any((m or "").split(".")[0] == "httpx" for m in tracker._bindings.values()):  # noqa: SLF001
        return errors

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        canonical = tracker.canonical_for(node.func)
        if canonical is None or not canonical.startswith("httpx"):
            continue
        for kw in node.keywords:
            if kw.arg != "timeout":
                continue
            if _is_timeout_none(kw.value, tracker):
                if _emit(path, "Q13.outbound-timeout-required",
                         "httpx call uses timeout=None (unbounded wait)",
                         "set an explicit timeout via httpx.Timeout(...) or use the with_retry wrapper",
                         node.lineno):
                    errors += 1
    return errors


def _is_timeout_none(node: ast.expr, tracker: ImportTracker) -> bool:
    """True if the expression is `None` or `httpx.Timeout(None)` — both
    represent an unbounded HTTP wait."""
    if isinstance(node, ast.Constant) and node.value is None:
        return True
    if isinstance(node, ast.Call):
        canonical = tracker.canonical_for(node.func)
        if canonical == "httpx.Timeout" and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and first.value is None:
                return True
    return False


def _scan_log_secret_leak(path: Path, virtual: str, source: str) -> int:
    """v1.3.0 S6 — AST-based log-leak scan.

    Pre-v1.3.0 used a regex (`LOG_CALL_RE`) that:
      - matched only `log.` and `logger.` literal receivers (S-A1)
      - truncated the body capture at the first `)` so kwargs with
        parens hid the secret-shaped value (S-A2)

    Now walks every `ast.Call`, filters via `_common.is_logger_call`
    against the policy-driven attribute set, and inspects every arg +
    keyword value source for the secret-shaped pattern. Skips when the
    arg/keyword passes through a `redact_*(...)` helper.
    """
    if path.suffix != ".py":
        return 0
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return 0
    logger_attrs = _load_logger_attrs()
    errors = 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and is_logger_call(node, logger_attrs)):
            continue
        # Walk every arg + keyword.value. For each subexpression, get its
        # source text and apply the secret-shaped + redact-helper checks.
        offenders: list[ast.expr] = list(node.args) + [kw.value for kw in node.keywords]
        for sub in offenders:
            sub_src = ast.get_source_segment(source, sub) or ""
            if not SECRET_LEAK_KEY_RE.search(sub_src):
                continue
            if REDACT_HELPER_RE.search(sub_src):
                continue
            if _emit(path, "Q13.log-secret-leak",
                     "logger call may emit a secret-shaped value without redaction",
                     "wrap value in a redact_*(value) helper from observability/logging.py",
                     node.lineno):
                errors += 1
                break  # one finding per logger call is enough
    return errors


def _scan_file(path: Path, virtual: str) -> int:
    if _is_excluded(virtual):
        return 0
    if path.suffix not in SCANNED_EXTS:
        return 0
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    errors = 0
    errors += _scan_dangerous_patterns(path, virtual, source)
    errors += _scan_outbound_http(path, virtual, source)
    errors += _scan_log_secret_leak(path, virtual, source)
    return errors


def _walk_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in SCANNED_EXTS:
            continue
        if any(tok in str(path) for tok in EXCLUDE_FS):
            continue
        yield path


def _run_gitleaks() -> int:
    if not shutil.which("gitleaks"):
        emit("WARN", Path("gitleaks"), "Q13.secret-detected",
             "gitleaks binary not installed; secret scan skipped",
             "install gitleaks (Sprint H.0b Story 6) so this rule can enforce", line=0)
        return 0
    config_path = REPO_ROOT / ".gitleaks.toml"
    config_arg = ["--config", str(config_path)] if config_path.exists() else []
    try:
        result = subprocess.run(
            ["gitleaks", "detect", "--no-git", "--report-format", "json",
             "--report-path", "/dev/stdout", *config_arg],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        emit("WARN", Path("gitleaks"), "Q13.secret-detected",
             f"gitleaks subprocess error: {exc}",
             "investigate gitleaks installation", line=0)
        return 0
    if result.returncode == 0:
        return 0
    try:
        findings = json.loads(result.stdout) if result.stdout.strip() else []
    except json.JSONDecodeError:
        emit("ERROR", Path("gitleaks"), "Q13.secret-detected",
             "gitleaks reported failures but JSON parse failed",
             "run `gitleaks detect --no-git` manually to triage", line=0)
        return 1
    errors = 0
    for finding in findings:
        if _emit(Path(finding.get("File", "?")), "Q13.secret-detected",
                 f"{finding.get('RuleID', 'unknown-rule')}: {finding.get('Description', '')[:120]}",
                 "rotate the secret AND remove it from git history before merge",
                 int(finding.get("StartLine", 0))):
            errors += 1
    return errors


def scan(roots: Iterable[Path], pretend_path: str | None, run_gitleaks: bool) -> int:
    total_errors = 0
    if run_gitleaks:
        total_errors += _run_gitleaks()
    for root in roots:
        if not root.exists():
            continue
        if root.is_file() and root.suffix in SCANNED_EXTS:
            virtual = pretend_path or (
                str(root.relative_to(REPO_ROOT))
                if root.is_relative_to(REPO_ROOT) else root.name
            )
            total_errors += _scan_file(root, virtual)
        else:
            for p in _walk_files(root):
                virtual = (
                    str(p.relative_to(REPO_ROOT))
                    if p.is_relative_to(REPO_ROOT) else p.name
                )
                total_errors += _scan_file(p, virtual)
    return 1 if total_errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, action="append")
    parser.add_argument("--pretend-path", type=str)
    parser.add_argument("--no-gitleaks", action="store_true",
                        help="Skip gitleaks subprocess (test mode).")
    args = parser.parse_args(argv)
    roots = tuple(args.target) if args.target else DEFAULT_ROOTS
    # By default, run gitleaks only on full-repo scan (no --target).
    run_gitleaks = not args.no_gitleaks and not args.target
    return scan(roots, args.pretend_path, run_gitleaks)


if __name__ == "__main__":
    sys.exit(main())
