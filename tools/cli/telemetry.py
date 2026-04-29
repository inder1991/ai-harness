"""Sprint 1 / S1.4 — `harness telemetry`.

Reads the rolling failure log (`.harness/.failure-log.jsonl`) and
produces summaries.

Privacy: Sprint 6 (S6.1) adds opt-in consent for cross-machine
aggregation. Today this command operates on the local log only.
Empty / corrupt log entries are skipped with a [WARN].
Future-dated entries are ignored (clock-skew guard).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_entries(log_path: Path) -> list[dict]:
    """Load valid entries; skip corrupt lines + future-dated entries with [WARN]."""
    if not log_path.exists():
        return []
    out: list[dict] = []
    skipped = 0
    future = 0
    now = datetime.now(timezone.utc)
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        try:
            ts = datetime.fromisoformat(entry["ts"])
            if ts > now + timedelta(minutes=5):
                future += 1
                continue
        except (KeyError, ValueError):
            skipped += 1
            continue
        out.append(entry)
    if skipped:
        print(f"[WARN] skipped {skipped} corrupt log entries", file=sys.stderr)
    if future:
        print(f"[WARN] ignored {future} future-dated entries (clock skew?)",
              file=sys.stderr)
    return out


def _slow_checks(args: argparse.Namespace) -> int:
    """Sprint 3 / S3.5 — surface per-check duration percentiles from
    .harness/.trace.jsonl. Useful for `harness doctor` flagging "check X
    is consistently the slowest"."""
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    from observability import TRACE_PATH, read_events
    events = read_events(TRACE_PATH)
    if not events:
        print(
            "no trace events yet — run `harness check --trace` to populate "
            ".harness/.trace.jsonl"
        )
        return 0
    by_check: dict[str, list[float]] = {}
    for e in events:
        by_check.setdefault(e["check"], []).append(e["duration_ms"])
    rows = sorted(
        ((name, sum(ds) / len(ds), max(ds), len(ds))
         for name, ds in by_check.items()),
        key=lambda r: r[1], reverse=True,
    )
    if args.json:
        print(json.dumps(
            [{"check": n, "avg_ms": a, "max_ms": m, "n": c}
             for n, a, m, c in rows],
            indent=2, sort_keys=True,
        ))
        return 0
    total = sum(len(v) for v in by_check.values())
    print(f"\nSlowest checks ({total} events total):\n")
    print(f"  {'Check':40} {'Avg ms':>10} {'Max ms':>10} {'#':>5}")
    for name, avg_ms, max_ms, n in rows[:20]:
        print(f"  {name:40} {avg_ms:>10.0f} {max_ms:>10.0f} {n:>5}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="harness telemetry")
    parser.add_argument("--since", type=str,
                        help="ISO date (e.g., 2026-04-01) — only entries since this date.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--slow-checks", action="store_true",
        help="Read .harness/.trace.jsonl and report per-check duration percentiles.",
    )
    args = parser.parse_args(argv)

    if args.slow_checks:
        return _slow_checks(args)

    log = REPO_ROOT / ".harness" / ".failure-log.jsonl"
    entries = _load_entries(log)
    if not entries:
        print("no telemetry yet — run `harness check` a few times to populate.")
        return 0

    if args.since:
        try:
            cutoff = datetime.fromisoformat(args.since)
            if cutoff.tzinfo is None:
                cutoff = cutoff.replace(tzinfo=timezone.utc)
        except ValueError:
            print(f"[ERROR] --since must be ISO format (got: {args.since})",
                  file=sys.stderr)
            return 2
        entries = [e for e in entries
                   if datetime.fromisoformat(e["ts"]) >= cutoff]

    if not entries:
        print("no entries in the requested range.")
        return 0

    if args.json:
        counts = Counter(e["rule"] for e in entries)
        print(json.dumps({
            "total": len(entries),
            "by_rule": dict(counts.most_common()),
        }, indent=2, sort_keys=True))
        return 0

    counts = Counter(e["rule"] for e in entries)
    seven_days = datetime.now(timezone.utc) - timedelta(days=7)
    recent = [e for e in entries
              if datetime.fromisoformat(e["ts"]) >= seven_days]

    print(f"\nTotal entries: {len(entries)}")
    print(f"Last 7 days:   {len(recent)}")
    print()
    print("Top firing rules:")
    for rule, n in counts.most_common(10):
        print(f"  {rule:50} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
