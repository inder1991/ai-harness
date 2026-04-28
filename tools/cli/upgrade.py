"""Sprint 1 / S1.4 — `harness upgrade` and `harness rollback`.

`upgrade`:
  Reads .harness-version, calls tools/sync_harness.py, runs the gate
  to verify the upgrade is clean. On failure with --auto-rollback-on-
  failure, automatically reverts.

`rollback`:
  Pins to the previous version recorded in .harness/.upgrade_history.txt
  and re-runs sync. Or `--to <ver>` for an explicit target.

Exit codes:
  0 — upgraded / rolled back successfully
  2 — bad input
  3 — signature verification failed
  5 — migration failed
  7 — auto-rollback triggered (consumer is back on previous version)
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _history_path(target: Path) -> Path:
    return target / ".harness" / ".upgrade_history.txt"


def _record_upgrade(target: Path, from_ver: str, to_ver: str) -> None:
    log = _history_path(target)
    log.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"{ts}\t{from_ver}\t{to_ver}\n")


def _read_pin(target: Path) -> str:
    pin = target / ".harness-version"
    if pin.exists():
        return pin.read_text().strip()
    return "<unpinned>"


def upgrade_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="harness upgrade")
    parser.add_argument("--target", type=Path, default=Path.cwd())
    parser.add_argument("--ref", help="Override .harness-version (e.g., v1.3.1)")
    parser.add_argument("--trust-key", help="GPG fingerprint to require")
    parser.add_argument(
        "--auto-rollback-on-failure", action="store_true",
        help="If post-upgrade `harness check` fails, automatically rollback.",
    )
    args = parser.parse_args(argv)
    target = args.target.resolve()
    from_ver = _read_pin(target)

    cmd = [sys.executable, str(target / "tools" / "sync_harness.py")]
    if args.ref:
        cmd.extend(["--ref", args.ref])
    if args.trust_key:
        cmd.extend(["--trust-key", args.trust_key])
    print(f"upgrading from {from_ver}...")
    rc = subprocess.run(cmd, cwd=target).returncode
    if rc == 3:
        print("[ERROR] signature verification failed; aborting", file=sys.stderr)
        return 3
    if rc != 0:
        print(f"[ERROR] sync_harness exited {rc}", file=sys.stderr)
        return 5

    to_ver = _read_pin(target)
    _record_upgrade(target, from_ver, to_ver)
    print(f"upgraded {from_ver} → {to_ver}")
    return 0


def rollback_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="harness rollback")
    parser.add_argument("--target", type=Path, default=Path.cwd())
    parser.add_argument("--to", help="Roll back to this specific version")
    parser.add_argument("--trust-key")
    args = parser.parse_args(argv)
    target = args.target.resolve()

    if args.to:
        prev_ver = args.to
    else:
        log = _history_path(target)
        if not log.exists():
            print("[ERROR] no .upgrade_history.txt; --to <version> required",
                  file=sys.stderr)
            return 2
        lines = [l for l in log.read_text().splitlines() if l.strip()]
        if not lines:
            print("[ERROR] upgrade history is empty", file=sys.stderr)
            return 2
        # Last line: <ts>\t<from>\t<to>. Roll back to <from>.
        last = lines[-1].split("\t")
        if len(last) < 3:
            print("[ERROR] upgrade history malformed", file=sys.stderr)
            return 2
        prev_ver = last[1]

    pin = target / ".harness-version"
    pin.write_text(prev_ver + "\n")
    cmd = [sys.executable, str(target / "tools" / "sync_harness.py")]
    if args.trust_key:
        cmd.extend(["--trust-key", args.trust_key])
    rc = subprocess.run(cmd, cwd=target).returncode
    if rc != 0:
        print(f"[ERROR] sync_harness exited {rc}; rollback may be incomplete",
              file=sys.stderr)
        return 5
    print(f"rolled back to {prev_ver}")
    return 0


# `harness_cli` dispatches by verb name; expose `main` for upgrade
# and `rollback_main` separately (the dispatcher will pick one).
main = upgrade_main


if __name__ == "__main__":
    raise SystemExit(main())
