---
owner: '@inder'
---

# Regression test index

Sprint 0 / S0.4 — every closed audit finding has a permanent test in this directory.

## Run only the regression suite

```bash
pytest tests/harness/regression/ -q
```

## Find the test for a specific bug

```bash
grep -rn "REGRESSION-FOR: B7" tests/harness/regression/
```

## Coverage by audit batch

| Audit batch | Test file | Bugs covered | Test count |
|-------------|-----------|--------------|------------|
| v1.0.x P0 (B1-B6) | `test_v1_0_x_audit_b1_b6.py` | B1, B2, B3, B4, B5, B6 | 10 |
| v1.1.0 P0 (B7-B10) | `test_v1_1_0_audit_b7_b10.py` | B7, B8, B9, B10 | 5 |
| v1.2.0 P1 (B11-B18) | `test_v1_2_0_audit_b11_b18.py` | B11, B12, B13, B14, B15, B16, B17, B18 | 9 |
| v1.2.1 P2 (B19-B27) | `test_v1_2_1_audit_b19_b27.py` | B19, B20, B21, B22, B23, B24, B25, B26, B27 | 9 |
| v1.3.0 P3 rule semantics | `test_v1_3_0_audit_rule_semantics.py` | S-A* (9), S-AS* (4), S-DB* (4), S-CV* (3), S-DP* (4), Q22 | 32 |

**Total regression tests: 65** (covers 27 P0/P1/P2 + 30+ rule-semantics findings).

## Adding a regression test

When a new bug is closed:

1. Pick (or create) the appropriate `test_v<release>_audit_*.py` file.
2. Write a test starting with `def test_<bug_id>_<short_description>(...):`.
3. Add `# REGRESSION-FOR: <bug-id>` as the first line of the test docstring or as a marker comment.
4. The test should construct the minimal fixture demonstrating the bug.
5. Add a row to the table above.

## Rules

- Tests in this directory are **never deleted**. They are renamed when superseded by a more comprehensive successor (with a comment cross-reference back to the original).
- Each test must pass on `main` at all times.
- A regression test that flakes is a critical bug — fix immediately.
- New tests must run in <2 seconds each (the suite must stay fast enough that contributors can run it locally before pushing).

## Why this matters

The audit ledger has 57+ closed findings. Without permanent regression coverage, future refactors silently re-introduce closed bugs. Every entry in this directory is one bug that can never come back undetected.
