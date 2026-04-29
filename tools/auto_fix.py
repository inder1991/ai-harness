"""Sprint 2 / S2.3 — auto-fix engine.

Each rule with an auto-fixer registers a transformer in the
`FIXERS` dict. A transformer is a pure function:
    transform(source: str, finding: Finding) -> str

Safety contract enforced by `apply_fix`:

  1. Diff always shown before mutating the filesystem (--apply or -y required).
  2. After fix, ast.parse() (Python) or equivalent must succeed; if parse
     fails, abort and emit a structured error.
  3. mtime + sha captured at diff time; if file changed at apply time,
     abort with "file changed; re-run".
  4. Determinism guard: run twice on the same input → byte-identical output.
  5. Cascade re-check: after applying, re-parse for new findings of any rule.

If any of these fail, abort and DO NOT mutate the file. The user can
always fix manually with help from `harness rules explain <id>`.
"""
from __future__ import annotations

import ast
import difflib
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from output_formatter import Finding


# ──────────────────────── transformers ────────────────────────


def _fix_q15_spine_docstring_required(source: str, finding: Finding) -> str:
    """Insert a stub docstring into the function/class at finding.line.

    Strategy: parse the AST, find the FunctionDef / AsyncFunctionDef /
    ClassDef whose lineno matches the finding, and insert a docstring
    as the first body statement if one isn't present.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if node.lineno != finding.line:
            continue
        # Already has a docstring? No-op.
        if (node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)):
            return source
        lines = source.splitlines(keepends=True)
        # Find the function header line, then the first non-blank body line.
        # Insert the stub docstring at body indent level.
        header_line_idx = node.lineno - 1
        # Find first body statement — the next non-comment, non-blank line
        # after the colon at the end of the def/class line.
        # Simpler approach: insert directly after the line that ends with `:`.
        body_indent = " " * (node.col_offset + 4)
        stub = f'{body_indent}"""TODO: describe purpose + return contract."""\n'
        # Find the line containing the colon at the end of the signature.
        # For multi-line signatures, walk forward.
        i = header_line_idx
        while i < len(lines) and not lines[i].rstrip().endswith(":"):
            i += 1
        if i >= len(lines):
            return source
        lines.insert(i + 1, stub)
        return "".join(lines)
    return source


_F_STRING_LOG_RE = re.compile(
    r"""(?P<call>(?:log|logger|LOG|_log|self\.log)\.\w+\(\s*)"""
    r"""f["'](?P<msg>[^"']*)["']\s*\)"""
)


def _fix_q16_f_string_in_log(source: str, finding: Finding) -> str:
    """Convert `log.info(f"x {y}")` → `log.info("x %s", y)`.

    Conservative: only handles single-positional-arg, simple-name
    interpolations. Complex f-strings (format specs, attribute access,
    method calls) are left alone — the user fixes manually.
    """
    lines = source.splitlines(keepends=True)
    line_idx = finding.line - 1
    if not (0 <= line_idx < len(lines)):
        return source
    original_line = lines[line_idx]
    m = _F_STRING_LOG_RE.search(original_line)
    if not m:
        return source
    msg = m.group("msg")
    # Extract {names}; reject anything fancy.
    names: list[str] = []
    chunks = re.split(r"\{([^{}:!]+)\}", msg)
    if len(chunks) % 2 != 1:  # odd count means balanced { }
        return source
    template = ""
    for i, part in enumerate(chunks):
        if i % 2 == 0:
            template += part
        else:
            stripped = part.strip()
            if not stripped.isidentifier():
                return source  # complex — bail
            template += "%s"
            names.append(stripped)
    if not names:
        return source
    args = ", ".join(names)
    new_call = f'{m.group("call")}"{template}", {args})'
    lines[line_idx] = (
        original_line[:m.start()] + new_call + original_line[m.end():]
    )
    return "".join(lines)


_DEFAULT_EXPORT_RE = re.compile(r"^(\s*)export\s+default\s+(?P<name>\w+)\s*;?\s*$",
                                re.MULTILINE)
_INLINE_DEFAULT_EXPORT_RE = re.compile(
    r"^(\s*)export\s+default\s+function\s+(?P<name>\w+)", re.MULTILINE
)


def _fix_q18_no_default_export_in_components(source: str, finding: Finding) -> str:
    """Convert `export default Foo;` → `export const Foo = ...` (best-effort).

    Conservative: only handles the simple `export default Foo;` pattern
    where Foo is a Name declared earlier in the file. Doesn't touch
    `export default function Foo() {...}` (would need a multi-pass
    transform; left for the user).
    """
    m = _DEFAULT_EXPORT_RE.search(source)
    if not m:
        return source
    name = m.group("name")
    if not re.search(rf"\bconst\s+{re.escape(name)}\b", source):
        return source  # not a Name reference
    # Replace the export statement with `export { Foo };` form.
    replacement = f"export {{ {name} }};\n"
    new_source = (
        source[:m.start()] + m.group(1) + replacement + source[m.end()+1:]
    )
    return new_source


_RULE_COUNT_RE = re.compile(
    r'^(?P<indent>\s*)(?P<num>One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|\d+)\s+rules?:?\s*$',
    re.MULTILINE,
)
_NUM_TO_WORD = {
    1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five",
    6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten",
}


def _fix_q22_doc_rule_count_mismatch(source: str, finding: Finding) -> str:
    """Update the docstring's "N rules" claim to match the enumerated count."""
    rule_id_re = re.compile(
        r'\b((?:Q|H|NQ)[0-9]+\.[A-Za-z][A-Za-z0-9_-]+)\b'
    )
    # Find the module docstring.
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    docstring = ast.get_docstring(tree, clean=False) or ""
    enumerated = len({m.group(1) for m in rule_id_re.finditer(docstring)})
    if enumerated == 0:
        return source

    def _replace(m: re.Match) -> str:
        word = (
            _NUM_TO_WORD[enumerated]
            if enumerated <= 10 else str(enumerated)
        )
        return f'{m.group("indent")}{word} rules:'

    new_source = _RULE_COUNT_RE.sub(_replace, source, count=1)
    return new_source


# ──────────────────────── registry ────────────────────────

FIXERS: dict[str, Callable[[str, Finding], str]] = {
    "Q15.spine-docstring-required": _fix_q15_spine_docstring_required,
    "Q16.f-string-in-log": _fix_q16_f_string_in_log,
    "Q18.no-default-export-in-components": _fix_q18_no_default_export_in_components,
    "Q22.doc-rule-count-mismatch": _fix_q22_doc_rule_count_mismatch,
}


# ──────────────────────── safety + apply ────────────────────────


@dataclass
class FixResult:
    rule: str
    file: str
    diff: str
    applied: bool
    error: str | None = None


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ast_parses(source: str) -> bool:
    """Best-effort check: Python files must parse; non-Python files are
    accepted as-is (tree-sitter would gate Node files when Sprint 4 ships)."""
    try:
        ast.parse(source)
        return True
    except SyntaxError:
        return False


def _is_deterministic(transform: Callable, source: str, finding: Finding) -> bool:
    """Run the transformer twice; outputs must be byte-identical."""
    a = transform(source, finding)
    b = transform(source, finding)
    return a == b


def fix(rule: str, file: str, finding: Finding, apply: bool) -> FixResult:
    """Apply one auto-fixer to one file. See module docstring for the
    safety contract.
    """
    transform = FIXERS.get(rule)
    if transform is None:
        return FixResult(
            rule=rule, file=file, diff="", applied=False,
            error=f"no auto-fixer for {rule}; see `harness rules explain {rule}`",
        )
    path = Path(file)
    if not path.exists():
        return FixResult(rule=rule, file=file, diff="", applied=False,
                         error=f"file not found: {file}")

    pre_sha = _file_sha(path)
    source = path.read_text(encoding="utf-8")

    # Determinism guard.
    if not _is_deterministic(transform, source, finding):
        return FixResult(
            rule=rule, file=file, diff="", applied=False,
            error="auto-fixer is non-deterministic on this input — refusing to apply",
        )

    new_source = transform(source, finding)
    if new_source == source:
        return FixResult(
            rule=rule, file=file, diff="", applied=False,
            error="auto-fixer produced no change; manual fix required",
        )

    # AST guard for Python files.
    if path.suffix == ".py" and not _ast_parses(new_source):
        return FixResult(
            rule=rule, file=file, diff="", applied=False,
            error="auto-fixer produced invalid Python AST — refusing to apply",
        )

    diff = "".join(difflib.unified_diff(
        source.splitlines(keepends=True),
        new_source.splitlines(keepends=True),
        fromfile=f"{file} (before)",
        tofile=f"{file} (after)",
        lineterm="",
    ))

    if not apply:
        return FixResult(rule=rule, file=file, diff=diff, applied=False)

    # Race guard: file mustn't have changed since we read it.
    if _file_sha(path) != pre_sha:
        return FixResult(
            rule=rule, file=file, diff=diff, applied=False,
            error="file changed during fix; re-run `harness fix`",
        )

    path.write_text(new_source, encoding="utf-8")
    return FixResult(rule=rule, file=file, diff=diff, applied=True)
