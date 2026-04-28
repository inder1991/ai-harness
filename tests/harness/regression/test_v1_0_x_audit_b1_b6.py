"""Sprint 0 / S0.4 — permanent regression tests for the v1.0.x audit batch (B1-B6).

Each test is `REGRESSION-FOR: B<N>`. If a future refactor accidentally
re-introduces the bug, the matching test fires. Tests in this file are
NEVER deleted; they're renamed when superseded.

See `docs/plans/2026-04-27-harness-sdet-audit.md` for the original
audit + closure history.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from _common import (  # noqa: E402
    ERROR_LINE_PATTERN,
    _escape_field,
    emit,
    load_baseline,
    normalize_path,
)


# REGRESSION-FOR: B1 (baseline `file` paths must be repo-relative POSIX)
def test_b1_normalize_path_strips_repo_prefix(tmp_path):
    """Pre-v1.1.0 baselines stored absolute paths from whatever machine
    snapshotted them. A baseline created on a developer's MacBook stopped
    suppressing anything in CI. v1.1.0 normalized at emit + load time.

    This test asserts: an absolute path inside REPO_ROOT becomes
    repo-relative POSIX. An absolute path outside REPO_ROOT stays as-is.
    """
    inside = REPO_ROOT / ".harness" / "checks" / "_common.py"
    assert normalize_path(inside) == ".harness/checks/_common.py"
    # An absolute path NOT inside the repo passes through (it's
    # legitimately external; we don't fabricate a repo-relative form).
    outside = Path("/usr/lib/python3.11/site-packages/yaml/__init__.py")
    assert normalize_path(outside) == "/usr/lib/python3.11/site-packages/yaml/__init__.py"


# REGRESSION-FOR: B1
def test_b1_relative_paths_pass_through(tmp_path):
    """Already-relative paths must round-trip without modification."""
    assert normalize_path("backend/src/api/routes.py") == "backend/src/api/routes.py"


# REGRESSION-FOR: B2 (failure-log fcntl.LOCK_EX around append)
def test_b2_failure_log_append_under_lock():
    """Pre-v1.1.0, two parallel `make validate-fast` runs could
    interleave their JSONL append bytes and corrupt the log. v1.1.0
    added fcntl.LOCK_EX around every append.

    This test imports the module and asserts the helper takes the lock
    when fcntl is available. We don't stress-test concurrent processes
    here (B10's separate test does); this just guards the lock from
    being silently removed.
    """
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    from tools import run_validate
    # The append helper must reference fcntl.LOCK_EX (or be on Windows
    # where _HAVE_FCNTL is False).
    src = (REPO_ROOT / "tools" / "run_validate.py").read_text()
    assert "_fcntl.LOCK_EX" in src or "_fcntl.flock" in src, (
        "run_validate.py must use fcntl.LOCK_EX around failure-log "
        "writes (B2 regression guard)"
    )
    assert run_validate._HAVE_FCNTL or sys.platform == "win32"


# REGRESSION-FOR: B3 (init_harness refuses --target == source repo)
def test_b3_init_harness_refuses_self_target(tmp_path):
    """Pre-v1.1.0, running `init_harness --target /path/to/source-repo`
    silently overwrote the source repo and produced 0-files written
    while reporting success. v1.1.0 added an explicit refusal."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools/init_harness.py"),
         "--target", str(REPO_ROOT),
         "--owner", "@regression",
         "--tech-stack", "polyglot"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 2, (
        f"init_harness must exit 2 when --target is the source repo. "
        f"Got rc={result.returncode}; stdout={result.stdout!r}"
    )
    assert "harness source repo itself" in result.stderr.lower() or \
           "resolves to" in result.stderr.lower()


# REGRESSION-FOR: B4 (setup_signing.sh defaults to --local scope)
def test_b4_setup_signing_default_scope_is_local():
    """Pre-v1.1.0, setup_signing.sh defaulted to --global, silently
    overwriting any existing personal user.signingkey."""
    src = (REPO_ROOT / "tools" / "setup_signing.sh").read_text()
    assert 'SCOPE="--local"' in src, (
        "setup_signing.sh's default scope must be --local (B4 guard)"
    )
    # The first occurrence of SCOPE=... in the script body is the default.
    first_assignment = re.search(r'^SCOPE="(--[a-z]+)"', src, re.MULTILINE)
    assert first_assignment is not None
    assert first_assignment.group(1) == "--local"


# REGRESSION-FOR: B5 (single canonical regex for the H-16 emit format)
def test_b5_error_line_pattern_in_common():
    """Pre-v1.1.0, run_validate.py and refresh_baselines.py each had
    their own copy of the parse regex with `\\S+?` for the file group,
    which choked on paths with spaces / unicode. v1.1.0 moved the
    canonical pattern to `_common.ERROR_LINE_PATTERN` with `.+?`."""
    # Spaces in path must round-trip.
    test_line = (
        '[ERROR] file=path with space/x.py:42 rule=Q13.dangerous '
        'message="x" suggestion="y"'
    )
    m = ERROR_LINE_PATTERN.match(test_line)
    assert m is not None
    assert m.group("file") == "path with space/x.py"
    assert m.group("line") == "42"
    assert m.group("rule") == "Q13.dangerous"


# REGRESSION-FOR: B5
def test_b5_run_validate_imports_canonical_regex():
    """run_validate.py and refresh_baselines.py must both import the
    shared regex, not redefine it locally."""
    rv_src = (REPO_ROOT / "tools" / "run_validate.py").read_text()
    rb_src = (REPO_ROOT / "tools" / "refresh_baselines.py").read_text()
    assert "ERROR_LINE_PATTERN" in rv_src or "from _common" in rv_src
    assert "ERROR_LINE_PATTERN" in rb_src or "from _common" in rb_src


# REGRESSION-FOR: B6 (emit() escapes control chars in messages)
def test_b6_emit_escapes_newlines(capsys):
    """Pre-v1.1.0, a check message containing `\\n` corrupted the
    line-based emit format (one finding became N invalid lines).
    v1.1.0 added _escape_field() to convert `\\n`, `\\r`, `\\t`, `"`."""
    msg_with_newline = "this has\na newline"
    safe = _escape_field(msg_with_newline)
    assert "\n" not in safe
    assert "\\n" in safe


# REGRESSION-FOR: B6
def test_b6_emit_escapes_double_quotes():
    """Double quotes break the H-16 line shape. _escape_field replaces with single quotes."""
    msg = 'this has "double quotes"'
    safe = _escape_field(msg)
    assert '"' not in safe
    assert "'" in safe


# REGRESSION-FOR: B6
def test_b6_emit_escapes_tabs_and_carriage_returns():
    msg = "tabs\tand\rcarriage"
    safe = _escape_field(msg)
    assert "\t" not in safe
    assert "\r" not in safe
    assert "\\t" in safe
    assert "\\r" in safe
