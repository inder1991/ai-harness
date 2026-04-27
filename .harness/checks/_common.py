"""Shared helpers for .harness/checks/ scripts.

Spine paths (#10): checks should resolve their default scan roots via
`spine_paths(role, fallback)` instead of hardcoding `REPO_ROOT / "backend"`.
This lets a consumer override paths via `.harness/spine_paths.yaml` without
forking the check. The fallback is the previous hardcoded value, kept for
backward compat with consumers that don't yet ship spine_paths.yaml.

Per H-16 / H-23, every check emits structured one-line records:

    [SEVERITY] file=<path>:<line> rule=<rule-id> message="..." suggestion="..."

`emit()` is the single point where that format is constructed, so
changing the format later is a one-file change.

`load_baseline(rule_file_stem)` returns the set of (file, line, rule)
tuples the check should suppress. Per H.1d.6 — first-class baselining of
H.1a/b/c live-repo violations until the underlying code can be migrated.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Iterable, Literal

Severity = Literal["ERROR", "WARN", "INFO"]


class ImportTracker:
    """v1.3.0 (S1) — resolve bound names back to canonical fully-qualified
    module paths.

    Eliminates the import-aliasing blind spot behind 5 audit findings
    (S-A4, S-AS3, S-AS4, S-AS6, S-DB5). Pre-v1.3.0, every check that
    matched `module.function(...)` literal text missed:
      * `import x as y; y(...)` (aliased import)
      * `from m import f; f(...)` (from-import)
      * `from m import f as g; g(...)` (aliased from-import)

    Build one tracker per parsed module:

        tree = ast.parse(source)
        tracker = ImportTracker(tree)

    Then either look up a bound name directly:

        tracker.module_for("Client")  # "httpx.Client" if `from httpx import Client`

    or resolve an arbitrary AST expression (Name or Attribute chain):

        tracker.canonical_for(call.func)  # walks `h.Client` → "httpx.Client"
    """

    def __init__(self, tree: ast.AST) -> None:
        self._bindings: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name.split(".")[0]
                    self._bindings[name] = alias.name
            elif isinstance(node, ast.ImportFrom):
                if not node.module:
                    continue
                for alias in node.names:
                    name = alias.asname or alias.name
                    self._bindings[name] = f"{node.module}.{alias.name}"

    def module_for(self, bound_name: str) -> str | None:
        """Return the canonical module path bound to `name`, or None
        if the name was never imported in this module."""
        return self._bindings.get(bound_name)

    def canonical_for(self, expr: ast.expr) -> str | None:
        """For Name or Attribute chains, return the canonical dotted path.

        Returns None if the chain's head Name isn't a tracked import
        (e.g. local variables, class-instance attributes).

        Example: with `import httpx as h`, the expression
        `h.AsyncClient.get` resolves to `"httpx.AsyncClient.get"`.
        """
        parts: list[str] = []
        cur: ast.expr | None = expr
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if not isinstance(cur, ast.Name):
            return None
        head = self._bindings.get(cur.id)
        if head is None:
            return None
        if not parts:
            return head
        parts.reverse()
        return f"{head}.{'.'.join(parts)}"

REPO_ROOT = Path(__file__).resolve().parents[2]


def normalize_path(file: "Path | str") -> str:
    """B1 hardening — return a repo-relative POSIX path for cross-machine portability.

    Cases:
      * absolute path INSIDE REPO_ROOT → strip prefix, return POSIX form
        (e.g. "/Users/alice/repo/backend/foo.py" → "backend/foo.py")
      * relative path → return POSIX form unchanged
        (e.g. "backend/foo.py" → "backend/foo.py")
      * absolute path OUTSIDE REPO_ROOT → return POSIX form as-is
        (e.g. "/usr/lib/python3.11/site-packages/x.py" stays absolute)

    Always uses forward slashes so Windows ↔ Unix baselines round-trip.
    """
    p = Path(file) if not isinstance(file, Path) else file
    if p.is_absolute():
        try:
            return p.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
        except ValueError:
            return p.as_posix()
    return p.as_posix()


def load_baseline(rule_file_stem: str) -> set[tuple[str, int, str]]:
    """Load `.harness/baselines/<rule_file_stem>_baseline.json` and return a
    set of (file, line, rule) tuples for filtering.

    Each baseline entry must have at least {file, line, rule} keys; extras
    ignored. Empty set on missing/unparseable file.

    B1 hardening: every baseline entry's `file` field is run through
    normalize_path() at READ time. This means:
      * legacy v1.0.x absolute paths from this machine migrate cleanly
        (relative_to(REPO_ROOT) succeeds → entry stored relative)
      * absolute paths from a DIFFERENT machine are dropped with a [WARN]
        to stderr (loud about the breaking change; user re-snapshots via
        `make harness-baseline-refresh` or `--migrate-paths`)
      * already-relative paths (v1.1.0+ format) pass through unchanged
    """
    baseline_path = REPO_ROOT / ".harness/baselines" / f"{rule_file_stem}_baseline.json"
    if not baseline_path.exists():
        return set()
    try:
        data = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(data, list):
        return set()
    repo_root_str = str(REPO_ROOT.resolve())
    out: set[tuple[str, int, str]] = set()
    foreign_dropped = 0
    for entry in data:
        if not (isinstance(entry, dict) and {"file", "line", "rule"} <= set(entry.keys())):
            continue
        raw = str(entry["file"])
        # Detect foreign-machine entries: absolute path with a prefix that's NOT this REPO_ROOT.
        if raw.startswith("/") or (len(raw) >= 2 and raw[1] == ":"):
            if not raw.startswith(repo_root_str + "/") and not raw.startswith(repo_root_str + "\\"):
                # Try resolving anyway in case symlinks differ
                try:
                    Path(raw).resolve().relative_to(REPO_ROOT.resolve())
                except (ValueError, OSError):
                    foreign_dropped += 1
                    continue
        normalized = normalize_path(raw)
        out.add((normalized, int(entry["line"]), str(entry["rule"])))
    if foreign_dropped:
        print(
            f"[WARN] {baseline_path.name}: dropped {foreign_dropped} foreign-machine "
            f"baseline entries (paths outside this repo). Re-snapshot via "
            f"`make harness-baseline-refresh` to regenerate cleanly.",
            file=sys.stderr,
        )
    return out


# B5 hardening — single canonical regex shared by run_validate.py + refresh_baselines.py.
# Anchors on `:LINE rule=` so the file capture (`.+?`) tolerates paths with spaces,
# unicode characters, parentheses, etc. Previously every parser used `\S+?` which
# choked on `path with space/x.py`.
import re as _re
ERROR_LINE_PATTERN = _re.compile(
    r'^\[ERROR\]\s+file=(?P<file>.+?):(?P<line>\d+)\s+rule=(?P<rule>\S+)'
)


def _escape_field(text: str) -> str:
    """Sanitize a message/suggestion field for the H-16 single-line protocol.

    B6 hardening: newlines, carriage returns, and tabs would corrupt the
    line-based emit format (the orchestrator splits on \\n; one finding
    becomes N invalid 'lines'). Replace with literal escape sequences so
    the AI consumer can still un-escape if needed.
    """
    return (
        text.replace('"', "'")
            .replace("\r\n", "\\n")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
    )


def emit(
    severity: Severity,
    file: Path | str,
    rule: str,
    message: str,
    suggestion: str,
    line: int | None = None,
    out=sys.stdout,
) -> None:
    """Write one structured violation record (H-16 / H-23 format).

    B1 hardening: normalizes the file path to repo-relative POSIX form so
    findings AND baseline entries from different machines / OSes share a
    canonical key. Pseudo-paths used for harness-internal diagnostics
    (`gitleaks`, `mypy`, `--target`, `docs/decisions/`) are passed
    through verbatim — they're sentinels, not file paths.
    """
    file_str = str(file)
    is_pseudo = (
        file_str in {"gitleaks", "mypy", "tsc", "git", "--target"}
        or file_str.endswith("/")
        or "://" in file_str
    )
    location_path = file_str if is_pseudo else normalize_path(file)
    location = f"{location_path}:{line}" if line is not None else location_path
    safe_msg = _escape_field(message)
    safe_sug = _escape_field(suggestion)
    print(
        f'[{severity}] file={location} rule={rule} '
        f'message="{safe_msg}" suggestion="{safe_sug}"',
        file=out,
    )


def walk_files(
    roots: Iterable[Path],
    suffixes: tuple[str, ...],
    skip_dirs: tuple[str, ...] = ("node_modules", ".git", "__pycache__", ".venv"),
) -> Iterable[Path]:
    """Yield every file under any of the roots whose suffix matches.

    H-25: handles missing roots silently (no exception) — upstream may
    not have a frontend/ or backend/ layout in every repo.
    """
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in suffixes:
                continue
            if any(part in skip_dirs for part in path.parts):
                continue
            yield path


_SPINE_PATHS_CACHE: dict | None = None


def _load_spine_paths() -> dict:
    """Read .harness/spine_paths.yaml once per process; cache the result."""
    global _SPINE_PATHS_CACHE
    if _SPINE_PATHS_CACHE is not None:
        return _SPINE_PATHS_CACHE
    spine_yaml = REPO_ROOT / ".harness" / "spine_paths.yaml"
    if not spine_yaml.exists():
        _SPINE_PATHS_CACHE = {}
        return _SPINE_PATHS_CACHE
    try:
        import yaml  # local import — kept off the top-level so checks
                     # without a yaml dep aren't penalized
        data = yaml.safe_load(spine_yaml.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 — best-effort; missing yaml lib falls through
        data = {}
    _SPINE_PATHS_CACHE = data
    return data


def spine_paths(role: str, fallback: tuple[str, ...]) -> tuple[Path, ...]:
    """Resolve the consumer's spine paths for `role`.

    Reads `.harness/spine_paths.yaml`; if `role` is declared there,
    returns those paths (relative resolution against REPO_ROOT). Otherwise
    returns `fallback` (which is the historical hardcoded default —
    typically `("backend/src",)` or similar). Always returns a tuple of
    Path objects, regardless of whether each path exists on disk.

    Example:
        DEFAULT_ROOTS = spine_paths("backend_api", ("backend/src/api",))
    """
    data = _load_spine_paths()
    raw = data.get(role) if isinstance(data, dict) else None
    chosen = raw if isinstance(raw, list) and raw else list(fallback)
    return tuple(REPO_ROOT / p for p in chosen)
