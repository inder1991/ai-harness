"""Sprint 1 — `harness <verb>` subcommand dispatchers.

Each verb has its own module under this package. The top-level
`harness_cli.py` dispatches by importing this package's `dispatch()`.
"""
from __future__ import annotations

from typing import Callable


def dispatch(verb: str, argv: list[str]) -> int:
    """Route `harness <verb> <args...>` to the matching module's main()."""
    handlers: dict[str, Callable[[list[str]], int]] = {}
    # Lazy imports so an early-stage CLI doesn't crash on missing modules.
    if verb == "init":
        from tools.cli import init as _init
        handlers["init"] = _init.main
    if verb == "check":
        from tools.cli import check as _check
        handlers["check"] = _check.main
    if verb == "rules":
        from tools.cli import rules as _rules
        handlers["rules"] = _rules.main
    if verb == "doctor":
        from tools.cli import doctor as _doctor
        handlers["doctor"] = _doctor.main
    if verb == "telemetry":
        from tools.cli import telemetry as _telemetry
        handlers["telemetry"] = _telemetry.main
    if verb == "baseline":
        from tools.cli import baseline as _baseline
        handlers["baseline"] = _baseline.main
    if verb == "upgrade":
        from tools.cli import upgrade as _upgrade
        handlers["upgrade"] = _upgrade.upgrade_main
    if verb == "rollback":
        from tools.cli import upgrade as _upgrade
        handlers["rollback"] = _upgrade.rollback_main
    if verb in handlers:
        return handlers[verb](argv)
    raise RuntimeError(f"verb {verb!r} not registered")
