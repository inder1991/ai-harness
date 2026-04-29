"""Sprint 4 / S4.5 — v1.x → v2.x migration.

Brings a consumer that installed ai-harness during v1.0.x – v1.3.x up to
the v2.x layout. The migration is **non-destructive by default**: every
step writes to a snapshot first, and any failure restores the snapshot.

What changes in v2.x that this migrator handles:

  1. `.harness/profiles/` is a new directory of composite YAMLs. v1.x
     consumers don't have it; we copy it from the source repo so
     `extends:` references can resolve.
  2. `.harness/profile.yaml` gains an optional `extends:` field that
     points at one of the new composites. We add it based on the
     installed `profile:` value (no-op if no matching composite ships).
  3. `HARNESS_CARD.yaml.version` is bumped to match `.harness-version`
     (Q21 — versions must agree).
  4. Pre-v1.1.0 baselines may have absolute paths from the original
     install machine. We invoke the existing
     `refresh_baselines.py --migrate-paths` to re-key them to repo-
     relative form.

Steps NOT yet automated (intentional — flagged in UPGRADE.md):
  - Moving flat `.harness/checks/*.py` into pack subdirs. The flat
    layout still works in v2.x (`active_check_files` falls back), so
    the migration leaves files where they are. Consumers who want the
    clean layout can run `tools/migrations/v2_pack_split.py` later.

Public surface (used by `harness upgrade --from v1.x --to v2.x` and by
`harness doctor --check-upgrade`):

    detect_state(target)         -> MigrationState
    plan(target)                 -> list[Step]      (read-only; for doctor)
    run(target, *, dry_run=...)  -> int             (0 on success)

Exit codes (when invoked via the CLI):
  0  migration completed
  2  bad input / target not a directory / not a v1.x install
  5  migration failed (snapshot restored)
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class MigrationState:
    """The detected pre-migration state of a consumer install."""

    target: Path
    pinned_version: str
    profile: str
    has_profiles_dir: bool
    has_extends: bool
    needs_card_bump: bool
    needs_baseline_migration: bool


@dataclass
class Step:
    """One migration step. `apply` runs the change; `describe` is the
    human-readable summary used by `harness doctor`."""

    name: str
    describe: str
    apply: Callable[[MigrationState], None]


def _read_pin(target: Path) -> str:
    pin = target / ".harness-version"
    if pin.exists():
        return pin.read_text(encoding="utf-8").strip()
    return ""


def _read_profile_yaml(target: Path) -> dict:
    p = target / ".harness" / "profile.yaml"
    if not p.exists():
        return {}
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}


def _read_card_version(target: Path) -> str:
    card = target / ".harness" / "HARNESS_CARD.yaml"
    if not card.exists():
        return ""
    try:
        data = yaml.safe_load(card.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return ""
    return str(data.get("version", ""))


def _read_baselines_for_absolute_paths(target: Path) -> bool:
    """True if any baseline JSON has an entry whose `file` is absolute,
    indicating it was generated pre-v1.1.0 on a foreign machine."""
    baselines_dir = target / ".harness" / "baselines"
    if not baselines_dir.is_dir():
        return False
    for path in baselines_dir.glob("*_baseline.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, list):
            continue
        for entry in data:
            if isinstance(entry, dict) and isinstance(entry.get("file"), str):
                f = entry["file"]
                if f.startswith("/") or (len(f) >= 2 and f[1] == ":"):
                    return True
    return False


def detect_state(target: Path) -> MigrationState:
    """Inspect a consumer install. Pure read; no writes."""
    pinned = _read_pin(target)
    pdoc = _read_profile_yaml(target)
    profile = str(pdoc.get("profile", "minimal"))
    has_profiles_dir = (target / ".harness" / "profiles").is_dir()
    has_extends = "extends" in pdoc
    card_v = _read_card_version(target)
    pinned_clean = pinned.lstrip("v")
    needs_card_bump = bool(pinned_clean and card_v and card_v != pinned_clean)
    needs_baseline = _read_baselines_for_absolute_paths(target)
    return MigrationState(
        target=target,
        pinned_version=pinned,
        profile=profile,
        has_profiles_dir=has_profiles_dir,
        has_extends=has_extends,
        needs_card_bump=needs_card_bump,
        needs_baseline_migration=needs_baseline,
    )


def _step_copy_profiles_dir(state: MigrationState) -> None:
    src = REPO_ROOT / ".harness" / "profiles"
    dst = state.target / ".harness" / "profiles"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _step_add_extends(state: MigrationState) -> None:
    pdoc = _read_profile_yaml(state.target)
    composite = REPO_ROOT / ".harness" / "profiles" / f"{state.profile}.yaml"
    if not composite.exists():
        # No matching composite ships; leave profile.yaml alone.
        return
    pdoc["extends"] = [state.profile]
    out = state.target / ".harness" / "profile.yaml"
    out.write_text(yaml.safe_dump(pdoc, sort_keys=False))


def _step_bump_card(state: MigrationState) -> None:
    card = state.target / ".harness" / "HARNESS_CARD.yaml"
    if not card.exists():
        return
    try:
        data = yaml.safe_load(card.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return
    pinned_clean = state.pinned_version.lstrip("v")
    if pinned_clean:
        data["version"] = pinned_clean
        card.write_text(yaml.safe_dump(data, sort_keys=False))


def _step_migrate_baselines(state: MigrationState) -> None:
    script = REPO_ROOT / "tools" / "refresh_baselines.py"
    if not script.exists():
        return
    subprocess.run(
        [sys.executable, str(script), "--migrate-paths"],
        cwd=state.target, check=False,
    )


def plan(target: Path) -> list[Step]:
    """Return the ordered list of migration steps for `target`. Read-only.

    Used by `harness doctor --check-upgrade` to surface what would happen.
    """
    state = detect_state(target)
    steps: list[Step] = []
    if not state.has_profiles_dir:
        steps.append(Step(
            name="copy-profiles-dir",
            describe="Copy `.harness/profiles/` from the source repo (composite YAMLs).",
            apply=_step_copy_profiles_dir,
        ))
    if not state.has_extends:
        composite = REPO_ROOT / ".harness" / "profiles" / f"{state.profile}.yaml"
        if composite.exists():
            steps.append(Step(
                name="add-extends",
                describe=f"Add `extends: [{state.profile}]` to .harness/profile.yaml.",
                apply=_step_add_extends,
            ))
    if state.needs_card_bump:
        steps.append(Step(
            name="bump-card",
            describe=f"Bump HARNESS_CARD.yaml.version to {state.pinned_version}.",
            apply=_step_bump_card,
        ))
    if state.needs_baseline_migration:
        steps.append(Step(
            name="migrate-baselines",
            describe="Re-key absolute-path baselines to repo-relative (refresh_baselines.py --migrate-paths).",
            apply=_step_migrate_baselines,
        ))
    return steps


def _snapshot(target: Path) -> Path:
    snap = target / ".harness.pre-upgrade"
    if snap.exists():
        shutil.rmtree(snap)
    src = target / ".harness"
    if not src.is_dir():
        snap.mkdir()
        return snap
    shutil.copytree(src, snap)
    return snap


def _restore(target: Path, snap: Path) -> None:
    dst = target / ".harness"
    if dst.exists():
        shutil.rmtree(dst)
    if snap.exists():
        shutil.copytree(snap, dst)


def run(target: Path, *, dry_run: bool = False, on_failure_restore: bool = True) -> int:
    """Apply the migration to `target`. Returns 0 on success, 5 on failure
    (snapshot restored, target back to v1.x state).

    Args:
        target: Consumer repo root.
        dry_run: If True, only print the plan; don't apply.
        on_failure_restore: If True (default), restore the snapshot on
            any per-step exception. Set False when the caller wants to
            inspect the partial state (used in tests).
    """
    if not target.is_dir():
        print(f"[ERROR] target is not a directory: {target}", file=sys.stderr)
        return 2
    if not (target / ".harness").is_dir():
        print(f"[ERROR] no .harness/ at {target}; not a v1.x install", file=sys.stderr)
        return 2

    state = detect_state(target)
    steps = plan(target)
    print(f"v1.x → v2.x migration: {len(steps)} step(s) on {target}")
    for step in steps:
        print(f"  · {step.describe}")
    if dry_run:
        return 0
    if not steps:
        print("nothing to migrate; already on v2 layout.")
        return 0

    snap = _snapshot(target)
    try:
        for step in steps:
            step.apply(state)
            # Refresh state after each step so subsequent steps see it.
            state = detect_state(target)
    except Exception as exc:  # noqa: BLE001 — best-effort step apply
        print(f"[ERROR] migration step failed: {exc}", file=sys.stderr)
        if on_failure_restore:
            _restore(target, snap)
            print("snapshot restored; target back to v1.x state.", file=sys.stderr)
            return 5
        raise
    print("migration complete.")
    return 0


__all__ = ["MigrationState", "Step", "detect_state", "plan", "run"]
