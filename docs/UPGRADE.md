# Upgrading ai-harness

This document covers how to move an existing ai-harness install across
release-line boundaries. Within a release line (e.g., v1.2.x → v1.3.x),
`harness upgrade` is a safe, idempotent operation. Across major lines
(v1.x → v2.x), there's a one-time migration that this guide walks through.

## TL;DR

- **Within the same major line:** `harness upgrade`
- **From v1.x to v2.x:** `harness upgrade --from v1.x --to v2.x --migrate-only`
  (then run plain `harness upgrade` to fetch the new substrate).
- **Diagnose pending migration:** `harness doctor --check-upgrade`
- **Roll back on failure:** the migration snapshots `.harness/` to
  `.harness.pre-upgrade/` automatically. On any step failure the
  snapshot is restored and the consumer is left exactly where it
  started.

## Within a release line (v1.0 → v1.3, v2.0 → v2.4, etc.)

```bash
harness upgrade
# or with auto-rollback on post-upgrade gate failure:
harness upgrade --auto-rollback-on-failure
```

This:

1. Reads `.harness-version`.
2. Calls `tools/sync_harness.py` (the v1.x sync mechanism) to fetch the
   new tag, verify GPG signature (when `--trust-key` is set), and copy
   the new substrate into the consumer.
3. Records the upgrade in `.harness/.upgrade_history.txt`.
4. (With `--auto-rollback-on-failure`) runs `harness check`; on
   non-zero exit, automatically reverts to the previous version.

## v1.x → v2.x migration

v2.0.0 introduces:

- `.harness/profiles/` — composite YAMLs that declare which packs to
  enable (Sprint 4 / S4.1).
- `extends:` field in `.harness/profile.yaml` referencing one of the
  composites (Sprint 4 / S4.3).
- A bumped `HARNESS_CARD.yaml.version` matching `.harness-version`
  (Q21 — the two must agree).

The migration brings a v1.x consumer up to that layout. It does **not**:

- Move flat `.harness/checks/*.py` into pack subdirectories. The flat
  layout still works in v2.x — `active_check_files` falls back when a
  pack name has no subdir. Consumers who want the cleaner layout can
  run `tools/migrations/v2_pack_split.py` later (opt-in).
- Modify any check file. Customizations that consumers wrote into
  `.harness/checks/*.py` are preserved.
- Touch baseline contents — only the `file:` field of pre-v1.1.0
  absolute-path baselines is rekeyed (delegated to
  `refresh_baselines.py --migrate-paths`).

### Run the migration

```bash
# Inspect what would happen (read-only):
harness doctor --check-upgrade

# Run the migration (snapshots before applying):
harness upgrade --from v1.x --to v2.x --migrate-only

# Then sync the new substrate the usual way:
harness upgrade
```

### What the migration does, step by step

| Step                  | Action |
|-----------------------|--------|
| `copy-profiles-dir`   | Copy `.harness/profiles/` from the source repo into the consumer so `extends:` references resolve locally. |
| `add-extends`         | If `.harness/profiles/<your-profile>.yaml` exists in the source repo, write `extends: [<your-profile>]` to your `profile.yaml`. No-op if no matching composite ships. |
| `bump-card`           | Bump `HARNESS_CARD.yaml.version` to match `.harness-version` (Q21). |
| `migrate-baselines`   | Re-key any pre-v1.1.0 absolute-path baseline entries to repo-relative form (delegated to `refresh_baselines.py --migrate-paths`). Skipped if no absolute paths are present. |

### Snapshot + rollback

Before any step runs, the migrator copies `.harness/` to
`.harness.pre-upgrade/`. If any step throws, the snapshot is restored
and the consumer is back on v1.x exactly. Snapshots are kept until the
next migration run replaces them.

### Migration matrix

| Starting line | Migration steps | Tested |
|---------------|-----------------|--------|
| v1.0.x        | All four steps (`copy-profiles-dir`, `add-extends`, `bump-card`, `migrate-baselines`) | ✓ Fixture: `tests/harness/fixtures/migrations/v1.0.4/` |
| v1.1.x        | All four steps (baselines were rekeyed in-line in v1.1.0; absolute-path baselines are rare here) | Covered transitively |
| v1.2.x        | `copy-profiles-dir`, `add-extends`, `bump-card` | ✓ Fixture: `tests/harness/fixtures/migrations/v1.2.1/` |
| v1.3.x        | `copy-profiles-dir`, `add-extends` (card already at 1.3.x; bump-card no-op when versions match) | ✓ Fixture: `tests/harness/fixtures/migrations/v1.3.1/` |

### Troubleshooting

- **"target is not a v1.x install"**: There's no `.harness/` directory
  at the target path. Run `harness init --owner @you` first; this is a
  fresh install, not a migration.
- **"profile yaml malformed"**: The migration delegates parsing to
  PyYAML and rejects anything that doesn't load as a mapping. Open
  `.harness/profile.yaml` and ensure it has a top-level dict.
- **Migration finishes but `harness check` reports new errors**: This
  happens when v2.x adds a check that didn't exist in v1.x and the
  baseline doesn't yet cover the legacy violations. Run
  `make harness-baseline-refresh` to re-snapshot, then commit the new
  baseline.
- **Snapshot wasn't restored**: The migrator catches every per-step
  exception and restores. If that didn't happen (e.g., the process was
  killed mid-migration), `.harness.pre-upgrade/` is your safety net —
  rename it back to `.harness/` to recover.

## Rollback (for any release line)

```bash
harness rollback                  # roll back to the previous pinned ver
harness rollback --to v2.0.0      # roll back to a specific version
```

Rollback re-pins `.harness-version` and re-runs `sync_harness.py` so
the substrate matches.

## Future migrations

Subsequent major-line bumps will follow the same pattern: a
`tools/migrations/v<from>_to_v<to>.py` module with the same
`detect_state` / `plan` / `run` surface, wired into `harness upgrade
--from / --to`.
