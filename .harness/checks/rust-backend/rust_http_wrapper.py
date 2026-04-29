#!/usr/bin/env python3
"""RQ7 — Rust HTTP-wrapper boundary check.

One rule enforced on the Rust spine:
  RQ7.no-reqwest-outside-wrapper — `use reqwest` and `use hyper` outside
        the canonical http module (default `src/http/`) bypass the
        retry/timeout/correlation-id substrate.
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
DEFAULT_WRAPPER_PREFIXES = ("src/http/", "src/client/", "crates/http/")
USE_HTTP_LIB = re.compile(r'^\s*use\s+(reqwest|hyper)\b', re.MULTILINE)


def _is_wrapper(virtual: str, prefixes: tuple[str, ...]) -> bool:
    return any(seg in virtual for seg in prefixes)


def scan_file(path: Path, virtual: str, wrapper_prefixes: tuple[str, ...]) -> int:
    if _is_wrapper(virtual, wrapper_prefixes):
        return 0
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    errors = 0
    for m in USE_HTTP_LIB.finditer(text):
        line = text[:m.start()].count("\n") + 1
        emit(
            "ERROR", virtual, "RQ7.no-reqwest-outside-wrapper",
            f"direct `use {m.group(1)}` bypasses the retry/timeout wrapper",
            f"import the http client from {wrapper_prefixes[0]} instead",
            line=line,
        )
        errors += 1
    return errors


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", type=Path, default=None)
    p.add_argument("--pretend-path", default=None)
    p.add_argument("--wrapper-prefix", action="append", default=None)
    args = p.parse_args(argv)
    wrapper = tuple(args.wrapper_prefix) if args.wrapper_prefix else DEFAULT_WRAPPER_PREFIXES
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
        errors += scan_file(path, virtual, wrapper)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
