"""Sprint 4 / S4.4 — shared helpers for rust-backend starter pack.

Like go-backend, this pack is regex-based to keep the install footprint
zero. Future expansion can swap to syn (via PyO3) or tree-sitter-rust.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

_HERE = Path(__file__).resolve().parent
_CHECKS_ROOT = _HERE.parent
sys.path.insert(0, str(_CHECKS_ROOT))

from _common import emit, normalize_path, spine_paths, walk_files  # noqa: E402


def iter_rust_files(roots: Iterable[Path]) -> Iterable[Path]:
    """Yield every .rs file under `roots`. Skips target/ + vendor."""
    return walk_files(
        roots,
        suffixes=(".rs",),
        skip_dirs=(
            "target", "vendor", ".git", "__pycache__", ".venv",
            "node_modules", "dist", "build",
        ),
    )


def rust_spine_paths(role: str, fallback: tuple[str, ...]) -> tuple[Path, ...]:
    return spine_paths(role, fallback)


__all__ = ["emit", "iter_rust_files", "rust_spine_paths", "normalize_path"]
