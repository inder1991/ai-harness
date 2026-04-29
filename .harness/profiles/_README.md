---
owner: '@inder'
---

# Composite profile YAMLs (Sprint 4 / S4.1)

A profile YAML in this directory is a **composite** that declares which
packs to enable via `extends:`. Consumers' `.harness/profile.yaml`
typically just sets `profile: <name>` and `extends: [<name>]` — the
composite expands the rest.

Packs (referenced by `extends`):

| Pack | Lives at | What it ships |
|------|----------|--------------|
| `cross-cutting` | `.harness/checks/*.py` (today, flat layout) | Stack-agnostic rules: dependency_policy, security_policy_a/b, accessibility, todo_in_prod, owners_present, claude_md_size_cap |
| `python-backend` | `.harness/checks/*.py` (today, flat layout) | Q7-Q12, Q15-Q18 backend rules |
| `react-frontend` | `.harness/checks/*.py` (today, flat layout) | Q1-Q6 frontend rules |
| `node-backend` | `.harness/checks/node-backend/*.py` | Sprint 4 / S4.2 |
| `go-backend` | `.harness/checks/go-backend/*.py` | Sprint 4 / S4.4 |
| `rust-backend` | `.harness/checks/rust-backend/*.py` | Sprint 4 / S4.4 |
| `self-tests` | `.harness/checks/*.py` self-test files | output_format, fixture_pairing, rule_coverage, policy_schema, harness_card_version, rule_count_conformance |

Sprint 4 ships the composition mechanism + the node/go/rust subdirs.
The Python+React substrate stays flat for now; Sprint 4 has a
documented migration script (`tools/migrations/v2_pack_split.py`) that
moves files into pack subdirectories — opt-in for consumers who want
the cleaner layout.
