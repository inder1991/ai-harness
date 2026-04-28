---
owner: '@inder'
---

# Exit code reference

Every shipped script + CLI verb in ai-harness uses a documented exit code. CI scripts depend on these; consumers depend on them; the orchestrator depends on them. Adding an undocumented exit code is a rule violation (Q24 self-test will enforce in Sprint 0+).

## The numbering scheme

| Code | Meaning | Reserved by |
|------|---------|-------------|
| `0`  | Success — operation completed and the system is in the desired state | All commands |
| `1`  | Findings present (`harness check`); rule violation; gate failure | Check / orchestrator |
| `2`  | Bad input — missing arg, invalid flag, target missing, prerequisite tool absent | All commands |
| `3`  | Signature verification failed — tag unsigned, untrusted key, or fingerprint mismatch | `sync_harness`, `sign_release` |
| `4`  | Smoke test failed — the carved repo failed its self-tests (B17) | `extract.sh` |
| `5`  | Upgrade migration failed — `harness upgrade` could not move the consumer to the new version. Reserved for v2.x. | `harness upgrade` |
| `6`  | Doctor diagnosed an unrecoverable issue — install is broken in a way the user must repair manually. Reserved for v2.x. | `harness doctor` |
| `7`  | Rollback required — `harness upgrade --auto-rollback-on-failure` triggered the rollback. Reserved for v2.x. | `harness upgrade` |
| `124` | Subprocess timeout — matches the GNU `timeout(1)` convention. Used when a wrapped subprocess exceeds its wall-clock budget. | every subprocess wrapper |
| `130` | Interrupted by user (SIGINT / Ctrl-C). Standard POSIX convention. | All commands |

## Usage rules for contributors

1. **Don't invent new numbers.** If your story needs a new exit code, add a row to this table FIRST and reference it from the story's acceptance criteria.
2. **2 means user-fixable input.** A missing flag, a missing file, a missing PATH dependency. Stderr must include a one-line remediation.
3. **3+ means meaningful failure modes.** Each code in 3+ is a distinct category that automation can branch on. Don't reuse 2 for "everything that's not success or findings."
4. **124 is for timeouts only.** If you wrap a subprocess that may hang, use `subprocess.run(..., timeout=N)` and re-raise as exit 124 with `raise SystemExit(124)` or equivalent. Document the timeout in the wrapper.
5. **130 is OS-set.** You don't return 130 directly; the OS does when SIGINT terminates the process. Just make sure your cleanup is signal-safe.

## Per-command authoritative table

This is the source of truth for what each command emits. The corresponding `--help` and the `Q24.exit-code-undocumented` self-test (Sprint 0+) cross-check it.

### `harness init`

| Code | When |
|------|------|
| 0 | Install completed, profile written, baselines snapshotted, summary printed |
| 2 | Missing `--owner`; `--target` not a directory; `.harness/` exists and `--force` not given; pre-commit hook collision (init succeeds but exits 0 with warning); read-only filesystem; not at git root |

### `harness check`

| Code | Mode | When |
|------|------|------|
| 0 | `human` | No findings, OR only P2/P3 findings |
| 1 | `human` | Any P0/P1 finding present |
| 0 | `json` | Always (consumer reads the JSON; exit code is unused by the orchestrator) |
| 1 | `pre-commit` / `raw` | Any finding (preserves v1.x behavior) |
| 2 | any | `--target` missing; check subprocess crashed unrecoverably |
| 124 | any | A check exceeded `CHECK_TIMEOUT_S` (180 s) |

### `harness upgrade` (Sprint 1+)

| Code | When |
|------|------|
| 0 | Pin updated, sync succeeded, post-upgrade `harness check` clean |
| 2 | Bad `--ref`, missing `.harness-version`, no signing key |
| 3 | Tag signature verification failed |
| 5 | Migration script (`tools/migrations/...`) returned non-zero |
| 7 | `--auto-rollback-on-failure` triggered; consumer is back on the previous version |

### `harness rollback` (Sprint 1+)

| Code | When |
|------|------|
| 0 | Rollback complete |
| 2 | Bad `--to <version>`; no `.harness/.upgrade_history.txt` |

### `harness doctor` (Sprint 1+)

| Code | When |
|------|------|
| 0 | Healthy install — every check ✓ |
| 6 | At least one ✗ (unrecoverable); message names the issue + remediation |

### `harness baseline add` (Sprint 1+)

| Code | When |
|------|------|
| 0 | Entry added, `_REASONS.md` updated |
| 2 | Missing `--reason`; rule unknown; file:line out of bounds |

### `harness fix` (Sprint 2+)

| Code | When |
|------|------|
| 0 | Diff shown (no `--apply`); OR fix applied successfully + post-fix re-check clean |
| 1 | Post-fix re-check found cascade findings the user must address |
| 2 | Bad `--rule`; rule has no auto-fixer; file changed between diff and apply |

### `tools/sync_harness.py`

| Code | When |
|------|------|
| 0 | Overlay applied |
| 2 | Missing `.harness-version`; `git` not on PATH; clone failed |
| 3 | Tag verification failed (unsigned, untrusted, fingerprint mismatch with `--trust-key`) |
| 124 | Clone or verify-tag timed out |

### `tools/init_harness.py`

| Code | When |
|------|------|
| 0 | Bootstrap complete |
| 2 | Missing `--target`/`--owner`; templates dir missing; source `.harness/` missing; `--target` resolves to source repo (B3) |

### `tools/run_validate.py`

| Code | When |
|------|------|
| 0 | All checks PASS |
| 1 | At least one check returned non-zero (FAIL) |
| 124 | A check exceeded its 180 s wall budget; a synthetic `harness.timeout` finding is emitted |

### `tools/refresh_baselines.py`

| Code | When |
|------|------|
| 0 | Refresh complete; no growth or growth is justified |
| 1 | Refresh complete BUT a baseline grew without an ADR |

### `tools/sign_release.sh`

| Code | When |
|------|------|
| 0 | Tag signed and pushed; release cut |
| 2 | Missing `<version>`; `user.signingkey` not set; `git-filter-repo` not on PATH |
| 3 | Tag signing failed (GPG key issue) |

### `tools/setup_signing.sh`

| Code | When |
|------|------|
| 0 | Key generated/imported; git config updated |
| 2 | Unknown flag; `--local` requires git repo and we're not in one; gnupg installation refused |
| 3 | Existing `user.signingkey` or `tag.gpgsign` would be overwritten without `--force` |

### `tools/extraction/extract.sh`

| Code | When |
|------|------|
| 0 | Carve complete; smoke-test passed |
| 2 | `git-filter-repo` not installed; manifest missing |
| 4 | Smoke-test (B17) failed against `/tmp/ai-harness` |

### `tools/publish_harness_backfill.sh`

| Code | When |
|------|------|
| 0 | All four backfill tags pushed |
| 2 | Unknown flag; signing key not set; required tool not on PATH |
| 3 | Failed to locate carved commit for at least one version |
| 4 | `extract.sh` smoke-test (B17) failed |

## Self-enforcement (Sprint 0+)

A new check `Q24.exit-code-undocumented` (planned for Sprint 1) parses every `tools/*.py` and `tools/*.sh`, extracts every `sys.exit(<N>)` and `exit <N>` literal, and asserts each is listed in the per-command table above. PRs that introduce new exit codes without updating this file fail the gate.

## Recovery procedures by exit code

For users hitting these codes:

- **2 → fix the input.** Read stderr; the message names what's wrong.
- **3 → signature problem.** Run `harness doctor` to find which key is missing, then `gpg --recv-keys <FPR>`.
- **4 → broken extraction.** Inspect `/tmp/ai-harness` manually; usually a manifest skew. File a bug.
- **5 → migration failed.** Read `.harness/.upgrade_history.txt` for the prior version; consider `harness rollback`.
- **6 → broken install.** Run `harness doctor --fix`; if that doesn't help, file a bug with the doctor output.
- **7 → automatic rollback succeeded.** Investigate why upgrade failed before re-attempting.
- **124 → timeout.** Increase the timeout (CLI flag where supported), profile the slow operation, or report via `harness telemetry --slow-checks`.
- **130 → interrupted.** Resume with the same command; most operations are idempotent.

## Revision history

- **2026-04-29** (this file) — initial publication; covers v1.x existing codes + reserves v2.x codes 5/6/7.
