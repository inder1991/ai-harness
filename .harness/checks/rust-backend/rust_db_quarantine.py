#!/usr/bin/env python3
"""RQ8 — Rust DB-quarantine check.

One rule enforced on the Rust spine:
  RQ8.raw-sql-outside-adapter — `sqlx::query!` macro invocations,
        `sqlx::query_as!`, and `diesel::sql_query` outside the canonical
        DB adapter directory (default `src/db/`) are SQL-injection vectors.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from _rust_common import emit, iter_rust_files, rust_spine_paths  # noqa: E402

DEFAULT_ROOTS = rust_spine_paths("rust_spine", ("src",))
DEFAULT_ADAPTER_PREFIXES = ("src/db/", "src/dbadapter/", "crates/db/")
RAW_SQL = re.compile(
    r'\b(?:sqlx::query(?:_as)?!|sqlx::query_unchecked!|'
    r'sqlx::query_scalar!|diesel::sql_query)\s*\('
)


def _is_adapter(virtual: str, prefixes: tuple[str, ...]) -> bool:
    return any(seg in virtual for seg in prefixes)


def scan_file(path: Path, virtual: str, adapter_prefixes: tuple[str, ...]) -> int:
    if _is_adapter(virtual, adapter_prefixes):
        return 0
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    errors = 0
    for m in RAW_SQL.finditer(text):
        line = text[:m.start()].count("\n") + 1
        macro = m.group(0).rstrip("(").rstrip()
        emit(
            "ERROR", virtual, "RQ8.raw-sql-outside-adapter",
            f"`{macro}(` outside the DB adapter is a SQL-injection risk",
            f"move the query into a typed function under {adapter_prefixes[0]}",
            line=line,
        )
        errors += 1
    return errors


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", type=Path, default=None)
    p.add_argument("--pretend-path", default=None)
    p.add_argument("--adapter-prefix", action="append", default=None)
    args = p.parse_args(argv)
    adapter = tuple(args.adapter_prefix) if args.adapter_prefix else DEFAULT_ADAPTER_PREFIXES
    if args.target is not None:
        if not args.target.exists():
            emit("ERROR", str(args.target), "harness.target-missing",
                 "target path does not exist", "pass an existing file or directory")
            return 2
        targets = [args.target] if args.target.is_file() else list(iter_rust_files([args.target]))
    else:
        targets = list(iter_rust_files(DEFAULT_ROOTS))
    errors = 0
    for path in targets:
        virtual = args.pretend_path or str(path)
        errors += scan_file(path, virtual, adapter)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
