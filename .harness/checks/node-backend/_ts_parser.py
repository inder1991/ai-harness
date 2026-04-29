"""Sprint 4 / S4.2 — tree-sitter wrapper for the node-backend pack.

Per the S0.1 ADR (`docs/decisions/2026-04-29-node-ast-parser.md`),
JS/TS parsing is provided by tree-sitter Python bindings. The bindings
are heavy (~30 MB) so we lazy-import them at first call — a consumer
with `python-only` or `python-react` profile never triggers the import
and never pays the install cost.

Public surface:
    parse(path)          -> NodeAST   (a parsed tree + source text)
    NodeAST.find(types)  -> Iterable  (yield every node whose .type matches)
    NodeAST.text(node)   -> str       (source slice for a node)
    NodeAST.line(node)   -> int       (1-based start line)

Grammars:
    .js  / .jsx          -> tree-sitter-javascript
    .ts                  -> tree-sitter-typescript (TS grammar)
    .tsx                 -> tree-sitter-typescript (TSX grammar)

The parser instance is process-cached (keyed by extension), so a single
check can scan thousands of files without repeated grammar loads.

H-25 contract:
    Missing input    : raise FileNotFoundError so the caller can decide.
    Malformed input  : tree-sitter is permissive; parse always returns a
                       tree. Callers that need strictness can check
                       NodeAST.has_errors().
    Upstream failed  : ImportError on first call signals the bindings
                       aren't installed; surface clearly to the user.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_PARSER_CACHE: dict[str, object] = {}


def _load_parser(ext: str):
    """Return a tree_sitter.Parser configured for `ext` (`.js`, `.ts`, ...).

    Lazy-imports tree_sitter on first call. Cached per extension so a
    repeated 5000-file scan only loads grammars once.
    """
    if ext in _PARSER_CACHE:
        return _PARSER_CACHE[ext]
    try:
        import tree_sitter as _ts
    except ImportError as exc:
        raise ImportError(
            "node-backend pack requires tree-sitter. Install with:\n"
            "    pip install 'tree-sitter==0.23.*' "
            "'tree-sitter-javascript==0.23.*' "
            "'tree-sitter-typescript==0.23.*'"
        ) from exc
    if ext in (".js", ".jsx", ".mjs", ".cjs"):
        import tree_sitter_javascript as ts_js
        lang = _ts.Language(ts_js.language())
    elif ext == ".ts":
        import tree_sitter_typescript as ts_ts
        lang = _ts.Language(ts_ts.language_typescript())
    elif ext == ".tsx":
        import tree_sitter_typescript as ts_ts
        lang = _ts.Language(ts_ts.language_tsx())
    else:
        raise ValueError(f"unsupported extension for node-backend: {ext}")
    parser = _ts.Parser(lang)
    _PARSER_CACHE[ext] = parser
    return parser


@dataclass
class NodeAST:
    """A parsed JS/TS file with helpers to walk it.

    Wraps a tree_sitter.Tree plus the original source bytes so callers
    can extract spans without re-reading the file. Node objects come
    from the underlying tree-sitter library — we don't subclass them.
    """
    path: Path
    source: bytes
    tree: object  # tree_sitter.Tree (kept untyped to skip the hard import here)

    def find(self, types: Iterable[str]) -> Iterable[object]:
        """Yield every node anywhere in the tree whose `.type` matches.

        Order is depth-first, left-to-right. `types` may be any iterable
        of node-type strings (e.g., `("call_expression",)`).
        """
        wanted = set(types)
        cursor = self.tree.walk()
        visited_children = False
        while True:
            node = cursor.node
            if not visited_children and node.type in wanted:
                yield node
            if not visited_children and cursor.goto_first_child():
                continue
            if cursor.goto_next_sibling():
                visited_children = False
                continue
            if not cursor.goto_parent():
                return
            visited_children = True

    def text(self, node) -> str:
        """Decoded UTF-8 source slice for `node`. Empty string on decode failure."""
        try:
            return self.source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 — best-effort; tree-sitter byte ranges
                           # are reliable but defensive against crafted inputs
            return ""

    def line(self, node) -> int:
        """1-based start line for emit() compatibility (tree-sitter is 0-based)."""
        return node.start_point[0] + 1

    def has_errors(self) -> bool:
        """True if tree-sitter encountered unparseable regions."""
        return self.tree.root_node.has_error


def parse(path: Path) -> NodeAST:
    """Parse a JS/TS source file. Raises FileNotFoundError on missing input.

    The returned NodeAST is read-only — callers walk it via `.find(...)`.
    Tree-sitter is permissive, so even broken syntax produces a tree
    (with ERROR nodes); use `.has_errors()` if you need strict mode.
    """
    if not path.exists():
        raise FileNotFoundError(path)
    ext = path.suffix.lower()
    parser = _load_parser(ext)
    source = path.read_bytes()
    tree = parser.parse(source)
    return NodeAST(path=path, source=source, tree=tree)


def supported_suffixes() -> tuple[str, ...]:
    """The file extensions this wrapper can parse. Used by walk_files callers."""
    return (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")
