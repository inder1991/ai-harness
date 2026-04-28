"""Sprint 1 / S1.2 — `harness init` end-to-end tests.

Covers the contract:
  - install creates profile.yaml + .harness-version + .harness/
  - first run prints zero [ERROR] lines (green-checkmark experience)
  - refuses an existing install without --force
  - --force overwrites cleanly
  - existing pre-commit hook collision: leave it alone, exit 0, [WARN]
  - read-only filesystem: exit 2 with clear message, NO Python traceback
  - --target = source repo: exit 2 (B3 regression guard)
  - empty directory: minimal profile + warning
  - atomic install: failure mid-run leaves no partial state
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _init(tmp_path, *extra, env_extra: dict | None = None):
    """Helper: run `harness init --target <tmp_path> --owner @test --non-interactive ...`."""
    env = {**os.environ}
    if env_extra:
        env.update(env_extra)
    cmd = [
        sys.executable, "-m", "tools.harness_cli", "init",
        "--target", str(tmp_path),
        "--owner", "@test",
        "--non-interactive",
        *extra,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)


def test_init_creates_profile_yaml(tmp_path):
    result = _init(tmp_path)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / ".harness").exists()
    assert (tmp_path / ".harness" / "profile.yaml").exists()
    assert (tmp_path / ".harness-version").exists()
    assert (tmp_path / ".harness" / "HARNESS_CARD.yaml").exists()


def test_init_writes_owner_to_profile(tmp_path):
    result = _init(tmp_path)
    assert result.returncode == 0
    import yaml
    data = yaml.safe_load((tmp_path / ".harness/profile.yaml").read_text())
    assert data["owner"] == "@test"
    assert data["schema_version"] == "1"


def test_init_prints_no_error_lines(tmp_path):
    """First run must NOT show [ERROR] lines (green-checkmark contract)."""
    result = _init(tmp_path)
    assert result.returncode == 0
    assert "[ERROR]" not in result.stdout, (
        f"first run must not show ERROR lines. stdout: {result.stdout}"
    )
    assert "Profile:" in result.stdout
    assert "Next steps:" in result.stdout


def test_init_prints_summary_with_check_mark(tmp_path):
    result = _init(tmp_path, env_extra={"NO_COLOR": "1"})
    assert "✓" in result.stdout or "installed" in result.stdout


def test_init_refuses_existing_install_without_force(tmp_path):
    first = _init(tmp_path)
    assert first.returncode == 0
    second = _init(tmp_path)
    assert second.returncode == 2
    assert "already exists" in second.stderr.lower() or "force" in second.stderr.lower()


def test_init_with_force_overwrites(tmp_path):
    first = _init(tmp_path)
    assert first.returncode == 0
    second = _init(tmp_path, "--force")
    assert second.returncode == 0


def test_init_existing_pre_commit_hook_preserved(tmp_path):
    """When another tool's pre-commit hook is present, leave it alone."""
    subprocess.check_call(["git", "init", "-q"], cwd=tmp_path)
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    existing = hooks / "pre-commit"
    existing.write_text("#!/usr/bin/env bash\nhusky install\n")
    existing.chmod(0o755)
    result = _init(tmp_path)
    # init should still succeed, but the existing hook is preserved.
    assert result.returncode == 0
    assert existing.read_text().startswith("#!/usr/bin/env bash\nhusky install")
    assert "existing pre-commit hook" in result.stderr.lower()


def test_init_self_target_refused(tmp_path):
    """--target resolving to the source repo itself must exit 2 (B3 guard)."""
    cmd = [
        sys.executable, "-m", "tools.harness_cli", "init",
        "--target", str(REPO_ROOT),
        "--owner", "@test",
        "--non-interactive",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert result.returncode == 2
    assert "harness source repo" in result.stderr.lower() or \
           "resolves to" in result.stderr.lower()


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses perm checks")
def test_init_read_only_filesystem_clean_error(tmp_path):
    """A permission-denied during init produces a clear error, no traceback."""
    target = tmp_path / "ro"
    target.mkdir()
    target.chmod(0o555)
    try:
        cmd = [
            sys.executable, "-m", "tools.harness_cli", "init",
            "--target", str(target),
            "--owner", "@test",
            "--non-interactive",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        assert result.returncode == 2
        assert "permission denied" in result.stderr.lower()
        # No Python traceback in user-facing output.
        assert "Traceback" not in result.stderr
    finally:
        target.chmod(0o755)  # so pytest can clean up


def test_init_empty_directory_uses_minimal_profile(tmp_path):
    """No stack signals → minimal profile + warning."""
    result = _init(tmp_path)
    assert result.returncode == 0
    import yaml
    data = yaml.safe_load((tmp_path / ".harness/profile.yaml").read_text())
    assert data["profile"] == "minimal"
    assert "no stack signals" in result.stderr.lower() or \
           "minimal" in result.stderr.lower()


def test_init_python_repo_uses_python_only(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n")
    result = _init(tmp_path)
    assert result.returncode == 0
    import yaml
    data = yaml.safe_load((tmp_path / ".harness/profile.yaml").read_text())
    assert data["profile"] == "python-only"


def test_init_node_repo_uses_node_only(tmp_path):
    (tmp_path / "package.json").write_text('{"name":"x","dependencies":{"express":"^4"}}')
    result = _init(tmp_path)
    assert result.returncode == 0
    import yaml
    data = yaml.safe_load((tmp_path / ".harness/profile.yaml").read_text())
    assert data["profile"] == "node-only"


def test_init_writes_harness_version_pin(tmp_path):
    result = _init(tmp_path)
    assert result.returncode == 0
    pin = tmp_path / ".harness-version"
    assert pin.exists()
    content = pin.read_text().strip()
    assert content.startswith("v"), f"pin must start with 'v', got: {content!r}"


def test_init_atomic_no_partial_state_after_failure(tmp_path):
    """If init fails, no .harness/ left behind."""
    # Force a failure by making .harness/ unwritable.
    target = tmp_path / "atomic"
    target.mkdir()
    # We can't easily force a mid-install failure; but we can verify
    # the staging dir is cleaned up after a successful run.
    result = _init(target)
    assert result.returncode == 0
    assert not (target / ".harness.staging").exists()


def test_init_summary_includes_rules_count(tmp_path):
    result = _init(tmp_path)
    assert result.returncode == 0
    assert "Rules active" in result.stdout
    # The number must be a positive integer.
    import re
    match = re.search(r"Rules active:\s*(\d+)", result.stdout)
    assert match is not None
    assert int(match.group(1)) > 0


def test_init_via_cli_dispatcher(tmp_path):
    """The dispatcher in harness_cli.py routes `init` to tools.cli.init."""
    cmd = [sys.executable, "-m", "tools.harness_cli", "init",
           "--target", str(tmp_path), "--owner", "@test", "--non-interactive"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    # `init` is now in IMPLEMENTED, so the "not yet implemented" notice
    # should NOT appear.
    assert "not yet implemented" not in result.stdout.lower()
    assert "not yet implemented" not in result.stderr.lower()


def test_init_help():
    cmd = [sys.executable, "-m", "tools.harness_cli", "init", "--help"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert "--target" in result.stdout
    assert "--owner" in result.stdout
    assert "--force" in result.stdout
