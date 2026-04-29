#!/usr/bin/env python3
"""NQ16 — Node logging policy.

Two rules enforced on the Node spine:
  NQ16.no-template-in-logger   — template literals inside `logger.<level>(...)`
                                 lose structured fields. Use logger.info({...}, "msg").
  NQ16.no-console-log-in-spine — `console.log` is unstructured noise. Spine
                                 services must use the project logger.

H-25 contract:
  Missing input    : exit 2, emit ERROR rule=harness.target-missing.
  Malformed input  : tree-sitter is permissive; broken files emit one
                     WARN rule=harness.unparseable and are still scanned.
  Upstream failed  : no upstream; reads only filesystem.
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
LOGGER_NAMES = {"logger", "log", "audit", "metrics"}
LOGGER_METHODS = {"trace", "debug", "info", "warn", "warning", "error", "fatal"}


def _is_logger_call(call_node, ast) -> tuple[str, str] | None:
    """If `call_node` is `<name>.<method>(...)` with name ∈ LOGGER_NAMES and
    method ∈ LOGGER_METHODS, return (name, method); else None."""
    func = call_node.child_by_field_name("function")
    if func is None or func.type != "member_expression":
        return None
    obj = func.child_by_field_name("object")
    prop = func.child_by_field_name("property")
    if obj is None or prop is None:
        return None
    obj_text = ast.text(obj)
    prop_text = ast.text(prop)
    if obj_text in LOGGER_NAMES and prop_text in LOGGER_METHODS:
        return (obj_text, prop_text)
    return None


def _first_arg_is_template(call_node) -> bool:
    args = call_node.child_by_field_name("arguments")
    if args is None or args.named_child_count == 0:
        return False
    first = args.named_child(0)
    return first.type == "template_string"


def _has_console_log(ast) -> list[int]:
    """Return 1-based line numbers where `console.<method>(...)` appears."""
    out: list[int] = []
    for call in ast.find(("call_expression",)):
        func = call.child_by_field_name("function")
        if func is None or func.type != "member_expression":
            continue
        obj = func.child_by_field_name("object")
        if obj is None or ast.text(obj) != "console":
            continue
        out.append(ast.line(call))
    return out


def scan_file(path: Path, virtual: str) -> int:
    ast = parse_or_warn(path)
    if ast is None:
        return 0
    errors = 0
    for call in ast.find(("call_expression",)):
        match = _is_logger_call(call, ast)
        if match is None:
            continue
        if _first_arg_is_template(call):
            emit(
                "ERROR", virtual, "NQ16.no-template-in-logger",
                f"{match[0]}.{match[1]}() received a template literal as first arg; "
                f"structured fields are lost",
                f"use {match[0]}.{match[1]}({{ ... }}, 'message') with separate fields",
                line=ast.line(call),
            )
            errors += 1
    for line in _has_console_log(ast):
        emit(
            "ERROR", virtual, "NQ16.no-console-log-in-spine",
            "console.<method>(...) is unstructured; spine services must use the project logger",
            "import { logger } from '@/lib/log' (or equivalent) and replace console with logger",
            line=line,
        )
        errors += 1
    return errors


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", type=Path, default=None,
                   help="File or directory to scan (default: spine roots)")
    p.add_argument("--pretend-path", default=None,
                   help="Override the virtual path reported in emit()")
    args = p.parse_args(argv)
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
        errors += scan_file(path, virtual)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
