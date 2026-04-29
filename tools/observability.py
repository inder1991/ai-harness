"""Sprint 3 / S3.5 — observability for the orchestrator.

When `harness check --trace` is invoked, every check's invocation
emits a structured event to `.harness/.trace.jsonl`:

    {ts, check, start_ms, duration_ms, exit_code, n_findings}

The trace file is gitignored; rotation kicks in at 10 MB; concurrent
writers are serialized via fcntl.LOCK_EX (the same B2/B10-pattern
already in run_validate's failure-log writer).

Used by:
  - `harness telemetry --slow-checks`  (find checks > 5s)
  - `harness doctor`                    ("check X is consistently slowest")

Trace is opt-in. Without --trace (or HARNESS_TRACE=1), no file is
created. Production / consumer environments don't pay for this unless
the operator asks.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TRACE_PATH = REPO_ROOT / ".harness" / ".trace.jsonl"
TRACE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB rotation threshold

try:
    import fcntl as _fcntl
    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover — Windows fallback
    _HAVE_FCNTL = False


def trace_enabled() -> bool:
    """True iff --trace flag set OR HARNESS_TRACE=1 env present."""
    if os.environ.get("HARNESS_TRACE") in ("1", "true", "yes"):
        return True
    return False


def enable_trace() -> None:
    """Mark this process as tracing. Called from `harness check --trace`
    after argparse runs, before subprocess spawns. Sets HARNESS_TRACE=1
    so child orchestrator subprocesses inherit it."""
    os.environ["HARNESS_TRACE"] = "1"


def _rotate_if_needed(path: Path) -> None:
    """Same pattern as run_validate._rotate_failure_log (B10)."""
    if not path.exists():
        return
    if not _HAVE_FCNTL:
        try:
            if path.stat().st_size > TRACE_MAX_BYTES:
                rotated = path.with_suffix(path.suffix + ".1")
                if rotated.exists():
                    rotated.unlink()
                path.rename(rotated)
        except OSError:
            pass
        return
    try:
        with path.open("a+", encoding="utf-8") as fh:
            _fcntl.flock(fh.fileno(), _fcntl.LOCK_EX)
            try:
                if path.stat().st_size <= TRACE_MAX_BYTES:
                    return
                rotated = path.with_suffix(path.suffix + ".1")
                if rotated.exists():
                    try:
                        rotated.unlink()
                    except OSError:
                        pass
                path.rename(rotated)
            finally:
                _fcntl.flock(fh.fileno(), _fcntl.LOCK_UN)
    except OSError:
        # Q17-EXEMPT: rotation must never abort `harness check`.
        pass


def emit_event(
    check: str,
    start_ms: float,
    duration_ms: float,
    exit_code: int,
    n_findings: int,
) -> None:
    """Append one trace event under fcntl.LOCK_EX (concurrent-safe).

    Args:
        check: check name (e.g., "security_policy_a")
        start_ms: monotonic-clock millis at start
        duration_ms: how long the subprocess took
        exit_code: subprocess exit code
        n_findings: number of [ERROR] lines emitted
    """
    if not trace_enabled():
        return
    _rotate_if_needed(TRACE_PATH)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "check": check,
        "start_ms": start_ms,
        "duration_ms": duration_ms,
        "exit_code": exit_code,
        "n_findings": n_findings,
    }
    try:
        TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with TRACE_PATH.open("a", encoding="utf-8") as fh:
            if _HAVE_FCNTL:
                _fcntl.flock(fh.fileno(), _fcntl.LOCK_EX)
                try:
                    fh.write(json.dumps(entry, sort_keys=True) + "\n")
                finally:
                    _fcntl.flock(fh.fileno(), _fcntl.LOCK_UN)
            else:
                fh.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError:
        # Q17-EXEMPT: trace write must never abort `harness check`.
        pass


def read_events(path: Path | None = None) -> list[dict]:
    """Read every event; skip corrupt JSONL lines with [WARN]."""
    p = path or TRACE_PATH
    if not p.exists():
        return []
    out: list[dict] = []
    skipped = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            skipped += 1
    if skipped:
        print(f"[WARN] skipped {skipped} corrupt trace entries", file=sys.stderr)
    return out
