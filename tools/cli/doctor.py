"""Sprint 1 / S1.4 — `harness doctor`.

Diagnoses an installation. One section per check; ✓/✗/⚠ for each.
At the bottom: concrete remediations.

Exit codes:
  0 — every section ✓
  6 — at least one ✗ (unrecoverable; manual fix needed)
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _color_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _green(s: str) -> str:
    return f"\x1b[32m{s}\x1b[0m" if _color_enabled() else s


def _red(s: str) -> str:
    return f"\x1b[31m{s}\x1b[0m" if _color_enabled() else s


def _yellow(s: str) -> str:
    return f"\x1b[33m{s}\x1b[0m" if _color_enabled() else s


def _check(label: str, ok: bool, detail: str = "", remediation: str = "") -> tuple[bool, str]:
    """Format one check result. Returns (passed, formatted_line)."""
    mark = _green("✓") if ok else _red("✗")
    line = f"  {mark} {label}"
    if detail:
        line += f" — {detail}"
    if not ok and remediation:
        line += f"\n      ▸ {remediation}"
    return ok, line


def _check_pre_commit_hook(target: Path) -> tuple[bool, str]:
    hook = target / ".git" / "hooks" / "pre-commit"
    if not (target / ".git").exists():
        return _check("pre-commit hook", False,
                      "not a git repo", "run `git init` first")
    if not hook.exists():
        return _check("pre-commit hook", False,
                      "missing", "harness init --force")
    if not os.access(hook, os.X_OK):
        return _check("pre-commit hook", False,
                      "not executable", "chmod +x .git/hooks/pre-commit")
    return _check("pre-commit hook", True, str(hook.relative_to(target)))


def _check_card_pin_parity(target: Path) -> tuple[bool, str]:
    card = target / ".harness" / "HARNESS_CARD.yaml"
    pin = target / ".harness-version"
    if not card.exists() or not pin.exists():
        return _check("HARNESS_CARD ↔ pin parity", False,
                      "missing card or pin",
                      "harness init or harness upgrade")
    try:
        card_v = str((yaml.safe_load(card.read_text()) or {}).get("version", ""))
        pin_v = pin.read_text().strip().lstrip("v")
    except (OSError, yaml.YAMLError) as exc:
        return _check("HARNESS_CARD ↔ pin parity", False,
                      f"parse error: {exc}", "fix the YAML/text")
    if card_v != pin_v:
        return _check("HARNESS_CARD ↔ pin parity", False,
                      f"card={card_v!r} pin={pin_v!r}",
                      f"bump HARNESS_CARD.yaml version to {pin_v!r}")
    return _check("HARNESS_CARD ↔ pin parity", True, f"both at {card_v}")


def _check_yamls_schema_valid(target: Path) -> tuple[bool, str]:
    """Best-effort: count yamls + schemas, report mismatches."""
    yamls = list((target / ".harness").glob("*.yaml")) if (target / ".harness").exists() else []
    schemas = list((target / ".harness" / "schemas").glob("*.schema.json")) if (target / ".harness" / "schemas").exists() else []
    if not yamls:
        return _check("policy YAMLs present", False, "none found",
                      "harness init")
    return _check("policy YAMLs present", True,
                  f"{len(yamls)} yamls, {len(schemas)} schemas")


def _check_path_tools(target: Path) -> list[tuple[bool, str]]:
    """Check optional CLI tools."""
    out = []
    for tool, why in (
        ("git", "required for sync_harness"),
        ("python3", "required"),
        ("gpg", "for tag signature verification"),
        ("gitleaks", "for Q13.secret-detected"),
    ):
        ok = shutil.which(tool) is not None
        if not ok:
            out.append(_check(f"PATH: {tool}", False, why,
                              f"install {tool}"))
        else:
            out.append(_check(f"PATH: {tool}", True))
    return out


def _check_upgrade_pending(target: Path) -> int:
    """Sprint 4 / S4.5 — `harness doctor --check-upgrade` mode.

    Surfaces pre-migration state: missing .harness/profiles/, no `extends:`
    in profile.yaml, card/pin mismatch, foreign-machine baselines.
    Returns 0 when on v2 layout, 1 when migration steps are pending.
    """
    sys.path.insert(0, str(REPO_ROOT))
    from tools.migrations import v1_to_v2  # noqa: E402

    state = v1_to_v2.detect_state(target)
    steps = v1_to_v2.plan(target)
    print(f"\nUpgrade check for {target}:")
    print(f"  pinned version:        {state.pinned_version or '(none)'}")
    print(f"  profile:               {state.profile}")
    print(f"  has profiles/ dir:     {'yes' if state.has_profiles_dir else 'NO'}")
    print(f"  has extends:           {'yes' if state.has_extends else 'no'}")
    if not steps:
        print(f"\n{_green('✓ on v2 layout — nothing to migrate.')}")
        return 0
    print(f"\n{_yellow(f'⚠ {len(steps)} migration step(s) pending:')}")
    for step in steps:
        print(f"  · {step.describe}")
    print(f"\nRun: harness upgrade --from {state.pinned_version or 'v1.x'} --to v2.x --migrate-only")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="harness doctor")
    parser.add_argument("--target", type=Path, default=Path.cwd())
    parser.add_argument("--fix", action="store_true",
                        help="Automate the safe fixes (re-install hook, etc.)")
    parser.add_argument("--check-upgrade", action="store_true",
                        help="Print pending v1.x → v2.x migration steps and exit "
                             "(0 if on v2 layout, 1 if migration pending).")
    args = parser.parse_args(argv)

    target = args.target.resolve()
    if args.check_upgrade:
        return _check_upgrade_pending(target)

    print(f"\nDiagnosing harness install at: {target}\n")
    print("Substrate:")
    results = [
        _check_pre_commit_hook(target),
        _check_card_pin_parity(target),
        _check_yamls_schema_valid(target),
    ]
    for _, line in results:
        print(line)

    print("\nDependencies:")
    for ok, line in _check_path_tools(target):
        print(line)
        results.append((ok, line))

    failed = sum(1 for ok, _ in results if not ok)
    print()
    if failed == 0:
        print(_green(f"✓ Healthy install (all {len(results)} checks passed)"))
        return 0
    print(_red(f"✗ {failed} of {len(results)} checks failed"))
    print("Run `harness doctor --fix` to automate safe remediations.")
    return 6


if __name__ == "__main__":
    raise SystemExit(main())
