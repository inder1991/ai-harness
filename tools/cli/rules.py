"""Sprint 1 / S1.4 — `harness rules`.

  harness rules                 — table of every rule with severity + status
  harness rules explain <id>    — full why/fix for one rule
  harness rules show-fixtures <id> — print the violation + compliant fixtures
  harness rules trending        — last-7-days fire-count delta from failure log
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_severity_map() -> dict:
    path = REPO_ROOT / ".harness" / "severity_map.yaml"
    if not path.exists():
        return {"rules": {}}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {"rules": {}}
    except (OSError, yaml.YAMLError) as exc:
        print(f"[WARN] could not parse {path}: {exc}", file=sys.stderr)
        return {"rules": {}}


def _list_rules(args: argparse.Namespace) -> int:
    """Print a table of every rule with its tier."""
    rules = _load_severity_map().get("rules", {})
    if args.json:
        print(json.dumps(rules, indent=2, sort_keys=True))
        return 0
    by_tier: dict[str, list[str]] = {}
    for rule_id, entry in rules.items():
        by_tier.setdefault(entry.get("tier", "uncategorized"), []).append(rule_id)
    for tier in ("P0_security", "P1_correctness", "P2_quality", "P3_style", "uncategorized"):
        ids = sorted(by_tier.get(tier, []))
        if not ids:
            continue
        print(f"\n{tier} ({len(ids)})")
        for rid in ids:
            print(f"  {rid}")
    print(f"\nTotal: {sum(len(v) for v in by_tier.values())} rules")
    return 0


def _explain(args: argparse.Namespace) -> int:
    rules = _load_severity_map().get("rules", {})
    entry = rules.get(args.rule_id)
    if not entry:
        print(f"unknown rule: {args.rule_id}", file=sys.stderr)
        return 2
    print(f"\n{args.rule_id}")
    print(f"  Tier:  {entry.get('tier')}")
    print(f"\n  Why:")
    for line in (entry.get("why") or "").splitlines():
        print(f"    {line}")
    print(f"\n  Fix:  {entry.get('fix_hint')}")
    print()
    return 0


def _show_fixtures(args: argparse.Namespace) -> int:
    """Print the violation + compliant fixtures for a check."""
    # Map rule prefix → check name. For a rule like "Q13.route-needs-auth",
    # the check is `security_policy_b.py` (which emits Q13.route-needs-*).
    # We don't have a perfect rule→check map; for now, scan checks and
    # find which one emits the rule.
    checks_dir = REPO_ROOT / ".harness" / "checks"
    rule_id = args.rule_id
    check_name = None
    for path in checks_dir.glob("*.py"):
        if path.name in {"_common.py", "__init__.py"}:
            continue
        if f'"{rule_id}"' in path.read_text(encoding="utf-8"):
            check_name = path.stem
            break
    if not check_name:
        print(f"no check emits {rule_id}", file=sys.stderr)
        return 2
    fixture_root = REPO_ROOT / "tests" / "harness" / "fixtures" / check_name
    print(f"\nFixtures for {rule_id} (check: {check_name}):\n")
    for variant in ("compliant", "violation"):
        d = fixture_root / variant
        if not d.is_dir():
            print(f"  {variant}/: (none)")
            continue
        print(f"  {variant}/:")
        for f in sorted(d.iterdir()):
            print(f"    {f.relative_to(REPO_ROOT)}")
    return 0


def _trending(args: argparse.Namespace) -> int:
    """Last-7-days fire-count delta from .harness/.failure-log.jsonl."""
    log = REPO_ROOT / ".harness" / ".failure-log.jsonl"
    if not log.exists():
        print(
            "no telemetry yet — run `harness check` a few times "
            "(failure log will populate)."
        )
        return 0
    entries = []
    for line in log.read_text(encoding="utf-8").splitlines():
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if len(entries) < 10:
        print(
            f"not enough telemetry yet (need 10+ findings; you have {len(entries)})."
        )
        return 0
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)
    recent = [
        e for e in entries
        if datetime.fromisoformat(e["ts"]) >= seven_days_ago
    ]
    counts = Counter(e["rule"] for e in recent)
    print(f"\nLast 7 days ({len(recent)} findings):")
    for rule, n in counts.most_common(10):
        print(f"  {rule:50} {n}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="harness rules")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON instead of human-readable text.")
    sub = parser.add_subparsers(dest="subcommand")

    sub.add_parser("explain", help="Show why+fix for a rule"
                   ).add_argument("rule_id", help="e.g., Q13.route-needs-auth")
    sub.add_parser("show-fixtures", help="Print fixtures for a rule"
                   ).add_argument("rule_id")
    sub.add_parser("trending", help="Last-7-days fire counts")

    args = parser.parse_args(argv)
    if args.subcommand == "explain":
        return _explain(args)
    if args.subcommand == "show-fixtures":
        return _show_fixtures(args)
    if args.subcommand == "trending":
        return _trending(args)
    return _list_rules(args)


if __name__ == "__main__":
    raise SystemExit(main())
