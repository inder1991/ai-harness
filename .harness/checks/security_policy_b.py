#!/usr/bin/env python3
"""Q13.B — every mutating FastAPI route has auth + rate-limit + CSRF.

Three rules:
  Q13.route-needs-auth        — POST/PUT/PATCH/DELETE handler missing an auth
                                 dependency (Depends(<auth_fn>) param OR
                                 @authenticated/@requires decorator).
  Q13.route-needs-rate-limit  — mutating handler missing @limiter.limit
                                 decorator unless verb:path in rate_limit_exempt.
  Q13.route-needs-csrf        — mutating handler missing CsrfProtect dependency
                                 unless verb:path in csrf_exempt.

H-25:
  Missing input    — exit 2.
  Malformed input  — WARN harness.unparseable.
  Upstream failed  — none.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import sys
from pathlib import Path
from typing import Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from _common import emit, load_baseline, normalize_path, spine_paths  # noqa: E402

DEFAULT_ROOTS = spine_paths("backend_api", ("backend/src/api",))
DEFAULT_POLICY = REPO_ROOT / ".harness" / "security_policy.yaml"
EXCLUDE_FS = (
    "node_modules", ".git", "dist", "site-packages",
    "tests/harness/fixtures", "__pycache__", ".venv", "/venv/",
    ".pytest_cache",
)
MUTATING_VERBS = {"post", "put", "patch", "delete"}
BASELINE = load_baseline("security_policy_b")


def _emit(path: Path, rule: str, msg: str, suggestion: str, line: int) -> bool:
    sig = (normalize_path(path), int(line), rule)
    if sig in BASELINE:
        return False
    emit("ERROR", path, rule, msg, suggestion, line=line)
    return True


def _load_policy(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _route_decorator_info(
    node: ast.AST,
    router_vars: set[str],
    module_constants: dict[str, str],
) -> tuple[str, str] | None:
    """Returns (verb, path) if `node` is a `@<router>.<verb>(<path>)` decorator.

    v1.3.0 S8 — `router_vars` policy-driven (router_var_names),
    not hardcoded {router, app}.

    v1.3.0 S10 — accepts:
      * literal string paths: `router.post("/x")`
      * f-strings reconstructed with `{name}` placeholders:
        `router.post(f"/api/{prefix}/x")` → `"/api/{prefix}/x"`
      * Name references resolved from module-level Constant assignments:
        `PATH = "/x"; router.post(PATH)` → `"/x"`

    Drops the dead `verb != "get"` branch (S-B7); routes are filtered
    upstream by MUTATING_VERBS anyway.
    """
    if not isinstance(node, ast.Call):
        return None
    if not (isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)):
        return None
    if node.func.value.id not in router_vars:
        return None
    verb = node.func.attr.lower()
    if verb not in MUTATING_VERBS:
        return None
    if not node.args:
        return None
    path_str = _resolve_path_arg(node.args[0], module_constants)
    if path_str is None:
        return None
    return verb, path_str


def _resolve_path_arg(node: ast.expr, module_constants: dict[str, str]) -> str | None:
    """Reconstruct a route path expression as a normalized string.

    v1.3.0 S10 — pre-v1.3.0 only matched ast.Constant(str). f-strings
    and Name references slipped (S-B5).
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for piece in node.values:
            if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                parts.append(piece.value)
            elif isinstance(piece, ast.FormattedValue):
                if isinstance(piece.value, ast.Name):
                    parts.append("{" + piece.value.id + "}")
                else:
                    parts.append("{...}")
        return "".join(parts)
    if isinstance(node, ast.Name) and node.id in module_constants:
        return module_constants[node.id]
    return None


def _collect_module_constants(tree: ast.AST) -> dict[str, str]:
    """Capture module-level `NAME = "..."` assignments so route decorators
    that reference path constants can resolve them (v1.3.0 S10)."""
    out: dict[str, str] = {}
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if (isinstance(target, ast.Name)
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)):
                out[target.id] = node.value.value
    return out


def _name_in_annotation(annotation: ast.expr, target_names: set[str]) -> bool:
    """Walk an annotation looking for a Name whose id is in `target_names`.

    Handles Annotated[T, ...] subscripts. Returns True only when a Name
    *exactly equals* one of the target names — substring matches like
    pre-v1.3.0's `"CsrfProtect" in ann_src` over-fire on
    `NoCsrfProtectNeeded` (S-B3 false negative).
    """
    if isinstance(annotation, ast.Name):
        return annotation.id in target_names
    if isinstance(annotation, ast.Subscript):
        for sub in ast.walk(annotation):
            if isinstance(sub, ast.Name) and sub.id in target_names:
                return True
    return False


def _depends_callee_name(call: ast.Call) -> str | None:
    """Inside `Depends(<expr>)`, return the name of the callee.

    Accepts both `ast.Name` and `ast.Attribute` (S-B2: pre-v1.3.0
    only matched Name). For `Depends(auth.get_current_user)` returns
    `"get_current_user"` so name matching works regardless of
    receiver shape.
    """
    if not call.args:
        return None
    inner = call.args[0]
    if isinstance(inner, ast.Name):
        return inner.id
    if isinstance(inner, ast.Attribute):
        return inner.attr
    return None


def _annotated_depends_callee(annotation: ast.expr) -> str | None:
    """If `annotation` is `Annotated[T, Depends(<f>), ...]`, return the
    name of `<f>`. Else None.

    v1.3.0 S8 — closes S-B2: the FastAPI 0.95+ idiomatic auth
    pattern (`user: Annotated[User, Depends(get_current_user)]`)
    was previously invisible to the auth check.
    """
    if not isinstance(annotation, ast.Subscript):
        return None
    # Annotated[T, Depends(...)]: slice may be a Tuple of arguments.
    slice_node = annotation.slice
    elts: list[ast.expr] = []
    if isinstance(slice_node, ast.Tuple):
        elts = list(slice_node.elts)
    else:
        elts = [slice_node]
    for elt in elts:
        if (isinstance(elt, ast.Call)
                and isinstance(elt.func, ast.Name)
                and elt.func.id == "Depends"):
            return _depends_callee_name(elt)
    return None


def _has_auth_dep(fn, auth_dep_names: set[str], auth_dec_names: set[str]) -> bool:
    """v1.3.0 S8 — covers Annotated[T, Depends(f)] and Depends(<Attribute>)."""
    for dec in fn.decorator_list:
        name = None
        if isinstance(dec, ast.Name):
            name = dec.id
        elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
            name = dec.func.id
        if name and name in auth_dec_names:
            return True
    args = list(fn.args.args) + list(fn.args.kwonlyargs)
    for arg in args:
        # PEP 593 Annotated[T, Depends(f)] (FastAPI 0.95+).
        if arg.annotation is not None:
            callee = _annotated_depends_callee(arg.annotation)
            if callee and callee in auth_dep_names:
                return True
        default = _arg_default(fn, arg)
        if default is None:
            continue
        # `arg = Depends(get_current_user)` or `arg = Depends(auth.get_current_user)`.
        if (isinstance(default, ast.Call)
                and isinstance(default.func, ast.Name)
                and default.func.id == "Depends"):
            callee = _depends_callee_name(default)
            if callee and callee in auth_dep_names:
                return True
    return False


def _arg_default(fn, arg: ast.arg) -> ast.AST | None:
    args = fn.args.args
    if arg in args:
        idx = args.index(arg)
        defaults = fn.args.defaults
        offset = len(args) - len(defaults)
        if idx >= offset:
            return defaults[idx - offset]
        return None
    kwonly = fn.args.kwonlyargs
    if arg in kwonly:
        idx = kwonly.index(arg)
        kw_defaults = fn.args.kw_defaults
        return kw_defaults[idx] if idx < len(kw_defaults) else None
    return None


def _has_rate_limit_decorator(fn) -> bool:
    for dec in fn.decorator_list:
        if (
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Attribute)
            and isinstance(dec.func.value, ast.Name)
            and dec.func.value.id == "limiter"
            and dec.func.attr == "limit"
        ):
            return True
    return False


def _has_csrf_dep(fn, csrf_dep_names: set[str]) -> bool:
    """v1.3.0 S9 — structural Name match instead of substring.

    Pre-v1.3.0 used `"CsrfProtect" in ast.dump(annotation)` which
    accepted `NoCsrfProtectNeeded`, `MyCsrfProtectStub`, etc.
    `csrf_dep_names` is policy-driven (defaults to {"CsrfProtect"}).
    """
    args = list(fn.args.args) + list(fn.args.kwonlyargs)
    for arg in args:
        if arg.annotation is None:
            continue
        if _name_in_annotation(arg.annotation, csrf_dep_names):
            return True
    return False


def _module_has_csrf_middleware(tree: ast.AST) -> bool:
    """Detect app-level CSRF middleware so per-route CsrfProtect dep isn't
    required when the FastAPI app already has CSRF enforced globally.

    v1.3.0 S9 — also recognizes the constructor pattern:
        app = FastAPI(middleware=[Middleware(CSRFMiddleware)])
    Pre-v1.3.0 only matched `app.add_middleware(...)` calls (S-B4).

    Catches:
      app.add_middleware(CSRFMiddleware, ...)
      app.add_middleware(SomethingCsrfMiddleware, ...)
      app = FastAPI(middleware=[Middleware(CsrfMiddleware), ...])
      from fastapi_csrf_protect import CsrfProtect → assume init elsewhere
    """
    for node in ast.walk(tree):
        # add_middleware call
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_middleware"
            and node.args
        ):
            first = node.args[0]
            name = (
                first.id if isinstance(first, ast.Name)
                else (first.attr if isinstance(first, ast.Attribute) else "")
            )
            if "csrf" in name.lower():
                return True
        # FastAPI(middleware=[Middleware(CsrfMiddleware), ...]) constructor
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "FastAPI"
        ):
            for kw in node.keywords:
                if kw.arg != "middleware":
                    continue
                if not isinstance(kw.value, ast.List):
                    continue
                for elt in kw.value.elts:
                    for sub in ast.walk(elt):
                        if isinstance(sub, ast.Name) and "csrf" in sub.id.lower():
                            return True
                        if isinstance(sub, ast.Attribute) and "csrf" in sub.attr.lower():
                            return True
    return False


def _exempt(verb: str, path: str, exempt_list: list[str]) -> bool:
    key = f"{verb.upper()}:{path}"
    for entry in exempt_list:
        if fnmatch.fnmatchcase(key, entry):
            return True
    return False


def _scan_file(path: Path, virtual: str, policy: dict) -> int:
    # v1.3.0 S10 — consume spine_paths "backend_api" so consumers can
    # override the route-scan scope without forking the check.
    api_roots = tuple(
        p.relative_to(REPO_ROOT).as_posix() + "/"
        for p in spine_paths("backend_api", ("backend/src/api",))
    )
    if not (
        any(virtual.startswith(root) for root in api_roots)
        or path.parent.name == "api"
    ):
        return 0
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeDecodeError):
        return 0
    except SyntaxError:
        emit("WARN", path, "harness.unparseable",
             f"could not parse {path.name}", "fix syntax", line=1)
        return 0

    auth_dep_names = set(policy.get("auth_dependency_names") or [])
    auth_dec_names = set(policy.get("auth_decorator_names") or [])
    rate_limit_exempt = list(policy.get("rate_limit_exempt") or [])
    csrf_exempt = list(policy.get("csrf_exempt") or [])
    # v1.3.0 S8 — router_var_names policy-driven; default {router, app}.
    router_vars = set(policy.get("router_var_names") or ["router", "app"])
    # v1.3.0 S9 — csrf_dependency_names policy-driven; default {CsrfProtect}.
    csrf_dep_names = set(policy.get("csrf_dependency_names") or ["CsrfProtect"])
    # If this module installs CSRF middleware globally, skip the per-route
    # CsrfProtect dependency check (the middleware enforces it for every route).
    has_global_csrf = _module_has_csrf_middleware(tree)
    # v1.3.0 S10 — capture module-level Constant assignments so route
    # decorators that reference path constants resolve them.
    module_constants = _collect_module_constants(tree)
    errors = 0

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            info = _route_decorator_info(dec, router_vars, module_constants)
            if info is None:
                continue
            verb, route_path = info
            line = node.lineno
            if not _has_auth_dep(node, auth_dep_names, auth_dec_names):
                first = sorted(auth_dep_names)[0] if auth_dep_names else "get_current_user"
                if _emit(path, "Q13.route-needs-auth",
                         f"{verb.upper()} {route_path} has no auth dependency",
                         f"add `user = Depends({first})`", line):
                    errors += 1
            if not _has_rate_limit_decorator(node) and not _exempt(verb, route_path, rate_limit_exempt):
                if _emit(path, "Q13.route-needs-rate-limit",
                         f"{verb.upper()} {route_path} missing @limiter.limit",
                         'add `@limiter.limit("<n>/minute")` or list in security_policy.yaml.rate_limit_exempt',
                         line):
                    errors += 1
            if (
                not has_global_csrf
                and not _has_csrf_dep(node, csrf_dep_names)
                and not _exempt(verb, route_path, csrf_exempt)
            ):
                if _emit(path, "Q13.route-needs-csrf",
                         f"{verb.upper()} {route_path} missing CsrfProtect dependency",
                         "add `csrf_protect: CsrfProtect = Depends()` or list under csrf_exempt",
                         line):
                    errors += 1
    return errors


def _walk_python(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        if any(tok in str(path) for tok in EXCLUDE_FS):
            continue
        yield path


def scan(roots: Iterable[Path], policy_path: Path, pretend_path: str | None) -> int:
    """Run Q13.B (auth + rate-limit + CSRF) on each FastAPI route under `roots`.
    Return 1 if any errors fired."""
    policy = _load_policy(policy_path)
    total_errors = 0
    for root in roots:
        if not root.exists():
            continue
        if root.is_file() and root.suffix == ".py":
            virtual = pretend_path or (
                str(root.relative_to(REPO_ROOT))
                if root.is_relative_to(REPO_ROOT) else root.name
            )
            total_errors += _scan_file(root, virtual, policy)
        else:
            for p in _walk_python(root):
                virtual = (
                    str(p.relative_to(REPO_ROOT))
                    if p.is_relative_to(REPO_ROOT) else p.name
                )
                total_errors += _scan_file(p, virtual, policy)
    return 1 if total_errors else 0


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: dispatch scan, return process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, action="append")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--pretend-path", type=str)
    args = parser.parse_args(argv)
    roots = tuple(args.target) if args.target else DEFAULT_ROOTS
    return scan(roots, args.policy, args.pretend_path)


if __name__ == "__main__":
    sys.exit(main())
