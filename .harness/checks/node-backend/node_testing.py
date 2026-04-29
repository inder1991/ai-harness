#!/usr/bin/env python3
"""NQ9 — Node test-suite hygiene check.

Two rules enforced ONLY on test files (`*.test.ts`, `*.test.tsx`,
`*.spec.ts`, `*.spec.tsx`, plus `.js/.jsx` variants):

  NQ9.no-live-llm-in-tests   — direct imports of `openai`, `anthropic`,
                               `langchain`, `cohere-ai` in tests cause
                               nondeterminism + spend.
  NQ9.no-raw-fetch-in-tests  — `fetch(...)` calls in tests bypass the
                               msw/respx mocking layer and produce flakes
                               on network outages.
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
LIVE_LLM_PACKAGES = {"openai", "anthropic", "langchain", "cohere-ai", "@anthropic-ai/sdk"}
TEST_SUFFIXES = (".test.ts", ".test.tsx", ".test.js", ".test.jsx",
                 ".spec.ts", ".spec.tsx", ".spec.js", ".spec.jsx")


def _is_test_file(virtual: str) -> bool:
    return virtual.endswith(TEST_SUFFIXES) or "/__tests__/" in virtual


def _import_source(import_node, ast) -> str:
    src = import_node.child_by_field_name("source")
    if src is None:
        return ""
    text = ast.text(src)
    if len(text) >= 2 and text[0] in {'"', "'"} and text[-1] == text[0]:
        return text[1:-1]
    return text


def _is_bare_fetch_call(call_node, ast) -> bool:
    func = call_node.child_by_field_name("function")
    if func is None:
        return False
    return func.type == "identifier" and ast.text(func) == "fetch"


def scan_file(path: Path, virtual: str) -> int:
    if not _is_test_file(virtual):
        return 0
    ast = parse_or_warn(path)
    if ast is None:
        return 0
    errors = 0
    for imp in ast.find(("import_statement",)):
        src = _import_source(imp, ast)
        if src in LIVE_LLM_PACKAGES:
            emit(
                "ERROR", virtual, "NQ9.no-live-llm-in-tests",
                f"test imports `{src}` directly; tests will hit the live API",
                "import a stub from `tests/mocks/llm.ts` (or msw handler) instead",
                line=ast.line(imp),
            )
            errors += 1
    for call in ast.find(("call_expression",)):
        if _is_bare_fetch_call(call, ast):
            emit(
                "ERROR", virtual, "NQ9.no-raw-fetch-in-tests",
                "raw fetch() in test bypasses the msw mock layer",
                "use msw handlers (server.use(...)) or the project's test http client",
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
