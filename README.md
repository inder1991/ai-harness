# ai-harness

> Stop your AI from drifting.

[![Latest release](https://img.shields.io/github/v/release/inder1991/ai-harness?include_prereleases&label=release)](https://github.com/inder1991/ai-harness/releases) · MIT · signed with Ed25519 fingerprint `73A7AF8F04F40EC9` ([`docs/keys.md`](./docs/keys.md))

When you let an AI write code in a real codebase, three things go wrong: it doesn't know your conventions, it forgets between sessions, and you can't tell it once and trust it. **ai-harness** loads your project's rules into the AI's context at session start, then enforces them at pre-commit and CI. Deterministic Python checks, $0 ongoing API spend, structured findings the AI reads back to fix itself.

---

## Does this work for my stack?

Honest table — not a marketing one.

| Stack | Status | What you get on day 1 |
|-------|--------|----------------------|
| Python + React | ✓ Native | All 30 rules + AI session integration + CLI + auto-fixers |
| Python only | ✓ Native | 22 rules + AI session integration + CLI |
| TypeScript + React (no backend) | ✓ Native | 18 rules + AI session integration + CLI |
| Node + React | ✓ Native (v2.2) | 18 cross-cutting rules + 8 first-class Node checks (HTTP wrapper, DB layer, validation, testing, security routes, storage, logging, deps) |
| Node only | ✓ Native (v2.2) | 10 cross-cutting rules + 8 first-class Node checks |
| Go-only | ⚠ Partial (v2.2) | Cross-cutting rules + 3 starter checks (HTTP wrapper, DB quarantine, error handling). Add more by contributing to `.harness/checks/go-backend/` |
| Rust-only | ⚠ Partial (v2.2) | Cross-cutting rules + 3 starter checks (HTTP wrapper, DB quarantine, no-unwrap). Add more by contributing to `.harness/checks/rust-backend/` |
| Java | 🟡 Substrate-only | AI session integration + dep policy + secret scan |
| Vue / Svelte | 🟡 Substrate-only | Cross-cutting rules; framework rules deferred |

`harness init` auto-detects your stack from manifest files (pyproject.toml, package.json, go.mod, Cargo.toml) and proposes the right profile. Override with `--profile <name>` if needed.

## Try it (60 seconds)

```bash
# Clone + bootstrap
git clone https://github.com/inder1991/ai-harness /tmp/ai-harness
pip install -e /tmp/ai-harness
cd /path/to/your/project
harness init --owner @your-team
```

What you'll see:

```
✓ ai-harness v2.0.0 installed.

  Profile:        python-react
  Rules active:   30 (12 backend, 8 frontend, 10 cross-cutting)
  Baselined:      4287 existing violations (legacy debt; we won't bug you about these)
  Pre-commit:     installed at .git/hooks/pre-commit
  CI workflow:    .github/workflows/validate.yml

Next steps:
  ▸ Open Claude Code in this repo — the AI will load the harness automatically.
  ▸ Make a commit; the gate runs. New violations block; legacy ones don't.
  ▸ See what rules are active:  harness rules
  ▸ Diagnose any issues:        harness doctor
```

That's the whole onboarding. **Zero `[ERROR]` lines on first run** — pre-existing violations land in baselines, not your terminal.

## What you get

### One CLI, eight verbs

```
$ harness
Usage: harness <command> [options]

  init        Bootstrap the harness into the current repo
  check       Run the validation gate
  fix         Apply auto-fixable rules         (Sprint 2)
  rules       List rules; explain a rule
  baseline    Refresh / show / add / prune
  telemetry   Show the rolling failure log
  doctor      Diagnose installation issues
  upgrade     Pull a new harness version
  rollback    Pin to the previous version
```

Run `harness <verb> --help` for command-specific help. Exit codes documented in [`docs/EXIT_CODES.md`](./docs/EXIT_CODES.md).

### Humane check output

`harness check` groups findings by severity (P0_security → P1_correctness → P2_quality → P3_style), collapses same-rule occurrences, and shows the *why* alongside the fix:

```
🔴 P0 critical (1 finding)
  Q13.route-needs-auth — backend/src/api/users.py:42
    POST /api/users has no auth dependency.
    Why:  Mutating route without an auth dependency — #1 cause of data leaks.
    Fix:  add `user: Annotated[User, Depends(get_current_user)]` to the handler signature.
    More: harness rules explain Q13.route-needs-auth

🟡 P2 quality (3 occurrences)
  Q15.spine-docstring-required — 3 occurrences
    · backend/src/api/orders.py:15
    · backend/src/api/refunds.py:7
    · backend/src/api/exports.py:23
    Why:  Spine code is read + extended frequently; undocumented contracts get re-derived.
    Fix:  add a one-line docstring describing purpose + return contract.
    More: harness rules explain Q15.spine-docstring-required

Status: FAIL (1 of 4 are P0/P1)
```

Modes: `human` (default tty), `json` (machine), `raw` (legacy v1.x), `pre-commit` (hook contract).

### AI session integration (the core value)

When the user opens Claude Code in a harness-equipped repo:

1. The session-start hook loads ~30 KB of structured context (rules, policy YAMLs, generated inventories) into the AI's context window. **~4% of a 200k token budget; the other 96% stays free for actual conversation.**
2. The AI now knows the conventions, the existing 47 endpoints, the auth dependency catalog, the dependency allow-list — without any prompt engineering.
3. When the AI proposes a change, it tends not to violate the rules in the first place.
4. When the gate fires anyway (humans do too), the AI runs `harness check --mode=json`, reads structured findings, calls `harness rules explain <id>` for the why, and proposes a fix — with `harness check --files <file>` to verify the fix.

**No human in the loop except for approval.** That's the difference between v2.0 and "paste these errors into your AI."

## The $0-API-cost design

Every check is deterministic Python (`ast`, regex, `tomllib`). No LLM calls in the pipeline. No tokens spent. No "evals" platform that bills you per PR. The harness's only API-spend contribution is *negative* — it makes Claude Code answer in one turn instead of "let me grep around to figure out the structure first."

The rolling failure log (`.harness/.failure-log.jsonl`) gives you trend visibility ("rule X fired 47 times this week") with zero cost. `harness telemetry` reads it.

Deeper rationale: [`docs/INTERNALS.md`](./docs/INTERNALS.md).

## How it differs from a `CLAUDE.md` file

`CLAUDE.md` is one input to the harness. The harness is the system around it.

| Layer | What it does |
|-------|--------------|
| `CLAUDE.md` (your single rules file) | Tells the AI "here's how we do things." Read at session start. |
| The harness on top | Loads `CLAUDE.md` *plus* directory-scoped rules, policy YAMLs, generated inventories — and **enforces them at pre-commit + CI**. |
| Naive LLM-judge harness | Asks an LLM to grade every PR. Burns tokens. We don't. |

Six-point comparison: [`docs/INTERNALS.md`](./docs/INTERNALS.md).

## Upgrading

```bash
harness upgrade --trust-key 73A7AF8F04F40EC9
```

The substrate is published as **GPG-signed git tags**. `harness upgrade` clones at the new tag, verifies the signature against your trust-pinned fingerprint, overlays only substrate files (`baselines/`, `generated/` are preserved). On a post-upgrade gate failure, `harness upgrade --auto-rollback-on-failure` reverts atomically to the previous version recorded in `.harness/.upgrade_history.txt`.

## Releases + signing

Every release is a GPG-signed annotated tag on this repo. Verify yourself:

```bash
git -C /tmp/ai-harness verify-tag v2.0.0
```

Release notes: [`RELEASES.md`](./RELEASES.md). Maintainer release flow: `bash tools/setup_signing.sh && bash tools/sign_release.sh v<X.Y.Z>`.

## Coverage and non-goals

What the harness covers (`HARNESS_CARD.yaml.coverage.covered`):

- Rule discipline (30 enforcement + 5 self-test deterministic AST/regex checks)
- Policy schema validation (12 yamls, all `additionalProperties: false`)
- Auto-derived inventories (20 generators with deterministic regen)
- Session-start AI context loading with byte budget
- Tag-signature verification on `harness upgrade`
- Consumer-overridable spine paths (any repo layout)
- Grandfathered baselines for legacy code, with structured `_REASONS.md`
- Rolling failure log + `harness telemetry` (zero API cost)

What it deliberately doesn't:

- Evals + observability beyond rule firings (no API cost — explicit choice)
- Browser/runtime validation in the AI fix loop
- Prompt-injection mitigation
- Sandbox / write-path allowlist
- Phone-home telemetry without explicit consent (Sprint 6 / S6.1)
- Long-running session checkpoints + handoff artifacts
- Spec-driven development primitives

Each non-goal is somebody else's product.

## Contributing

Three small templates:

```
# Add a check
1. Write .harness/checks/<your_check>.py using _common.emit().
2. Add tests/harness/fixtures/<check>/{compliant,violation}/.
3. Add an entry to .harness/severity_map.yaml.
4. Add tests/harness/checks/test_<check>.py via _helpers.assert_check_fires/silent.

# Add a generator
1. Write .harness/generators/extract_<thing>.py emitting JSON.
2. Add a JSON Schema at .harness/schemas/<thing>.schema.json.
3. Declare any prereqs in tools/run_harness_regen.py.DEPENDENCIES.

# Add a policy YAML
1. Write .harness/<topic>_policy.yaml.
2. Write a JSON Schema at .harness/schemas/<topic>_policy.schema.json with additionalProperties:false.
3. Consume it from your check via yaml.safe_load(...).
```

Coverage gate ≥65% line + branch (95% target by Sprint 3). No silent error handling. Permanent regression test for every closed bug. Cross-platform CI (ubuntu + macOS × Py 3.11/3.12/3.13).

## Pointers

- Internals deep-dive: [`docs/INTERNALS.md`](./docs/INTERNALS.md)
- Production roadmap: [`docs/plans/2026-04-29-harness-v2.0-production-roadmap.md`](./docs/plans/2026-04-29-harness-v2.0-production-roadmap.md)
- Exit codes: [`docs/EXIT_CODES.md`](./docs/EXIT_CODES.md)
- Supported platforms: [`docs/SUPPORTED_PLATFORMS.md`](./docs/SUPPORTED_PLATFORMS.md)
- Audit history: `docs/plans/2026-04-27-harness-sdet-audit.md` and `docs/plans/2026-04-28-harness-rule-semantics-audit.md`
- HarnessCard: [`.harness/HARNESS_CARD.yaml`](./.harness/HARNESS_CARD.yaml)

## License

MIT.
