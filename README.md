# ai-harness

Repo-level scaffolding that makes AI-assisted development productive in any
codebase. Two consumers, one contract — humans in IDE + autonomous CI agents.

## Bootstrap a new project

```bash
git clone https://github.com/<owner>/ai-harness /tmp/ai-harness
python3 /tmp/ai-harness/tools/init_harness.py \
  --target /path/to/your/project \
  --owner "@your-team" \
  --tech-stack polyglot
cd /path/to/your/project
make harness-install
make harness
make validate-fast
```

See `docs/plans/2026-04-26-ai-harness.md` for the full design — 25 H-rules,
19 stack-decision Q-rules, 7-sprint implementation history.
