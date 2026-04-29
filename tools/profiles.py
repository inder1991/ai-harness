"""Sprint 4 / S4.1 — profile composition.

A profile YAML lists which check-packs to enable, plus per-key
overrides for inherited policy YAMLs and a list of locked rules
(reserved for Sprint 6 / S6.5 RBAC).

  # .harness/profile.yaml or .harness/profiles/<name>.yaml
  schema_version: "1"
  profile: python-react   # the canonical profile name
  owner: '@team'
  extends:                # NEW in Sprint 4 (optional; can be omitted)
    - python-backend
    - react-frontend
    - cross-cutting
    - self-tests
  disabled:               # NEW (optional; rule IDs to suppress)
    - Q15.frontend-jsdoc-required
  overrides:              # NEW (optional; per-key policy YAML overrides)
    security_policy.yaml:
      rate_limit_exempt:
        - "GET:/healthz"

Resolution algorithm:
  1. Topo-sort `extends` (cycles → ProfileError).
  2. For each pack name, glob `.harness/checks/<pack>/*.py`.
  3. Merge in source order; later packs override earlier ones on
     same-rule conflicts (with a [WARN]).
  4. Apply `disabled` set (excluded from active rules).
  5. Apply `overrides` to the policy-yaml-load step (consumers'
     existing yaml read path goes through this layer).

Pure functions; no I/O outside the target dir.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


class ProfileError(Exception):
    """Raised on cycles, missing packs, or schema violations."""


@dataclass
class ResolvedProfile:
    """The flattened result of resolving a profile YAML."""
    profile: str
    owner: str
    packs_resolved: list[str] = field(default_factory=list)
    disabled: set[str] = field(default_factory=set)
    overrides: dict[str, dict] = field(default_factory=dict)
    locked_rules: list[str] = field(default_factory=list)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise ProfileError(f"profile yaml not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProfileError(f"profile yaml malformed: {path}: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ProfileError(
            f"profile yaml malformed: {path}: top-level must be a mapping, "
            f"got {type(data).__name__}"
        )
    return data


def _expand_pack(pack: str, profiles_dir: Path, seen: set[str]) -> Iterator[str]:
    """Recursively expand `extends`. Cycle detection raises ProfileError.

    Pack names map to either:
      - .harness/profiles/<pack>.yaml (composite profile referencing more packs), OR
      - .harness/checks/<pack>/ (a leaf pack — directory of check files), OR
      - the special name itself (treated as a leaf if no yaml/dir found).
    """
    if pack in seen:
        cycle = " → ".join(list(seen) + [pack])
        raise ProfileError(f"profile inheritance cycle: {cycle}")
    seen.add(pack)
    profile_yaml = profiles_dir / f"{pack}.yaml"
    if profile_yaml.exists():
        sub = _load_yaml(profile_yaml)
        for child in (sub.get("extends") or []):
            yield from _expand_pack(child, profiles_dir, seen)
    else:
        # Leaf pack — yields itself; the caller decides if checks are present.
        yield pack
    seen.discard(pack)


def resolve_profile(target: Path) -> ResolvedProfile:
    """Read `<target>/.harness/profile.yaml`, expand `extends`, return
    a flattened ResolvedProfile.

    Args:
        target: The consumer repo root (the directory containing .harness/).

    Returns:
        A ResolvedProfile with `packs_resolved` topologically ordered.

    Raises:
        ProfileError: cycle, malformed yaml, missing profile yaml.
    """
    profile_yaml_path = target / ".harness" / "profile.yaml"
    data = _load_yaml(profile_yaml_path)
    profile = data.get("profile", "minimal")
    owner = data.get("owner", "")
    extends = data.get("extends") or []

    profiles_dir = target / ".harness" / "profiles"
    packs: list[str] = []
    if extends:
        seen: set[str] = set()
        for pack_name in extends:
            for resolved in _expand_pack(pack_name, profiles_dir, seen):
                if resolved not in packs:
                    packs.append(resolved)

    disabled = set(data.get("disabled") or [])
    overrides = data.get("overrides") or {}
    locked = list(data.get("locked_rules") or [])

    return ResolvedProfile(
        profile=profile,
        owner=owner,
        packs_resolved=packs,
        disabled=disabled,
        overrides=overrides,
        locked_rules=locked,
    )


def active_check_files(target: Path, profile: ResolvedProfile) -> list[Path]:
    """Walk the resolved packs and return every active check file.

    Lookup order for a pack name:
      1. .harness/checks/<pack>/*.py  (Sprint 4 layout — pack subdir)
      2. .harness/checks/*.py         (v1.x flat layout — used when a
         pack name has no subdir; the flat layout is included so
         cross-cutting / self-tests / etc. still run on a Node-only
         consumer until the migration script moves them into subdirs)

    A check is "active" if its module emits any rule NOT in
    `profile.disabled`. (Per-rule disabling is enforced at emit-time
    by the orchestrator; this function returns the FILES to scan.)
    """
    checks_root = target / ".harness" / "checks"

    def _flat_files() -> list[Path]:
        out: list[Path] = []
        for p in sorted(checks_root.glob("*.py")):
            if p.name in {"__init__.py", "_common.py"}:
                continue
            out.append(p)
        return out

    if not profile.packs_resolved:
        # No `extends` declared → keep v1.x behavior: every flat check file.
        return _flat_files()

    seen: set[Path] = set()
    out: list[Path] = []
    any_unresolved = False
    for pack in profile.packs_resolved:
        sub = checks_root / pack
        if sub.is_dir():
            for p in sorted(sub.glob("*.py")):
                if p.name in {"__init__.py", "_common.py"}:
                    continue
                if p not in seen:
                    seen.add(p)
                    out.append(p)
            continue
        any_unresolved = True

    # If any pack name didn't resolve to a subdir, supplement with flat
    # checks so v1.x consumers (and Node-only profiles whose `cross-cutting`
    # / `self-tests` packs aren't migrated yet) keep their checks.
    if any_unresolved or not out:
        for p in _flat_files():
            if p not in seen:
                seen.add(p)
                out.append(p)
    return out


def is_rule_disabled(rule_id: str, profile: ResolvedProfile) -> bool:
    """True if the rule is in the profile's `disabled` list."""
    return rule_id in profile.disabled


def policy_overrides(profile: ResolvedProfile, yaml_name: str) -> dict:
    """Return the override dict for one policy yaml. Empty if no override."""
    return dict(profile.overrides.get(yaml_name) or {})
