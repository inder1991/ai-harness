"""Sprint 2 / S2.2 — onboarding status line tests."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))


def test_status_line_present_in_render():
    """The status line must appear at the very top of the rendered context."""
    from load_harness import build_context, render_text
    ctx = build_context(None)
    out = render_text(ctx, max_bytes=0)
    # Status line is the very first thing.
    first_line = out.split("\n", 1)[0]
    assert "ai-harness" in first_line
    assert "active" in first_line


def test_status_line_includes_rules_count():
    from load_harness import _status_line
    line = _status_line()
    assert "rules loaded" in line


def test_status_line_includes_last_check_marker():
    from load_harness import _status_line
    line = _status_line()
    assert "last check:" in line


def test_status_line_with_no_failure_log(tmp_path, monkeypatch):
    """When the failure log is missing, status says 'never' — no crash."""
    import load_harness
    monkeypatch.setattr(
        load_harness, "REPO_ROOT", tmp_path,
        raising=False,
    )
    line = load_harness._status_line()
    assert "never" in line


def test_status_line_within_byte_budget():
    """The status line must add <500 bytes to the session-start bundle."""
    from load_harness import _status_line
    line = _status_line()
    assert len(line.encode("utf-8")) < 500, (
        f"status line is {len(line.encode('utf-8'))} bytes; budget is 500"
    )


def test_ai_hints_file_exists():
    """The canned 'what does the harness know?' answer lives at .harness/AI_HINTS.md."""
    hints = REPO_ROOT / ".harness" / "AI_HINTS.md"
    assert hints.exists()
    text = hints.read_text(encoding="utf-8")
    assert "what does the harness know" in text.lower()


def test_status_line_includes_top_rule_with_synthetic_log(tmp_path, monkeypatch):
    """When the failure log has recent entries, the top firing rule shows."""
    fake_repo = tmp_path / "repo"
    (fake_repo / ".harness" / "checks").mkdir(parents=True)
    (fake_repo / ".harness" / "HARNESS_CARD.yaml").write_text("version: 9.9.9\n")
    log = fake_repo / ".harness" / ".failure-log.jsonl"
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    log.write_text(
        "\n".join(
            json.dumps({
                "ts": ts,
                "rule": "Q13.route-needs-auth",
                "file": "x.py", "line": 1, "commit": "abc",
                "host": "h", "session": "s",
            })
            for _ in range(15)
        ) + "\n"
    )
    import load_harness
    monkeypatch.setattr(load_harness, "REPO_ROOT", fake_repo, raising=False)
    line = load_harness._status_line()
    assert "Q13.route-needs-auth" in line
    assert "Top firing" in line
