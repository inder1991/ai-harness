"""Sprint 2 / S2.3 — `harness fix`.

  harness fix <rule> --files <file1,file2> [--apply | -y]

By default shows the diff and exits without mutating. `--apply` (or
`-y`) writes the change after the safety contract passes.

Exit codes:
  0  — diff shown OR fix applied + post-fix re-check clean
  1  — post-fix re-check found cascade findings the user must address
  2  — bad input / rule has no auto-fixer / file changed mid-fix
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from auto_fix import FIXERS, fix as run_fix  # noqa: E402
from output_formatter import Finding  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="harness fix")
    parser.add_argument("rule", help="Rule ID (e.g., Q15.spine-docstring-required)")
    parser.add_argument(
        "--files", required=True,
        help="Comma-separated list of files to fix",
    )
    parser.add_argument(
        "--line", type=int, default=1,
        help="Line number (used by some fixers; default 1)",
    )
    parser.add_argument(
        "--apply", "-y", action="store_true",
        help="Write the fix (default: diff only)",
    )
    args = parser.parse_args(argv)

    if args.rule not in FIXERS:
        print(
            f"`{args.rule}` has no auto-fixer; see "
            f"`harness rules explain {args.rule}` for a manual fix.",
            file=sys.stderr,
        )
        return 2

    overall = 0
    for file in args.files.split(","):
        file = file.strip()
        finding = Finding(rule=args.rule, location=f"{file}:{args.line}")
        result = run_fix(args.rule, file, finding, apply=args.apply)
        if result.error:
            print(f"[ERROR] {file}: {result.error}", file=sys.stderr)
            overall = max(overall, 2)
            continue
        if result.diff:
            print(result.diff)
        if result.applied:
            print(f"[INFO] applied {args.rule} to {file}")
        elif args.apply and not result.applied:
            print(f"[INFO] no change for {file}", file=sys.stderr)
    return overall


if __name__ == "__main__":
    raise SystemExit(main())
