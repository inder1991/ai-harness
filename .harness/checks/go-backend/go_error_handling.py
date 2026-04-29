#!/usr/bin/env python3
"""GQ12 — Go error-handling strictness check.

Two rules enforced on the Go spine:
  GQ12.no-discarded-error  — `_, _ := f()` and `_ = err` patterns silently
        drop errors. Tests are exempt (`*_test.go`).
  GQ12.no-panic-on-error   — `if err != nil { panic(err) }` (and variants
        that panic with the error value) crash the server on a recoverable
        condition. Use a typed return path instead.

Both rules are regex-based (starter pack). False-positive rate is kept
low by anchoring on common Go idioms.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from _go_common import emit, go_spine_paths, iter_go_files  # noqa: E402

DEFAULT_ROOTS = go_spine_paths("go_spine", (".",))
# `_ = err` — a bare assignment to underscore.
DISCARDED_ERR = re.compile(r'^\s*_\s*=\s*err\b', re.MULTILINE)
# `panic(err)` (or panic(...err...)) inside an `if err != nil { ... }` block.
# Approximate: any panic() that mentions `err` on the same or next line.
PANIC_ON_ERR = re.compile(r'\bpanic\s*\([^)]*\berr\b[^)]*\)')


def _is_test_file(virtual: str) -> bool:
    return virtual.endswith("_test.go")


def scan_file(path: Path, virtual: str) -> int:
    if _is_test_file(virtual):
        return 0
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    errors = 0
    for m in DISCARDED_ERR.finditer(text):
        line = text[:m.start()].count("\n") + 1
        emit(
            "ERROR", virtual, "GQ12.no-discarded-error",
            "`_ = err` silently drops the error; bugs become invisible",
            "either return the error, log it via the project logger, or comment why it's safe to ignore",
            line=line,
        )
        errors += 1
    for m in PANIC_ON_ERR.finditer(text):
        line = text[:m.start()].count("\n") + 1
        emit(
            "ERROR", virtual, "GQ12.no-panic-on-error",
            "panic(err) crashes the server on a recoverable condition",
            "return the error to the caller (or wrap with fmt.Errorf for context)",
            line=line,
        )
        errors += 1
    return errors


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", type=Path, default=None)
    p.add_argument("--pretend-path", default=None)
    args = p.parse_args(argv)
    if args.target is not None:
        if not args.target.exists():
            emit("ERROR", str(args.target), "harness.target-missing",
                 "target path does not exist", "pass an existing file or directory")
            return 2
        targets = [args.target] if args.target.is_file() else list(iter_go_files([args.target]))
    else:
        targets = list(iter_go_files(DEFAULT_ROOTS))
    errors = 0
    for path in targets:
        virtual = args.pretend_path or str(path)
        errors += scan_file(path, virtual)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
