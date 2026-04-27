"""v1.3.0 S1 — ImportTracker shared helper.

Resolves bound names back to canonical fully-qualified module paths
across `import / import-as / from-import / from-import-as` forms.
Closes the import-aliasing gap behind 5 audit findings (S-A4, S-AS3,
S-AS4, S-AS6, S-DB5).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from _common import ImportTracker  # noqa: E402


def test_tracks_plain_import():
    tree = ast.parse("import requests\n")
    t = ImportTracker(tree)
    assert t.module_for("requests") == "requests"
    assert t.module_for("nope") is None


def test_tracks_aliased_import():
    tree = ast.parse("import requests as r\n")
    t = ImportTracker(tree)
    assert t.module_for("r") == "requests"
    assert t.module_for("requests") is None  # alias hides the original name


def test_tracks_from_import():
    tree = ast.parse("from httpx import Client\n")
    t = ImportTracker(tree)
    assert t.module_for("Client") == "httpx.Client"


def test_tracks_aliased_from_import():
    tree = ast.parse("from time import sleep as nap\n")
    t = ImportTracker(tree)
    assert t.module_for("nap") == "time.sleep"
    assert t.module_for("sleep") is None


def test_resolves_attribute_chain():
    tree = ast.parse("import httpx\nx = httpx.Client()\n")
    t = ImportTracker(tree)
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    assert t.canonical_for(call.func) == "httpx.Client"


def test_resolves_aliased_attribute_chain():
    tree = ast.parse("import httpx as h\nx = h.Client()\n")
    t = ImportTracker(tree)
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    assert t.canonical_for(call.func) == "httpx.Client"


def test_resolves_from_imported_name():
    tree = ast.parse("from httpx import Client\nx = Client()\n")
    t = ImportTracker(tree)
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    assert t.canonical_for(call.func) == "httpx.Client"


def test_canonical_returns_none_for_unknown_name():
    tree = ast.parse("x = local_var()\n")
    t = ImportTracker(tree)
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    assert t.canonical_for(call.func) is None


def test_canonical_handles_deep_attribute_chain():
    tree = ast.parse("import sqlalchemy\nx = sqlalchemy.ext.asyncio.AsyncSession()\n")
    t = ImportTracker(tree)
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    assert t.canonical_for(call.func) == "sqlalchemy.ext.asyncio.AsyncSession"
