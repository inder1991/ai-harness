# rust-backend pack — contributing guide

Sprint 4 / S4.4 starter pack — 3 first-class checks for Rust services.

## Why regex (not syn or tree-sitter)?

Rust macros (sqlx::query! etc.) parse cleanly with regex because the
invocation pattern is stable. Adding `syn` (via PyO3) or
`tree-sitter-rust` would add ~30 MB to the install footprint with
diminishing returns for 3 starter checks. If a future sprint expands
this pack to 8+ checks, swap to a real parser in `_rust_common.py` —
call sites need not change.

## Rule namespace

`RQ7` HTTP wrapper, `RQ8` DB quarantine, `RQ12` error handling. Reuse
these prefixes when adding new checks.

## Adding a new check

1. Create `<your_check>.py`. Mirror `rust_http_wrapper.py`.
2. Add violation + compliant fixtures under `tests/harness/fixtures/rust-backend/`.
3. Parametrise into `tests/harness/checks/test_rust_backend_pack.py`.
4. Update `.harness/severity_map.yaml` with the new rule's tier.

## Known limitations of the regex approach

- Inline `#[cfg(test)] mod tests` blocks aren't detected; `.unwrap()`
  inside them will fire RQ12. Workaround: move tests to a `tests/`
  directory or `_test.rs` filename suffix, or baseline the entry.
- `let _ = result.unwrap();` is treated as a violation (it is — error
  ignored), but `let _ = result;` (intentional drop without unwrap) is
  legal and silent.
- `#[cfg(test)]` immediate guarding of `.unwrap()` is not honoured.
  Move test code into the test file/dir conventions instead.

These are deliberate starter-pack tradeoffs — accept the false-positive
rate or upgrade to a parser-based pack in a future sprint.
