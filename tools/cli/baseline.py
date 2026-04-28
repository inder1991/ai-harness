"""Sprint 1 / S1.4 — `harness baseline`.

  baseline refresh   — wraps tools/refresh_baselines.py
  baseline show      — list baseline entries (optionally filter by rule)
  baseline add       — add ONE suppression with required --reason
  baseline prune     — drop entries that no longer match any code

The `_REASONS.md` audit log is appended to on every `add`. The
`Q23.baseline-missing-reason` self-test (planned) enforces consistency.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINES_DIR = REPO_ROOT / ".harness" / "baselines"
REASONS_LOG = BASELINES_DIR / "_REASONS.md"


def _refresh(args: argparse.Namespace) -> int:
    cmd = [sys.executable, str(REPO_ROOT / "tools" / "refresh_baselines.py")]
    return subprocess.run(cmd, timeout=600).returncode


def _show(args: argparse.Namespace) -> int:
    if not BASELINES_DIR.exists():
        print("no baselines/ directory yet")
        return 0
    rule_filter = args.rule
    total = 0
    for path in sorted(BASELINES_DIR.glob("*_baseline.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            print(f"[WARN] {path.name}: unparseable", file=sys.stderr)
            continue
        if not isinstance(data, list):
            continue
        matching = [e for e in data if not rule_filter or e.get("rule") == rule_filter]
        if matching:
            print(f"\n{path.name}: {len(matching)} entries")
            for e in matching[:5]:
                print(f"  {e.get('rule')} @ {e.get('file')}:{e.get('line')}")
            if len(matching) > 5:
                print(f"  …and {len(matching) - 5} more")
            total += len(matching)
    print(f"\nTotal: {total} entries")
    return 0


def _add(args: argparse.Namespace) -> int:
    if not args.reason or not args.reason.strip():
        print("[ERROR] --reason is required (and may not be empty)",
              file=sys.stderr)
        return 2
    try:
        file, line_str = args.location.rsplit(":", 1)
        line = int(line_str)
    except (ValueError, AttributeError):
        print(f"[ERROR] location must be 'file:line' (got: {args.location!r})",
              file=sys.stderr)
        return 2

    # Pick the right baseline file. Convention: rule_id like Q13.x → check
    # whose stem emits Q13.x. For now, use the rule ID prefix as a best guess.
    # Sprint 4+ may improve this with a manifest.
    # Find which baseline file already contains entries for this rule.
    target_baseline = None
    for path in sorted(BASELINES_DIR.glob("*_baseline.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if any(e.get("rule") == args.rule for e in data):
            target_baseline = path
            break
    if target_baseline is None:
        print(f"[ERROR] no existing baseline contains rule {args.rule}; "
              f"pick a specific check's baseline file manually",
              file=sys.stderr)
        return 2

    data = json.loads(target_baseline.read_text())
    new_entry = {"file": file, "line": line, "rule": args.rule}
    if new_entry in data:
        print(f"already baselined: {args.rule} @ {file}:{line}")
        return 0
    data.append(new_entry)
    data.sort(key=lambda e: (e["file"], e["line"], e["rule"]))
    target_baseline.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n"
    )

    # Append to _REASONS.md.
    REASONS_LOG.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    block = (
        f"\n## {today}\n"
        f"- **Rule:** {args.rule}\n"
        f"- **Site:** {file}:{line}\n"
        f"- **Reason:** {args.reason}\n"
    )
    if args.tracking:
        block += f"- **Tracking:** {args.tracking}\n"
    if not REASONS_LOG.exists():
        REASONS_LOG.write_text(
            "# Baseline reasons\n\n"
            "Every `harness baseline add` invocation appends a block here.\n"
        )
    with REASONS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(block)

    print(f"baselined: {args.rule} @ {file}:{line}")
    print(f"reason logged to: {REASONS_LOG.relative_to(REPO_ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="harness baseline")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    sub.add_parser("refresh", help="Re-snapshot all baselines")
    show = sub.add_parser("show", help="List baseline entries")
    show.add_argument("--rule", help="Filter by rule ID")

    add = sub.add_parser("add", help="Add ONE suppression")
    add.add_argument("rule", help="Rule ID, e.g., Q13.route-needs-auth")
    add.add_argument("location", help="file:line, e.g., backend/x.py:42")
    add.add_argument("--reason", required=True,
                     help="Why is this suppression justified? (required)")
    add.add_argument("--tracking", help="Tracking ticket ID (optional)")

    sub.add_parser("prune", help="Drop entries that no longer match any code")

    args = parser.parse_args(argv)
    if args.subcommand == "refresh":
        return _refresh(args)
    if args.subcommand == "show":
        return _show(args)
    if args.subcommand == "add":
        return _add(args)
    if args.subcommand == "prune":
        print("[INFO] `harness baseline prune` is reserved (Sprint 1.X)")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
