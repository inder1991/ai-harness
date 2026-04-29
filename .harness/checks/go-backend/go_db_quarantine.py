#!/usr/bin/env python3
"""GQ8 — Go DB-quarantine check.

One rule enforced on the Go spine:
  GQ8.raw-sql-outside-adapter — `db.Exec(...)`, `db.Query(...)`,
        `db.QueryRow(...)`, and the `Context` variants outside the
        canonical DB adapter directory (default `pkg/dbadapter/`)
        are SQL-injection vectors. Wrap them in typed adapter
        functions instead.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from _go_common import emit, go_spine_paths, iter_go_files  # noqa: E402

DEFAULT_ROOTS = go_spine_paths("go_spine", (".",))
DEFAULT_ADAPTER_PREFIXES = ("pkg/dbadapter/", "internal/dbadapter/", "pkg/db/")
RAW_DB_CALL = re.compile(
    r'\b(?:db|tx|conn)\.(?:Exec|Query|QueryRow)(?:Context)?\s*\('
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
    for m in RAW_DB_CALL.finditer(text):
        line = text[:m.start()].count("\n") + 1
        emit(
            "ERROR", virtual, "GQ8.raw-sql-outside-adapter",
            f"raw `{m.group(0).rstrip('(').rstrip()}(` call outside the DB adapter is a SQL-injection risk",
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
        targets = [args.target] if args.target.is_file() else list(iter_go_files([args.target]))
    else:
        targets = list(iter_go_files(DEFAULT_ROOTS))
    errors = 0
    for path in targets:
        virtual = args.pretend_path or str(path)
        errors += scan_file(path, virtual, adapter)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
