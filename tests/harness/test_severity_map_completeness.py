"""Sprint 0 / S0.2 — every rule emitted by any check has a severity entry.

Walks .harness/checks/*.py, extracts every quoted rule ID literal,
asserts each is listed in .harness/severity_map.yaml.

Adding a new check?
  1. Add an entry for every rule ID it emits to .harness/severity_map.yaml.
  2. This test enforces it.

Adding a rule to an existing check?
  Same — extend the severity_map entry.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKS_DIR = REPO_ROOT / ".harness" / "checks"
SEVERITY_MAP = REPO_ROOT / ".harness" / "severity_map.yaml"

# Match any quoted rule ID in source: "Q13.route-needs-auth", "H16.foo-bar", etc.
# Allows camelCase (`Q6.useNavigate-not-at-top-level`) and underscores.
RULE_ID_RE = re.compile(
    r'"((?:Q|H|NQ)[0-9]+\.[A-Za-z][A-Za-z0-9_-]+)"'
)


def _collect_emitted_rule_ids() -> set[str]:
    """Walk every check file; return the set of rule IDs it emits."""
    out: set[str] = set()
    for path in sorted(CHECKS_DIR.glob("*.py")):
        if path.name in {"__init__.py", "_common.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        out.update(m.group(1) for m in RULE_ID_RE.finditer(text))
    return out


def _load_severity_map() -> dict:
    return yaml.safe_load(SEVERITY_MAP.read_text(encoding="utf-8")) or {}


def test_severity_map_exists():
    assert SEVERITY_MAP.exists(), (
        ".harness/severity_map.yaml is required since Sprint 0 (S0.2)"
    )


def test_severity_map_schema_version_present():
    data = _load_severity_map()
    assert data.get("schema_version") == "1"


def test_every_emitted_rule_has_severity_entry():
    """Every quoted rule ID in any check must appear in severity_map.rules."""
    emitted = _collect_emitted_rule_ids()
    mapped = set((_load_severity_map().get("rules") or {}).keys())
    missing = sorted(emitted - mapped)
    assert not missing, (
        f"{len(missing)} rule IDs emitted by checks but missing from "
        f".harness/severity_map.yaml: {missing}\n"
        f"Add an entry for each with tier + why + fix_hint."
    )


def test_no_orphaned_severity_entries():
    """Every entry in severity_map.rules must correspond to a real emitted rule.
    Catches drift in the other direction: someone removes a rule but the
    severity map still has it."""
    emitted = _collect_emitted_rule_ids()
    mapped = set((_load_severity_map().get("rules") or {}).keys())
    orphans = sorted(mapped - emitted)
    assert not orphans, (
        f"{len(orphans)} severity_map entries reference rule IDs no check "
        f"emits anymore: {orphans}\n"
        f"Either restore the check or remove the stale entry."
    )


def test_every_entry_has_required_fields():
    rules = _load_severity_map().get("rules") or {}
    incomplete = {
        rid: {k for k in ("tier", "why", "fix_hint") if not entry.get(k)}
        for rid, entry in rules.items()
    }
    incomplete = {rid: missing for rid, missing in incomplete.items() if missing}
    assert not incomplete, (
        f"severity_map entries with missing required fields: {incomplete}"
    )


def test_every_tier_is_valid():
    rules = _load_severity_map().get("rules") or {}
    valid_tiers = {"P0_security", "P1_correctness", "P2_quality", "P3_style"}
    bad = {
        rid: entry["tier"]
        for rid, entry in rules.items()
        if entry.get("tier") not in valid_tiers
    }
    assert not bad, f"unknown severity tiers: {bad}"


@pytest.mark.parametrize(
    "rule_id",
    sorted(_collect_emitted_rule_ids()),
)
def test_individual_rule_has_complete_entry(rule_id):
    """Per-rule parametrized test — produces clear failure messages naming
    the specific rule that's missing or incomplete."""
    rules = _load_severity_map().get("rules") or {}
    assert rule_id in rules, f"{rule_id} is emitted but has no severity entry"
    entry = rules[rule_id]
    assert entry.get("tier") in {"P0_security", "P1_correctness", "P2_quality", "P3_style"}, \
        f"{rule_id} has invalid tier: {entry.get('tier')}"
    assert len(entry.get("why", "")) >= 10, f"{rule_id} has empty/short why"
    assert len(entry.get("fix_hint", "")) >= 5, f"{rule_id} has empty/short fix_hint"
