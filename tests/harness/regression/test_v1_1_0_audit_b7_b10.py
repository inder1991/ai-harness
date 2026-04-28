"""Sprint 0 / S0.4 — regression tests for v1.1.0 P0 audit (B7-B10).

These four bugs were regressions INTRODUCED by v1.1.0 itself; v1.1.1
closed them. Each gets a permanent test.
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
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tools"))


# REGRESSION-FOR: B7 (sign_release.sh uses scope-agnostic git config)
def test_b7_sign_release_does_not_query_global():
    """v1.1.0's B4 made setup_signing.sh default to --local. v1.1.1
    realized sign_release.sh still hardcoded `git config --global
    user.signingkey`, which falsely refused on a clean install."""
    text = (REPO_ROOT / "tools/sign_release.sh").read_text()
    bad_lines = [
        line for line in text.splitlines()
        if "git config" in line
        and "--global" in line
        and "user.signingkey" in line
    ]
    assert not bad_lines, (
        f"sign_release.sh must use scope-agnostic `git config user.signingkey` "
        f"(B7 regression). Found: {bad_lines}"
    )


# REGRESSION-FOR: B8 (CI workflow runs validate-full, not validate-fast)
def test_b8_ci_workflow_invokes_validate_full():
    """v1.1.1 swapped the CI gate from validate-fast to validate-full
    so 5 FULL_ONLY_CHECKS + typecheck_policy actually run on PRs."""
    wf = yaml.safe_load(
        (REPO_ROOT / ".github/workflows/validate.yml").read_text()
    )
    steps = wf["jobs"]["validate"]["steps"]
    run_steps = [s for s in steps if "run" in s]
    full_step = next(
        (s for s in run_steps if "validate-full" in s["run"]), None,
    )
    assert full_step is not None, (
        "CI must invoke `make validate-full` — fast tier skips "
        "FULL_ONLY_CHECKS + typecheck_policy (B8 regression)"
    )
    fast_only = [
        s for s in run_steps
        if "validate-fast" in s["run"] and "validate-full" not in s["run"]
    ]
    assert not fast_only, f"validate-fast still appears in CI: {fast_only}"


# REGRESSION-FOR: B9 (_resolve_latest_tag uses semver, not lexical sort)
def test_b9_resolve_latest_tag_semver():
    """Pre-v1.1.1: lexical `sorted()` on version strings ranked v1.10.0
    below v1.2.0. Once we cross v1.10, init_harness --from-git latest
    would have pinned a stale ref."""
    from unittest.mock import patch
    from tools.init_harness import _resolve_latest_tag
    fake = (
        "abc\trefs/tags/v1.0.4\n"
        "def\trefs/tags/v1.10.0\n"
        "ghi\trefs/tags/v1.2.0\n"
        "jkl\trefs/tags/v1.10.0^{}\n"
    )
    with patch("subprocess.check_output", return_value=fake):
        latest = _resolve_latest_tag("https://example/x.git")
    assert latest == "v1.10.0", (
        f"semver sort must rank v1.10.0 ahead of v1.2.0; got {latest} (B9 regression)"
    )


# REGRESSION-FOR: B9 (rejects non-semver pre-release tags)
def test_b9_resolve_latest_tag_rejects_non_semver():
    from unittest.mock import patch
    from tools.init_harness import _resolve_latest_tag
    fake = (
        "abc\trefs/tags/v1.0.4\n"
        "def\trefs/tags/some-feature-branch\n"
        "ghi\trefs/tags/v1.4\n"            # short form
        "jkl\trefs/tags/v1.0.4-rc1\n"      # pre-release
    )
    with patch("subprocess.check_output", return_value=fake):
        latest = _resolve_latest_tag("https://example/x.git")
    assert latest == "v1.0.4"


def _rotate_worker(log_path_str: str) -> None:
    """Worker for the B10 stress test."""
    sys.path.insert(0, str(REPO_ROOT))
    from tools import run_validate
    run_validate.FAILURE_LOG_PATH = Path(log_path_str)
    run_validate.FAILURE_LOG_MAX_BYTES = 100
    run_validate._rotate_failure_log()


# REGRESSION-FOR: B10 (failure-log rotate under LOCK_EX)
def test_b10_concurrent_rotates_dont_corrupt():
    """v1.1.1 made the rotate path hold LOCK_EX (B2 only covered
    append). Without B10's fix, two parallel validate-fast runs could
    both observe size > cap and both rename onto .1, clobbering the
    first rotation's bytes."""
    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / "log.jsonl"
        with log.open("w") as fh:
            for i in range(50):
                fh.write(json.dumps({"i": i}) + "\n")
        size_before = log.stat().st_size
        assert size_before > 100

        with mp.Pool(10) as pool:
            pool.map(_rotate_worker, [str(log)] * 10)

        rotated = log.with_suffix(log.suffix + ".1")
        assert rotated.exists()
        assert rotated.stat().st_size == size_before, (
            f"concurrent rotates clobbered each other: "
            f".1 size={rotated.stat().st_size} != original {size_before} "
            "(B10 regression)"
        )
