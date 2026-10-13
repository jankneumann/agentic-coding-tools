"""Scenario registry.

Every module in this package that defines a module-level ``SCENARIOS`` mapping
(scenario id -> scenario object) is discovered with ``pkgutil``, so adding a
scenario family never edits a shared list (design D2).
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any


def discover() -> dict[str, Any]:
    """Import every scenario module and merge their ``SCENARIOS`` mappings."""
    found: dict[str, Any] = {}
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
        module = importlib.import_module(f"{__name__}.{info.name}")
        for scenario_id, scenario in getattr(module, "SCENARIOS", {}).items():
            if scenario_id in found:
                raise RuntimeError(f"duplicate scenario id {scenario_id!r} in {info.name}")
            found[scenario_id] = scenario
    return dict(sorted(found.items()))


def scenario_ids() -> list[str]:
    return list(discover())
