"""Sprint 0 / S0.3 — stack-detection tests against the 17-fixture corpus.

Each fixture under `tests/harness/fixtures/stack_detector/<repo_kind>/`
represents a real-world variant. The detector is tested against all of
them via parametrize so failures clearly name the failing case.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from stack_detector import detect_stack  # noqa: E402

FIXTURE_ROOT = REPO_ROOT / "tests/harness/fixtures/stack_detector"


@pytest.mark.parametrize(
    "fixture_name,expected_profile",
    [
        ("python-pyproject-modern", "python-only"),
        ("python-poetry", "python-only"),
        ("python-setup-py", "python-only"),
        ("python-requirements-txt", "python-only"),
        ("python-django", "python-only"),
        ("python-react-monorepo", "python-react"),
        ("node-only-express", "node-only"),
        ("node-only-fastify", "node-only"),
        ("node-only-nest", "node-nest"),
        ("react-only-vite", "react-only"),
        ("nextjs-app-router", "nextjs"),
        ("vue-pinia", "vue"),
        ("svelte-kit", "svelte"),
        ("go-mod-only", "go-only"),
        ("rust-cargo", "rust-only"),
        ("polyglot-python-go-react", "polyglot"),
        ("empty-directory", "minimal"),
    ],
)
def test_detect_stack(fixture_name: str, expected_profile: str) -> None:
    target = FIXTURE_ROOT / fixture_name
    assert target.exists(), f"missing fixture: {target}"
    result = detect_stack(target)
    assert result.recommended == expected_profile, (
        f"{fixture_name}: expected {expected_profile}, got {result.recommended} "
        f"(signals={result.signals}, warning={result.warning})"
    )


def test_detect_stack_warns_on_empty():
    result = detect_stack(FIXTURE_ROOT / "empty-directory")
    assert result.warning is not None
    assert "minimal" in result.warning.lower() or "no stack signals" in result.warning.lower()


def test_detect_stack_warns_on_unsupported_framework():
    """Vue / Svelte / Go / Rust → warning about partial coverage."""
    for fixture in ("vue-pinia", "svelte-kit", "go-mod-only", "rust-cargo"):
        result = detect_stack(FIXTURE_ROOT / fixture)
        assert result.warning is not None, f"{fixture} should warn"


def test_detect_stack_pure_function(tmp_path):
    """Detector must not write anything outside target. Verify by
    snapshotting tmp_path before+after."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n")
    before = sorted(p.name for p in tmp_path.iterdir())
    result = detect_stack(tmp_path)
    after = sorted(p.name for p in tmp_path.iterdir())
    assert before == after, "detector mutated target dir"
    assert result.recommended == "python-only"


def test_detect_stack_handles_nonexistent():
    """Non-existent target falls back to minimal with a warning."""
    result = detect_stack(Path("/nonexistent/path/that/does/not/exist"))
    assert result.recommended == "minimal"
    assert result.warning is not None


def test_detect_stack_pyproject_modern():
    """Specific signals exposed for debugging."""
    result = detect_stack(FIXTURE_ROOT / "python-pyproject-modern")
    assert "pyproject.toml" in result.signals


def test_detect_stack_polyglot_signals():
    result = detect_stack(FIXTURE_ROOT / "polyglot-python-go-react")
    assert "pyproject.toml" in result.signals
    assert "go.mod" in result.signals


def test_detect_stack_handles_malformed_package_json(tmp_path):
    """A malformed package.json shouldn't crash detection."""
    (tmp_path / "package.json").write_text("{ this is not valid json")
    result = detect_stack(tmp_path)
    # Falls back to node-only because file exists; no react signal because parse failed.
    assert result.recommended == "node-only"
