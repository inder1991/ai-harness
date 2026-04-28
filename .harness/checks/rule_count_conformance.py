#!/usr/bin/env python3
"""v1.3.0 S3 / Q22 — doc-vs-impl rule-count conformance.

One rule:
  Q22.doc-rule-count-mismatch
      A check's module docstring claims "N rules" but enumerates a
      different number of distinct `Q\\d+\\.[a-z][a-z0-9-]+` /
      `H\\d+\\.[a-z][a-z0-9-]+` rule IDs. Catches the recurring drift
      that v1.0.x audit found in 3+ checks (S-A9, S-AS1, S-DB1).

H-25:
  Missing input    — silently return 0 if .harness/checks/ missing.
  Malformed input  — WARN harness.unparseable on bad source.
  Upstream failed  — none.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from _common import emit, load_baseline, normalize_path  # noqa: E402

CHECKS_DIR = REPO_ROOT / ".harness" / "checks"
SELF_NAME = "rule_count_conformance.py"
EXEMPT_NAMES = {
    "_common.py", "__init__.py", SELF_NAME,
}
# Allow camelCase + kebab-case rule suffixes (e.g.,
# `Q6.useNavigate-not-at-top-level`).
RULE_ID_RE = re.compile(r'\b(Q\d+\.[A-Za-z][A-Za-z0-9_-]+|H\d+\.[A-Za-z][A-Za-z0-9_-]+)\b')
# Match `N rule(s)` / `N rules enforced` etc. in the leading docstring.
COUNT_RE = re.compile(
    r'\b(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|\d+)\s+rules?\b',
    re.IGNORECASE,
)
WORD_TO_INT = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
BASELINE = load_baseline("rule_count_conformance")


def _emit(file: Path, rule: str, msg: str, suggestion: str, line: int) -> bool:
    sig = (normalize_path(file), int(line), rule)
    if sig in BASELINE:
        return False
    emit("ERROR", file, rule, msg, suggestion, line=line)
    return True


def _parse_count(token: str) -> int | None:
    token = token.strip().lower()
    if token.isdigit():
        return int(token)
    return WORD_TO_INT.get(token)


def _scan_check(path: Path) -> int:
    """Compare the docstring's claimed rule count vs the count of
    distinct rule IDs enumerated in that same docstring."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeDecodeError):
        return 0
    except SyntaxError:
        emit("WARN", path, "harness.unparseable",
             f"could not parse {path.name}", "fix syntax", line=1)
        return 0
    docstring = ast.get_docstring(tree, clean=False) or ""
    if not docstring.strip():
        return 0
    m = COUNT_RE.search(docstring)
    if not m:
        return 0  # check doesn't make a numeric rule-count claim
    claimed = _parse_count(m.group(1))
    if claimed is None:
        return 0
    distinct_rules = {match.group(0) for match in RULE_ID_RE.finditer(docstring)}
    enumerated = len(distinct_rules)
    if enumerated == 0:
        # The docstring claims a count but doesn't list any IDs — that's
        # a different shape (e.g., a free-form description). Don't fire.
        return 0
    if claimed != enumerated:
        if _emit(path, "Q22.doc-rule-count-mismatch",
                 f"docstring claims {claimed} rules but enumerates {enumerated} "
                 f"({sorted(distinct_rules)})",
                 "update the docstring count or add the missing rule enumeration",
                 line=1):
            return 1
    return 0


def main() -> int:
    """Walk .harness/checks/*.py; emit Q22 on docstring count drift."""
    if not CHECKS_DIR.is_dir():
        return 0
    errors = 0
    for path in sorted(CHECKS_DIR.glob("*.py")):
        if path.name in EXEMPT_NAMES:
            continue
        errors += _scan_check(path)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
