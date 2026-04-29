#!/usr/bin/env python3
"""NQ13 — Node security-routes middleware check.

One rule enforced on Express-style route declarations:
  NQ13.mutating-route-needs-auth — POST/PUT/DELETE/PATCH routes must have
        at least one middleware between the path string and the final
        handler. The check looks for any middleware function named
        `requireAuth`, `auth`, `authenticate`, `csrf`, `rateLimit`,
        `rateLimiter` in the call's argument list.

A route declaration matches if the call shape is:
    <obj>.<method>(<path>, <handler>)
or  <obj>.<method>(<path>, <middleware...>, <handler>)
where method ∈ {post, put, delete, patch}.

The single-arg form (just a handler, no path) is ignored — it's typically
a global app.use(handler) rather than a route.
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
MUTATING_METHODS = {"post", "put", "delete", "patch"}
AUTH_MIDDLEWARE_NAMES = {
    "requireAuth", "auth", "authenticate", "authorize",
    "csrf", "csrfProtection", "rateLimit", "rateLimiter",
}


def _route_method(call_node, ast) -> str | None:
    func = call_node.child_by_field_name("function")
    if func is None or func.type != "member_expression":
        return None
    prop = func.child_by_field_name("property")
    if prop is None:
        return None
    method = ast.text(prop)
    return method if method in MUTATING_METHODS else None


def _has_auth_middleware(call_node, ast) -> bool:
    """Inspect every argument; return True if any one is a Name (or a
    member-call with prop) matching an AUTH_MIDDLEWARE_NAMES entry."""
    args = call_node.child_by_field_name("arguments")
    if args is None:
        return False
    for i in range(args.named_child_count):
        arg = args.named_child(i)
        if arg is None:
            continue
        if arg.type == "identifier" and ast.text(arg) in AUTH_MIDDLEWARE_NAMES:
            return True
        if arg.type == "call_expression":
            inner_func = arg.child_by_field_name("function")
            if inner_func is None:
                continue
            text = ast.text(inner_func)
            last = text.rsplit(".", 1)[-1]
            if last in AUTH_MIDDLEWARE_NAMES:
                return True
        if arg.type == "member_expression":
            prop = arg.child_by_field_name("property")
            if prop is not None and ast.text(prop) in AUTH_MIDDLEWARE_NAMES:
                return True
    return False


def scan_file(path: Path, virtual: str) -> int:
    ast = parse_or_warn(path)
    if ast is None:
        return 0
    errors = 0
    for call in ast.find(("call_expression",)):
        method = _route_method(call, ast)
        if method is None:
            continue
        args = call.child_by_field_name("arguments")
        if args is None or args.named_child_count < 2:
            continue
        if _has_auth_middleware(call, ast):
            continue
        emit(
            "ERROR", virtual, "NQ13.mutating-route-needs-auth",
            f"`{method}` route declares no auth/csrf/rate-limit middleware",
            "add requireAuth (and rateLimit/csrf where appropriate) before the handler arg",
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
