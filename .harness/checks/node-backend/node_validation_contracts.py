#!/usr/bin/env python3
"""NQ10 — Node validation-contract strictness check.

Two rules enforced on API request/response schemas defined with zod:
  NQ10.request-needs-strict   — `z.object({...})` used for request bodies
                                without `.strict()` chained allows extra
                                fields silently and breaks SLO contracts.
  NQ10.response-needs-readonly — response schemas exported from controllers
                                without `.readonly()` allow callers to mutate
                                shared instances.

Heuristic: a schema is treated as a "request" if its containing variable
name ends in `Request`, `RequestSchema`, or `Body`. A "response" if it
ends in `Response`, `ResponseSchema`, or `Reply`. Other schemas are
ignored to keep false-positive rate low.
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
REQUEST_SUFFIXES = ("Request", "RequestSchema", "Body", "BodySchema")
RESPONSE_SUFFIXES = ("Response", "ResponseSchema", "Reply", "ReplySchema")


def _called_zod_object(call_node, ast) -> bool:
    """True iff `call_node` is `z.object(...)` (or aliased z.object)."""
    func = call_node.child_by_field_name("function")
    if func is None or func.type != "member_expression":
        return False
    obj = func.child_by_field_name("object")
    prop = func.child_by_field_name("property")
    if obj is None or prop is None:
        return False
    return ast.text(obj) == "z" and ast.text(prop) == "object"


def _outermost_call(call_node):
    """Walk up the chained-call tree: from `z.object({})` find the
    outermost `(...)` so `.strict().readonly()` post-fixes are visible."""
    cur = call_node
    while True:
        parent = cur.parent
        if parent is None:
            return cur
        if parent.type == "member_expression" and parent.child_by_field_name("object") == cur:
            grand = parent.parent
            if grand is not None and grand.type == "call_expression":
                cur = grand
                continue
        return cur


def _has_chained_method(outer_call_node, ast, method: str) -> bool:
    """Walk every ancestor call_expression and return True if any of them
    are `<...>.<method>(...)`."""
    cur = outer_call_node
    while cur is not None and cur.type == "call_expression":
        func = cur.child_by_field_name("function")
        if func is not None and func.type == "member_expression":
            prop = func.child_by_field_name("property")
            if prop is not None and ast.text(prop) == method:
                return True
        next_cur = cur.child_by_field_name("function")
        if next_cur is None or next_cur.type != "member_expression":
            return False
        obj = next_cur.child_by_field_name("object")
        if obj is None or obj.type != "call_expression":
            return False
        cur = obj
    return False


def _enclosing_var_name(call_node, ast) -> str | None:
    """Walk up to the nearest variable_declarator / assignment_expression
    and return the bound name."""
    cur = call_node.parent
    while cur is not None:
        if cur.type == "variable_declarator":
            name = cur.child_by_field_name("name")
            if name is not None:
                return ast.text(name)
            return None
        if cur.type == "assignment_expression":
            left = cur.child_by_field_name("left")
            if left is not None:
                return ast.text(left)
            return None
        cur = cur.parent
    return None


def scan_file(path: Path, virtual: str) -> int:
    ast = parse_or_warn(path)
    if ast is None:
        return 0
    errors = 0
    for call in ast.find(("call_expression",)):
        if not _called_zod_object(call, ast):
            continue
        var_name = _enclosing_var_name(call, ast)
        if var_name is None:
            continue
        outer = _outermost_call(call)
        is_request = var_name.endswith(REQUEST_SUFFIXES)
        is_response = var_name.endswith(RESPONSE_SUFFIXES)
        if is_request and not _has_chained_method(outer, ast, "strict"):
            emit(
                "ERROR", virtual, "NQ10.request-needs-strict",
                f"request schema `{var_name}` allows extra fields silently",
                "chain `.strict()` after z.object({...}) to reject unknown keys",
                line=ast.line(call),
            )
            errors += 1
        if is_response and not _has_chained_method(outer, ast, "readonly"):
            emit(
                "ERROR", virtual, "NQ10.response-needs-readonly",
                f"response schema `{var_name}` is mutable; callers can corrupt shared state",
                "chain `.readonly()` after z.object({...}) for response schemas",
                line=ast.line(call),
            )
            errors += 1
    return errors


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", type=Path, default=None)
    p.add_argument("--pretend-path", default=None)
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
