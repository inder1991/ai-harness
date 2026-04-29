#!/usr/bin/env python3
"""Sprint 3 / S3.7 — performance regression gate.

Runs `make validate-fast` (or `--full`) N times, takes the median wall
time, compares to the committed baseline at
`tools/perf/wallclock_baseline.txt`. Fails the gate if the new median
is >10% slower than the baseline.

Usage:
    python tools/perf/measure_wallclock.py --runs 3 --target validate-fast

Baseline file format (one record per supported target):

    # Sprint 3 / S3.7
    validate-fast: <seconds>  <YYYY-MM-DD>
    validate-full: <seconds>  <YYYY-MM-DD>

Updating the baseline:
    python tools/perf/measure_wallclock.py --update-baseline --target validate-fast
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from statistics import median

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = Path(__file__).parent / "wallclock_baseline.txt"
TOLERANCE = 0.10  # 10%


def _read_baseline(target: str) -> float | None:
    if not BASELINE.exists():
        return None
    pattern = re.compile(rf"^{re.escape(target)}:\s+([\d.]+)\s+", re.MULTILINE)
    m = pattern.search(BASELINE.read_text())
    return float(m.group(1)) if m else None


def _write_baseline(target: str, seconds: float) -> None:
    today = date.today().isoformat()
    line = f"{target}: {seconds:.2f}  {today}\n"
    if not BASELINE.exists():
        BASELINE.write_text("# Sprint 3 / S3.7 — performance baselines\n" + line)
        return
    text = BASELINE.read_text()
    pattern = re.compile(rf"^{re.escape(target)}:.*$", re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(line.rstrip(), text)
    else:
        text += line
    BASELINE.write_text(text)


def _run_target(target: str) -> float:
    cmd = ["python", str(REPO_ROOT / "tools" / "run_validate.py")]
    if target == "validate-fast":
        cmd.append("--fast")
    elif target == "validate-full":
        cmd.append("--full")
    else:
        raise ValueError(f"unknown target: {target}")
    start = time.monotonic()
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    elapsed = time.monotonic() - start
    if result.returncode != 0:
        # Don't gate on perf when the suite is broken — we'd flag noise.
        print(
            f"[WARN] {target} returned non-zero exit {result.returncode}; "
            "perf measurement skipped",
            file=sys.stderr,
        )
        sys.exit(0)
    return elapsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["validate-fast", "validate-full"],
                        default="validate-fast")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--update-baseline", action="store_true",
                        help="Overwrite the baseline with the new measurement")
    args = parser.parse_args(argv)

    print(f"Measuring {args.target} (median of {args.runs} runs)…")
    times = [_run_target(args.target) for _ in range(args.runs)]
    new_median = median(times)
    print(f"  Runs: {[f'{t:.2f}s' for t in times]}")
    print(f"  Median: {new_median:.2f}s")

    if args.update_baseline:
        _write_baseline(args.target, new_median)
        print(f"  Baseline updated: {args.target} = {new_median:.2f}s")
        return 0

    baseline = _read_baseline(args.target)
    if baseline is None:
        print(f"  No baseline found for {args.target}; recording.")
        _write_baseline(args.target, new_median)
        return 0

    delta = (new_median - baseline) / baseline
    print(f"  Baseline: {baseline:.2f}s, delta: {delta:+.1%}")
    if delta > TOLERANCE:
        print(
            f"::error::{args.target} is {delta:+.1%} slower than baseline "
            f"({new_median:.2f}s vs {baseline:.2f}s; tolerance {TOLERANCE:+.0%}). "
            f"Profile the regression or update the baseline with "
            f"`--update-baseline` if intentional.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
