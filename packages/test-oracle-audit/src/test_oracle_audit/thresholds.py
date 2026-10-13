"""Display thresholds and shared kill-rate terciles (design D1).

No module holds a threshold literal: display thresholds come from
``config/thresholds.json``; tercile cut-points are computed from data.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from importlib import resources
from pathlib import Path
from typing import Any

REQUIRED_KEYS = ("judged_impl_derived_p", "co_change_high")

TERCILES = ("bottom", "middle", "top")


def load_thresholds(path: Path | None = None) -> dict[str, Any]:
    """Load display thresholds; raise ``KeyError`` naming any missing key."""
    if path is None:
        text = resources.files("test_oracle_audit").joinpath("config/thresholds.json").read_text("utf-8")
    else:
        text = Path(path).read_text("utf-8")
    data = json.loads(text)
    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        raise KeyError(f"thresholds config is missing required key(s): {', '.join(missing)}")
    return data


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile, ``q`` in [0, 1]."""
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = q * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return float(sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac)


def tercile_cutpoints(values: Sequence[float]) -> tuple[float, float]:
    """33.3rd and 66.7th percentiles of ``values`` (linear interpolation)."""
    if not values:
        raise ValueError("tercile_cutpoints needs at least one value")
    ordered = sorted(float(v) for v in values)
    return _percentile(ordered, 1 / 3), _percentile(ordered, 2 / 3)


def tercile_of(value: float, cuts: tuple[float, float]) -> str:
    """``"bottom"`` (<= first cut), ``"middle"`` (<= second cut) or ``"top"``."""
    low, high = cuts
    if value <= low:
        return "bottom"
    if value <= high:
        return "middle"
    return "top"
