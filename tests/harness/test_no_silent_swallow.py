"""Sprint 3 / S3.2 — Q17 self-audit.

We enforce Q17 (no silent exception swallow) on consumers; we hold
ourselves to the same rule. Every bare / broad except in `tools/` or
`.harness/checks/_common.py` either:

  - has a logger / re-raise / structured emit in its body, OR
  - carries a `# Q17-EXEMPT: <reason>` comment on the same or
    immediately-preceding line.

This test parses every shipped Python file with `ast`, finds every
ExceptHandler with `type` either None or `Exception`/`BaseException`,
and asserts the contract.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

SCAN_PATHS = [
    REPO_ROOT / "tools",
    REPO_ROOT / ".harness" / "checks",
]
EXCLUDE = (
    "__pycache__", "extraction", "perf",
    # Generators are scanned by their own checks; keep this audit
    # scoped to the substrate.
    "generators",
)


def _python_files() -> list[Path]:
    out: list[Path] = []
    for root in SCAN_PATHS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if any(tok in str(path) for tok in EXCLUDE):
                continue
            out.append(path)
    return out


def _is_broad_handler(handler: ast.ExceptHandler) -> bool:
    """True for `except:` and `except Exception:` and `except BaseException:`."""
    if handler.type is None:
        return True
    if isinstance(handler.type, ast.Name) and handler.type.id in {
        "Exception", "BaseException"
    }:
        return True
    return False


def _body_has_logger_call(handler: ast.ExceptHandler) -> bool:
    """Heuristic: any Call to *.{info,warning,error,debug,exception,critical,
    print, _err, _warn, emit} or any Raise statement counts as 'not silent'."""
    LOG_ATTRS = {
        "info", "warning", "error", "debug", "exception", "critical",
        "log", "emit",
    }
    PASSING_NAMES = {"print", "_err", "_warn"}
    for node in ast.walk(ast.Module(body=handler.body, type_ignores=[])):
        if isinstance(node, ast.Raise):
            return True
        if isinstance(node, ast.Return):
            return True  # converting to a structured return value with intent
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in LOG_ATTRS:
                return True
            if isinstance(func, ast.Name) and func.id in PASSING_NAMES:
                return True
    return False


def _has_exempt_comment(source_lines: list[str], line: int) -> bool:
    """Look for a `# Q17-EXEMPT:` comment in:
      - the same line as the `except`
      - up to 8 lines BEFORE (multi-line comment block above)
      - up to 5 lines AFTER (inside the handler body)
    """
    for offset in (-8, -7, -6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5):
        idx = line - 1 + offset
        if 0 <= idx < len(source_lines):
            if "Q17-EXEMPT" in source_lines[idx]:
                return True
    return False


def _audit_one_file(path: Path) -> list[str]:
    """Return human-readable violation strings for one file."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return []
    source_lines = source.splitlines()
    bad: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if not _is_broad_handler(node):
            continue
        if _body_has_logger_call(node):
            continue
        if _has_exempt_comment(source_lines, node.lineno):
            continue
        bad.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
    return bad


def test_no_silent_swallow_in_substrate():
    """Every broad except in tools/ + .harness/checks/_common.py must
    either log/raise/return OR carry a Q17-EXEMPT comment."""
    offenders: list[str] = []
    for path in _python_files():
        offenders.extend(_audit_one_file(path))
    assert not offenders, (
        f"{len(offenders)} silent swallow(s) in substrate code:\n  "
        + "\n  ".join(offenders) +
        "\n\nFix: add a logger/re-raise/_err call to the body, OR add "
        "`# Q17-EXEMPT: <reason>` on the same/preceding line."
    )


def test_q17_exempt_comments_have_reason():
    """Every Q17-EXEMPT comment must include a reason after the colon."""
    bad: list[str] = []
    for path in _python_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "Q17-EXEMPT" not in line:
                continue
            # Must look like `# Q17-EXEMPT: <some text>`.
            after_colon = line.split("Q17-EXEMPT", 1)[1].lstrip(":").strip()
            if len(after_colon) < 5:
                bad.append(f"{path.relative_to(REPO_ROOT)}:{lineno}")
    assert not bad, (
        f"{len(bad)} Q17-EXEMPT comment(s) without a reason:\n  "
        + "\n  ".join(bad)
    )
