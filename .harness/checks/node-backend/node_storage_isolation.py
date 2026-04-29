#!/usr/bin/env python3
"""NQ8 — Node storage-isolation check.

One rule enforced on the Node spine:
  NQ8.fs-outside-storage-boundary — `fs.readFileSync(...)`,
        `fs.writeFileSync(...)`, `fs.appendFileSync(...)` and their async
        twins are restricted to the storage adapter (default
        `storage/`, override with --storage-path).

Direct fs use elsewhere couples business logic to disk layout and skips
the project's path-validation / quota / atomic-write substrate.
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
DEFAULT_STORAGE_PREFIXES = ("storage/", "src/storage/", "backend/src/storage/")
FS_METHODS = {
    "readFile", "readFileSync", "writeFile", "writeFileSync",
    "appendFile", "appendFileSync", "unlink", "unlinkSync",
    "mkdir", "mkdirSync", "rmdir", "rmdirSync", "rm", "rmSync",
}


def _is_in_storage(virtual: str, prefixes: tuple[str, ...]) -> bool:
    return any(seg in virtual for seg in prefixes)


def _fs_method(call_node, ast) -> str | None:
    func = call_node.child_by_field_name("function")
    if func is None or func.type != "member_expression":
        return None
    obj = func.child_by_field_name("object")
    prop = func.child_by_field_name("property")
    if obj is None or prop is None:
        return None
    obj_text = ast.text(obj)
    if obj_text not in {"fs", "fsp", "fs.promises"}:
        return None
    method = ast.text(prop)
    return method if method in FS_METHODS else None


def scan_file(path: Path, virtual: str, storage_prefixes: tuple[str, ...]) -> int:
    if _is_in_storage(virtual, storage_prefixes):
        return 0
    ast = parse_or_warn(path)
    if ast is None:
        return 0
    errors = 0
    for call in ast.find(("call_expression",)):
        method = _fs_method(call, ast)
        if method is not None:
            emit(
                "ERROR", virtual, "NQ8.fs-outside-storage-boundary",
                f"fs.{method}(...) outside the storage adapter bypasses path/quota validation",
                f"call into the storage adapter (under {storage_prefixes[0]}) instead",
                line=ast.line(call),
            )
            errors += 1
    return errors


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", type=Path, default=None)
    p.add_argument("--pretend-path", default=None)
    p.add_argument("--storage-path", action="append", default=None,
                   help="Allowed storage-adapter path prefix (repeatable)")
    args = p.parse_args(argv)
    storage = tuple(args.storage_path) if args.storage_path else DEFAULT_STORAGE_PREFIXES
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
        errors += scan_file(path, virtual, storage)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
