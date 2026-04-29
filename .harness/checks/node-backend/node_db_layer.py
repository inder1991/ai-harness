#!/usr/bin/env python3
"""NQ8 — Node DB layer boundary check.

One rule enforced on the Node spine:
  NQ8.queryraw-outside-analytics — `prisma.$queryRaw(...)` /
        `prisma.$queryRawUnsafe(...)` calls are restricted to the
        analytics adapter (default `db/analytics.ts`). Raw SQL elsewhere
        is the most common SQL-injection vector.

Wrapper paths are configurable via --analytics-path (repeatable).

H-25 contract: same as node_logging.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from _node_common import (  # noqa: E402
    emit, iter_node_files, node_spine_paths, parse_or_warn,
)

DEFAULT_ROOTS = node_spine_paths("node_spine", ("backend",))
DEFAULT_ANALYTICS_PATHS = ("db/analytics.ts", "src/db/analytics.ts", "backend/src/db/analytics.ts")
RAW_METHODS = {"$queryRaw", "$queryRawUnsafe", "$executeRaw", "$executeRawUnsafe"}


def _is_analytics(virtual: str, allowed: tuple[str, ...]) -> bool:
    return any(virtual.endswith(p) for p in allowed)


def _is_raw_call(call_node, ast) -> str | None:
    func = call_node.child_by_field_name("function")
    if func is None or func.type != "member_expression":
        return None
    prop = func.child_by_field_name("property")
    if prop is None:
        return None
    method = ast.text(prop)
    return method if method in RAW_METHODS else None


def scan_file(path: Path, virtual: str, analytics_paths: tuple[str, ...]) -> int:
    if _is_analytics(virtual, analytics_paths):
        return 0
    ast = parse_or_warn(path)
    if ast is None:
        return 0
    errors = 0
    for call in ast.find(("call_expression",)):
        method = _is_raw_call(call, ast)
        if method is not None:
            emit(
                "ERROR", virtual, "NQ8.queryraw-outside-analytics",
                f"{method} outside the analytics adapter is a SQL-injection risk",
                f"move the query into {analytics_paths[0]} or use the typed prisma client API",
                line=ast.line(call),
            )
            errors += 1
    return errors


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", type=Path, default=None)
    p.add_argument("--pretend-path", default=None)
    p.add_argument("--analytics-path", action="append", default=None,
                   help="Allowed analytics-adapter path (repeatable)")
    args = p.parse_args(argv)
    analytics_paths = tuple(args.analytics_path) if args.analytics_path else DEFAULT_ANALYTICS_PATHS
    if args.target is not None:
        if not args.target.exists():
            emit("ERROR", str(args.target), "harness.target-missing",
                 "target path does not exist", "pass an existing file or directory")
            return 2
        targets = [args.target] if args.target.is_file() else list(iter_node_files([args.target]))
    else:
        targets = list(iter_node_files(DEFAULT_ROOTS))
    errors = 0
    for path in targets:
        virtual = args.pretend_path or str(path)
        errors += scan_file(path, virtual, analytics_paths)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
