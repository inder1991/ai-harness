# Releases

## v1.3.0 — Rule-semantics hardening (signed)

Closes the 30 P3 findings from the post-v1.2.1 second-pass audit
(`docs/plans/2026-04-28-harness-rule-semantics-audit.md`). All checks
that previously matched literal `module.function(...)` text now use
canonical resolution (ImportTracker), so aliased and from-import forms
fire correctly. Single squash release covering both the original
v1.3.0 (root-cause infra) and v1.3.1 (long-tail polish) plans.

Cross-cutting infrastructure:
- **`_common.ImportTracker`** — single helper that maps bound names
  back to canonical fully-qualified module paths. Covers `import`,
  `import-as`, `from-import`, `from-import-as`. Used by 4+ checks.
- **`_common.is_logger_call`** — single predicate for "this AST Call
  is a logger emission". `logging_policy` and `security_policy_a`
  now agree on what counts.
- **`Q22.doc-rule-count-mismatch`** — new self-test catches docstring
  drift; each check's "N rules" claim must match enumerated IDs.
- **Runtime stdlib detection** — `dependency_policy` uses
  `sys.stdlib_module_names` instead of a hand-maintained set.

Per-check fixes (audit IDs in parentheses):
- security_policy_a: AST scan for dangerous patterns + multi-line
  shell=True (S-A4, S-A5, S-A8); imports-aware outbound HTTP scan
  + httpx.Timeout(None) wrap detection (S-A3, S-A6, S-A7);
  log-leak via shared predicate + AST source segments (S-A1, S-A2);
  docstring drift (S-A9).
- security_policy_b: policy-driven `router_var_names` (S-B1);
  Annotated[T, Depends()] + Depends(<Attribute>) auth (S-B2);
  structural `csrf_dependency_names` instead of substring match
  (S-B3); FastAPI(middleware=[]) constructor pattern (S-B4); route
  paths from f-strings + Name references (S-B5); spine_paths
  consumption (S-B6); dead `verb != "get"` branch removed (S-B7).
- backend_async_correctness: ImportTracker for asyncio.run /
  httpx.Client / time.sleep coverage of from-import + aliased forms
  (S-AS3, S-AS4, S-AS6); wrapper file exemption (S-AS2); docstring
  drift (S-AS1).
- backend_db_layer: AST + canonical text() / cursor.execute (S-DB4,
  S-DB5); raw-SQL scan limited to string literals, docstrings
  excluded (S-DB2); RAW-SQL-JUSTIFIED line-scoped (S-DB3);
  inheritance-aware db-model-needs-table (S-DB6); docstring drift
  (S-DB1).
- conventions_policy: tightened DOTDOT regex (S-CV1); allow single-
  dot bare imports for re-exports (S-CV2); strip multi-dot stems
  before PascalCase (S-CV3); document dunder acceptance (S-CV4).
- dependency_policy: pyproject extras + Poetry + build-system reqs
  (S-DP1); separate runtime/dev npm allow-lists (S-DP2); npm version
  refs + scoped-package handling (S-DP3); runtime stdlib (S-DP4).

Q22 also surfaced 5 NEW docstring drifts beyond the audit
(validation_contracts, data_layer, frontend_routing camelCase rule
names, output_format, typecheck) — all fixed in this release.

Tests: 280 → 301+ passing in the harness self-test surface
(+~25 new fixtures + tests across 9 checks).

## v1.2.1 — P2 polish (signed)

Closes the 9 P2 findings from the post-v1.1.0 audit (B19-B27):

- **B19** — `refresh_baselines._read_existing_count` WARNs on JSON
  parse errors instead of silently returning 0.
- **B20** — `load_harness._read_file_safe` records OSError reads in
  the malformed_files surface.
- **B21** — `extract.sh` logs `find -delete` failures instead of
  swallowing.
- **B22** — `setup_signing.sh --protect` flag for human signers
  (passphrase-protected key generation); CI default stays
  passphrase-less.
- **B23** — `install_pre_commit.sh` falls back to
  `python3 tools/run_validate.py --fast` when make isn't on PATH.
- **B24** — `load_harness.collect_cross_cutting` switches to
  `fnmatch.fnmatchcase` for cross-platform deterministic matching.
- **B25** — `refresh_baselines._refresh_one` refuses to overwrite a
  baseline with `[]` when a check exited non-zero with no parseable
  findings (silent reset guard).
- **B26** — `_session_start_hook.sh` adds `set -o pipefail`.
- **B27** — confirmed `harness_policy_schema` covers
  HARNESS_CARD.yaml (no code change needed).

## v1.2.0 — P1 hardening batch (signed)

Closes the eight P1 findings from the post-v1.1.0 SDET audit
(`docs/plans/2026-04-27-harness-sdet-audit.md`):

- **B11** — `tools/init_harness.py` now copies `.gitattributes` into
  the bootstrapped repo. Without it, Windows checkouts broke the
  `make harness` byte-deterministic regen gate.
- **B12** — `tools/init_harness.py` writes a `.harness-version` pin
  on bootstrap (the resolved ref for `--from-git`, or `main` for
  local-source). Stops `sync_harness.py` from exiting 2 on the
  consumer's first run.
- **B13** — every git subprocess in `tools/init_harness.py` and
  `tools/sync_harness.py` now runs under an explicit `timeout=`
  (30s for `ls-remote`, 120s for `clone`, 10s for `cat-file`, 15s
  for `verify-tag`). A hung remote can no longer stall bootstrap or
  sync indefinitely.
- **B14** — `tools/run_validate.py` enforces `CHECK_TIMEOUT_S = 180s`
  per check subprocess. A check that hangs (infinite loop, blocked
  I/O) now surfaces as a synthetic `[ERROR] file=<check>
  rule=harness.timeout` finding plus a failure-log entry, and the
  orchestrator returns 1.
- **B15** — `tools/sync_harness.py --trust-key <FINGERPRINT>`
  (or `HARNESS_TRUST_KEY` env) requires the tag's signature to come
  from a specific GPG fingerprint. Without this pin, `git verify-tag`
  accepts any key in the consumer's keyring — a maintainer with
  many imported keys downgrades the trust model. Documented in
  `tools/init_harness_templates/keys.md`.
- **B16** — new check `Q21.harness-card-version-mismatch`. Fires when
  `HARNESS_CARD.yaml.version` doesn't match `.harness-version`
  (stripped of leading `v`). Catches the silent drift the card
  version had before this release.
- **B17** — `tools/extraction/extract.sh` smoke-tests the carved
  repo with `pytest tests/harness -q --tb=short -x` after the carve
  commits land. Aborts with exit 4 on any self-test failure;
  broken extractions never reach `git push`.
- **B18** — `run_validate.run_tests` actually runs vitest (was
  claimed by the docstring since v1.0.0 but never wired up). Gated
  on `frontend/package.json` and `frontend/node_modules` existing
  so Python-only consumers don't fail.

19+ new tests across 8 files. The harness substrate is fully green
under `validate-full`.

## v1.1.1 — Patch on the v1.1.0 hardening batch (signed)

Closes the four P0 regressions surfaced by the post-v1.1.0 audit
(`docs/plans/2026-04-27-harness-sdet-audit.md`):

- **B7** — `tools/sign_release.sh` no longer queries `--global`
  user.signingkey; uses git's standard local→global→system resolution
  so the v1.1.0 `setup_signing.sh --local` default flows through to
  release time.
- **B8** — `.github/workflows/validate.yml` runs `make validate-full`
  instead of `make validate-fast`. The fast tier was silently skipping
  six enforcers (output_format_conformance, backend_testing,
  frontend_testing, backend_async_correctness, backend_db_layer,
  typecheck_policy) on every PR. Step timeout bumped 10→20 min for the
  full tier.
- **B9** — `init_harness._resolve_latest_tag` parses tags as semver
  tuples instead of lexical sort. Lexical sort ranks v1.10.0 below
  v1.2.0; once the harness crosses v1.10 the bug would have pinned a
  stale ref. Adds `timeout=30` to the underlying `git ls-remote`
  (partial B13).
- **B10** — `_rotate_failure_log` re-checks size and renames under
  `fcntl.LOCK_EX`. B2's lock covered append, not rotate; concurrent
  validate-fast runs could double-rename onto `.1` and clobber the
  first rotation's bytes. 10/10 stress runs pass.

306+/306+ harness tests pass after the fixes; new unit tests added
for each P0.

## v1.1.0 — Production hardening (signed) — **breaking baseline format**

P0 bugs from the SDET production-readiness audit. **Bumps minor** because
the on-disk baseline format changes: every entry's `file` field is now a
repo-relative POSIX path instead of whatever absolute string the snapshot
machine emitted. After upgrading, run **once**:

```
python3 tools/refresh_baselines.py --migrate-paths
```

Same-machine absolute paths migrate silently on next load. Foreign-machine
absolute paths drop with `[WARN]` and need re-snapshotting via
`make harness-baseline-refresh`.

Fixes (audit IDs B1–B6):

- **B1 — relative baseline paths.** `_common.normalize_path()` strips
  `REPO_ROOT` from every emitted file location and at-load every baseline
  entry. CI ↔ local stop diverging. (`load_baseline` migrate-on-read drops
  foreign-machine entries loudly so merge surprises end at the WARN.)
- **B5 — single regex source.** `_common.ERROR_LINE_PATTERN` is the only
  place the H-16 `[ERROR] file=…:LINE rule=…` shape is described.
  `run_validate.py` and `refresh_baselines.py` both import it. The new
  `.+?` file capture handles paths with spaces / unicode / parens that the
  old `\S+?` choked on.
- **B6 — escape control chars in messages.** A docstring containing `\n`
  or `\t` no longer corrupts the line-based emit format. `_escape_field()`
  replaces `\n`, `\r`, `\t`, and `"`.
- **B2 — atomic failure-log appends.** `tools/run_validate.py` takes
  `fcntl.LOCK_EX` before each `.harness/.failure-log.jsonl` write so two
  parallel `make validate-fast` invocations no longer interleave bytes.
- **B4 — opt-in global GPG config.** `tools/setup_signing.sh` now defaults
  to `--local` scope. `--global` is opt-in and refuses to overwrite an
  existing `user.signingkey` / `tag.gpgsign` without `--force`.
- **B3 — refuse `init_harness --target <self>`.** `tools/init_harness.py`
  exits 2 if `--target` resolves to the harness source repo, preventing a
  "what just happened to my main branch" footgun.
- **`refresh_baselines.py --migrate-paths`** — in-place migrator for
  v1.0.x baselines that doesn't re-run every check.

302/302 harness tests pass; 145/145 check-rule tests pass; `validate-fast`
is byte-identical between two consecutive runs after the migration.

See `docs/decisions/2026-04-27-baseline-paths-relative-v1.1.0.md` for the
full reasoning behind the breaking change.

## v1.0.4 — Enforcement + telemetry batch (signed)

Four awesome-harness audit follow-ups, all $0 / no API spend:

- **CI workflow** — `.github/workflows/validate.yml` runs `make validate-full`
  on every PR + push to main. Closes the `git commit -n` bypass loophole.
- **`.gitattributes`** — `eol=lf` on all text extensions; prevents Windows
  checkout from breaking the `make harness` byte-deterministic regen gate.
- **HarnessCard** — `.harness/HARNESS_CARD.yaml` declares at-a-glance what
  this harness covers using the CAR (Control / Agency / Runtime) decomposition.
  Includes `coverage.covered` + `coverage.not_covered` (honest about gaps),
  `consumer_fit` profiles, distribution commands. Schema-validated.
- **Rolling failure log** — `tools/run_validate.py` appends every `[ERROR]`
  to `.harness/.failure-log.jsonl` with timestamp + commit + session UUID +
  host. 10 MB rotation cap, gitignored. Gives the AI trend visibility ("rule
  X fired 47 times this week") with zero API cost — closest thing to "evals"
  we can build for free.

## v1.0.3 — Tier 2 completion (signed)

Closes the Tier 2 partial completions from v1.0.2:

- **Every check now resolves spine paths via `.harness/spine_paths.yaml`.**
  14 module-level migrations + 5 inline migrations. Adds 9 new roles
  (backend_models_api, backend_models_agent, backend_storage_gateway,
  backend_contracts, backend_learning_sidecars, backend_tests_learning,
  backend_pyproject, frontend_package_json, plus existing). Non-monorepo
  / Python-only / JS-only consumers can adopt the harness with one
  `spine_paths.yaml` override — no check forks needed.
- **5 remaining policy schemas tightened** to `additionalProperties: false`
  with explicit `required` arrays, type constraints, and pattern
  constraints (e.g. `^[A-Z]+:.+$` for `verb:path` exempt entries).
  Schema typos in policy yamls now fail fast at pre-commit.

145/145 check tests pass; harness_policy_schema clean against all
9 policy yamls.

## v1.0.2 — Hardening sweep (signed)

First **signed** release. Consumers no longer need `--no-verify-tag`.

Includes everything from v1.0.1 plus the awesome-harness audit fixes:

- **`load_harness` budget cap** (point 1). New `--max-bytes` flag (default 32 KB)
  caps total emitted bytes. Mandatory tier (root + policies) always emits;
  larger files drop with `[TRUNCATED] <path>` pointers the AI can `cat`. Also
  fixes the long-standing argparse-crash on no-target invocation (which is
  what the SessionStart hook does).
- **GPG signing infrastructure** (point 5). New `tools/setup_signing.sh` +
  `tools/sign_release.sh`. v1.0.2 is signed with key `73A7AF8F04F40EC9`
  (`ai-harness signer`). Public key + import instructions live at
  `docs/keys.md`.
- **Tier 2 cleanup** (8 correctness/quality fixes):
  - `extract_outbound_http_inventory` 1609 → 32 callsites via receiver-chain analysis
  - `extract_dependency_inventory` regex → tomllib (handles multi-line specs + extras)
  - 3 most-touched policy schemas tightened (logging, error_handling, documentation)
  - `security_policy_b` skips per-route CsrfProtect when global CSRF middleware present
  - `.harness/spine_paths.yaml` mechanism for consumer-overridable spine paths (PoC migration)
  - `harness_rule_coverage` strips ` ``` ` blocks + inline `code` before regex
  - `refresh_baselines` warns on baseline growth + atomic per-check writes

## v1.0.1 — Maintenance

Three harness-engineering hardening fixes:

- Stripped DebugDuck-specific tests from carve (218/218 self-tests now green)
- `_session_start_hook.sh` surfaces `load_harness.py` failures with
  `[HARNESS_WARN]` instead of silent degradation
- `sync_harness.py` verifies signed git tags (`--no-verify-tag` escape hatch)

`extract.sh` also strips stale `.harness/{baselines,generated}/*.json` (consumer
regenerates) but preserves the README + `_TICKETS.md` documentation.

## v1.0.0 — initial GA

Seven-sprint substrate for AI-assisted development:

- **H.0a** — schema & substrate (loader, Makefile, root CLAUDE.md, orchestrator).
- **H.0b** — stack-foundation scaffolding (Q5/Q8/Q9/Q11–Q19 configs, gitleaks
  install, mypy/tsc strict baselines).
- **H.1a** — backend basic checks (Q7–Q12 + 4 self-learning invariants).
- **H.1b** — frontend checks (Q1–Q6, Q14, Q18 + meta-validator).
- **H.1c** — cross-stack policy checks (Q13 secrets/auth/rate-limit/CSRF, Q15
  documentation, Q16 logging, Q17 error handling).
- **H.1d** — typecheck enforcement (Q19) + four harness self-tests
  (rule coverage, fixture pairing, policy schema, perf regression) +
  baseline buffer + refresh tool.
- **H.2** — 18 generators emitting deterministic JSON inventories +
  `run_harness_regen` two-phase orchestrator + Claude Code SessionStart hook +
  `init_harness` bootstrap + full contributor docs.

**By the numbers:**
- 24 deterministic checks under `.harness/checks/`.
- 18 deterministic generators under `.harness/generators/`.
- 25 H-rules (process + structural contracts).
- 19 Q-decisions (locked stack/style/security choices).
- `validate-fast` settles at ~18s wall on a representative repo (well within
  H-17's 30s budget).

**Distribution:** scaffold into a fresh repo via
`tools/init_harness.py --target <path> --owner <handle> --tech-stack <python|typescript|polyglot>`,
or pull a pinned version into an existing repo via
`tools/sync_harness.py` (reads `.harness-version`).

See `docs/plans/2026-04-26-ai-harness.md` for the full design and the
seven sprint plans (`2026-04-26-harness-sprint-h*-tasks.md`) for per-task
implementation history.
