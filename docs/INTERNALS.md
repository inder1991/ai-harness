# ai-harness

> Repo-level scaffolding that makes AI-assisted development productive in any codebase. Two consumers, one contract — humans in IDE + autonomous CI agents.

[Latest release · v1.3.1](https://github.com/inder1991/ai-harness/releases/latest) · MIT · signed with Ed25519 fingerprint `73A7AF8F04F40EC9` (see `docs/keys.md`)

---

## TL;DR

`ai-harness` is a directory of policy files (`.harness/`), a few orchestration tools (`tools/`), and 35 deterministic checks (30 enforcement + 5 self-tests) that ride alongside your code. At AI session start, a loader bundles the relevant slice into the AI's context window so the AI knows your project's rules and what already exists. At pre-commit and at CI, an orchestrator runs every check against the changes; violations block the commit or the PR.

The substrate is published from this repo as **GPG-signed git tags**. Each consumer pins a version (`.harness-version`) and pulls updates with `tools/sync_harness.py --trust-key 73A7AF8F04F40EC9`.

**Cost:** $0 ongoing API spend. Every check is deterministic Python (no LLM calls). The harness's only contribution to your AI bill is *negative* — it makes Claude Code answer in one turn instead of "let me grep around to figure out the structure first."

**Footprint:** ~30 KB hard-capped at session start (~4% of a 200k context window). Other 96% stays available for actual conversation.

---

## Why does this exist?

When you let an AI write code in a real codebase, three things go wrong:

1. **The AI doesn't know your conventions.** It writes `requests.get()` even though you standardized on `httpx.AsyncClient` six months ago. It writes a SQL query inline even though everything else routes through `StorageGateway`. It uses `localStorage` when your team banned it after a security review.

2. **The AI forgets between sessions.** Each new conversation starts blank. The rule you explained yesterday is gone today.

3. **You can't tell the AI "stop doing that" once and trust it.** Even within a session it drifts when the user asks for something quickly. There's no enforcement — only a promise.

`ai-harness` fixes all three:

- **Knowledge** — every session starts with the rules + the inventory of what exists, loaded into context automatically.
- **Persistence** — the rules live in version-controlled files, not chat history. They survive every session reset.
- **Enforcement** — 30 enforcement checks (plus 5 that validate the harness itself) gate every commit and every PR. The AI doesn't *promise* to follow the rules; the gate doesn't let drift through.

---

## How it works (end to end)

A concrete walkthrough of one developer-with-AI session in a harness-equipped repo:

### Step 1 — open the IDE, AI session starts

You open Claude Code. The session-start hook (`tools/_session_start_hook.sh`) runs `tools/load_harness.py`. The loader:

- Reads root `CLAUDE.md`.
- Walks **upward** from whatever file you opened, collecting every per-directory `CLAUDE.md` along the way.
- Loads every `.harness/*.yaml` policy file.
- Loads every cross-cutting `.harness/*.md` rule whose `applies_to` glob matches your target file.
- Loads every `.harness/generated/*.json` inventory (the auto-derived facts).

It packs it all into a structured text block, capped at **32 KB by default** (~8k tokens, ~4% of a 200k window). When the budget is tight, low-priority files get replaced with `[TRUNCATED] backend/src/api/routes.py (4231 bytes) — read with: cat backend/src/api/routes.py` pointers, so the AI knows what exists and where to fetch it on demand.

The AI walks in already knowing:

- That this is a FastAPI + React + Tailwind project.
- That `backend/src/api/` holds routes, each requires auth + rate limit + CSRF.
- That every API request model needs Pydantic `extra="forbid"`.
- That the canonical HTTP wrapper is `backend/src/utils/http.py`.
- That all 47 existing endpoints are listed in `api_endpoints.json`.

### Step 2 — you ask for a change

> "Add an endpoint that deletes a user."

The AI checks the loaded inventories:

- Sees `users_router` already exists, scoped to `/api/v4/users/...`.
- Sees the auth dependency `require_admin` is in the policy.
- Sees the convention "every mutating route has rate limit + CSRF."

It writes the code in the matching shape:

```python
@users_router.delete("/{user_id}")
@limiter.limit("3/minute")
async def delete_user(
    request: Request,
    user_id: int,
    user: Annotated[User, Depends(require_admin)],
    csrf_protect: CsrfProtect = Depends(),
) -> dict:
    await gateway.delete_user(user_id)
    return {"ok": True}
```

### Step 3 — pre-commit hook fires

You save and `git commit`. The pre-commit hook (installed by `tools/install_pre_commit.sh`) runs `make validate-fast`. The orchestrator (`tools/run_validate.py`) spawns each of 30 checks as a subprocess with a 180 s wall budget. Each check parses the changed files and emits findings in the **H-16 emit format**:

```
[ERROR] file=backend/src/api/users.py:42 rule=Q13.route-needs-rate-limit message="POST /api/users missing @limiter.limit" suggestion="add `@limiter.limit(\"<n>/minute\")` or list in security_policy.yaml.rate_limit_exempt"
```

If any check exits non-zero, the orchestrator prints the findings and the commit is blocked. The hook is bypassable with `git commit -n` for the rare case where you must commit through (CI is the safety net).

### Step 4 — fix and re-commit

The AI sees the structured error in your conversation, knows exactly which rule fired, and applies the fix. You re-commit. The hook passes. The commit lands.

### Step 5 — CI gate

You push to a PR. GitHub Actions runs `make validate-full` — same 30 checks, plus typecheck (`mypy` + `tsc`), plus the actual test suites. A second guarantee that the harness rules hold.

If anything fires in CI that didn't fire pre-commit (e.g. you bypassed the hook), the PR fails. The reviewer doesn't have to manually verify "did this PR follow our async conventions / our route protection rules / our dep allow-list" — the gate already enforced it.

### Step 6 — telemetry accrues silently

Every `[ERROR]` the orchestrator processed gets appended to `.harness/.failure-log.jsonl` with timestamp + rule ID + commit SHA + host + session UUID. The log is gitignored (per-machine), capped at 10 MB rotation. Over time it answers questions like:

- Which rule fired most this week? (Where the AI keeps tripping.)
- Did rule X stop firing after our refactor? (Did our change actually work?)
- Are new violations clustered in `backend/src/api/`? (Which surface needs more guardrails.)

That's a regression dashboard with **zero API spend**. Not as good as real evals, but free + always running.

---

## What's inside

### `.harness/`

```
.harness/
├── checks/                # 35 deterministic Python checks (30 enforcement + 5 self-test)
├── generators/            # 20 deterministic generators
├── generated/             # auto-built JSON output (gitignored)
├── baselines/             # per-rule grandfather lists for legacy code
├── schemas/               # JSON schemas for every policy YAML
├── HARNESS_CARD.yaml      # at-a-glance "what does this harness cover?"
├── *.yaml                 # 9 policy files
└── *.md                   # cross-cutting rules
```

#### `.harness/checks/` — the rule enforcers

35 small Python scripts (30 enforcement, 5 self-test). Each reads source code (with `ast` and/or regex) and emits findings in the H-16 format. Examples:

| Check | Rules | What it catches |
|-------|-------|-----------------|
| `security_policy_a.py` | Q13 | `eval()` / `exec()`, multi-line `shell=True`, secrets in log messages, TLS disabled, unbounded `httpx` timeouts |
| `security_policy_b.py` | Q13 | Mutating FastAPI route missing auth / rate-limit / CSRF; modern `Annotated[T, Depends()]` style supported |
| `backend_async_correctness.py` | Q7 | `import requests` (banned outside the wrapper); `time.sleep` inside `async def`; sync `httpx.Client()` |
| `backend_db_layer.py` | Q8 | SQL outside `StorageGateway`; raw SQL string literals without `# RAW-SQL-JUSTIFIED:` on the same/preceding line |
| `dependency_policy.py` | Q11 | npm/pip dep not in allow-list; uses `sys.stdlib_module_names` for the runtime stdlib |
| `frontend_style_system.py` | Q1 | Ad-hoc Tailwind classes, hex literals, custom shadows |
| `accessibility_policy.py` | Q14 | `<img>` without `alt`; `<button>` without accessible name |
| `logging_policy.py` | Q16 | f-string in log call; bare `except:` swallowing errors |
| `error_handling_policy.py` | Q17 | `except: pass`; `raise NewError(...)` without `from exc` |
| `documentation_policy.py` | Q15 | Public function/class missing docstring; ADR required on substrate change |

Plus 5 **self-test checks** that validate the harness *itself* using the same machinery it offers consumers:

| Self-test check | Rule | What it enforces about the harness |
|-----------------|------|------------------------------------|
| `output_format_conformance.py` | H-16 | Every check's stdout matches the canonical `[SEVERITY] file=…:LINE rule=… message="…" suggestion="…"` shape |
| `harness_fixture_pairing.py` | H-24 | Every check has paired `compliant/` + `violation/` fixtures under `tests/harness/fixtures/<check>/` |
| `harness_rule_coverage.py` | H-21 | Every rule ID referenced in plans/docs has a check (or is in `rule_coverage_exemptions.yaml` with a `reason:`) |
| `harness_policy_schema.py` | — | Every `.harness/*.yaml` validates against its JSON Schema in `.harness/schemas/` |
| `harness_card_version.py` | Q21 | `HARNESS_CARD.yaml.version` matches `.harness-version` (stripped of leading `v`) |
| `rule_count_conformance.py` | Q22 | Each check's docstring "N rules" claim matches the enumerated rule IDs |

Every check follows the same template, so the orchestrator parses them all the same way. Each rule ID has a paired fixture under `tests/harness/fixtures/<check>/{compliant,violation}/` — `harness_fixture_pairing.py` enforces this.

#### `.harness/generators/` — the inventory builders

20 scripts that scan your codebase and emit deterministic JSON files into `.harness/generated/`. **They use `ast` and `tomllib` and regex — no LLM calls.** Examples:

| Generator | Output | Why the AI cares |
|-----------|--------|------------------|
| `extract_api_endpoints.py` | `api_endpoints.json` | "Does this route already exist?" |
| `extract_db_models.py` | `db_models.json` | "What does the User table look like?" |
| `extract_ui_primitives.py` | `ui_primitives.json` | "Do we have a Button component?" |
| `extract_outbound_http_inventory.py` | `outbound_http.json` | "Where do we already call this API?" |
| `extract_dependency_inventory.py` | `dependency_inventory.json` | "Is httpx pinned? Which version?" |
| `extract_test_coverage_targets.py` | `test_coverage_targets.json` | "Which functions need a hypothesis test?" |

`make harness` runs all generators in dependency order via `tools/run_harness_regen.py`. The output is byte-deterministic — re-run on the same code produces identical bytes. That property is what lets `harness_policy_schema.py` validate the JSONs against their schemas as a self-test.

#### `.harness/baselines/` — grandfather lists

When the harness is first installed, you almost certainly have thousands of pre-existing violations. Forcing every developer to fix all of them before merging would block the team for months.

Each check writes a baseline at install time: "these specific (file, line, rule-id) tuples already existed; suppress them." New violations fire; old ones don't. Each baseline can only **shrink** without an ADR — `Q19.baseline-grew-without-adr` catches silent widening.

Baselines store **repo-relative POSIX paths** (since v1.1.0) so the same baseline file works across CI runners, dev machines, and OSes.

#### `.harness/*.yaml` — policy files

Consumer-editable knobs. Every check reads its policy file at startup. Every YAML is JSON-Schema-validated by `harness_policy_schema.py` (typos fail at pre-commit, not at runtime).

| YAML | Controls |
|------|----------|
| `security_policy.yaml` | `auth_dependency_names`, `auth_decorator_names`, `csrf_dependency_names`, `router_var_names`, `rate_limit_exempt`, `csrf_exempt` |
| `logging_policy.yaml` | `logger_attr_names`, `secret_log_patterns`, `spine_paths` |
| `error_handling_policy.yaml` | `http_exception_names`, `generic_exception_names` |
| `documentation_policy.yaml` | `spine_python_paths`, `frontend_jsdoc_paths`, `adr_required_on_change` |
| `dependencies.yaml` | `python.allowed`, `python.allowed_on_spine`, `npm.runtime_allowed`, `npm.dev_allowed`, `global_blacklist` |
| `performance_budgets.yaml` | `agent_budgets.default`, `database.single_query_max_ms`, `frontend_bundle.*` |

#### `.harness/spine_paths.yaml` — the consumer override layer

Hardcoded paths are the enemy of reusability. Instead of `backend/src/api/`, every check resolves its scan roots through `spine_paths("backend_api", ("backend/src/api",))`. The fallback is the historical default; the YAML lets a non-monorepo consumer point the same role at `services/web/handlers/`. This is what makes the harness portable across very different repo shapes.

#### `.harness/HARNESS_CARD.yaml` — the manifest

A single file declaring "I am ai-harness vX.Y.Z, I cover these things, I deliberately don't cover these other things, my signing key is this fingerprint." Consumers can read it before adopting the harness to know what they're getting.

`Q21.harness-card-version-mismatch` enforces parity between the card's `version` field and the consumer's `.harness-version` pin (stripped of leading `v`). Bump both atomically.

### `tools/`

```
tools/
├── load_harness.py              # session-start context loader
├── run_validate.py              # the orchestrator
├── run_harness_regen.py         # `make harness` driver
├── refresh_baselines.py         # re-snapshot baselines (rare; needs ADR)
├── sync_harness.py              # pull a new harness version
├── init_harness.py              # bootstrap into a fresh project
├── setup_signing.sh             # one-time GPG signing key
├── sign_release.sh              # extract + sign + push a new version
├── extraction/                  # one-shot carve from monorepo to standalone repo
└── _common.py                   # shared helpers (ImportTracker, emit, ...)
```

The two daily-driver scripts:

#### `tools/load_harness.py` — what runs at session start

Two modes:

- `--target <path>` — per-file mode. Walks up from `<path>`, collects directory rules, matches `applies_to` globs.
- (no flag) — global mode used by the SessionStart hook. Includes every cross-cutting `.md` and every generated JSON regardless of target.

Always emits the **mandatory tier** first (root `CLAUDE.md` + every policy YAML, ignoring the byte budget — this stuff is small and always relevant). Then the **should tier** (cross-cutting + directory rules — emit if it fits). Then the **nice tier** (generated JSON, smallest first — this is where truncation happens).

`--max-bytes 0` disables the cap (CI agents with huge context). The default 32 KB is sized for interactive Claude Code sessions where you want to leave 96% of the window free for actual conversation.

#### `tools/run_validate.py` — the orchestrator

Two modes:

- `make validate-fast` (< 30 s) — pre-commit gate. Runs 24 of 30 checks. Five FULL_ONLY checks (typecheck, output-format, *_testing, async-correctness, db-layer) are deferred to keep the inner loop tight. Bypassable with `git commit -n`.
- `make validate-full` (a few minutes) — CI gate. Runs everything: lint + typecheck + 30 checks + pytest + vitest. Not bypassable.

For each check, the orchestrator:

1. Spawns it as a subprocess with `timeout=180`.
2. Captures stdout, parses every `[ERROR] file=… rule=…` line via the shared `_common.ERROR_LINE_PATTERN` regex.
3. Forwards the output to the user.
4. Appends each finding to `.harness/.failure-log.jsonl` (under `fcntl.LOCK_EX` so concurrent runs don't interleave; rotation happens under the same lock).

If a check exceeds its 180 s wall budget, the orchestrator emits a synthetic `[ERROR] file=<check> rule=harness.timeout` finding and returns 1.

---

## The $0-API-cost design

The harness is deliberately built to spend **$0 on API calls**. Five mechanisms:

### 1. Every check is deterministic Python, not an LLM call

A check reads source with Python's built-in `ast` parser or regex and emits findings. Zero tokens.

A naive LLM-judge harness asks "is this code secure?" on every commit. At ~3000 tokens × 200 files × 50 commits/day × 30 days ≈ **9M tokens/month**. Real money.

`ai-harness` does the same job with `security_policy_a.py`. AST parse, regex match, exit. **0 tokens.** The savings are biggest in CI (50+ runs/day per repo).

### 2. Generators replace "ask the AI to summarize the code"

A naive harness asks the AI: "What endpoints does this API expose? What components live in the frontend? What deps are pinned?" That's tokens × every-question × every-session.

`ai-harness` instead has 20 deterministic generators that produce the same answers as JSON files. They run **once on `make harness`**, not per-question. The AI **reads** them — never asks for them.

### 3. The failure log is "evals for free"

Real evals burn tokens (replay 100 prompts, see if the model answers correctly). `ai-harness` sidesteps with the rolling failure log: every `[ERROR]` gets appended with timestamp + rule + commit. After a week you have a regression dashboard. No API spend.

### 4. Defer to existing free CLI tools

Some harnesses re-implement secret detection or type-checking with prompts. `ai-harness` defers to:

- `gitleaks` for secrets
- `mypy` for Python types
- `tsc` for TypeScript types
- `ruff` for Python lint

Each tool has decades of optimization. Reinventing them with an LLM would be slower AND more expensive AND less accurate. The harness is a thin wrapper that aggregates their output into the H-16 format.

### 5. No "agent that fixes the code"

Some AI harnesses run an autonomous fix-loop agent — make a fix attempt, validate, retry. Each attempt is more tokens. `ai-harness` intentionally **doesn't do this**. It produces structured findings; a human (with their AI in the IDE) reads them and fixes them in the existing chat session — no separate API call.

### Net result

The harness's only ongoing API cost is whatever happens **inside the developer's existing Claude Code session**, which they're already paying for. The harness's contribution to that cost is **negative**, because the structured context lets the AI answer in one turn instead of "let me grep around to figure out the structure first" (which would be 3–5 turns of tool calls).

That's why `HARNESS_CARD.yaml.coverage.not_covered` lists "evals + observability beyond rule firings (deliberate — no API cost)" as a non-goal. It's an explicit choice.

---

## Context-window discipline

The AI's context window is finite (200k for most models). Naive context loading dumps everything into it and starves you for actual conversation. `ai-harness` is engineered around that constraint.

### 1. Hard byte cap on session-start context

`load_harness.py` enforces a **default 32 KB cap (~8k tokens)** on the bundle it sends. That's ~4% of a 200k window. The other 96% stays available for code + conversation.

Override with `--max-bytes 0` for autonomous CI agents that have huge context.

### 2. Priority-tiered emission

When the budget is tight, the loader doesn't truncate randomly. Order:

1. **Mandatory tier (always emitted, ignores the budget):** root `CLAUDE.md`, every policy YAML.
2. **Should tier (emit if it fits):** cross-cutting `*.md` (matched via `applies_to`), per-directory `CLAUDE.md` (closest first).
3. **Nice tier (smallest first, drop the rest):** generated JSON inventories.

When budget runs out, the loader emits `[TRUNCATED] <path> (4231 bytes)` pointers so the AI knows the file exists and can `cat` it on demand.

### 3. Per-file targeting via `applies_to` globs

A cross-cutting rule like `.harness/auth.md` declares in its front-matter:

```yaml
---
applies_to:
  - "backend/src/api/**/*.py"
---
```

If you're editing `frontend/src/components/Dashboard.tsx`, the loader checks the glob, doesn't match, doesn't emit `auth.md`. You only see auth rules when editing API routes.

### 4. JSON over prose

Compare:
- "There are 47 API endpoints. The first one is GET /healthz which returns a status object…" — ~30 tokens per endpoint, ~1500 for 47.
- `api_endpoints.json` with one record per endpoint — ~15 tokens each, ~700 total.

JSON is denser than prose. AIs read it natively.

### 5. Pointers, not full files

When the loader emits `[TRUNCATED] backend/src/api/users.py (4231 bytes) — read with: cat backend/src/api/users.py`:

- Pointer cost: ~50 tokens.
- If the conversation is about routes: AI fetches the file (~1k tokens), only when needed.
- If the conversation is about the frontend: AI never reads it (saves 1k).

This is the difference between **context as a buffet** (eat everything up front) and **context as a library** (here's the catalog, fetch what you need).

### 6. Deterministic regen → no stale context

When code changes, `make harness` regenerates inventories. The next session loads fresh JSON. You never end up with the AI's mental model from a week ago.

### Net result

A typical session in a harness-equipped repo:

- Session start: ~30 KB of structured rules + inventories.
- During conversation: pulls specific files on demand via pointers.
- Total harness footprint: 5–10% of the context window.

Without the harness, the AI either has no context (re-derives from scratch every conversation) or has unstructured context (you paste big chunks into chat, silently bloating every turn). Structured-context-on-demand is strictly better than either.

---

## How is this different from a `CLAUDE.md` file?

`CLAUDE.md` is **one input** to the harness. The harness is the system around it. Six concrete differences:

### 1. CLAUDE.md is text. The harness has enforcement.

`CLAUDE.md` says "use httpx.AsyncClient, not requests." The AI reads it, **promises** to follow it, then forgets when the user asks for something quickly.

The harness has `Q7.no-requests` — a deterministic Python check. Pre-commit fails. CI fails. The rule isn't a suggestion; it's a gate.

### 2. CLAUDE.md is one file. The harness is many layers.

A typical `CLAUDE.md` is one ~5 KB markdown file at the repo root. Either it's massive (and the AI skims) or it's incomplete.

The harness layers:

- Root `CLAUDE.md` → broadest rules (always loaded).
- Per-directory `CLAUDE.md` → narrower rules (loaded only when you're in that dir).
- Cross-cutting `.harness/*.md` → topic rules (loaded by glob match).
- Policy YAMLs → machine-readable thresholds (always loaded).
- Generated JSON → factual inventories (loaded if budget allows).

Each layer is targeted. You only see what's relevant.

### 3. CLAUDE.md is hand-written. The harness has machine-derived inventories.

`CLAUDE.md` says "we have an API at backend/src/api/". The harness has `api_endpoints.json` listing every actual route, regenerated when code changes.

`CLAUDE.md` describes the structure. The harness describes the **state**. State drifts; `CLAUDE.md` doesn't update itself. Generators do.

### 4. CLAUDE.md doesn't ship between repos. The harness does.

Three projects with shared conventions = three CLAUDE.md copies that drift. Update the auth rule, update three files, forget one, that project diverges silently.

The harness is published from one source repo as signed tags. Each consumer pins (`.harness-version`) and pulls updates with `tools/sync_harness.py --trust-key …`. Same rules, atomic updates.

### 5. CLAUDE.md doesn't gate. The harness gates.

`CLAUDE.md` is read-only context. The only verification is "did the AI happen to follow the rules this time?"

The harness has 35 deterministic checks (30 enforcement + 5 self-test) at pre-commit, the same checks in CI, baselines that block widening, a failure log that surfaces "rule X fired 47 times this week" trends.

### 6. CLAUDE.md mixes facts and rules. The harness separates them.

`CLAUDE.md` mixes "we use Pydantic with extra='forbid'" + "auth functions are X, Y, Z" + "frontend bundle target is < 200 KB" in one place.

The harness:
- The **rule** in `.harness/checks/backend_validation_contracts.py` (Q10).
- The **reference list** in `.harness/security_policy.yaml.auth_dependency_names`.
- The **threshold** in `.harness/performance_budgets.yaml.frontend_bundle.initial_js_kb_gzipped`.

Each piece has a JSON Schema validating its shape. When the threshold changes, you change one number; every check that depends on it updates immediately.

### Mental model

| Layer | What it does |
|-------|--------------|
| `CLAUDE.md` | Tells the AI "here's how we do things" |
| The harness on top | Loads `CLAUDE.md` tactically + inventories + policies + checks |
| Naive LLM-judge harness | Asks an LLM to verify rules on every commit (burns tokens) |
| Naive context dump | Pastes everything into chat (burns tokens) |

`ai-harness` = `CLAUDE.md + targeted layers + enforcement + signed distribution + per-session budget cap`. `CLAUDE.md` is one input, not a substitute.

---

## Bootstrap into a new project

```bash
# One-time: clone the harness somewhere
git clone https://github.com/inder1991/ai-harness /tmp/ai-harness

# Bootstrap into your project
python3 /tmp/ai-harness/tools/init_harness.py \
  --target /path/to/your/project \
  --owner "@your-team" \
  --tech-stack polyglot \
  --from-git latest

cd /path/to/your/project
make harness-install              # installs the pre-commit hook
make harness                      # runs all generators, populates .harness/generated/
make harness-baseline-refresh     # snapshot existing violations into baselines
make validate-fast                # smoke-test the gate
```

After this:

- `.harness-version` is pinned to whichever tag `--from-git latest` resolved to.
- `.harness/HARNESS_CARD.yaml.version` matches the pin (Q21 enforces parity).
- `.gitattributes` is in place (eol=lf protection on Windows checkouts).
- `.github/workflows/validate.yml` runs `make validate-full` on every PR.
- Pre-commit hook is installed at `.git/hooks/pre-commit`.

Edit `.harness/spine_paths.yaml` if your repo doesn't use the canonical layout (`backend/src/`, `frontend/src/`).

---

## Upgrading an existing consumer

```bash
# Pin to a new version
echo "v1.3.1" > .harness-version

# Bump the card to match (Q21 enforces parity in the same commit)
sed -i.bak 's/^version:.*/version: 1.3.1/' .harness/HARNESS_CARD.yaml \
  && rm .harness/HARNESS_CARD.yaml.bak

# Pull the new substrate
python3 tools/sync_harness.py --trust-key 73A7AF8F04F40EC9

# Re-snapshot baselines if any rules tightened (read RELEASES.md first)
python3 tools/refresh_baselines.py

# Verify
make validate-fast
```

`tools/sync_harness.py`:

1. Reads `.harness-version`.
2. Shallow-clones this repo at that tag (with `timeout=120`).
3. Verifies the tag is signed by `--trust-key` (or `HARNESS_TRUST_KEY` env). Mismatched fingerprint → exit 3.
4. Overlays the substrate files into your repo.

`baselines/` and `generated/` are **preserved** during overlay (consumer-specific). Everything else gets refreshed.

The signed-tag + trust-pin model means an attacker who hijacks the upstream repo can't ship malicious overlay code — your verify step rejects unsigned tags and tags signed by the wrong key.

---

## Releases + signing

Every release is a **GPG-signed annotated tag** on this repo. The signing key fingerprint is `73A7AF8F04F40EC9` (Ed25519). See `docs/keys.md` for the full key block and import instructions.

Verify any tag yourself:

```bash
git -C /tmp/ai-harness verify-tag v1.3.1
```

Release flow (run from a maintainer machine):

```bash
bash tools/setup_signing.sh         # one-time per machine, default --local scope
bash tools/sign_release.sh v1.3.1   # extract + force-push main + sign + push tag
```

For a current change list see [`RELEASES.md`](./RELEASES.md).

---

## Key invariants the harness enforces on itself

The harness validates *itself* with the same machinery it offers consumers:

- **`H-16` / `H-23`** — every check's stdout must match `[SEVERITY] file=<path>:<line> rule=<id> message="..." suggestion="..."`. Enforced by `output_format_conformance.py`.
- **`H-17`** — `validate-fast` settles in < 30 s.
- **`H-21` / `harness_rule_coverage.py`** — every rule referenced in plans/docs must have a corresponding check (or an exemption with a written reason).
- **`H-24` / `harness_fixture_pairing.py`** — every check has paired `compliant/` + `violation/` fixtures.
- **`Q19.baseline-grew-without-adr`** — baselines can shrink freely, but growth requires a written ADR.
- **`Q21.harness-card-version-mismatch`** — `HARNESS_CARD.yaml.version` matches `.harness-version` (consumer-side).
- **`Q22.doc-rule-count-mismatch`** — every check's "N rules" docstring claim matches the count of enumerated rule IDs in the same docstring.

---

## Contributing

### Add a check

1. Write `.harness/checks/<your_check>.py`. Use `_common.emit()` to produce H-16 lines. Use `_common.ImportTracker` if you need scope-aware import resolution.
2. Add paired fixtures: `tests/harness/fixtures/<your_check>/{compliant,violation}/`. Each violation fixture must produce ≥1 ERROR with the matching rule ID; each compliant fixture must produce zero ERRORs.
3. Write `tests/harness/checks/test_<your_check>.py` using `_helpers.assert_check_fires` / `assert_check_silent`.
4. The orchestrator auto-discovers it via the `.harness/checks/*.py` glob — no central registry to update.

Read `.harness/checks/accessibility_policy.py` (~100 lines) for a minimal example.

### Add a generator

1. Write `.harness/generators/extract_<thing>.py`. Output deterministic JSON to `.harness/generated/<thing>.json`.
2. Add a JSON Schema at `.harness/schemas/<thing>.schema.json`. `harness_policy_schema.py` will validate every output against it.
3. Declare any prereqs in `tools/run_harness_regen.py.DEPENDENCIES`.

### Add a policy YAML

1. Write `.harness/<topic>_policy.yaml`.
2. Write a JSON Schema at `.harness/schemas/<topic>_policy.schema.json` with `additionalProperties: false`.
3. Consume it from your check via `yaml.safe_load(...)` — same pattern every other check uses.

---

## Coverage and non-goals

What the harness covers (`HARNESS_CARD.yaml.coverage.covered`):

- Rule discipline (30 deterministic AST/regex checks)
- Policy schema validation (10 yamls all strict)
- Auto-derived inventories (20 generators with deterministic regen)
- Session-start context loading with byte budget
- Tag-signature verification on harness-sync
- Consumer-overridable spine paths
- Grandfathered baselines for legacy code
- Rolling failure log for trend visibility (zero API cost)

What it deliberately doesn't (`coverage.not_covered`):

- Evals + observability beyond rule firings (no API cost — explicit choice)
- Browser/runtime validation in the AI fix loop
- Prompt injection mitigation
- Sandbox / write-path allowlist
- Long-running session checkpoints + handoff artifacts
- Spec-driven development primitives
- Agent-budget runtime enforcement (only declarations exist)

Each non-goal is a real harness concern; this one chose to do rule discipline + inventory + signed distribution well rather than every harness concern badly.

---

## License

MIT.

---

## Pointers

- Latest release notes: [`RELEASES.md`](./RELEASES.md)
- Signing key reference: [`docs/keys.md`](./docs/keys.md)
- Original design + sprint plans: `docs/plans/2026-04-26-ai-harness.md`
- Audit history: `docs/plans/2026-04-27-harness-sdet-audit.md` and `docs/plans/2026-04-28-harness-rule-semantics-audit.md`
- HarnessCard: [`.harness/HARNESS_CARD.yaml`](./.harness/HARNESS_CARD.yaml)
