"""Sprint 2 / S2.1 — first-commit welcome banner tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))


def test_banner_prints_when_marker_absent(capsys, monkeypatch, tmp_path):
    """First run with no marker → banner shows."""
    marker = tmp_path / "marker"
    import run_validate
    monkeypatch.setattr(run_validate, "FIRST_COMMIT_MARKER", marker)
    run_validate._maybe_print_first_commit_banner(rules_count=30, elapsed_s=4.3)
    captured = capsys.readouterr()
    assert "first harness-gated commit" in captured.out
    assert "30 rules" in captured.out
    assert "4.3s" in captured.out
    assert marker.exists()


def test_banner_skipped_when_marker_present(capsys, monkeypatch, tmp_path):
    """Marker exists → banner stays silent."""
    marker = tmp_path / "marker"
    marker.write_text("seen")
    import run_validate
    monkeypatch.setattr(run_validate, "FIRST_COMMIT_MARKER", marker)
    run_validate._maybe_print_first_commit_banner(rules_count=30, elapsed_s=4.3)
    captured = capsys.readouterr()
    assert captured.out == ""


def test_banner_reappears_when_marker_deleted(capsys, monkeypatch, tmp_path):
    """Delete the marker → banner shows again on the next run.
    Useful for testing in-place + recovery flows."""
    marker = tmp_path / "marker"
    import run_validate
    monkeypatch.setattr(run_validate, "FIRST_COMMIT_MARKER", marker)
    # First run.
    run_validate._maybe_print_first_commit_banner(rules_count=10, elapsed_s=2.0)
    capsys.readouterr()  # discard
    # Delete the marker.
    marker.unlink()
    # Second run — banner shows again.
    run_validate._maybe_print_first_commit_banner(rules_count=10, elapsed_s=2.0)
    captured = capsys.readouterr()
    assert "first harness-gated commit" in captured.out


def test_banner_includes_pointers_to_next_steps(capsys, monkeypatch, tmp_path):
    marker = tmp_path / "marker"
    import run_validate
    monkeypatch.setattr(run_validate, "FIRST_COMMIT_MARKER", marker)
    run_validate._maybe_print_first_commit_banner(rules_count=5, elapsed_s=1.0)
    captured = capsys.readouterr()
    assert "harness rules" in captured.out
    assert "harness telemetry" in captured.out


def test_banner_marker_write_failure_doesnt_crash(capsys, monkeypatch, tmp_path):
    """If the marker can't be written (permission denied), banner still
    prints but doesn't raise. Subsequent commits would re-trigger; that's
    acceptable for this rare failure mode."""
    bad_marker = tmp_path / "ro" / "marker"
    bad_marker.parent.mkdir()
    bad_marker.parent.chmod(0o555)
    import run_validate
    monkeypatch.setattr(run_validate, "FIRST_COMMIT_MARKER", bad_marker)
    try:
        # Should not raise.
        run_validate._maybe_print_first_commit_banner(
            rules_count=1, elapsed_s=0.1
        )
        captured = capsys.readouterr()
        assert "first harness-gated commit" in captured.out
    finally:
        bad_marker.parent.chmod(0o755)
