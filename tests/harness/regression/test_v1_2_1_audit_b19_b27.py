"""Sprint 0 / S0.4 — regression tests for v1.2.1 P2 audit (B19-B27)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


# REGRESSION-FOR: B19 (refresh_baselines WARNs on JSON parse error)
def test_b19_refresh_baselines_warns_on_unparseable():
    src = (REPO_ROOT / "tools/refresh_baselines.py").read_text()
    # The function MUST emit a [WARN] when JSONDecodeError is caught,
    # not silently return 0.
    assert "[WARN]" in src and "unparseable" in src.lower()


# REGRESSION-FOR: B20 (load_harness records OSError reads)
def test_b20_load_harness_records_read_errors():
    src = (REPO_ROOT / "tools/load_harness.py").read_text()
    assert "_READ_ERRORS" in src, (
        "load_harness must record OSError reads in _READ_ERRORS (B20)"
    )


# REGRESSION-FOR: B21 (extract.sh logs find -delete failures)
def test_b21_extract_sh_logs_find_delete_failures():
    src = (REPO_ROOT / "tools/extraction/extract.sh").read_text()
    # Look for the for-loop that emits a [WARN] on find failure.
    assert ".find-err" in src or "find -delete failed" in src.lower()


# REGRESSION-FOR: B22 (setup_signing.sh --protect flag)
def test_b22_setup_signing_supports_protect():
    src = (REPO_ROOT / "tools/setup_signing.sh").read_text()
    assert "--protect" in src, "setup_signing must accept --protect (B22)"


# REGRESSION-FOR: B23 (install_pre_commit.sh falls back to python3)
def test_b23_install_pre_commit_has_make_fallback():
    src = (REPO_ROOT / "tools/install_pre_commit.sh").read_text()
    # Hook body falls back to python3 when make absent.
    assert "command -v make" in src or "tools/run_validate.py" in src


# REGRESSION-FOR: B24 (load_harness uses fnmatchcase for determinism)
def test_b24_load_harness_uses_fnmatchcase():
    src = (REPO_ROOT / "tools/load_harness.py").read_text()
    assert "fnmatchcase" in src, (
        "load_harness must use fnmatch.fnmatchcase, not fnmatch (B24)"
    )


# REGRESSION-FOR: B25 (refresh_baselines doesn't overwrite on buggy zero-finding)
def test_b25_refresh_baselines_guards_silent_reset():
    src = (REPO_ROOT / "tools/refresh_baselines.py").read_text()
    # The guard: if check exited non-zero AND produced 0 findings AND
    # we had a previous baseline, refuse to overwrite.
    assert "refusing to overwrite" in src.lower() or \
           "old_count > 0" in src


# REGRESSION-FOR: B26 (_session_start_hook has pipefail)
def test_b26_session_start_hook_has_pipefail():
    src = (REPO_ROOT / "tools/_session_start_hook.sh").read_text()
    assert "set -o pipefail" in src or "pipefail" in src


# REGRESSION-FOR: B27 (HARNESS_CARD covered by schema)
def test_b27_harness_card_schema_exists():
    schema = REPO_ROOT / ".harness/schemas/HARNESS_CARD.schema.json"
    assert schema.exists(), "HARNESS_CARD.yaml must have a schema (B27)"
