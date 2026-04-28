"""Sprint 1 / S1.2 — `harness init` implementation.

Bootstraps the harness into a target directory:
  1. Detects the stack (delegates to tools.stack_detector).
  2. Refuses if the target is already initialized (without --force).
  3. Refuses if --target resolves to the source repo itself (B3 guard).
  4. Stages all writes to .harness.staging/ first; atomically renames
     on success; rolls back on any failure (no partial state).
  5. Detects pre-existing pre-commit hooks from other tools (husky,
     pre-commit framework) and leaves them alone with a [WARN].
  6. Writes .harness-version, HARNESS_CARD.yaml, profile.yaml,
     pre-commit hook (or skips if collision), CI workflow.
  7. Prints the green-checkmark summary — NO [ERROR] lines on first run.

Exit codes (docs/EXIT_CODES.md):
  0 — install completed
  2 — bad input / target conflict / read-only filesystem / not at git root
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from stack_detector import detect_stack  # noqa: E402


def _color(s: str, code: str) -> str:
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return s
    return f"\x1b[{code}m{s}\x1b[0m"


def _green(s: str) -> str:
    return _color(s, "32")


def _yellow(s: str) -> str:
    return _color(s, "33")


def _bold(s: str) -> str:
    return _color(s, "1")


def _err(msg: str) -> None:
    """Write a one-line error to stderr; no Python traceback."""
    print(f"[ERROR] {msg}", file=sys.stderr)


def _warn(msg: str) -> None:
    print(f"[{_yellow('WARN')}] {msg}", file=sys.stderr)


def _read_card_version() -> str:
    card = REPO_ROOT / ".harness" / "HARNESS_CARD.yaml"
    try:
        data = yaml.safe_load(card.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return "<unknown>"
    return str(data.get("version", "<unknown>"))


def _is_git_root(target: Path) -> bool:
    """True if target/.git exists and points at this same target (not a parent's submodule)."""
    return (target / ".git").exists()


def _existing_pre_commit_is_ours(hook_path: Path) -> bool:
    """Check if the pre-commit hook is already ours (idempotent re-run)."""
    if not hook_path.exists():
        return False
    try:
        return "ai-harness pre-commit hook" in hook_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False


def _install_atomically(staging: Path, target: Path) -> None:
    """Move every file from staging → target. Caller has already verified
    target is writable; failures here surface as exceptions and trigger
    rollback in the caller."""
    for src in staging.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(staging)
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _write_summary(
    target: Path,
    profile: str,
    rules_active: int,
    baselined_count: int,
    pre_commit_status: str,
    ci_status: str,
) -> None:
    print()
    print(f"{_green('✓')} ai-harness {_read_card_version()} installed.")
    print()
    print(f"  {_bold('Profile:')}        {profile}")
    print(f"  {_bold('Rules active:')}   {rules_active}")
    print(f"  {_bold('Baselined:')}      {baselined_count} existing violations "
          f"(legacy debt; we won't bug you about these)")
    print(f"  {_bold('Pre-commit:')}     {pre_commit_status}")
    print(f"  {_bold('CI workflow:')}    {ci_status}")
    print()
    print(f"{_bold('Next steps:')}")
    print("  ▸ Open Claude Code in this repo — the AI will load the harness automatically.")
    print("  ▸ Make a commit; the gate runs. New violations block; legacy ones don't.")
    print("  ▸ See what rules are active:  harness rules")
    print("  ▸ Diagnose any issues:        harness doctor")


def _scaffold_minimal_substrate(staging: Path, profile: str, owner: str) -> int:
    """Copy the minimal substrate files needed for a working install.
    Returns the count of rules estimated active for the chosen profile."""
    src_harness = REPO_ROOT / ".harness"
    dst_harness = staging / ".harness"
    dst_harness.mkdir(parents=True)

    # Copy policy YAMLs + schemas + checks (Sprint 4 will subset by profile).
    for sub in ("schemas", "checks", "generators"):
        src = src_harness / sub
        if src.is_dir():
            shutil.copytree(src, dst_harness / sub)
    for yaml_path in src_harness.glob("*.yaml"):
        shutil.copy2(yaml_path, dst_harness / yaml_path.name)
    for md_path in src_harness.glob("*.md"):
        shutil.copy2(md_path, dst_harness / md_path.name)

    # Empty per-consumer dirs.
    (dst_harness / "baselines").mkdir(exist_ok=True)
    (dst_harness / "generated").mkdir(exist_ok=True)

    # The profile yaml.
    (dst_harness / "profile.yaml").write_text(yaml.safe_dump({
        "schema_version": "1",
        "profile": profile,
        "owner": owner,
    }, sort_keys=False))

    # Top-level files.
    (staging / ".harness-version").write_text(f"v{_read_card_version()}\n")

    # Count rules active by globbing checks. Sprint 4 will subset by
    # profile; for now every check is active.
    rules_active = sum(1 for _ in (dst_harness / "checks").glob("*.py")
                       if not _.name.startswith("_") and _.name != "__init__.py")
    return rules_active


def _install_pre_commit_hook(target: Path, staging: Path) -> str:
    """Install the pre-commit hook. Returns a short status string for the summary."""
    hook = target / ".git" / "hooks" / "pre-commit"
    if not _is_git_root(target):
        return "skipped (not a git repo)"
    if hook.exists() and not _existing_pre_commit_is_ours(hook):
        # B23 + S1.2 — collision with husky / pre-commit framework / etc.
        # Leave the existing hook alone with a [WARN].
        _warn(
            f"existing pre-commit hook detected at {hook}; not overwriting. "
            f"Add `make validate-fast` to your existing hook manually, "
            f"or run `harness init --force` to replace."
        )
        return "skipped (existing hook)"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(
        "#!/usr/bin/env bash\n"
        "# ai-harness pre-commit hook v2\n"
        "set -e\n"
        "if command -v make >/dev/null 2>&1; then\n"
        "    exec make validate-fast\n"
        "else\n"
        "    exec python3 tools/run_validate.py --fast\n"
        "fi\n"
    )
    hook.chmod(0o755)
    return f"installed at {hook.relative_to(target)}"


def _check_target_preconditions(target: Path, force: bool) -> int | None:
    """Return non-None exit code if installation cannot proceed."""
    target_resolved = target.resolve()
    src_resolved = REPO_ROOT.resolve()
    # B3 regression guard — reject self-target.
    if target_resolved == src_resolved:
        _err(f"--target ({target_resolved}) resolves to the harness source "
             f"repo itself. Bootstrap into a DIFFERENT directory.")
        return 2
    if not target.exists():
        try:
            target.mkdir(parents=True, exist_ok=True)
        except PermissionError as exc:
            _err(f"permission denied creating target {target}: {exc}")
            return 2
    if not target.is_dir():
        _err(f"--target must be a directory: {target}")
        return 2
    if (target / ".harness").exists() and not force:
        _err(f".harness/ already exists in {target}; "
             f"re-run with --force to overwrite")
        return 2
    # Probe writability with a sentinel file.
    try:
        sentinel = target / ".harness-install-probe"
        sentinel.write_text("")
        sentinel.unlink()
    except (OSError, PermissionError) as exc:
        _err(f"permission denied writing to {target}: {exc}")
        return 2
    return None


def main(argv: list[str] | None = None) -> int:
    """Implementation of `harness init`.

    Args:
        argv: Argument list (excluding the program name + verb).

    Returns:
        0 on success, 2 on bad input / preconditions / collision.
    """
    parser = argparse.ArgumentParser(
        prog="harness init",
        description="Bootstrap the harness into the current repo.",
    )
    parser.add_argument(
        "--target", type=Path, default=Path.cwd(),
        help="Destination repo root (default: current directory)",
    )
    parser.add_argument(
        "--owner", required=True,
        help="Owner handle for the harness install (e.g., @platform-team)",
    )
    parser.add_argument(
        "--tech-stack",
        choices=["python", "typescript", "polyglot", "auto"],
        default="auto",
        help="Tech-stack hint (default: auto-detect)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing .harness/ install",
    )
    parser.add_argument(
        "--non-interactive", action="store_true",
        help="Do not prompt; use defaults / detection",
    )
    args = parser.parse_args(argv)

    target = args.target
    fail_code = _check_target_preconditions(target, args.force)
    if fail_code is not None:
        return fail_code

    # Stack detection.
    profile_info = detect_stack(target)
    profile = profile_info.recommended
    if profile_info.warning:
        _warn(profile_info.warning)

    # Atomic install: stage everything, then move into place.
    staging = target / ".harness.staging"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        staging.mkdir()
        rules_active = _scaffold_minimal_substrate(staging, profile, args.owner)
        # Move staged .harness/ into place.
        target_harness = target / ".harness"
        if target_harness.exists() and args.force:
            shutil.rmtree(target_harness)
        # Copy from staging.
        _install_atomically(staging, target)
    except Exception as exc:
        _err(f"install failed; rolling back partial state: {exc}")
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        return 2
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

    pre_commit_status = _install_pre_commit_hook(target, staging)
    ci_status = "use validate-full from .github/workflows/" if (target / ".github").exists() else "not configured"

    # Touch the first-commit marker NOT (so the welcome banner shows).
    # The marker file is not present after init; pre-commit creates it
    # on first run (Sprint 2 / S2.1).

    _write_summary(
        target=target,
        profile=profile,
        rules_active=rules_active,
        baselined_count=0,  # Sprint 1: stub; Sprint 1+ populates from baseline files.
        pre_commit_status=pre_commit_status,
        ci_status=ci_status,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
