"""Sprint 4 / S4.2 — shared helpers for node-backend checks.

Mirrors `.harness/checks/_common.py` but specialised for JS/TS:
  * `iter_node_files(roots)` — yield every .js/.jsx/.mjs/.cjs/.ts/.tsx file.
  * `parse_or_warn(path)` — parse and emit a [WARN] on tree-sitter error.
  * `node_spine_paths(role, fallback)` — alias to `_common.spine_paths`,
    so consumers can override via `.harness/spine_paths.yaml`.

Each check imports the parent `_common` for `emit/load_baseline/...`,
then this module for JS/TS-specific extras.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

# Allow the parent `_common` to import: every check is invoked with the
# repo root as cwd, but as a script we need to find sibling modules.
_HERE = Path(__file__).resolve().parent
_CHECKS_ROOT = _HERE.parent
sys.path.insert(0, str(_CHECKS_ROOT))

from _common import emit, normalize_path, spine_paths, walk_files  # noqa: E402

from _ts_parser import NodeAST, parse, supported_suffixes  # noqa: E402


def iter_node_files(roots: Iterable[Path]) -> Iterable[Path]:
    """Yield every JS/TS file under `roots`. Skips node_modules + dist-style dirs."""
    return walk_files(
        roots,
        suffixes=supported_suffixes(),
        skip_dirs=(
            "node_modules", ".git", "__pycache__", ".venv",
            "dist", "build", ".next", "coverage", ".turbo",
        ),
    )


def parse_or_warn(path: Path) -> NodeAST | None:
    """Parse `path`; on tree-sitter ERROR nodes emit a [WARN] and return None.

    Permissive parse (no-error) returns the NodeAST. Caller can then walk
    the tree without re-checking has_errors() unless it wants strict mode.
    """
    try:
        ast = parse(path)
    except FileNotFoundError:
        emit("WARN", path, "harness.target-missing",
             f"file not found: {path}",
             "ensure --target points at an existing path", line=None)
        return None
    if ast.has_errors():
        emit("WARN", path, "harness.unparseable",
             "tree-sitter found syntax errors; check is best-effort",
             "fix the syntax error and re-run", line=1)
    return ast


def node_spine_paths(role: str, fallback: tuple[str, ...]) -> tuple[Path, ...]:
    """Resolve the consumer's Node spine paths for `role`.

    Same contract as `_common.spine_paths` but namespaced so a consumer
    can keep `backend_src` (Python) and `node_spine` (Node) distinct.
    """
    return spine_paths(role, fallback)


__all__ = [
    "emit",
    "iter_node_files",
    "node_spine_paths",
    "normalize_path",
    "parse_or_warn",
    "NodeAST",
]
