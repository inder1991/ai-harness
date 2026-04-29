# go-backend pack — contributing guide

Sprint 4 / S4.4 starter pack — 3 first-class checks for Go services.

## Why regex (not tree-sitter)?

The Node pack uses tree-sitter because TS/JSX requires real AST. Go is
simpler: most rules anchor on stable textual idioms (`import "net/http"`,
`db.Exec(`, `_ = err`). For 3 starter checks the regex approach keeps
the install footprint zero. If a future sprint expands this pack to 8+
checks like the Node pack, swap to tree-sitter-go in this directory's
`_go_common.py` — call sites need not change.

## Rule namespace

`GQ7` HTTP wrapper, `GQ8` DB quarantine, `GQ12` error handling. Reuse
these prefixes when adding new checks; coordinate with the Python
pack's Q-prefix table to avoid collisions.

## Adding a new check

1. Create `<your_check>.py` in this directory. Mirror `go_http_wrapper.py`.
2. Add a violation + compliant fixture under
   `tests/harness/fixtures/go-backend/`.
3. Parametrise into `tests/harness/checks/test_go_backend_pack.py`.
4. Update `.harness/severity_map.yaml` with the new rule's tier.

## What this pack does NOT cover (yet)

- Goroutine leak detection
- Context propagation
- Mutex / channel race patterns
- Generics constraints
- Module/package layering rules

These are deliberately deferred until consumer demand justifies the
maintenance cost.
