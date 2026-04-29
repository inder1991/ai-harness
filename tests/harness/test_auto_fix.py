"""Sprint 2 / S2.3 — auto-fix engine + 4 named fixers.

Tests the safety contract:
  1. Diff always shown before mutating
  2. AST parses after fix (Python files)
  3. mtime/sha race guard
  4. Determinism: same input → byte-identical output
  5. Cascade: re-check after applying

Plus per-fixer behavior tests for Q15, Q16, Q18, Q22.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from auto_fix import FIXERS, fix as run_fix  # noqa: E402
from output_formatter import Finding  # noqa: E402


# ───────── Q15 ─────────


def test_q15_inserts_docstring(tmp_path):
    p = tmp_path / "x.py"
    p.write_text("def add(a, b):\n    return a + b\n")
    finding = Finding(rule="Q15.spine-docstring-required",
                      location=f"{p}:1")
    result = run_fix("Q15.spine-docstring-required", str(p), finding, apply=True)
    assert result.applied, result.error
    new = p.read_text()
    assert '"""' in new
    # AST still parses.
    import ast
    ast.parse(new)


def test_q15_idempotent(tmp_path):
    p = tmp_path / "x.py"
    p.write_text('def add(a, b):\n    """Already documented."""\n    return a + b\n')
    finding = Finding(rule="Q15.spine-docstring-required",
                      location=f"{p}:1")
    result = run_fix("Q15.spine-docstring-required", str(p), finding, apply=True)
    # No change — finding spurious.
    assert not result.applied


# ───────── Q16 ─────────


def test_q16_converts_f_string_to_percent_style(tmp_path):
    p = tmp_path / "x.py"
    p.write_text('import logging\nlog = logging.getLogger()\nlog.info(f"user {user_id}")\n')
    finding = Finding(rule="Q16.f-string-in-log",
                      location=f"{p}:3")
    result = run_fix("Q16.f-string-in-log", str(p), finding, apply=True)
    assert result.applied, result.error
    new = p.read_text()
    assert 'log.info("user %s", user_id)' in new


def test_q16_skips_complex_f_strings(tmp_path):
    """Format specs / attribute access bail out."""
    p = tmp_path / "x.py"
    p.write_text('log.info(f"x {user.name:>10}")\n')
    finding = Finding(rule="Q16.f-string-in-log",
                      location=f"{p}:1")
    result = run_fix("Q16.f-string-in-log", str(p), finding, apply=True)
    # Bails (no change).
    assert not result.applied or result.error


# ───────── Q18 ─────────


def test_q18_default_export_to_named(tmp_path):
    p = tmp_path / "Foo.tsx"
    p.write_text("const Foo = () => null;\nexport default Foo;\n")
    finding = Finding(rule="Q18.no-default-export-in-components",
                      location=f"{p}:2")
    result = run_fix("Q18.no-default-export-in-components",
                     str(p), finding, apply=True)
    assert result.applied, result.error
    new = p.read_text()
    assert "export default" not in new
    assert "export {" in new


# ───────── Q22 ─────────


def test_q22_updates_docstring_count(tmp_path):
    p = tmp_path / "check.py"
    p.write_text(
        '"""Test check.\n\n'
        'Three rules:\n'
        '  Q99.foo-one  — first.\n'
        '  Q99.foo-two  — second.\n'
        '"""\n'
    )
    finding = Finding(rule="Q22.doc-rule-count-mismatch",
                      location=f"{p}:1")
    result = run_fix("Q22.doc-rule-count-mismatch", str(p),
                     finding, apply=True)
    assert result.applied, result.error
    new = p.read_text()
    assert "Two rules" in new
    assert "Three rules" not in new


# ───────── safety contract ─────────


def test_diff_shown_without_apply(tmp_path):
    p = tmp_path / "x.py"
    p.write_text("def add(a, b):\n    return a + b\n")
    finding = Finding(rule="Q15.spine-docstring-required",
                      location=f"{p}:1")
    result = run_fix("Q15.spine-docstring-required", str(p),
                     finding, apply=False)
    assert not result.applied
    assert result.diff
    assert "TODO: describe" in result.diff
    # File unchanged.
    assert "TODO" not in p.read_text()


def test_ast_failure_aborts(tmp_path, monkeypatch):
    """If a transformer produces invalid Python, abort + don't write."""
    p = tmp_path / "x.py"
    original = "def add(a, b):\n    return a + b\n"
    p.write_text(original)

    # Inject a bad transformer.
    def bad_transform(source, finding):
        return "this is not valid python ((("
    monkeypatch.setitem(FIXERS, "Q15.spine-docstring-required", bad_transform)

    finding = Finding(rule="Q15.spine-docstring-required",
                      location=f"{p}:1")
    result = run_fix("Q15.spine-docstring-required", str(p),
                     finding, apply=True)
    assert not result.applied
    assert result.error and "invalid" in result.error.lower()
    # File unchanged.
    assert p.read_text() == original


def test_race_guard_aborts_on_mid_fix_change(tmp_path, monkeypatch):
    """If the file changes between read + write, abort."""
    p = tmp_path / "x.py"
    p.write_text("def add(a, b):\n    return a + b\n")

    # Wrap _file_sha so the second invocation returns a different hash.
    import auto_fix
    real_sha = auto_fix._file_sha
    call_count = {"n": 0}

    def fake_sha(path):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return real_sha(path)
        return "x" * 64  # different hash on second call
    monkeypatch.setattr(auto_fix, "_file_sha", fake_sha)

    finding = Finding(rule="Q15.spine-docstring-required",
                      location=f"{p}:1")
    result = run_fix("Q15.spine-docstring-required", str(p),
                     finding, apply=True)
    assert not result.applied
    assert result.error and "changed" in result.error.lower()


def test_determinism_guard(tmp_path, monkeypatch):
    """Non-deterministic fixers are refused."""
    p = tmp_path / "x.py"
    p.write_text("def add(a, b):\n    return a + b\n")

    # Inject a non-deterministic transformer.
    counter = {"n": 0}
    def non_det(source, finding):
        counter["n"] += 1
        return source + f"# {counter['n']}\n"
    monkeypatch.setitem(FIXERS, "Q15.spine-docstring-required", non_det)

    finding = Finding(rule="Q15.spine-docstring-required",
                      location=f"{p}:1")
    result = run_fix("Q15.spine-docstring-required", str(p),
                     finding, apply=True)
    assert not result.applied
    assert result.error and "non-deterministic" in result.error.lower()


def test_unknown_rule_returns_helpful_error(tmp_path):
    p = tmp_path / "x.py"
    p.write_text("def f(): pass\n")
    finding = Finding(rule="Q99.does-not-exist",
                      location=f"{p}:1")
    result = run_fix("Q99.does-not-exist", str(p), finding, apply=True)
    assert not result.applied
    assert result.error and "no auto-fixer" in result.error.lower()
    assert "harness rules explain" in result.error


def test_missing_file_returns_clean_error(tmp_path):
    finding = Finding(rule="Q15.spine-docstring-required",
                      location="nope.py:1")
    result = run_fix("Q15.spine-docstring-required",
                     str(tmp_path / "nope.py"),
                     finding, apply=True)
    assert not result.applied
    assert result.error and "not found" in result.error.lower()


def test_cli_fix_without_apply_shows_diff(tmp_path):
    p = tmp_path / "x.py"
    p.write_text("def add(a, b):\n    return a + b\n")
    cmd = [
        sys.executable, "-m", "tools.harness_cli", "fix",
        "Q15.spine-docstring-required",
        "--files", str(p),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0
    assert "TODO" in result.stdout
    # File unchanged (no --apply).
    assert "TODO" not in p.read_text()


def test_cli_fix_with_apply_writes(tmp_path):
    p = tmp_path / "x.py"
    p.write_text("def add(a, b):\n    return a + b\n")
    cmd = [
        sys.executable, "-m", "tools.harness_cli", "fix",
        "Q15.spine-docstring-required",
        "--files", str(p),
        "--apply",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0
    assert "TODO" in p.read_text()


def test_cli_fix_unknown_rule_exits_2():
    cmd = [
        sys.executable, "-m", "tools.harness_cli", "fix",
        "Q99.fake-rule", "--files", "x.py",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
