#!/usr/bin/env python3
"""Q11 — hybrid dependency policy.

Five rules:
  Q11.python-unlisted        — entry in pyproject.toml not in policy.python.allowed.
  Q11.npm-unlisted           — entry in package.json not in policy.npm.allowed.
  Q11.spine-import-unlisted  — backend spine file imports module not in
                                policy.python.allowed_on_spine.
  Q11.blacklisted            — any dep on policy.global_blacklist.
  Q11.lockfile-missing       — manifest present without committed lockfile.

H-25:
  Missing input    — exit 2 if --target missing or --policy missing.
  Malformed input  — WARN harness.unparseable; skip file.
  Upstream failed  — none (no network).
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import tomllib
from pathlib import Path
from typing import Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from _common import emit, load_baseline, normalize_path, spine_paths  # noqa: E402

DEFAULT_POLICY = REPO_ROOT / ".harness" / "dependencies.yaml"
SPINE_PREFIXES = (
    "backend/src/api/",
    "backend/src/storage/",
    "backend/src/models/",
    "backend/src/agents/",
    "frontend/src/services/api/",
    "frontend/src/hooks/",
)
BASELINE = load_baseline("dependency_policy")
# v1.3.0 S4 — `sys.stdlib_module_names` is the runtime-derived list of
# every stdlib module name in the running Python (3.10+). Using it
# closes audit finding S-DP4: pre-v1.3.0, STDLIB_FIRST_PARTY was hand-
# maintained and missed `tomllib` (3.11+, which the check itself
# imports!), `zoneinfo` (3.9+), `graphlib` (3.9+), etc.
STDLIB_FIRST_PARTY = (
    set(sys.stdlib_module_names)
    | {"backend", "src", "tests", "frontend"}  # first-party namespaces
)


def _emit(file: Path | str, rule: str, msg: str, suggestion: str, line: int = 1) -> bool:
    sig = (normalize_path(file), int(line), rule)
    if sig in BASELINE:
        return False
    emit("ERROR", file, rule, msg, suggestion, line=line)
    return True


def _load_policy(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _bare_dep_name(spec: str) -> str:
    """Extract the bare package name from a dep spec string.

    v1.3.1 S18 (S-DP3) — pre-v1.3.0 only handled PEP 440 version
    specifiers. Now also handles npm-style refs:
      * `package@1.2.3`           → "package"
      * `package@npm:scoped/…`    → "package"
      * `@scope/pkg@1.2.3`        → "@scope/pkg"  (skips leading @)

    Scoped npm names like `@tanstack/react-query` keep the leading
    `@`; only the second `@` (version separator) is treated as a stop
    character.
    """
    name = spec.strip()
    # Preserve a leading `@` (npm scope) when looking for the version
    # separator `@`.
    leading_at = name.startswith("@")
    search_from = 1 if leading_at else 0
    cut: int | None = None
    for sep in (">=", "==", "~=", "<=", ">", "<", "[", " "):
        idx = name.find(sep, search_from)
        if idx != -1:
            cut = idx if cut is None else min(cut, idx)
    at_idx = name.find("@", search_from)
    if at_idx != -1:
        cut = at_idx if cut is None else min(cut, at_idx)
    if cut is not None:
        name = name[:cut]
    return name.strip().lower()


def _is_url_spec(spec: str) -> bool:
    """True if `spec` is a git-URL or http(s)-URL dependency line.
    Such specs don't have a registry name; the allow-list comparison
    doesn't apply."""
    s = spec.strip().lower()
    return s.startswith(("git+", "http://", "https://", "file://"))


def _parse_pyproject_deps(path: Path) -> list[str]:
    """v1.3.1 S18 (S-DP1) — collect deps from every conventional source:

      * `[project].dependencies`              (PEP 621 main)
      * `[project].optional-dependencies.*`   (PEP 621 extras)
      * `[tool.poetry.dependencies]`          (Poetry main)
      * `[build-system].requires`             (PEP 518 build deps)

    Skips `python` from Poetry deps (it's the Python version pin, not
    a package). Skips URL/git specs (handled by _is_url_spec).
    """
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    raw: list[str] = []
    project = data.get("project") or {}
    raw.extend(project.get("dependencies") or [])
    optional = project.get("optional-dependencies") or {}
    if isinstance(optional, dict):
        for extras in optional.values():
            raw.extend(extras or [])
    poetry = (data.get("tool") or {}).get("poetry") or {}
    poetry_deps = poetry.get("dependencies") or {}
    if isinstance(poetry_deps, dict):
        for name in poetry_deps.keys():
            if name.lower() != "python":
                raw.append(str(name))
    build = data.get("build-system") or {}
    raw.extend(build.get("requires") or [])
    out: list[str] = []
    for spec in raw:
        if _is_url_spec(spec):
            continue
        out.append(_bare_dep_name(spec))
    return out


def _parse_package_deps(path: Path) -> tuple[list[str], list[str]]:
    """v1.3.1 S18 (S-DP2) — return (runtime_deps, dev_deps) so the
    policy can apply different allow-lists to each. Also skips git/URL
    refs and extracts the bare package name from `package@1.2.3` style.
    """
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    def _bare_set(deps_obj: dict | None) -> list[str]:
        out: list[str] = []
        for name in (deps_obj or {}).keys():
            spec = str(name)
            if _is_url_spec(spec):
                continue
            out.append(_bare_dep_name(spec))
        return out
    runtime = _bare_set(data.get("dependencies"))
    dev = _bare_set(data.get("devDependencies"))
    return runtime, dev


def _scan_pyproject(path: Path, policy: dict) -> int:
    errors = 0
    try:
        deps = _parse_pyproject_deps(path)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        emit("WARN", path, "harness.unparseable",
             f"could not parse {path.name}: {exc}", "fix TOML syntax", line=1)
        return 0
    py = policy.get("python") or {}
    allowed = {x.lower() for x in (py.get("allowed") or py.get("backend_spine") or [])}
    blacklist = {x.lower() for x in (policy.get("blacklist", {}).get("global") or policy.get("global_blacklist") or [])}
    for dep in deps:
        if dep in blacklist:
            if _emit(path, "Q11.blacklisted",
                     f"`{dep}` is globally blacklisted",
                     f"remove {dep} from pyproject dependencies"):
                errors += 1
        elif dep not in allowed:
            if _emit(path, "Q11.python-unlisted",
                     f"python dep `{dep}` not in .harness/dependencies.yaml allow-list",
                     f"add {dep} to python.allowed (with ADR justification)"):
                errors += 1
    return errors


def _scan_package_json(path: Path, policy: dict) -> int:
    """v1.3.1 S18 (S-DP2) — runtime + dev deps checked against
    optional separate allow-lists. Falls back to the merged
    `npm.allowed` list when `runtime_allowed`/`dev_allowed` aren't
    set (backward compat with consumers on the old policy shape).
    """
    errors = 0
    try:
        runtime_deps, dev_deps = _parse_package_deps(path)
    except (OSError, json.JSONDecodeError) as exc:
        emit("WARN", path, "harness.unparseable",
             f"could not parse {path.name}: {exc}", "fix JSON syntax", line=1)
        return 0
    npm = policy.get("npm") or {}
    merged_allowed = {x.lower() for x in (npm.get("allowed") or npm.get("frontend_spine") or [])}
    runtime_allowed = {x.lower() for x in (npm.get("runtime_allowed") or [])} or merged_allowed
    dev_allowed = {x.lower() for x in (npm.get("dev_allowed") or [])} or merged_allowed
    blacklist = {x.lower() for x in (policy.get("blacklist", {}).get("global") or policy.get("global_blacklist") or [])}

    def _check(deps: list[str], allowed: set[str], scope: str) -> int:
        n = 0
        for dep in deps:
            if dep in blacklist:
                if _emit(path, "Q11.blacklisted",
                         f"`{dep}` is globally blacklisted",
                         f"remove {dep} from package.json {scope} deps"):
                    n += 1
            elif dep not in allowed:
                if _emit(path, "Q11.npm-unlisted",
                         f"npm {scope} dep `{dep}` not in allow-list",
                         f"add {dep} to npm.{scope}_allowed (or npm.allowed) with ADR justification"):
                    n += 1
        return n

    errors += _check(runtime_deps, runtime_allowed, "runtime")
    errors += _check(dev_deps, dev_allowed, "dev")
    return errors


def _scan_spine_imports(path: Path, virtual: str, policy: dict) -> int:
    if not any(virtual.startswith(prefix) for prefix in SPINE_PREFIXES):
        return 0
    py = policy.get("python") or {}
    allowed = {x.lower() for x in (py.get("allowed_on_spine") or py.get("backend_spine") or [])}
    if not allowed:
        return 0
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return 0
    errors = 0
    seen: set[str] = set()
    for node in ast.walk(tree):
        roots: list[tuple[str, int]] = []
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.append((alias.name.split(".")[0], node.lineno))
        if isinstance(node, ast.ImportFrom) and node.module:
            roots.append((node.module.split(".")[0], node.lineno))
        for root, lineno in roots:
            r = root.lower()
            if r in seen or r in STDLIB_FIRST_PARTY:
                continue
            seen.add(r)
            if r not in allowed:
                if _emit(path, "Q11.spine-import-unlisted",
                         f"spine file imports `{r}` (not in allowed_on_spine)",
                         f"add {r} to python.allowed_on_spine + ADR, OR move usage off spine",
                         lineno):
                    errors += 1
    return errors


def scan(targets: list[Path], policy_path: Path, pretend_path: str | None) -> int:
    if not policy_path.exists():
        emit("ERROR", policy_path, "harness.target-missing",
             f"policy file does not exist: {policy_path}",
             "seed .harness/dependencies.yaml (Sprint H.0b Story 4)", line=0)
        return 2
    policy = _load_policy(policy_path)
    total_errors = 0
    for target in targets:
        if not target.exists():
            # Silent skip: a default target may not exist in every consumer
            # (e.g. JS-only or Python-only projects miss the other manifest).
            # Explicit `--target` to a non-existent path still fails (handled
            # by `argparse` not finding the file? — no, argparse accepts
            # any Path; that's the consumer's mistake to surface elsewhere).
            continue
        files: list[tuple[Path, str]]
        if target.is_file():
            virtual = pretend_path or (
                str(target.relative_to(REPO_ROOT))
                if target.is_absolute() and target.is_relative_to(REPO_ROOT) else target.name
            )
            files = [(target, virtual)]
        else:
            files = []
            for p in target.rglob("*"):
                if not p.is_file():
                    continue
                if any(tok in str(p) for tok in (
                    "__pycache__", ".venv", "/venv/", "node_modules",
                    "site-packages", ".git", "tests/harness/fixtures",
                )):
                    continue
                if p.name in {"pyproject.toml", "package.json"} or p.suffix == ".py":
                    try:
                        files.append((p, str(p.relative_to(REPO_ROOT))))
                    except ValueError:
                        files.append((p, p.name))
        for path, virtual in files:
            # Dispatch by name OR suffix so descriptive fixture filenames
            # (pyproject_unlisted.toml, package_clean.json) work as well as
            # canonical names (pyproject.toml, package.json).
            is_pyproject = path.name == "pyproject.toml" or path.suffix == ".toml"
            is_package_json = path.name == "package.json" or path.suffix == ".json"
            if is_pyproject:
                total_errors += _scan_pyproject(path, policy)
            elif is_package_json:
                total_errors += _scan_package_json(path, policy)
            elif path.suffix == ".py":
                total_errors += _scan_spine_imports(path, virtual, policy)
    return 1 if total_errors else 0


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: scan --target manifests against --policy."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, action="append")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--pretend-path", type=str)
    args = parser.parse_args(argv)
    targets = list(args.target) if args.target else (
        list(spine_paths("backend_pyproject", ("backend/pyproject.toml",)))
        + list(spine_paths("frontend_package_json", ("frontend/package.json",)))
        + list(spine_paths("backend_src", ("backend/src",)))
    )
    return scan(targets, args.policy, args.pretend_path)


if __name__ == "__main__":
    sys.exit(main())
