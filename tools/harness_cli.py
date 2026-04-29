#!/usr/bin/env python3
"""Sprint 1 / S1.1 — `harness` CLI dispatcher.

The single user-facing surface for ai-harness. Every command listed
here is documented in `docs/EXIT_CODES.md` (Sprint 0 / S0.8).

This is a THIN delegation layer. Each subcommand calls existing scripts
under the hood, so v1.x `make` targets continue to work even if the
CLI breaks. Both surfaces co-exist through v2.x.

Verbs (all 9 advertised in --help; not all implemented in S1.1):
    init        Bootstrap the harness into the current repo (S1.2)
    check       Run the validation gate (S1.3)
    fix         Apply auto-fixable rules (S2.3)
    rules       List rules; explain a rule; show fixtures (S1.4)
    baseline    Refresh / show / add / prune (S1.4)
    telemetry   Show the rolling failure log (S1.4)
    doctor      Diagnose installation issues (S1.4)
    upgrade     Pull a new version (S1.4)
    rollback    Pin to the previous version (S1.4)

Exit codes (see docs/EXIT_CODES.md):
    0   Success
    2   Bad input / unknown command / missing flag
    *   Subcommand-specific (3, 4, 5, 6, 7, 124, 130)

Color: respects NO_COLOR env var (https://no-color.org/) and the
`--no-color` flag. Defaults to color when stdout.isatty().
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

# All 9 verbs Sprint 1+ exposes. Listed here so `harness` with no args
# always advertises the full surface, even before each verb is wired up.
VERBS = (
    "init",
    "check",
    "fix",
    "rules",
    "baseline",
    "telemetry",
    "doctor",
    "upgrade",
    "rollback",
)

# Subcommands implemented as of THIS revision. Unimplemented ones print
# a one-line "coming in <story>" message and exit 0 (not 2 — they're a
# documented future surface, not a typo).
IMPLEMENTED: set[str] = {  # populated as stories land
    "init", "check", "rules", "doctor", "telemetry",
    "baseline", "upgrade", "rollback", "fix",
}


def _read_version() -> str:
    """Read `version` from .harness/HARNESS_CARD.yaml. Falls back to a
    placeholder if the card is missing (e.g. during early bootstrap)."""
    card = REPO_ROOT / ".harness" / "HARNESS_CARD.yaml"
    if not card.exists():
        return "<unpinned>"
    try:
        data = yaml.safe_load(card.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        # Q17-EXEMPT: --version is best-effort; if the card is malformed
        # the user has bigger problems and `harness doctor` will surface
        # them. We don't crash on a yaml error here.
        return "<unparseable>"
    return f"v{data.get('version', '<unknown>')}"


def _color_enabled() -> bool:
    """True iff color output should be emitted to stdout.

    Honors:
      - NO_COLOR env (https://no-color.org/) — disables when set.
      - HARNESS_COLOR env — overrides isatty detection ("always", "never").
      - stdout.isatty() — default behavior.

    The `--no-color` CLI flag is handled in main(); not visible here.
    """
    if os.environ.get("NO_COLOR"):
        return False
    forced = os.environ.get("HARNESS_COLOR")
    if forced == "always":
        return True
    if forced == "never":
        return False
    return sys.stdout.isatty()


def _print_help() -> None:
    """Print the top-level usage banner. Always exits with status 0."""
    color = _color_enabled()
    bold = "\x1b[1m" if color else ""
    dim = "\x1b[2m" if color else ""
    reset = "\x1b[0m" if color else ""
    print(f"{bold}Usage:{reset} harness <command> [options]")
    print()
    print(f"  {bold}init{reset}        Bootstrap the harness into the current repo")
    print(f"  {bold}check{reset}       Run the validation gate")
    print(f"  {bold}fix{reset}         Apply auto-fixable rules         {dim}(Sprint 2){reset}")
    print(f"  {bold}rules{reset}       List rules; explain a rule")
    print(f"  {bold}baseline{reset}    Refresh / show / add / prune")
    print(f"  {bold}telemetry{reset}   Show the rolling failure log")
    print(f"  {bold}doctor{reset}      Diagnose installation issues")
    print(f"  {bold}upgrade{reset}     Pull a new harness version")
    print(f"  {bold}rollback{reset}    Pin to the previous version")
    print()
    print(f"  {bold}--version{reset}   Print version + exit")
    print(f"  {bold}--help, -h{reset}  This message")
    print()
    print(f"  {dim}NO_COLOR=1{reset}   Disable color output")
    print(f"  {dim}--no-color{reset}   Disable color output for this invocation")
    print()
    print("Run `harness <command> --help` for command-specific help.")
    print("Exit codes: see docs/EXIT_CODES.md")


def _dispatch_unimplemented(verb: str) -> int:
    """A verb that's reserved but not yet implemented. Print a friendly
    notice (not an error) so the user knows it's planned."""
    plan_map = {
        "init": "Sprint 1 / S1.2",
        "check": "Sprint 1 / S1.3",
        "fix": "Sprint 2 / S2.3",
        "rules": "Sprint 1 / S1.4",
        "baseline": "Sprint 1 / S1.4",
        "telemetry": "Sprint 1 / S1.4",
        "doctor": "Sprint 1 / S1.4",
        "upgrade": "Sprint 1 / S1.4",
        "rollback": "Sprint 1 / S1.4",
    }
    when = plan_map.get(verb, "a future sprint")
    print(
        f"`harness {verb}` is reserved but not yet implemented; "
        f"coming in {when}.",
        file=sys.stderr,
    )
    print(
        "Roadmap: "
        "https://github.com/inder1991/ai-harness/blob/main/"
        "docs/plans/2026-04-29-harness-v2.0-production-roadmap.md",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Dispatch to a subcommand. Exit 0 on success, 2 on bad input.

    Args:
        argv: Argument list excluding the program name. Defaults to
            `sys.argv[1:]` when None (the standard pattern).

    Returns:
        Process exit code. See docs/EXIT_CODES.md for the table.
    """
    if argv is None:
        argv = sys.argv[1:]

    # Strip --no-color early; it's a global flag.
    if "--no-color" in argv:
        os.environ["NO_COLOR"] = "1"
        argv = [a for a in argv if a != "--no-color"]

    if not argv or argv[0] in ("-h", "--help"):
        _print_help()
        return 0

    if argv[0] in ("--version", "-V"):
        print(f"ai-harness {_read_version()}")
        return 0

    verb = argv[0]
    if verb not in VERBS:
        # Did the user type something close? Suggest the nearest verb.
        from difflib import get_close_matches
        suggestions = get_close_matches(verb, VERBS, n=1, cutoff=0.6)
        suggestion = f" Did you mean `harness {suggestions[0]}`?" if suggestions else ""
        print(
            f"unknown command '{verb}'.{suggestion}\n"
            f"Run `harness --help` for the list of available commands.",
            file=sys.stderr,
        )
        return 2

    if verb in IMPLEMENTED:
        # Future stories register entrypoints here.
        from tools.cli import dispatch  # noqa: PLC0415  -- lazy import
        return dispatch(verb, argv[1:])

    return _dispatch_unimplemented(verb)


if __name__ == "__main__":
    raise SystemExit(main())
