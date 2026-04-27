"""v1.3.0 S2 — `_common.is_logger_call` shared predicate.

Both `logging_policy.py` and `security_policy_a.py` need to detect
"this AST Call is invoking a logger method." Pre-v1.3.0 each had its
own implementation: logging_policy used a policy-driven attr set;
security_policy_a hardcoded `r'\\b(log|logger)\\.\\w+\\s*\\('` and
missed `LOG.`, `_log.`, `self.log.`, custom names from the policy.

Closes audit finding S-A1.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / ".harness/checks"))

from _common import is_logger_call  # noqa: E402


def _first_call(source: str) -> ast.Call:
    tree = ast.parse(source)
    return next(n for n in ast.walk(tree) if isinstance(n, ast.Call))


def test_matches_logger_dot_info():
    call = _first_call('logger.info("x")\n')
    assert is_logger_call(call, attrs={"info", "warning", "error"})


def test_matches_uppercase_LOG():
    """Custom logger name from a policy YAML."""
    call = _first_call('LOG.info("x")\n')
    assert is_logger_call(call, attrs={"info"})


def test_matches_self_log_attribute():
    src = 'class X:\n    def m(self):\n        self.log.info("x")\n'
    call = _first_call(src)
    assert is_logger_call(call, attrs={"info"})


def test_rejects_non_logger_attribute_call():
    call = _first_call('foo.bar("x")\n')
    assert not is_logger_call(call, attrs={"info", "warning", "error"})


def test_rejects_bare_function_call():
    call = _first_call('print("x")\n')
    assert not is_logger_call(call, attrs={"info", "warning", "error"})


def test_attrs_is_required_set():
    """Empty attrs → nothing matches."""
    call = _first_call('logger.info("x")\n')
    assert not is_logger_call(call, attrs=set())
