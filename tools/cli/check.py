"""Sprint 1 / S1.3 — `harness check` implementation.

Wraps `tools.run_validate` and pipes its H-16 output through the
`tools.output_formatter` module. Exit-code contract is mode-dependent
(see docs/EXIT_CODES.md).

  human       — exit 1 only on P0/P1; warning summary on P2/P3
  json        — always exit 0 (consumer reads the JSON)
  raw         — exit 1 on any finding (legacy v1.x parsers)
  pre-commit  — exit 1 on any finding (preserves v1.x hook behavior)

Mode default:
  - When stdout.isatty(): human
  - When piped:           raw
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from output_formatter import format_findings, parse_h16_output  # noqa: E402


def _default_mode() -> str:
    if not sys.stdout.isatty():
        return "raw"
    return "human"


def main(argv: list[str] | None = None) -> int:
    """Implementation of `harness check`."""
    parser = argparse.ArgumentParser(
        prog="harness check",
        description="Run the validation gate.",
    )
    parser.add_argument(
        "--mode",
        choices=["human", "json", "raw", "pre-commit"],
        default=_default_mode(),
        help="Output format (default: human when tty, raw when piped)",
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Run the full tier (typecheck + heavy checks).",
    )
    args = parser.parse_args(argv)

    # Run the orchestrator. Capture stdout for parsing; show stderr live.
    cmd = [sys.executable, str(REPO_ROOT / "tools" / "run_validate.py")]
    cmd.append("--full" if args.full else "--fast")
    proc = subprocess.run(
        cmd, capture_output=True, text=True,
    )

    findings = parse_h16_output(proc.stdout)
    result = format_findings(findings, mode=args.mode)
    sys.stdout.write(result.text)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
