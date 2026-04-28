"""Sprint 0 / S0.1 — node parser benchmark.

Compares cold-start + warm-start parse cost for the three options
considered in `docs/decisions/2026-04-29-node-ast-parser.md`.

Run: `python tools/perf/node_parser_bench.py`

Not shipped to consumers; this is a maintainer tool for re-validating
the architectural decision when tree-sitter / oxc evolve.

This script is intentionally a placeholder — the actual benchmark code
will be filled in during Sprint 4 prep when we install the candidate
parsers. The skeleton + the corpus structure are committed now so the
plan is concrete.
"""
from __future__ import annotations

import time
from pathlib import Path

CORPUS_DIR = Path(__file__).parent / "node_corpus"


def _build_corpus() -> None:
    """Generate 50 small + 5 large fixture files for benchmarking."""
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    # Skeleton: actual corpus generation lives in Sprint 4 prep.
    pass


def bench_tree_sitter() -> dict:
    """Option A: tree-sitter Python bindings."""
    return {"option": "tree-sitter", "status": "not yet implemented (Sprint 4 prep)"}


def bench_node_subprocess() -> dict:
    """Option B: Node subprocess + esprima."""
    return {"option": "node-subprocess", "status": "not yet implemented (Sprint 4 prep)"}


def bench_swc_subprocess() -> dict:
    """Option C: swc/oxc subprocess."""
    return {"option": "swc-subprocess", "status": "not yet implemented (Sprint 4 prep)"}


def main() -> int:
    """Run all three benchmarks; emit a comparison table."""
    print("ai-harness node parser benchmark")
    print(f"Corpus: {CORPUS_DIR} (size: pending Sprint 4 prep)")
    print()
    for fn in (bench_tree_sitter, bench_node_subprocess, bench_swc_subprocess):
        result = fn()
        print(f"  {result['option']:20} {result['status']}")
    print()
    print("Sprint 4 / S4.2 will populate this script with real measurements.")
    print("ADR: docs/decisions/2026-04-29-node-ast-parser.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
