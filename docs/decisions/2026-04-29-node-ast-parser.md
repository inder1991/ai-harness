# Use tree-sitter-javascript + tree-sitter-typescript for the Node pack

Status: Accepted
Date: 2026-04-29
Owner: @inder

## Context

Sprint 4 (v2.2.0) introduces a Node-pack of 8 first-class checks for JavaScript / TypeScript projects. Each check needs to parse JS/TS source. The Python-pack uses Python's built-in `ast` module; there's no equivalent stdlib parser for JS/TS, so we have to choose a third-party route.

This decision blocks Sprint 4 entirely. Picking the wrong parser at the start would mean rewriting 8 checks mid-sprint when limitations surface.

## Options considered

### A. tree-sitter Python bindings (tree-sitter-javascript + tree-sitter-typescript)

In-process via Python C-extension bindings. Fast per-call (~10ms after warm). Heavy install (compiled C extensions; ~30 MB on disk). Maintained by GitHub (the parsers underpin GitHub's own code search).

- ✓ In-process, no subprocess overhead.
- ✓ Mature parsers (used in Atom, Neovim, GitHub UI, Zed).
- ✓ Same API for JS, TS, JSX, TSX.
- ✓ Decorator support out of the box.
- ✗ Heavy install (compiled wheels per platform).
- ✗ Adds to the harness's install footprint when Node-pack disabled (we'd need lazy import).
- ✗ Bindings versioning churn (tree-sitter 0.x → 1.0 transition is recent).

### B. Subprocess to `node --eval` running esprima or babel parser

Zero install footprint when Node-pack disabled. Slow per-call (~150ms cold start each). Requires Node already installed (which any Node consumer has).

- ✓ Zero install impact for non-Node consumers.
- ✓ Easy to evolve — bump esprima/babel version without touching Python.
- ✗ Subprocess startup cost: ~150ms × N files = noticeable on large repos. A 5000-file repo at 50 files/check × 8 checks = 60,000 subprocess starts ≈ 150 minutes. Unacceptable.
- ✗ Per-call IPC (JSON-over-stdout) adds parsing overhead.
- ✗ Requires Node on PATH for any harness consumer running Node-pack — not a blocker since they have it, but coupling.

### C. Subprocess to `swc` or `oxc` (Rust-native parsers)

Fast even cold (~30ms via `swc parse <file>`). Heavy install (Rust binaries; install via `npm i @swc/core` or `cargo install`).

- ✓ Fastest cold-start of the three.
- ✓ Rust-native; produces structured JSON.
- ✗ Heavy install (Rust toolchain or compiled binary per platform).
- ✗ `oxc` is still pre-1.0; API churn risk over the next 12 months.
- ✗ Newer ecosystem; less battle-tested than tree-sitter or babel.

## Decision

**Adopt option A — tree-sitter Python bindings.**

Concrete plan:

1. Sprint 4 / S4.2 imports `tree_sitter` lazily inside the Node-pack checks only. A consumer with `python-react` or `python-only` profile never installs the bindings.
2. Pin specific versions: `tree-sitter==0.23.*`, `tree-sitter-javascript==0.23.*`, `tree-sitter-typescript==0.23.*` (latest stable as of this ADR).
3. Provide a small wrapper `.harness/checks/node-backend/_ts_parser.py` that:
   - Imports tree-sitter lazily.
   - Returns a uniform `NodeAST` object regardless of whether the file is `.ts`, `.tsx`, `.js`, or `.jsx`.
   - Caches the loaded parser (one per process).
4. Document install-impact in the README: "node-backend pack adds ~30 MB to the install footprint."
5. Include a benchmark script `tools/perf/node_parser_bench.py` so future maintainers can re-run if the choice needs revisiting.

## Why option A wins

- **Cold-start cost is the dominant concern.** A check fires on every PR, 50× per file × 5000 files. Option B's ~150ms per parse compounds to 150+ minutes of wall time on a single large-repo run. Option A's ~10ms per parse keeps the inner loop sub-30s.
- **Maturity matters more than novelty.** tree-sitter parsers underpin GitHub Code Search and several major editors. Option C's `oxc` is impressive but pre-1.0; we'd be paying for its instability with refactor work over the next 12 months.
- **Lazy install mitigates the heavy-install concern.** The 30 MB only lands when the consumer enables `node-backend` in their profile. Pure Python-React consumers never see it.
- **Reversibility.** The wrapper module is the single point of coupling. Switching to option B or C in the future is one wrapper rewrite, not 8 check rewrites.

## Consequences

- Positive — Sub-30s validate-fast preserved on large Node repos.
- Positive — One parser API for both JS and TS (with the right grammar selected per extension).
- Positive — Decorator + JSX support included.
- Negative — 30 MB install impact for Node-pack users. Documented + scoped to the pack.
- Negative — Tree-sitter Python bindings have an in-progress 0.x → 1.0 transition; we'll need to track the migration.
- Neutral — Future maintainers can revisit if `oxc` matures or tree-sitter ships a Rust-native Python wrapper.

## What changes if we revisit this in 12 months

If `oxc` reaches 1.0 with a stable Python binding, AND tree-sitter Python bindings become a maintenance burden, switch. The wrapper module is the only file that needs to change. Re-run the benchmark, update this ADR, ship as v2.x patch.

## Alternatives rejected (recap)

- **B (Node subprocess)** — cold-start cost makes large repos infeasible.
- **C (Rust-native)** — pre-1.0 maturity risk.

## Benchmark sketch

A standalone benchmark script lives at `tools/perf/node_parser_bench.py` (committed in this story). It runs each option against a fixture corpus of 50 small files + 5 large files; reports cold-start time, warm-start time, and total wall.

The first benchmark run will populate the numbers above with measured values. Sprint 4 / S4.2 must not begin until this benchmark is run + the numbers confirm option A meets the sub-30s validate-fast budget.
