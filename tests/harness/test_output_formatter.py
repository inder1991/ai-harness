"""Sprint 1 / S1.3 — humane output formatter tests.

Asserts the contract:
  - human mode groups by severity (P0 → P1 → P2 → P3)
  - same-rule findings collapse to "N occurrences"
  - each rule shows why/fix/more
  - passing summary on empty findings
  - json mode produces stable, schema-validatable shape
  - raw mode emits exact H-16 lines
  - pre-commit mode preserves v1.x exit-1-on-any
  - human mode exit codes: 0 on no-findings or only-P3, 1 on P0+P1
  - parsing of H-16 input lines round-trips
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from output_formatter import (  # noqa: E402
    Finding,
    explainer_for,
    format_findings,
    parse_h16_output,
    tier_for,
)


# ────────── parsing ──────────


def test_parse_h16_line():
    line = (
        '[ERROR] file=backend/api.py:42 rule=Q13.route-needs-auth '
        'message="POST /users has no auth" suggestion="add Depends"'
    )
    findings = parse_h16_output(line)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule == "Q13.route-needs-auth"
    assert f.location == "backend/api.py:42"
    assert f.file == "backend/api.py"
    assert f.line == 42
    assert "POST /users" in f.message


def test_parse_skips_non_error_lines():
    text = (
        "INFO: starting check\n"
        '[ERROR] file=x.py:1 rule=Q15.spine-docstring-required '
        'message="m" suggestion="s"\n'
        "OTHER: noise\n"
    )
    findings = parse_h16_output(text)
    assert len(findings) == 1


def test_parse_handles_paths_with_spaces():
    """B5 regression — paths with spaces must round-trip."""
    line = (
        '[ERROR] file=path with space/x.py:1 rule=Q15.spine-docstring-required '
        'message="m" suggestion="s"'
    )
    findings = parse_h16_output(line)
    assert len(findings) == 1
    assert findings[0].file == "path with space/x.py"


# ────────── severity_map integration ──────────


def test_tier_for_known_rule():
    assert tier_for("Q13.route-needs-auth") == "P0_security"
    assert tier_for("Q15.spine-docstring-required") == "P2_quality"
    assert tier_for("Q18.python-snake-case") == "P3_style"


def test_tier_for_unknown_rule():
    assert tier_for("ZZ99.totally-unknown") == "uncategorized"


def test_explainer_for_known_rule():
    why, fix = explainer_for("Q13.route-needs-auth")
    assert "auth" in why.lower()
    assert len(fix) > 0


# ────────── human mode ──────────


def test_human_mode_empty_findings():
    result = format_findings([], mode="human")
    assert result.exit_code == 0
    assert "✓" in result.text or "No findings" in result.text


def test_human_mode_groups_by_severity():
    findings = [
        Finding("Q13.route-needs-auth", "backend/api.py:42"),
        Finding("Q15.spine-docstring-required", "backend/x.py:10"),
        Finding("Q15.spine-docstring-required", "backend/y.py:20"),
    ]
    result = format_findings(findings, mode="human")
    # P0 should appear before P2.
    p0_idx = result.text.find("P0")
    p2_idx = result.text.find("P2")
    assert p0_idx >= 0 and p2_idx >= 0
    assert p0_idx < p2_idx


def test_human_mode_collapses_same_rule():
    findings = [
        Finding("Q15.spine-docstring-required", f"backend/f{i}.py:1")
        for i in range(5)
    ]
    result = format_findings(findings, mode="human")
    assert "5 occurrences" in result.text


def test_human_mode_shows_why_and_fix_and_more():
    findings = [Finding("Q13.route-needs-auth", "backend/api.py:1")]
    result = format_findings(findings, mode="human")
    assert "Why:" in result.text
    assert "Fix:" in result.text
    assert "More:" in result.text
    assert "harness rules explain Q13.route-needs-auth" in result.text


def test_human_mode_exit_1_on_p0():
    findings = [Finding("Q13.route-needs-auth", "x.py:1")]
    result = format_findings(findings, mode="human")
    assert result.exit_code == 1


def test_human_mode_exit_1_on_p1():
    findings = [Finding("Q7.no-requests", "x.py:1")]
    result = format_findings(findings, mode="human")
    assert result.exit_code == 1


def test_human_mode_exit_0_on_only_p3():
    findings = [Finding("Q18.python-snake-case", "x.py:1")]
    result = format_findings(findings, mode="human")
    assert result.exit_code == 0
    assert "non-blocking" in result.text or "PASS" in result.text


def test_human_mode_exit_0_on_only_p2():
    findings = [Finding("Q15.spine-docstring-required", "x.py:1")]
    result = format_findings(findings, mode="human")
    assert result.exit_code == 0


def test_human_mode_status_fail_label():
    findings = [Finding("Q13.route-needs-auth", "x.py:1")]
    result = format_findings(findings, mode="human")
    assert "FAIL" in result.text


def test_human_mode_status_pass_label():
    findings = [Finding("Q15.spine-docstring-required", "x.py:1")]
    result = format_findings(findings, mode="human")
    assert "PASS" in result.text


def test_human_mode_no_color_when_piped_no_color_env(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    findings = [Finding("Q13.route-needs-auth", "x.py:1")]
    result = format_findings(findings, mode="human")
    assert "\x1b[" not in result.text


# ────────── json mode ──────────


def test_json_mode_stable_shape():
    findings = [
        Finding("Q13.route-needs-auth", "x.py:42",
                message="m", suggestion="s"),
    ]
    result = format_findings(findings, mode="json")
    assert result.exit_code == 0
    parsed = json.loads(result.text)
    assert "summary" in parsed
    assert "findings" in parsed
    assert parsed["summary"]["total"] == 1
    assert "P0_security" in parsed["summary"]["by_severity"]
    assert parsed["findings"][0]["rule"] == "Q13.route-needs-auth"
    assert parsed["findings"][0]["file"] == "x.py"
    assert parsed["findings"][0]["line"] == 42
    assert parsed["findings"][0]["tier"] == "P0_security"


def test_json_mode_empty_findings():
    result = format_findings([], mode="json")
    assert result.exit_code == 0
    parsed = json.loads(result.text)
    assert parsed["summary"]["total"] == 0
    assert parsed["findings"] == []


def test_json_mode_always_exit_0():
    """Even with critical findings, --mode=json exits 0 (consumer reads JSON)."""
    findings = [Finding("Q13.route-needs-auth", "x.py:1") for _ in range(10)]
    result = format_findings(findings, mode="json")
    assert result.exit_code == 0


# ────────── raw + pre-commit ──────────


def test_raw_mode_emits_h16_lines():
    findings = [
        Finding("Q13.route-needs-auth", "x.py:1",
                message="m", suggestion="s"),
    ]
    result = format_findings(findings, mode="raw")
    assert result.text.startswith("[ERROR] file=x.py:1 rule=Q13.route-needs-auth")


def test_raw_mode_exit_1_on_any_finding():
    findings = [Finding("Q15.spine-docstring-required", "x.py:1")]
    result = format_findings(findings, mode="raw")
    assert result.exit_code == 1


def test_raw_mode_empty_exit_0():
    result = format_findings([], mode="raw")
    assert result.exit_code == 0
    assert result.text.strip() == ""


def test_pre_commit_mode_exit_1_on_p3_only():
    """v1.x compat: pre-commit fails on ANY finding, including P3."""
    findings = [Finding("Q18.python-snake-case", "x.py:1")]
    result = format_findings(findings, mode="pre-commit")
    assert result.exit_code == 1


def test_pre_commit_mode_emits_h16_format():
    findings = [Finding("Q15.spine-docstring-required", "x.py:1",
                        message="m", suggestion="s")]
    result = format_findings(findings, mode="pre-commit")
    assert "[ERROR] file=x.py:1" in result.text


def test_unknown_mode_raises():
    with pytest.raises(ValueError, match="unknown mode"):
        format_findings([], mode="invalid")


# ────────── round-trip ──────────


def test_h16_line_roundtrip():
    """parse_h16_output(format_raw(...)) returns the same Finding."""
    original = [
        Finding("Q13.route-needs-auth", "backend/api.py:42",
                message="m1", suggestion="s1"),
        Finding("Q15.spine-docstring-required", "backend/x.py:10",
                message="m2", suggestion="s2"),
    ]
    result = format_findings(original, mode="raw")
    reparsed = parse_h16_output(result.text)
    assert len(reparsed) == len(original)
    for orig, parsed in zip(original, reparsed):
        assert orig.rule == parsed.rule
        assert orig.location == parsed.location
        assert orig.message == parsed.message
