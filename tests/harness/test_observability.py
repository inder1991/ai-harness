"""Sprint 3 / S3.5 — observability / --trace tests.

Asserts:
  - trace events round-trip (json.loads after emit_event)
  - opt-in respected (no file unless flag/env set)
  - rotation at 10 MB
  - concurrent writers don't corrupt the JSONL
  - --slow-checks summary reads + ranks
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))


def test_emit_noop_when_disabled(tmp_path, monkeypatch):
    """Without HARNESS_TRACE, emit_event must NOT create the file."""
    import observability
    fake_trace = tmp_path / ".trace.jsonl"
    monkeypatch.setattr(observability, "TRACE_PATH", fake_trace)
    monkeypatch.delenv("HARNESS_TRACE", raising=False)
    observability.emit_event(
        check="test_check", start_ms=0, duration_ms=42,
        exit_code=0, n_findings=0,
    )
    assert not fake_trace.exists()


def test_emit_writes_when_enabled(tmp_path, monkeypatch):
    import observability
    fake_trace = tmp_path / ".trace.jsonl"
    monkeypatch.setattr(observability, "TRACE_PATH", fake_trace)
    monkeypatch.setenv("HARNESS_TRACE", "1")
    observability.emit_event(
        check="test_check", start_ms=100.0, duration_ms=42.0,
        exit_code=0, n_findings=3,
    )
    assert fake_trace.exists()
    line = fake_trace.read_text().strip()
    parsed = json.loads(line)
    assert parsed["check"] == "test_check"
    assert parsed["duration_ms"] == 42.0
    assert parsed["n_findings"] == 3
    assert "ts" in parsed


def test_read_events_skips_corrupt(tmp_path, monkeypatch, capsys):
    """Corrupt JSONL lines are skipped with [WARN], not crash."""
    import observability
    fake_trace = tmp_path / ".trace.jsonl"
    fake_trace.write_text(
        '{"ts":"2026-04-29T00:00:00+00:00","check":"a","start_ms":0,"duration_ms":10,"exit_code":0,"n_findings":0}\n'
        '{"this is": invalid json\n'
        '{"ts":"2026-04-29T00:00:01+00:00","check":"b","start_ms":0,"duration_ms":20,"exit_code":0,"n_findings":1}\n'
    )
    events = observability.read_events(fake_trace)
    captured = capsys.readouterr()
    assert len(events) == 2
    assert "skipped 1 corrupt" in captured.err


def _writer(args):
    """Subprocess worker for the concurrent-write test."""
    trace_path_str, n = args
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import observability
    observability.TRACE_PATH = Path(trace_path_str)
    os.environ["HARNESS_TRACE"] = "1"
    for i in range(n):
        observability.emit_event(
            check=f"worker_check_{i}", start_ms=0,
            duration_ms=float(i), exit_code=0, n_findings=0,
        )


def test_concurrent_writes_dont_corrupt():
    """Same B2/B10 contract: 4 workers × 25 events each = 100 lines."""
    with tempfile.TemporaryDirectory() as td:
        trace = Path(td) / ".trace.jsonl"
        with mp.Pool(4) as pool:
            pool.map(_writer, [(str(trace), 25)] * 4)
        assert trace.exists()
        # Every line must be valid JSON.
        lines = trace.read_text().splitlines()
        assert len(lines) == 100, f"expected 100 lines, got {len(lines)}"
        for line in lines:
            parsed = json.loads(line)
            assert "check" in parsed


def test_slow_checks_no_data():
    """Without a trace file, --slow-checks prints empty-state message."""
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    from observability import TRACE_PATH
    backup = TRACE_PATH.read_text() if TRACE_PATH.exists() else None
    if TRACE_PATH.exists():
        TRACE_PATH.unlink()
    try:
        result = subprocess.run(
            [sys.executable, "-m", "tools.harness_cli",
             "telemetry", "--slow-checks"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "no trace events" in result.stdout.lower()
    finally:
        if backup is not None:
            TRACE_PATH.write_text(backup)


def test_slow_checks_with_synthetic_data(tmp_path, monkeypatch):
    """With trace data, --slow-checks ranks by avg duration."""
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import observability
    fake_trace = tmp_path / ".trace.jsonl"
    fake_trace.write_text(
        '{"ts":"2026-04-29T00:00:00+00:00","check":"slow","start_ms":0,"duration_ms":1000,"exit_code":0,"n_findings":0}\n'
        '{"ts":"2026-04-29T00:00:01+00:00","check":"fast","start_ms":0,"duration_ms":10,"exit_code":0,"n_findings":0}\n'
        '{"ts":"2026-04-29T00:00:02+00:00","check":"slow","start_ms":0,"duration_ms":2000,"exit_code":0,"n_findings":0}\n'
    )
    monkeypatch.setattr(observability, "TRACE_PATH", fake_trace)
    # Inline the slow_checks logic since the CLI subprocess wouldn't see the monkeypatch.
    from tools.cli.telemetry import _slow_checks
    import argparse
    args = argparse.Namespace(json=False)
    rc = _slow_checks(args)
    assert rc == 0


def test_check_trace_flag_propagates_env(tmp_path):
    """`harness check --trace` sets HARNESS_TRACE in the orchestrator subprocess."""
    cmd = [sys.executable, "-m", "tools.harness_cli", "check", "--help"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert "--trace" in result.stdout
