# Releases

## v1.0.1 — Maintenance

Two harness-engineering hardening fixes from awesome-harness audit:

- **Stripped DebugDuck-specific tests from the carve.** v1.0.0 shipped 13
  files (every file under `tests/harness/configs/` plus
  `test_directory_claude_mds.py`) that hardcoded DebugDuck paths and
  failed in any other consumer. v1.0.1 manifest excludes them; `pytest
  tests/harness/` now passes 218/218 out of the box.
- **Surfaced loader failures.** `tools/_session_start_hook.sh` no
  longer swallows `tools/load_harness.py` crashes with `|| true`. On
  loader failure it emits a multi-line `[HARNESS_WARN]` block to stdout
  (which Claude Code consumes) including exit code, stderr preview, and
  the manual-rerun command. Hook itself still exits 0 so a loader bug
  never aborts session start.
- **Tag-signature gate in `sync_harness.py`.** Before overlaying, the
  script verifies the pinned ref is an annotated, GPG-signed tag.
  Default ON; `--no-verify-tag` is the loud opt-out for environments
  without GPG configured. Closes the supply-chain attack vector where
  an attacker who can write to the upstream repo lands malicious code
  in a tag.

Also: `extract.sh` now drops stale `.harness/{baselines,generated}/*.json`
files (consumer regenerates) but preserves the README + `_TICKETS.md`
documentation.

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
- `validate-fast` settles at ~18s wall on a representative repo.

**Distribution:** scaffold into a fresh repo via
`tools/init_harness.py --target <path> --owner <handle> --tech-stack <python|typescript|polyglot>`,
or pull a pinned version into an existing repo via
`tools/sync_harness.py` (reads `.harness-version`).

See `docs/plans/2026-04-26-ai-harness.md` for the full design.
