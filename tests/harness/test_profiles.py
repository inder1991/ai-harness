"""Sprint 4 / S4.1 — profile composition tests."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from profiles import (  # noqa: E402
    ProfileError,
    active_check_files,
    is_rule_disabled,
    policy_overrides,
    resolve_profile,
)


def _make_consumer(tmp_path: Path, profile_yaml: str,
                   profile_dir_files: dict[str, str] | None = None) -> Path:
    """Set up a fake consumer root with .harness/profile.yaml and
    optional .harness/profiles/*.yaml composites."""
    target = tmp_path / "consumer"
    (target / ".harness" / "profiles").mkdir(parents=True)
    (target / ".harness" / "checks").mkdir(parents=True)
    (target / ".harness" / "profile.yaml").write_text(profile_yaml)
    for name, contents in (profile_dir_files or {}).items():
        (target / ".harness" / "profiles" / name).write_text(contents)
    return target


def test_resolves_minimal_profile(tmp_path):
    target = _make_consumer(tmp_path,
        "schema_version: '1'\nprofile: minimal\nowner: '@x'\n")
    p = resolve_profile(target)
    assert p.profile == "minimal"
    assert p.owner == "@x"
    assert p.packs_resolved == []
    assert p.disabled == set()


def test_extends_expands(tmp_path):
    """extends: [python-backend, cross-cutting] resolves to both packs."""
    composite = (
        "schema_version: '1'\n"
        "profile: python-react\n"
        "extends: [python-backend, react-frontend, cross-cutting]\n"
    )
    target = _make_consumer(
        tmp_path,
        "schema_version: '1'\nprofile: python-react\nowner: '@x'\n"
        "extends: [python-react]\n",
        profile_dir_files={"python-react.yaml": composite},
    )
    p = resolve_profile(target)
    assert "python-backend" in p.packs_resolved
    assert "react-frontend" in p.packs_resolved
    assert "cross-cutting" in p.packs_resolved


def test_cycle_detected(tmp_path):
    """profile A extends B, B extends A → ProfileError."""
    target = _make_consumer(
        tmp_path,
        "schema_version: '1'\nprofile: A\nowner: '@x'\nextends: [A-composite]\n",
        profile_dir_files={
            "A-composite.yaml": "schema_version: '1'\nprofile: A\nextends: [B-composite]\n",
            "B-composite.yaml": "schema_version: '1'\nprofile: B\nextends: [A-composite]\n",
        },
    )
    with pytest.raises(ProfileError, match="cycle"):
        resolve_profile(target)


def test_disabled_rules_loaded(tmp_path):
    target = _make_consumer(
        tmp_path,
        "schema_version: '1'\nprofile: minimal\nowner: '@x'\n"
        "disabled: [Q15.spine-docstring-required, Q18.python-snake-case]\n"
    )
    p = resolve_profile(target)
    assert is_rule_disabled("Q15.spine-docstring-required", p)
    assert is_rule_disabled("Q18.python-snake-case", p)
    assert not is_rule_disabled("Q13.route-needs-auth", p)


def test_overrides_loaded(tmp_path):
    target = _make_consumer(
        tmp_path,
        """schema_version: '1'
profile: minimal
owner: '@x'
overrides:
  security_policy.yaml:
    rate_limit_exempt:
      - "GET:/healthz"
      - "GET:/internal/x"
"""
    )
    p = resolve_profile(target)
    over = policy_overrides(p, "security_policy.yaml")
    assert over["rate_limit_exempt"] == ["GET:/healthz", "GET:/internal/x"]


def test_active_check_files_no_extends_uses_flat_layout(tmp_path):
    """When extends is empty, every flat check file is active (v1.x compat)."""
    target = _make_consumer(tmp_path,
        "schema_version: '1'\nprofile: minimal\nowner: '@x'\n")
    (target / ".harness" / "checks" / "foo.py").write_text("# stub")
    (target / ".harness" / "checks" / "bar.py").write_text("# stub")
    p = resolve_profile(target)
    files = active_check_files(target, p)
    names = {f.name for f in files}
    assert names == {"foo.py", "bar.py"}


def test_active_check_files_with_pack_subdir(tmp_path):
    """When extends names a pack with a subdir, only those files load."""
    composite = (
        "schema_version: '1'\nprofile: minimal\nextends: [my-pack]\n"
    )
    target = _make_consumer(
        tmp_path,
        "schema_version: '1'\nprofile: minimal\nowner: '@x'\nextends: [minimal-composite]\n",
        profile_dir_files={"minimal-composite.yaml": composite},
    )
    (target / ".harness" / "checks" / "my-pack").mkdir()
    (target / ".harness" / "checks" / "my-pack" / "in_pack.py").write_text("# stub")
    (target / ".harness" / "checks" / "outside_pack.py").write_text("# stub")
    p = resolve_profile(target)
    files = active_check_files(target, p)
    assert {f.name for f in files} == {"in_pack.py"}


def test_missing_profile_yaml_raises(tmp_path):
    target = tmp_path / "consumer"
    (target / ".harness").mkdir(parents=True)
    with pytest.raises(ProfileError, match="not found"):
        resolve_profile(target)


def test_malformed_profile_yaml_raises(tmp_path):
    target = _make_consumer(tmp_path, "this is { not valid yaml")
    with pytest.raises(ProfileError, match="malformed"):
        resolve_profile(target)


def test_locked_rules_loaded(tmp_path):
    target = _make_consumer(
        tmp_path,
        """schema_version: '1'
profile: minimal
owner: '@x'
locked_rules:
  - "Q13.*"
  - "Q10.api-request-needs-forbid"
"""
    )
    p = resolve_profile(target)
    assert "Q13.*" in p.locked_rules
    assert "Q10.api-request-needs-forbid" in p.locked_rules


def test_named_profiles_in_source_repo_load_cleanly():
    """Every shipped .harness/profiles/*.yaml loads + validates."""
    profiles_dir = REPO_ROOT / ".harness" / "profiles"
    for path in profiles_dir.glob("*.yaml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["schema_version"] == "1"
        assert "profile" in data
        assert "extends" in data
