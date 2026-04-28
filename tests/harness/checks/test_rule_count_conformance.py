"""v1.3.0 S3 / Q22 — doc-vs-impl rule-count conformance check tests."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CHECK = REPO_ROOT / ".harness/checks/rule_count_conformance.py"
COMMON = REPO_ROOT / ".harness/checks/_common.py"


def _stage_repo(tmp_path: Path, fixture_name: str, source_kind: str) -> Path:
    """Copy the check + a single fixture into a tmp tree, returning the
    path to the staged check script."""
    fake = tmp_path / "fake_repo"
    fake_checks = fake / ".harness" / "checks"
    fake_checks.mkdir(parents=True)
    shutil.copy2(CHECK, fake_checks / "rule_count_conformance.py")
    shutil.copy2(COMMON, fake_checks / "_common.py")
    (fake_checks / "__init__.py").write_text("")
    src = REPO_ROOT / "tests/harness/fixtures/rule_count_conformance" / source_kind / fixture_name
    shutil.copy2(src, fake_checks / fixture_name)
    return fake_checks / "rule_count_conformance.py"


def test_compliant_fixture_passes(tmp_path):
    check = _stage_repo(tmp_path, "check_two_rules.py", "compliant")
    result = subprocess.run(
        [sys.executable, str(check)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, (
        f"check should pass on compliant fixture. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_violation_fixture_fires(tmp_path):
    check = _stage_repo(tmp_path, "check_count_drift.py", "violation")
    result = subprocess.run(
        [sys.executable, str(check)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 1
    assert "Q22.doc-rule-count-mismatch" in result.stdout
    assert "claims 3" in result.stdout
    assert "enumerates 2" in result.stdout


def test_silent_when_no_count_claim(tmp_path):
    """A check whose docstring doesn't make a numeric `N rules` claim
    must not fire (Q22 only catches contradictions, not omissions)."""
    fake = tmp_path / "fake_repo"
    fake_checks = fake / ".harness" / "checks"
    fake_checks.mkdir(parents=True)
    shutil.copy2(CHECK, fake_checks / "rule_count_conformance.py")
    shutil.copy2(COMMON, fake_checks / "_common.py")
    (fake_checks / "__init__.py").write_text("")
    (fake_checks / "no_count_claim.py").write_text(
        '"""A check with no numeric rule count claim.\n'
        '\n'
        'It enforces Q99.something but does not say how many rules.\n'
        '"""\n'
    )
    result = subprocess.run(
        [sys.executable, str(fake_checks / "rule_count_conformance.py")],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
