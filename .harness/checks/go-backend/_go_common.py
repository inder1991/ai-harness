"""Sprint 4 / S4.4 — shared helpers for go-backend starter pack.

Starter pack: regex-based checks rather than full AST parsing. Go's
standard library doesn't ship a Python parser; adding tree-sitter-go
would add another ~30 MB to the install footprint with diminishing
returns for 3 starter checks. If a future sprint expands to a full Go
pack like the Node pack, the parser swap happens in this module only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

_HERE = Path(__file__).resolve().parent
_CHECKS_ROOT = _HERE.parent
sys.path.insert(0, str(_CHECKS_ROOT))

from _common import emit, normalize_path, spine_paths, walk_files  # noqa: E402


def iter_go_files(roots: Iterable[Path]) -> Iterable[Path]:
    """Yield every .go file under `roots`. Skips vendor + generated dirs."""
    return walk_files(
        roots,
        suffixes=(".go",),
        skip_dirs=(
            "vendor", ".git", "__pycache__", ".venv", "node_modules",
            "dist", "build", "tmp", ".cache",
        ),
    )


def go_spine_paths(role: str, fallback: tuple[str, ...]) -> tuple[Path, ...]:
    return spine_paths(role, fallback)


__all__ = ["emit", "iter_go_files", "go_spine_paths", "normalize_path"]
