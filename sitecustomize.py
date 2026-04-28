# Sprint 0 / S0.5 — subprocess coverage hook.
#
# Why this file exists:
#   The harness's test suite runs every check as a subprocess (via
#   tests/harness/_helpers.py:assert_check_fires/silent). Coverage.py
#   in the parent process doesn't follow into those subprocesses.
#   `sitecustomize.py` is auto-imported by every Python process; setting
#   COVERAGE_PROCESS_START=<.coveragerc-or-pyproject> tells coverage.py
#   to instrument the subprocess too.
#
# Activation:
#   COVERAGE_PROCESS_START=pyproject.toml .venv/bin/coverage run -m pytest ...
#
# This file is intentionally tiny + side-effect-free. If COVERAGE_PROCESS_START
# isn't set, this is a no-op. Production / consumer environments never
# touch this file.

import os

if os.environ.get("COVERAGE_PROCESS_START"):
    try:
        import coverage
        coverage.process_startup()
    except ImportError:
        # Q17-EXEMPT: coverage is dev-only; if it's not installed, the
        # consumer hasn't set COVERAGE_PROCESS_START anyway. The hook
        # genuinely has nothing to do.
        pass
