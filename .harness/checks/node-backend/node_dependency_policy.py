#!/usr/bin/env python3
"""NQ11 — Node dependency-policy check.

Two rules enforced on `package.json` files:
  NQ11.runtime-needs-dev — packages that are clearly dev-only (testing
        frameworks, build tools, type packages) appearing in `dependencies`
        bloat the prod bundle and increase attack surface.
  NQ11.dev-shouldnt-be-runtime — packages that runtime code obviously
        needs (typed validators, http clients, db drivers) appearing only
        in `devDependencies` will fail at runtime in prod.

This check parses JSON directly — no tree-sitter needed. It complements
the polyglot dependency_policy.py by adding Node-aware package taxonomy.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from _node_common import emit  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]

DEV_ONLY_PACKAGES = {
    "vitest", "jest", "mocha", "chai", "ava",
    "playwright", "@playwright/test", "cypress",
    "msw", "supertest", "nock",
    "eslint", "prettier", "tslint",
    "typescript", "ts-node", "tsx",
    "webpack", "vite", "rollup", "esbuild", "tsup", "turbo",
    "@types/node", "@types/express", "@types/jest", "@types/react",
    "nodemon", "concurrently",
}

RUNTIME_REQUIRED_HINTS = {
    "express", "fastify", "koa", "hapi", "@nestjs/core",
    "axios", "node-fetch", "got", "undici",
    "pg", "mysql2", "mongoose", "@prisma/client",
    "zod", "joi", "yup",
    "pino", "winston", "bunyan",
    "dotenv",
}


def _check_package_json(path: Path, virtual: str) -> int:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        emit("WARN", virtual, "harness.unparseable",
             f"package.json could not be parsed: {exc}",
             "validate the JSON and re-run", line=1)
        return 0
    deps = data.get("dependencies") or {}
    dev_deps = data.get("devDependencies") or {}
    errors = 0
    for pkg in deps:
        if pkg in DEV_ONLY_PACKAGES or pkg.startswith("@types/"):
            emit(
                "ERROR", virtual, "NQ11.runtime-needs-dev",
                f"`{pkg}` is dev-only but appears in dependencies (ships to prod)",
                f"move `{pkg}` from dependencies to devDependencies",
                line=1,
            )
            errors += 1
    for pkg in dev_deps:
        if pkg in RUNTIME_REQUIRED_HINTS:
            emit(
                "ERROR", virtual, "NQ11.dev-shouldnt-be-runtime",
                f"`{pkg}` is runtime-required but only in devDependencies; prod will crash",
                f"move `{pkg}` from devDependencies to dependencies",
                line=1,
            )
            errors += 1
    return errors


def _iter_package_json(roots: list[Path]):
    for root in roots:
        if root.is_file() and root.name == "package.json":
            yield root
            continue
        if not root.exists():
            continue
        for path in root.rglob("package.json"):
            if any(part in {"node_modules", ".git"} for part in path.parts):
                continue
            yield path


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
        roots = [args.target]
    else:
        roots = [REPO_ROOT]
    errors = 0
    for path in _iter_package_json(roots):
        virtual = args.pretend_path or str(path)
        errors += _check_package_json(path, virtual)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
