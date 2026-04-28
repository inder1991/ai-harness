"""Sprint 1 / S1.4 — minimal-but-meaningful tests for each subcommand.

Per the v2.0 plan: ≥3 tests each (happy path, error path, JSON output)
for rules / baseline / telemetry / doctor / upgrade-rollback.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(*args, env_extra=None, cwd=None):
    env = {**os.environ, "NO_COLOR": "1"}
    if env_extra:
        env.update(env_extra)
    cmd = [sys.executable, "-m", "tools.harness_cli", *args]
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=60, env=env, cwd=cwd,
    )


# ────────── rules ──────────


def test_rules_lists_all():
    result = _run("rules")
    assert result.returncode == 0
    # Should mention each tier.
    for tier in ("P0_security", "P1_correctness", "P2_quality", "P3_style"):
        assert tier in result.stdout


def test_rules_explain_known():
    result = _run("rules", "explain", "Q13.route-needs-auth")
    assert result.returncode == 0
    assert "Tier:" in result.stdout
    assert "Why:" in result.stdout
    assert "Fix:" in result.stdout


def test_rules_explain_unknown_exits_2():
    result = _run("rules", "explain", "ZZ99.totally-fake")
    assert result.returncode == 2
    assert "unknown rule" in result.stderr.lower()


def test_rules_json_mode():
    result = _run("rules", "--json")
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    # Should have rules in it.
    assert isinstance(parsed, dict)


# ────────── doctor ──────────


def test_doctor_runs_against_source_repo():
    """Source repo (this one) should mostly diagnose green."""
    result = _run("doctor", "--target", str(REPO_ROOT))
    # Either 0 (all green) or 6 (some PATH tools missing). Not crash.
    assert result.returncode in (0, 6)
    assert "Diagnosing" in result.stdout
    assert "Substrate:" in result.stdout
    assert "Dependencies:" in result.stdout


def test_doctor_against_empty_target_exits_6(tmp_path):
    """Empty dir → no harness install → multiple ✗."""
    result = _run("doctor", "--target", str(tmp_path))
    assert result.returncode == 6
    assert "✗" in result.stdout
    assert "checks failed" in result.stdout.lower()


def test_doctor_help():
    result = _run("doctor", "--help")
    assert result.returncode == 0


# ────────── telemetry ──────────


def test_telemetry_no_log():
    """No failure log → friendly empty-state message, exit 0."""
    log = REPO_ROOT / ".harness" / ".failure-log.jsonl"
    backup = log.read_text() if log.exists() else None
    if log.exists():
        log.unlink()
    try:
        result = _run("telemetry")
        assert result.returncode == 0
        assert "no telemetry yet" in result.stdout.lower()
    finally:
        if backup is not None:
            log.write_text(backup)


def test_telemetry_with_synthetic_log(tmp_path):
    """Pre-populate the failure log with synthetic entries; verify counts."""
    log = REPO_ROOT / ".harness" / ".failure-log.jsonl"
    backup = None
    if log.exists():
        backup = log.read_text()
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        synthetic = "\n".join(
            json.dumps({"ts": ts, "rule": f"Q15.foo-{i % 3}",
                        "file": f"x.py", "line": i, "commit": "abc",
                        "host": "h", "session": "s"})
            for i in range(15)
        )
        log.write_text(synthetic + "\n")
        result = _run("telemetry")
        assert result.returncode == 0
        assert "Total entries:" in result.stdout
        assert "15" in result.stdout
    finally:
        if backup is not None:
            log.write_text(backup)
        elif log.exists():
            log.unlink()


def test_telemetry_invalid_since():
    """--since validation requires entries to validate against; populate first."""
    log = REPO_ROOT / ".harness" / ".failure-log.jsonl"
    backup = log.read_text() if log.exists() else None
    log.parent.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    synthetic = "\n".join(
        json.dumps({"ts": ts, "rule": "Q15.foo",
                    "file": "x.py", "line": i, "commit": "abc",
                    "host": "h", "session": "s"})
        for i in range(15)
    )
    log.write_text(synthetic + "\n")
    try:
        result = _run("telemetry", "--since", "not-a-date")
        assert result.returncode == 2
    finally:
        if backup is not None:
            log.write_text(backup)
        elif log.exists():
            log.unlink()


# ────────── baseline ──────────


def test_baseline_show_runs():
    result = _run("baseline", "show")
    # Either no baselines/ or empty list — both exit 0.
    assert result.returncode == 0


def test_baseline_add_requires_reason():
    result = _run("baseline", "add", "Q13.foo", "x.py:1")
    # argparse rejects missing --reason.
    assert result.returncode != 0
    # Combined output: argparse may write to stderr.
    combined = result.stdout + result.stderr
    assert "reason" in combined.lower()


def test_baseline_add_bad_location():
    result = _run("baseline", "add", "Q13.foo", "no-colon",
                  "--reason", "test")
    assert result.returncode == 2
    assert "file:line" in result.stderr.lower()


# ────────── upgrade / rollback ──────────


def test_upgrade_help():
    result = _run("upgrade", "--help")
    assert result.returncode == 0
    assert "--ref" in result.stdout
    assert "--trust-key" in result.stdout


def test_rollback_no_history_no_to(tmp_path):
    """Without --to and no upgrade_history, rollback exits 2."""
    target = tmp_path / "consumer"
    target.mkdir()
    result = _run("rollback", "--target", str(target))
    assert result.returncode == 2
    assert ("history" in result.stderr.lower() or
            "--to" in result.stderr.lower())


def test_upgrade_dispatcher_routes_correctly():
    """Confirm `harness upgrade --help` doesn't print "not yet implemented"."""
    result = _run("upgrade", "--help")
    combined = result.stdout + result.stderr
    assert "not yet implemented" not in combined.lower()
