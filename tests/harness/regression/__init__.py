"""Sprint 0 / S0.4 — permanent regression test suite.

Every closed audit finding (B1-B27 + S-A1 through S-DP4) gets a
permanent test that asserts the fix stays. If a future refactor
re-introduces the bug, the matching test fires.

Tests in this directory are NEVER deleted; they are renamed when
superseded by a more comprehensive successor (with a comment cross-
reference).

Each test has a `# REGRESSION-FOR: <bug-id>` marker comment so a grep
can find every bug's regression test:

    grep -rn "REGRESSION-FOR:" tests/harness/regression/

The full index is at `_INDEX.md` in this directory.
"""
