"""Sprint 1 / S1.1 — `harness` CLI dispatcher tests.

Asserts the CLI's contract:
  - all 9 verbs advertised in --help
  - unknown commands exit 2 with a helpful suggestion
  - --version reads HARNESS_CARD.yaml
  - NO_COLOR env disables ANSI escapes
  - --no-color flag disables ANSI escapes
  - HARNESS_COLOR=always forces color even when piped
  - unimplemented verbs print a friendly notice + exit 0
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(*args, env_extra: dict | None = None, **kwargs):
    """Helper: run `python -m tools.harness_cli` with default kwargs."""
    env = {**os.environ}
    if env_extra:
        env.update(env_extra)
    cmd = [sys.executable, "-m", "tools.harness_cli", *args]
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=10, env=env, **kwargs,
    )


def test_no_args_prints_usage():
    result = _run()
    assert result.returncode == 0
    assert "Usage: harness <command>" in result.stdout


def test_help_lists_all_nine_verbs():
    result = _run("--help")
    assert result.returncode == 0
    for verb in ("init", "check", "fix", "rules", "baseline",
                 "telemetry", "doctor", "upgrade", "rollback"):
        assert verb in result.stdout, f"verb '{verb}' missing from --help"


def test_help_short_flag():
    result = _run("-h")
    assert result.returncode == 0
    assert "Usage: harness <command>" in result.stdout


def test_unknown_command_exits_2():
    result = _run("frobnicate")
    assert result.returncode == 2
    assert "unknown command" in result.stderr.lower()


def test_unknown_command_suggests_nearest():
    """`harness chec` should suggest `check`."""
    result = _run("chec")
    assert result.returncode == 2
    assert "did you mean" in result.stderr.lower()
    assert "check" in result.stderr


def test_version_short_and_long():
    for flag in ("--version", "-V"):
        result = _run(flag)
        assert result.returncode == 0
        assert "ai-harness" in result.stdout
        assert "v" in result.stdout


def test_no_color_env_disables_color():
    """NO_COLOR (https://no-color.org/) must disable ANSI escapes."""
    result = _run("--help", env_extra={"NO_COLOR": "1"})
    assert "\x1b[" not in result.stdout, (
        "NO_COLOR was set; output must not contain ANSI escapes"
    )


def test_no_color_flag_disables_color():
    """The --no-color CLI flag also disables."""
    result = _run("--help", "--no-color")
    assert "\x1b[" not in result.stdout


def test_harness_color_always_forces_color():
    """HARNESS_COLOR=always forces color even when piped to capture."""
    result = _run(
        "--help",
        env_extra={"HARNESS_COLOR": "always", "NO_COLOR": ""},
    )
    assert "\x1b[" in result.stdout, (
        "HARNESS_COLOR=always must force ANSI escapes even when piped"
    )


def test_unimplemented_verb_prints_friendly_notice():
    """A verb in the catalog but not yet wired prints a `not yet implemented` notice.

    `fix` is the canonical unimplemented verb after Sprint 1 (planned
    for Sprint 2 / S2.3); the other 8 are all wired."""
    result = _run("fix")
    # Exit 0 (not 2): it's a documented future surface, not a typo.
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "not yet implemented" in combined.lower() or \
           "coming in" in combined.lower()


def test_unimplemented_verb_references_sprint():
    result = _run("fix")
    combined = result.stdout + result.stderr
    assert "S2.3" in combined or "Sprint 2" in combined


def test_unimplemented_verb_includes_roadmap_pointer():
    result = _run("fix")
    combined = result.stdout + result.stderr
    assert "roadmap" in combined.lower() or "production-roadmap" in combined.lower()


def test_cli_module_importable():
    """The CLI module imports cleanly (catches import-time errors)."""
    sys.path.insert(0, str(REPO_ROOT))
    import tools.harness_cli  # noqa: F401  -- side-effect-free import
    assert hasattr(tools.harness_cli, "main")
    assert hasattr(tools.harness_cli, "VERBS")
    assert len(tools.harness_cli.VERBS) == 9


def test_main_callable_with_argv_list():
    """main(argv=['--version']) works without touching sys.argv."""
    sys.path.insert(0, str(REPO_ROOT))
    import tools.harness_cli as cli
    code = cli.main(["--version"])
    assert code == 0


def test_main_callable_with_unknown_returns_2():
    sys.path.insert(0, str(REPO_ROOT))
    import tools.harness_cli as cli
    code = cli.main(["frobnicate"])
    assert code == 2
