# node-backend pack — contributing guide

This pack ships 8 first-class checks for JavaScript / TypeScript spines
(Express, Fastify, NestJS, etc). It is **additive**: a Python-only
consumer never sees these unless they add `node-backend` to their
profile's `extends:` list.

## Install

```bash
pip install 'ai-harness[node]'
```

That installs `tree-sitter`, `tree-sitter-javascript`, and
`tree-sitter-typescript` (~30 MB combined). Without these, the checks
emit a clear `ImportError` from `_ts_parser.py:_load_parser`.

## Adding a new check to this pack

1. Pick a rule prefix from the canonical Node namespace (`NQ7` async, `NQ8`
   data layer, `NQ9` testing, `NQ10` validation, `NQ11` deps, `NQ13`
   security, `NQ16` logging). New rules in this pack should reuse one of
   those prefixes — don't invent a new one.
2. Create `<your_check>.py` in this directory. Mirror the structure of
   `node_logging.py`:
   - lazy import via `_node_common`,
   - `scan_file(path, virtual)` returns int errors,
   - `main(argv)` parses `--target` + `--pretend-path` + check-specific args.
3. Add one violation fixture and one compliant fixture under
   `tests/harness/fixtures/node-backend/{violation,compliant}/`.
4. Add the parametrised case to `tests/harness/checks/test_node_backend_pack.py`.
5. Update `.harness/severity_map.yaml` with the new rule's tier.

## Parser wrapper API

`_ts_parser.py` exposes:

- `parse(path) -> NodeAST` — parses any `.js/.jsx/.mjs/.cjs/.ts/.tsx`.
- `NodeAST.find(types)` — depth-first walk yielding nodes whose `.type` matches.
- `NodeAST.text(node)` / `NodeAST.line(node)` — span helpers.
- `NodeAST.has_errors()` — set when tree-sitter found ERROR regions.

**Identity gotcha:** every accessor returns a NEW Python wrapper around
the underlying C node. Use `==`, never `is`, when comparing two node
references (e.g., when checking whether a member_expression's `.object`
field points at a known call).

## Performance

Each check should finish < 10s on a 5,000-file Node repo (S4.2 acceptance
criterion). Tree-sitter cold-start is ~10ms per parser; the wrapper
caches one parser per extension per process.

## Why tree-sitter (not Babel / esprima / swc / oxc)

See `docs/decisions/2026-04-29-node-ast-parser.md`.
