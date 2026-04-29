#!/usr/bin/env python3
"""NQ7 — Node async-strict correctness check.

Two rules enforced on the Node spine:
  NQ7.no-axios-outside-wrapper — `axios` import is banned everywhere
                                 except the canonical HTTP wrapper file
                                 (default `src/lib/http.ts`). Direct
                                 imports skip retry/timeout/correlation-id
                                 enforcement.
  NQ7.no-execsync-in-async    — `child_process.execSync(...)` inside an
                                 `async function` body blocks the event
                                 loop. Use `execFile` from `node:child_process/promises`.

Wrapper path can be overridden by `node_policy.yaml`:
    http_wrapper_paths:
      - src/lib/http.ts
      - src/server/http.ts

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
DEFAULT_WRAPPER_PATHS = ("src/lib/http.ts", "src/server/http.ts", "backend/src/lib/http.ts")


def _is_wrapper(virtual: str, allowed: tuple[str, ...]) -> bool:
    return any(virtual.endswith(allowed_p) for allowed_p in allowed)


def _import_source(import_node, ast) -> str:
    """Extract the string literal source from an `import` statement.

    Returns "" if the node isn't a recognizable import-from form.
    """
    src = import_node.child_by_field_name("source")
    if src is None:
        return ""
    text = ast.text(src)
    if len(text) >= 2 and text[0] in {'"', "'"} and text[-1] == text[0]:
        return text[1:-1]
    return text


def _node_within_async_function(node) -> bool:
    """Walk parents until we hit a function; return True iff that function
    is async."""
    cur = node.parent
    while cur is not None:
        if cur.type in ("function_declaration", "function_expression",
                        "arrow_function", "method_definition"):
            for child in cur.children:
                if child.type == "async":
                    return True
                if child.is_named:
                    break
            return False
        cur = cur.parent
    return False


def _is_execsync_call(call_node, ast) -> bool:
    func = call_node.child_by_field_name("function")
    if func is None:
        return False
    text = ast.text(func)
    return text.endswith("execSync")


def scan_file(path: Path, virtual: str, wrapper_paths: tuple[str, ...]) -> int:
    ast = parse_or_warn(path)
    if ast is None:
        return 0
    errors = 0
    is_wrapper = _is_wrapper(virtual, wrapper_paths)
    if not is_wrapper:
        for imp in ast.find(("import_statement",)):
            if _import_source(imp, ast) == "axios":
                emit(
                    "ERROR", virtual, "NQ7.no-axios-outside-wrapper",
                    "direct `axios` import bypasses the retry/timeout wrapper",
                    f"import the http client from {wrapper_paths[0]} instead",
                    line=ast.line(imp),
                )
                errors += 1
    for call in ast.find(("call_expression",)):
        if _is_execsync_call(call, ast) and _node_within_async_function(call):
            emit(
                "ERROR", virtual, "NQ7.no-execsync-in-async",
                "execSync(...) inside an async function blocks the event loop",
                "use `execFile` from `node:child_process/promises` and await it",
                line=ast.line(call),
            )
            errors += 1
    return errors


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", type=Path, default=None)
    p.add_argument("--pretend-path", default=None)
    p.add_argument("--wrapper", action="append", default=None,
                   help="Allowed http-wrapper path (repeatable)")
    args = p.parse_args(argv)
    wrapper_paths = tuple(args.wrapper) if args.wrapper else DEFAULT_WRAPPER_PATHS
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
        errors += scan_file(path, virtual, wrapper_paths)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
