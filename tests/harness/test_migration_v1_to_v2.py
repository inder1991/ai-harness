"""Sprint 4 / S4.5 — v1.x → v2.x migration tests.

Three fixture snapshots represent the three release lines a real
consumer might be on (v1.0.4, v1.2.1, v1.3.1). For each, the migration
must:
  * detect the v1 layout
  * propose at least one step (copy profiles dir + add extends)
  * run end-to-end without throwing
  * leave the consumer with a valid v2 layout (`.harness/profiles/`,
    `extends: [<profile>]` in profile.yaml, HARNESS_CARD bumped)
  * support dry-run (no writes)
  * snapshot + restore on failure
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tools.migrations import v1_to_v2  # noqa: E402

FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures/migrations"


def _stage(tmp_path: Path, fixture_name: str) -> Path:
    """Copy a v1.x fixture snapshot into tmp_path and return the new root."""
    src = FIXTURE_ROOT / fixture_name
    dst = tmp_path / fixture_name
    shutil.copytree(src, dst)
    return dst


@pytest.mark.parametrize("fixture", ["v1.0.4", "v1.2.1", "v1.3.1"])
def test_migration_detects_v1_state(tmp_path, fixture: str) -> None:
    target = _stage(tmp_path, fixture)
    state = v1_to_v2.detect_state(target)
    assert state.pinned_version.startswith("v1.")
    assert state.has_profiles_dir is False
    assert state.has_extends is False


@pytest.mark.parametrize("fixture", ["v1.0.4", "v1.2.1", "v1.3.1"])
def test_migration_plan_is_non_empty(tmp_path, fixture: str) -> None:
    target = _stage(tmp_path, fixture)
    steps = v1_to_v2.plan(target)
    assert len(steps) >= 2  # at minimum: copy-profiles + add-extends
    names = {step.name for step in steps}
    assert "copy-profiles-dir" in names
    assert "add-extends" in names


@pytest.mark.parametrize("fixture", ["v1.0.4", "v1.2.1", "v1.3.1"])
def test_migration_runs_end_to_end(tmp_path, fixture: str) -> None:
    target = _stage(tmp_path, fixture)
    rc = v1_to_v2.run(target)
    assert rc == 0
    # Post-conditions:
    assert (target / ".harness/profiles").is_dir()
    pdoc = yaml.safe_load((target / ".harness/profile.yaml").read_text())
    assert "extends" in pdoc
    assert pdoc["extends"][0] == pdoc["profile"]
    # HARNESS_CARD should match .harness-version (Q21).
    card = yaml.safe_load((target / ".harness/HARNESS_CARD.yaml").read_text())
    pin = (target / ".harness-version").read_text().strip().lstrip("v")
    assert str(card["version"]) == pin


def test_migration_dry_run_makes_no_changes(tmp_path) -> None:
    target = _stage(tmp_path, "v1.0.4")
    pdoc_before = (target / ".harness/profile.yaml").read_text()
    rc = v1_to_v2.run(target, dry_run=True)
    assert rc == 0
    pdoc_after = (target / ".harness/profile.yaml").read_text()
    assert pdoc_before == pdoc_after
    assert not (target / ".harness/profiles").exists()


def test_migration_snapshot_restored_on_failure(tmp_path, monkeypatch) -> None:
    """If a step throws mid-flight, the snapshot is restored."""
    target = _stage(tmp_path, "v1.2.1")
    pdoc_before = (target / ".harness/profile.yaml").read_text()

    # Force the second step (add-extends) to throw.
    real = v1_to_v2._step_add_extends

    def boom(state):  # noqa: ANN001
        raise RuntimeError("simulated migration failure")

    monkeypatch.setattr(v1_to_v2, "_step_add_extends", boom)
    rc = v1_to_v2.run(target)
    assert rc == 5
    # Snapshot restored: profile.yaml unchanged, profiles dir gone.
    pdoc_after = (target / ".harness/profile.yaml").read_text()
    assert pdoc_before == pdoc_after
    assert not (target / ".harness/profiles").exists()


def test_migration_idempotent_on_already_v2_install(tmp_path) -> None:
    """Running migration on an already-migrated install is a no-op."""
    target = _stage(tmp_path, "v1.3.1")
    assert v1_to_v2.run(target) == 0
    # Second run finds nothing to migrate.
    rc = v1_to_v2.run(target)
    assert rc == 0
    state = v1_to_v2.detect_state(target)
    assert state.has_profiles_dir
    assert state.has_extends


def test_doctor_check_upgrade_flags_pending(tmp_path) -> None:
    """`harness doctor --check-upgrade` exits 1 when migration is pending."""
    target = _stage(tmp_path, "v1.0.4")
    cmd = [
        sys.executable, "-m", "tools.harness_cli", "doctor",
        "--target", str(target), "--check-upgrade",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert result.returncode == 1
    assert "migration step(s) pending" in result.stdout


def test_doctor_check_upgrade_clean_on_v2_install(tmp_path) -> None:
    target = _stage(tmp_path, "v1.3.1")
    v1_to_v2.run(target)
    cmd = [
        sys.executable, "-m", "tools.harness_cli", "doctor",
        "--target", str(target), "--check-upgrade",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0
    assert "on v2 layout" in result.stdout


def test_upgrade_cli_runs_migration_with_explicit_versions(tmp_path) -> None:
    """`harness upgrade --from v1.0.4 --to v2.0.0 --migrate-only` works."""
    target = _stage(tmp_path, "v1.0.4")
    cmd = [
        sys.executable, "-m", "tools.harness_cli", "upgrade",
        "--target", str(target),
        "--from", "v1.0.4", "--to", "v2.0.0",
        "--migrate-only",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    pdoc = yaml.safe_load((target / ".harness/profile.yaml").read_text())
    assert "extends" in pdoc


def test_v1_0_4_baseline_path_migration_flagged(tmp_path) -> None:
    """v1.0.4 fixture has an absolute-path baseline; plan must include
    the migrate-baselines step."""
    target = _stage(tmp_path, "v1.0.4")
    state = v1_to_v2.detect_state(target)
    assert state.needs_baseline_migration is True
    names = {step.name for step in v1_to_v2.plan(target)}
    assert "migrate-baselines" in names
