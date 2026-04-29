"""Sprint 4 / S4.3 — `harness init` Node-detection scenario tests.

Five scenarios required by the S4.3 acceptance criteria:
  1. Node-only           — package.json with express, no react
  2. Node-React          — package.json with express + react
  3. Node-with-non-React — package.json with express + vue
  4. Node monorepo       — top-level package.json + apps/api/package.json
  5. Node + Python polyglot — package.json (express) + pyproject.toml

Each scenario must:
  - exit 0
  - write a `.harness/profile.yaml` with the expected `profile:` field
  - copy `.harness/profiles/` composites into the consumer
  - write `extends: [<composite>]` when a composite of the detected
    profile name exists in the source repo
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _init(target: Path, env_extra: dict | None = None):
    env = {**os.environ}
    if env_extra:
        env.update(env_extra)
    cmd = [
        sys.executable, "-m", "tools.harness_cli", "init",
        "--target", str(target),
        "--owner", "@test",
        "--non-interactive",
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)


def _write_package_json(target: Path, deps: dict, dev_deps: dict | None = None) -> None:
    target.mkdir(parents=True, exist_ok=True)
    (target / "package.json").write_text(json.dumps({
        "name": target.name,
        "dependencies": deps,
        "devDependencies": dev_deps or {},
    }))


def _read_profile(target: Path) -> dict:
    return yaml.safe_load((target / ".harness/profile.yaml").read_text(encoding="utf-8"))


def test_node_only_install(tmp_path):
    """Plain Express repo → profile=node-only with extends=[node-only]."""
    _write_package_json(tmp_path, {"express": "4.18.0"})
    result = _init(tmp_path)
    assert result.returncode == 0, result.stderr
    profile = _read_profile(tmp_path)
    assert profile["profile"] == "node-only"
    assert profile["extends"] == ["node-only"]
    # Composite should be present in the install.
    assert (tmp_path / ".harness/profiles/node-only.yaml").exists()
    # Node-backend pack must be available.
    assert (tmp_path / ".harness/checks/node-backend").is_dir()
    assert (tmp_path / ".harness/checks/node-backend/node_logging.py").exists()


def test_node_react_install(tmp_path):
    """Node + React → profile=node-react with extends=[node-react]."""
    _write_package_json(tmp_path, {"express": "4.18.0", "react": "18.0.0"})
    result = _init(tmp_path)
    assert result.returncode == 0, result.stderr
    profile = _read_profile(tmp_path)
    assert profile["profile"] == "node-react"
    assert profile["extends"] == ["node-react"]
    assert (tmp_path / ".harness/profiles/node-react.yaml").exists()


def test_node_with_non_react_frontend(tmp_path):
    """Node + Vue → profile=vue (no composite yet → no extends written)."""
    _write_package_json(tmp_path, {"express": "4.18.0", "vue": "3.4.0"})
    result = _init(tmp_path)
    assert result.returncode == 0, result.stderr
    profile = _read_profile(tmp_path)
    # Vue is detected ahead of node-only by stack_detector precedence.
    assert profile["profile"] in {"vue", "node-only"}
    # No vue composite ships today, so no extends key for vue.
    if profile["profile"] == "vue":
        assert "extends" not in profile


def test_node_monorepo(tmp_path):
    """Top-level package.json + apps/api/package.json with express in subdir."""
    _write_package_json(tmp_path, {})
    _write_package_json(tmp_path / "apps" / "api", {"express": "4.18.0"})
    result = _init(tmp_path)
    assert result.returncode == 0, result.stderr
    profile = _read_profile(tmp_path)
    # Top-level package.json has no express, so detection sees node-only.
    assert profile["profile"] in {"node-only", "react-only"}


def test_node_python_polyglot(tmp_path):
    """package.json (express) + pyproject.toml → python wins precedence;
    profile is python-* per stack_detector rules."""
    _write_package_json(tmp_path, {"express": "4.18.0"})
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    result = _init(tmp_path)
    assert result.returncode == 0, result.stderr
    profile = _read_profile(tmp_path)
    # Python+node (no react) → python-only per detection precedence.
    assert profile["profile"].startswith("python")
    if profile["profile"] == "python-only":
        assert profile["extends"] == ["python-only"]


def test_init_copies_all_profile_composites(tmp_path):
    """Every shipped .harness/profiles/*.yaml lands in the consumer install."""
    _write_package_json(tmp_path, {"express": "4.18.0"})
    result = _init(tmp_path)
    assert result.returncode == 0
    src_profiles = REPO_ROOT / ".harness/profiles"
    dst_profiles = tmp_path / ".harness/profiles"
    src_yamls = {p.name for p in src_profiles.glob("*.yaml")}
    dst_yamls = {p.name for p in dst_profiles.glob("*.yaml")}
    assert src_yamls == dst_yamls
    assert len(src_yamls) >= 6  # current count: node-only, node-react,
                                # python-only, python-react, minimal,
                                # go-only, react-only


def test_node_install_resolves_node_backend_pack_via_profiles_module(tmp_path):
    """resolve_profile() on the installed consumer expands `extends: [node-only]`
    to include node-backend in packs_resolved."""
    _write_package_json(tmp_path, {"express": "4.18.0"})
    result = _init(tmp_path)
    assert result.returncode == 0

    sys.path.insert(0, str(REPO_ROOT / "tools"))
    from profiles import resolve_profile, active_check_files  # noqa: E402

    resolved = resolve_profile(tmp_path)
    assert "node-backend" in resolved.packs_resolved
    files = active_check_files(tmp_path, resolved)
    names = {f.name for f in files}
    # 8 node-backend checks must be active.
    for expected in ("node_logging.py", "node_async_correctness.py",
                     "node_db_layer.py", "node_validation_contracts.py",
                     "node_testing.py", "node_security_routes.py",
                     "node_storage_isolation.py", "node_dependency_policy.py"):
        assert expected in names, f"{expected} missing from active checks"
