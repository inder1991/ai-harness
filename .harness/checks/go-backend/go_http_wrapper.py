#!/usr/bin/env python3
"""GQ7 — Go HTTP-wrapper boundary check.

One rule enforced on the Go spine:
  GQ7.no-net-http-outside-wrapper — direct `import "net/http"` outside
        the canonical HTTP wrapper directory (default `pkg/httpclient/`)
        bypasses retry / timeout / correlation-id middleware.

The wrapper directory is configurable via --wrapper-prefix.
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
DEFAULT_WRAPPER_PREFIXES = ("pkg/httpclient/", "internal/httpclient/")
NET_HTTP_IMPORT = re.compile(r'^\s*"net/http"', re.MULTILINE)


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
    for m in NET_HTTP_IMPORT.finditer(text):
        line = text[:m.start()].count("\n") + 1
        emit(
            "ERROR", virtual, "GQ7.no-net-http-outside-wrapper",
            "direct net/http import bypasses the timeout/retry wrapper",
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
        targets = [args.target] if args.target.is_file() else list(iter_go_files([args.target]))
    else:
        targets = list(iter_go_files(DEFAULT_ROOTS))
    errors = 0
    for path in targets:
        virtual = args.pretend_path or str(path)
        errors += scan_file(path, virtual, wrapper)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
