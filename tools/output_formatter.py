"""Sprint 1 / S1.3 — humane output formatter for `harness check`.

Takes a list of Finding records (parsed from the orchestrator's H-16
emit lines) and produces output in one of four modes:

  - `human`       (default for tty) — colors, severity groups,
                  collapsed counts ("3 occurrences"), why/fix/more.
  - `json`        — schema-validated structured output.
                  Always exits 0; consumer reads the JSON.
  - `raw`         — exact H-16 lines, no summary. Backward compat.
  - `pre-commit`  — same as raw PLUS exit 1 on any finding (v1.x compat).

Severity tiers come from .harness/severity_map.yaml (Sprint 0 / S0.2).
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SEVERITY_MAP_PATH = REPO_ROOT / ".harness" / "severity_map.yaml"

# Tier ordering for display + exit-code decisions.
TIERS_ORDERED = ("P0_security", "P1_correctness", "P2_quality", "P3_style")

# Tiers that fail the gate in `human` mode. In `pre-commit` mode, ANY
# finding fails (preserves v1.x). In `json` mode, exit code is always 0
# (consumer reads the JSON; exit code is unused by the orchestrator).
HUMAN_BLOCKING_TIERS = {"P0_security", "P1_correctness"}

TIER_COLORS = {
    "P0_security": "31",      # red
    "P1_correctness": "31",   # red
    "P2_quality": "33",       # yellow
    "P3_style": "34",         # blue
    "uncategorized": "37",    # white
}

TIER_LABELS = {
    "P0_security": "🔴 P0 critical",
    "P1_correctness": "🔴 P1 high",
    "P2_quality": "🟡 P2 quality",
    "P3_style": "🔵 P3 style",
    "uncategorized": "⚪ uncategorized",
}


@dataclass
class Finding:
    """One H-16 emit-line worth of data, parsed for the formatter.

    Attributes:
        rule: The rule ID (e.g., "Q13.route-needs-auth").
        location: "file:line" string.
        message: The human-readable message.
        suggestion: The fix hint emitted by the check.
    """
    rule: str
    location: str
    message: str = ""
    suggestion: str = ""

    @property
    def file(self) -> str:
        return self.location.rsplit(":", 1)[0]

    @property
    def line(self) -> int:
        try:
            return int(self.location.rsplit(":", 1)[1])
        except (ValueError, IndexError):
            return 0


@dataclass
class FormatResult:
    text: str
    exit_code: int


# ───────────────────────── severity map ────────────────────────────


_SEVERITY_CACHE: dict | None = None


def _load_severity_map() -> dict:
    """Load .harness/severity_map.yaml once per process. Returns a dict
    with `rules: {rule_id: {tier, why, fix_hint}}`."""
    global _SEVERITY_CACHE
    if _SEVERITY_CACHE is not None:
        return _SEVERITY_CACHE
    if not SEVERITY_MAP_PATH.exists():
        _SEVERITY_CACHE = {"rules": {}}
        return _SEVERITY_CACHE
    try:
        _SEVERITY_CACHE = yaml.safe_load(
            SEVERITY_MAP_PATH.read_text(encoding="utf-8")
        ) or {"rules": {}}
    except (OSError, yaml.YAMLError):
        # Q17-EXEMPT: severity_map malformed → fall back to "uncategorized"
        # tier; emit a single [WARN] so users notice.
        print(
            f"[WARN] {SEVERITY_MAP_PATH} unparseable; "
            "all findings will be tier=uncategorized",
            file=sys.stderr,
        )
        _SEVERITY_CACHE = {"rules": {}}
    return _SEVERITY_CACHE


def tier_for(rule_id: str) -> str:
    rules = _load_severity_map().get("rules", {})
    entry = rules.get(rule_id) or {}
    return entry.get("tier") or "uncategorized"


def explainer_for(rule_id: str) -> tuple[str, str]:
    """Return (why, fix_hint) for a rule. Empty strings when missing."""
    rules = _load_severity_map().get("rules", {})
    entry = rules.get(rule_id) or {}
    return entry.get("why", ""), entry.get("fix_hint", "")


# ───────────────────────── color ──────────────────────────────────


def _color_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    forced = os.environ.get("HARNESS_COLOR")
    if forced == "always":
        return True
    if forced == "never":
        return False
    return sys.stdout.isatty()


def _colored(s: str, code: str) -> str:
    if not _color_enabled():
        return s
    return f"\x1b[{code}m{s}\x1b[0m"


# ───────────────────────── parsers ────────────────────────────────


_LINE_RE = None


def _parse_h16_line(line: str) -> Finding | None:
    """Parse a single H-16 line into a Finding. Returns None on miss."""
    global _LINE_RE
    if _LINE_RE is None:
        import re
        _LINE_RE = re.compile(
            r'^\[ERROR\]\s+file=(?P<file>.+?):(?P<line>\d+)\s+'
            r'rule=(?P<rule>\S+)\s+'
            r'message="(?P<message>[^"]*)"\s+'
            r'suggestion="(?P<suggestion>[^"]*)"\s*$'
        )
    m = _LINE_RE.match(line)
    if not m:
        return None
    return Finding(
        rule=m.group("rule"),
        location=f"{m.group('file')}:{m.group('line')}",
        message=m.group("message"),
        suggestion=m.group("suggestion"),
    )


def parse_h16_output(text: str) -> list[Finding]:
    """Walk every line; collect Findings."""
    out: list[Finding] = []
    for line in text.splitlines():
        f = _parse_h16_line(line)
        if f:
            out.append(f)
    return out


# ───────────────────────── formatters ──────────────────────────────


def _format_human(findings: list[Finding]) -> FormatResult:
    """Color, severity-grouped, count-collapsed presentation."""
    if not findings:
        text = (
            f"\n{_colored('✓', '32')} No findings. All rules passed cleanly.\n"
        )
        return FormatResult(text=text, exit_code=0)

    # Group by tier, then collapse same-rule occurrences.
    by_tier: dict[str, list[Finding]] = {t: [] for t in TIERS_ORDERED}
    by_tier["uncategorized"] = []
    for f in findings:
        by_tier.setdefault(tier_for(f.rule), []).append(f)

    blocking_count = 0
    for t in HUMAN_BLOCKING_TIERS:
        blocking_count += len(by_tier.get(t, []))

    out: list[str] = []
    out.append("")
    out.append("─" * 60)

    for tier in (*TIERS_ORDERED, "uncategorized"):
        items = by_tier.get(tier, [])
        if not items:
            continue
        # Collapse by rule.
        by_rule: dict[str, list[Finding]] = {}
        for f in items:
            by_rule.setdefault(f.rule, []).append(f)

        label = _colored(TIER_LABELS[tier], TIER_COLORS[tier])
        out.append(f"\n{label} ({len(items)} finding{'s' if len(items) != 1 else ''})")

        for rule, occurrences in sorted(by_rule.items()):
            why, fix = explainer_for(rule)
            if len(occurrences) == 1:
                f = occurrences[0]
                out.append(f"  {_colored(rule, '1')} — {f.location}")
                if f.message:
                    out.append(f"    {f.message}")
            else:
                out.append(
                    f"  {_colored(rule, '1')} — {len(occurrences)} occurrences"
                )
                # Show first 3 locations.
                for f in occurrences[:3]:
                    out.append(f"    · {f.location}")
                if len(occurrences) > 3:
                    out.append(f"    · …and {len(occurrences) - 3} more")
            if why:
                indented_why = "\n      ".join(line for line in why.strip().splitlines())
                out.append(f"    {_colored('Why:', '2')}  {indented_why}")
            if fix:
                out.append(f"    {_colored('Fix:', '2')}  {fix}")
            out.append(
                f"    {_colored('More:', '2')} harness rules explain {rule}"
            )

    # Trailing summary.
    total = len(findings)
    out.append("")
    out.append("─" * 60)
    if blocking_count:
        out.append(
            f"{_colored('Status:', '1')} {_colored('FAIL', '31')} "
            f"({blocking_count} of {total} are P0/P1)"
        )
    else:
        out.append(
            f"{_colored('Status:', '1')} {_colored('PASS', '32')} "
            f"({total} non-blocking warning{'s' if total != 1 else ''})"
        )
    out.append("")
    out.append("To bypass this gate (rare):  git commit --no-verify")
    out.append("To suppress one finding:     harness baseline add <rule> <file:line> "
               '--reason "..."')
    out.append("")

    exit_code = 1 if blocking_count else 0
    return FormatResult(text="\n".join(out), exit_code=exit_code)


def _format_raw(findings: list[Finding], pre_commit: bool) -> FormatResult:
    """Backward-compatible H-16 emit lines, no summary."""
    lines = []
    for f in findings:
        lines.append(
            f'[ERROR] file={f.location} rule={f.rule} '
            f'message="{f.message}" suggestion="{f.suggestion}"'
        )
    text = "\n".join(lines) + ("\n" if lines else "")
    if pre_commit:
        # v1.x behavior: any finding fails.
        return FormatResult(text=text, exit_code=1 if findings else 0)
    # `raw`: also exit 1 on any finding (matches `pre-commit` semantically)
    return FormatResult(text=text, exit_code=1 if findings else 0)


def _format_json(findings: list[Finding]) -> FormatResult:
    """Structured output. Always exits 0."""
    by_tier_count: dict[str, int] = {}
    for f in findings:
        t = tier_for(f.rule)
        by_tier_count[t] = by_tier_count.get(t, 0) + 1
    payload = {
        "summary": {
            "total": len(findings),
            "by_severity": by_tier_count,
        },
        "findings": [
            {
                "rule": f.rule,
                "file": f.file,
                "line": f.line,
                "tier": tier_for(f.rule),
                "message": f.message,
                "suggestion": f.suggestion,
            }
            for f in findings
        ],
    }
    return FormatResult(
        text=json.dumps(payload, indent=2, sort_keys=True) + "\n",
        exit_code=0,
    )


def format_findings(
    findings: list[Finding],
    mode: str = "human",
) -> FormatResult:
    """Entry point. Pick a formatter by mode and return text + exit code."""
    if mode == "human":
        return _format_human(findings)
    if mode == "json":
        return _format_json(findings)
    if mode == "raw":
        return _format_raw(findings, pre_commit=False)
    if mode == "pre-commit":
        return _format_raw(findings, pre_commit=True)
    raise ValueError(f"unknown mode: {mode!r}")
