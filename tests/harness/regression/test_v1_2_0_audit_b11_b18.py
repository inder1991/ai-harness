"""Sprint 0 / S0.4 — regression tests for v1.2.0 P1 audit (B11-B18)."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tools"))


# REGRESSION-FOR: B11 (init_harness copies .gitattributes)
def test_b11_init_harness_copies_gitattributes(tmp_path):
    target = tmp_path / "consumer"
    subprocess.check_call(
        [sys.executable, str(REPO_ROOT / "tools/init_harness.py"),
         "--target", str(target), "--owner", "@test", "--tech-stack", "polyglot"],
        timeout=60,
    )
    ga = target / ".gitattributes"
    assert ga.exists(), "init_harness must copy .gitattributes (B11)"
    assert "eol=lf" in ga.read_text()


# REGRESSION-FOR: B12 (init_harness writes .harness-version pin)
def test_b12_init_harness_writes_pin(tmp_path):
    target = tmp_path / "consumer"
    subprocess.check_call(
        [sys.executable, str(REPO_ROOT / "tools/init_harness.py"),
         "--target", str(target), "--owner", "@test", "--tech-stack", "polyglot"],
        timeout=60,
    )
    pin = target / ".harness-version"
    assert pin.exists(), "init_harness must write .harness-version (B12)"
    assert pin.read_text().strip() == "main"


# REGRESSION-FOR: B13 (every git subprocess has timeout=)
def test_b13_every_git_subprocess_has_timeout():
    GIT_CALL_RE = re.compile(
        r'subprocess\.(?:run|check_call|check_output)\s*\(\s*\[\s*["\']git["\']',
        re.MULTILINE,
    )
    targets = [
        REPO_ROOT / "tools/init_harness.py",
        REPO_ROOT / "tools/sync_harness.py",
    ]
    offenders: list[str] = []
    for path in targets:
        text = path.read_text()
        for match in GIT_CALL_RE.finditer(text):
            # Walk to the matching close paren at depth 0.
            depth, close = 0, None
            for i, ch in enumerate(text[match.start(): match.start() + 800]):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        close = i
                        break
            window = text[match.start(): match.start() + (close + 1 if close else 800)]
            if "timeout=" not in window:
                line_no = text[: match.start()].count("\n") + 1
                offenders.append(f"{path.name}:{line_no}")
    assert not offenders, (
        f"git subprocess calls missing timeout= (B13): {offenders}"
    )


# REGRESSION-FOR: B14 (run_validate enforces CHECK_TIMEOUT_S per check)
def test_b14_run_validate_has_check_timeout():
    src = (REPO_ROOT / "tools/run_validate.py").read_text()
    assert "CHECK_TIMEOUT_S" in src, (
        "run_validate.py must declare CHECK_TIMEOUT_S (B14)"
    )
    # The timeout must actually be passed to subprocess.run.
    assert "timeout=CHECK_TIMEOUT_S" in src or "timeout = CHECK_TIMEOUT_S" in src


# REGRESSION-FOR: B15 (sync_harness --trust-key fingerprint pinning)
def test_b15_sync_harness_supports_trust_key():
    src = (REPO_ROOT / "tools/sync_harness.py").read_text()
    assert "--trust-key" in src, "sync_harness must accept --trust-key (B15)"
    assert "HARNESS_TRUST_KEY" in src, "must honor env-var fallback"


# REGRESSION-FOR: B15 (mismatched fingerprint rejected)
def test_b15_verify_tag_rejects_mismatched_fingerprint(tmp_path):
    from tools import sync_harness
    fake_clone = tmp_path / "clone"
    fake_clone.mkdir()

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["git", "cat-file", "-t"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="tag\n", stderr="")
        if cmd[:2] == ["git", "verify-tag"]:
            stderr = (
                "[GNUPG:] VALIDSIG ATTACKER_FPR_DEADBEEF 2026-04-27 1745... "
                "0 4 0 22 8 ATTACKER_FPR_DEADBEEF\n"
            )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr=stderr)
        raise AssertionError(f"unexpected: {cmd}")

    with patch("subprocess.run", side_effect=fake_run):
        ok, msg = sync_harness._verify_tag(
            fake_clone, "v1.0.0", trust_fingerprint="73A7AF8F04F40EC9",
        )
    assert not ok
    assert "fingerprint" in msg.lower()


# REGRESSION-FOR: B16 (Q21 harness-card-version-mismatch check exists)
def test_b16_harness_card_version_check_exists():
    check = REPO_ROOT / ".harness/checks/harness_card_version.py"
    assert check.exists(), "Q21 check must ship (B16)"


# REGRESSION-FOR: B17 (extract.sh smoke-tests the carved repo)
def test_b17_extract_sh_runs_smoke_test():
    text = (REPO_ROOT / "tools/extraction/extract.sh").read_text()
    assert "pytest tests/harness" in text, (
        "extract.sh must smoke-test (B17)"
    )
    smoke_idx = text.find("pytest tests/harness")
    move_idx = text.find('mv "${MIRROR}" "${TARGET}"')
    assert move_idx >= 0 and smoke_idx > move_idx, (
        "smoke test must run AFTER `mv MIRROR TARGET` (B17)"
    )


# REGRESSION-FOR: B18 (run_validate.run_tests invokes vitest)
def test_b18_run_tests_calls_vitest_when_frontend_present():
    src = (REPO_ROOT / "tools/run_validate.py").read_text()
    assert "vitest" in src, "run_validate must invoke vitest (B18)"
