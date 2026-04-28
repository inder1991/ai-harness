"""Sprint 0 / S0.3 — stack detection.

Inspects a target directory's manifest files to recommend a profile for
`harness init`. Returns a `StackProfile` dataclass with:

  - `recommended`: one of the canonical profile names (see below).
  - `signals`: which files signaled this stack (for debugging / display).
  - `warning`: a one-line warning when detection is ambiguous or empty.

Pure function: no I/O outside the target directory; no network; no
subprocess. Decisions are based purely on file presence + content
inspection of small manifest files.

Profile names are stable contracts; consumers reference them in their
`.harness/profile.yaml`. Adding a new profile is a deliberate decision
documented in an ADR.

Detection precedence (when multiple signals present):
  1. polyglot (Python + Go OR Python + Rust)        → `polyglot`
  2. python + react frontend                        → `python-react`
  3. python only (any of: pyproject, requirements,  → `python-only`
       setup.py, Pipfile, poetry, manage.py)
  4. nextjs (full-stack node)                       → `nextjs`
  5. nest (decorated node backend)                  → `node-nest`
  6. node + react frontend (no python backend)      → `node-react`
  7. node-only (express, fastify, koa, ...)         → `node-only`
  8. react-only (CRA, vite, no backend)             → `react-only`
  9. vue                                            → `vue` (warning: best-effort)
 10. svelte                                         → `svelte` (warning: best-effort)
 11. go-only (go.mod, no other manifest)            → `go-only`
 12. rust-only (Cargo.toml, no other manifest)      → `rust-only`
 13. nothing detected                               → `minimal` (warning)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class StackProfile:
    """The output of `detect_stack()`. See module docstring for the
    profile name catalog. Always returns a profile (never None);
    `recommended == "minimal"` is the empty-directory fallback."""

    recommended: str
    signals: list[str] = field(default_factory=list)
    warning: str | None = None


def _has_python_signal(target: Path) -> tuple[bool, list[str]]:
    """Detect any Python-project signal."""
    signals: list[str] = []
    for fname in ("pyproject.toml", "requirements.txt", "setup.py", "Pipfile", "manage.py"):
        if (target / fname).exists():
            signals.append(fname)
    return bool(signals), signals


def _has_react_signal(target: Path) -> tuple[bool, list[str]]:
    """Detect React in any package.json under target (target itself + immediate subdirs)."""
    signals: list[str] = []
    candidates = [target / "package.json"]
    for sub in target.iterdir() if target.is_dir() else []:
        if sub.is_dir():
            p = sub / "package.json"
            if p.exists():
                candidates.append(p)
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # Q17-EXEMPT: malformed package.json is best-effort skipped;
            # the caller's `_has_node_signal` will report it via signals.
            continue
        deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
        if "react" in deps:
            signals.append(str(path.relative_to(target)))
    return bool(signals), signals


def _has_node_signal(target: Path) -> tuple[bool, list[str]]:
    """Detect any Node-project signal."""
    signals: list[str] = []
    if (target / "package.json").exists():
        signals.append("package.json")
    return bool(signals), signals


def _node_framework(target: Path) -> str | None:
    """Detect a specific Node framework signature; returns canonical name or None."""
    pkg = target / "package.json"
    if not pkg.exists():
        return None
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
    if "next" in deps:
        return "nextjs"
    if "@nestjs/core" in deps or (target / "nest-cli.json").exists():
        return "nest"
    if "express" in deps or "fastify" in deps or "koa" in deps:
        return "node-backend"
    if "vue" in deps:
        return "vue"
    if "@sveltejs/kit" in deps or (target / "svelte.config.js").exists():
        return "svelte"
    return None


def _has_go_signal(target: Path) -> bool:
    return (target / "go.mod").exists()


def _has_rust_signal(target: Path) -> bool:
    return (target / "Cargo.toml").exists()


def detect_stack(target: Path) -> StackProfile:
    """Inspect `target` and return a `StackProfile`.

    Pure function: only reads files inside `target` (and its immediate
    subdirectories for nested package.json detection). No subprocesses,
    no network.

    Args:
        target: Directory to inspect. Must exist; a non-existent target
            is treated as `minimal` with a warning.

    Returns:
        A `StackProfile` whose `recommended` is one of the canonical
        names listed in the module docstring.
    """
    if not target.is_dir():
        return StackProfile(
            recommended="minimal",
            warning=f"target is not a directory: {target}",
        )

    py, py_sig = _has_python_signal(target)
    node, node_sig = _has_node_signal(target)
    react, react_sig = _has_react_signal(target)
    framework = _node_framework(target)
    go = _has_go_signal(target)
    rust = _has_rust_signal(target)

    signals: list[str] = []
    signals.extend(py_sig)
    signals.extend(node_sig)
    signals.extend(react_sig)
    if go:
        signals.append("go.mod")
    if rust:
        signals.append("Cargo.toml")

    # 1. Polyglot detection (most specific first)
    if py and (go or rust):
        return StackProfile(recommended="polyglot", signals=signals)

    # 2. Python + React
    if py and react:
        return StackProfile(recommended="python-react", signals=signals)

    # 3. Python only
    if py:
        return StackProfile(recommended="python-only", signals=signals)

    # 4-5-6-7-8-9-10. Node-family
    if node:
        if framework == "nextjs":
            return StackProfile(recommended="nextjs", signals=signals)
        if framework == "nest":
            return StackProfile(recommended="node-nest", signals=signals)
        if framework == "node-backend" and react:
            return StackProfile(recommended="node-react", signals=signals)
        if framework == "node-backend":
            return StackProfile(recommended="node-only", signals=signals)
        if framework == "vue":
            return StackProfile(
                recommended="vue",
                signals=signals,
                warning="Vue stack detected; only the cross-cutting pack ships rules for it today",
            )
        if framework == "svelte":
            return StackProfile(
                recommended="svelte",
                signals=signals,
                warning="Svelte stack detected; only the cross-cutting pack ships rules for it today",
            )
        if react:
            return StackProfile(recommended="react-only", signals=signals)
        # Generic node: package.json with no specific framework signal.
        return StackProfile(recommended="node-only", signals=signals)

    # 11. Go only
    if go:
        return StackProfile(
            recommended="go-only",
            signals=signals,
            warning="Go-only consumer; only starter-pack rules ship today",
        )

    # 12. Rust only
    if rust:
        return StackProfile(
            recommended="rust-only",
            signals=signals,
            warning="Rust-only consumer; only starter-pack rules ship today",
        )

    # 13. Empty fallback
    return StackProfile(
        recommended="minimal",
        signals=signals,
        warning="no stack signals detected; using minimal profile (cross-cutting + self-tests only)",
    )
