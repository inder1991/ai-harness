#!/usr/bin/env python3
"""RQ12 — Rust error-handling strictness check.

One rule enforced on the Rust spine:
  RQ12.no-unwrap-in-spine — `.unwrap()` and `.expect(...)` calls in
        non-test source files panic on error and crash the server.
        Test files (`#[cfg(test)]` + `tests/` directory) are exempt.

Heuristic: a file is treated as test code if its path contains `/tests/`
or its name ends in `_test.rs`. Inline `#[cfg(test)] mod tests` blocks
are NOT detected by the regex (false negatives in that case are
acceptable for a starter pack).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from _rust_common import emit, iter_rust_files, rust_spine_paths  # noqa: E402

DEFAULT_ROOTS = rust_spine_paths("rust_spine", ("src",))
UNWRAP_OR_EXPECT = re.compile(r'\.(unwrap|expect)\s*\(')


def _is_test_file(virtual: str) -> bool:
    return "/tests/" in virtual or virtual.endswith("_test.rs")


def scan_file(path: Path, virtual: str) -> int:
    if _is_test_file(virtual):
        return 0
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    errors = 0
    for m in UNWRAP_OR_EXPECT.finditer(text):
        line = text[:m.start()].count("\n") + 1
        method = m.group(1)
        emit(
            "ERROR", virtual, "RQ12.no-unwrap-in-spine",
            f"`.{method}()` panics on error; spine code must propagate Result",
            "use `?` or match the Result and return a typed error",
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
        targets = [args.target] if args.target.is_file() else list(iter_rust_files([args.target]))
    else:
        targets = list(iter_rust_files(DEFAULT_ROOTS))
    errors = 0
    for path in targets:
        virtual = args.pretend_path or str(path)
        errors += scan_file(path, virtual)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
