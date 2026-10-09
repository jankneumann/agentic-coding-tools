"""Report builder (design D8).

Every property of ``sim-report.schema.json`` is always present; the ones that do not
apply to a scenario are ``null``. Rendering refuses any value that would make two runs
differ by host: the world's temporary root or a 40-character hexadecimal string.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any

from mpsim.errors import ScenarioError

SCHEMA_VERSION = "1"
_HEX40 = re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{40}(?![0-9a-fA-F])")


class ReportError(ScenarioError):
    """A report value would leak host-specific data."""


def new_report(
    scenario_id: str,
    *,
    principals: list[dict[str, str]] | None = None,
    collision_present: bool | None = None,
    collision_detected: bool | None = None,
    probes: list[dict[str, Any]] | None = None,
    blocked_ticks: dict[str, int] | None = None,
    unblocked: dict[str, bool] | None = None,
    final_tick: int | None = None,
    timeline: list[dict[str, Any]] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "scenario_id": scenario_id,
        "principals": list(principals or []),
        "collision_present": collision_present,
        "collision_detected": collision_detected,
        "probes": probes,
        "blocked_ticks": blocked_ticks,
        "unblocked": unblocked,
        "final_tick": final_tick,
        "timeline": timeline,
        "error": error,
    }


def render(report: dict[str, Any], *, forbidden_paths: Sequence[str] = ()) -> str:
    """Serialize with sorted keys and no trailing whitespace, after the leak checks."""
    text = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    for path in forbidden_paths:
        if path and path in text:
            raise ReportError("report contains the world's temporary root")
    if _HEX40.search(text):
        raise ReportError("report contains a 40-character hex string (commit id)")
    return text
