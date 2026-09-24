"""Threshold config loader.

Thresholds live in a package-owned data file, never as literals in the
scoring logic (see design.md D3). JSON, not YAML: the package declares no
required dependencies (see the "Package exports and dependency-free import"
spec requirement), and parsing YAML would add `pyyaml` as one; `json` is
stdlib. The file lives inside `system_one_decisions/` itself, not the package
root, so `importlib.resources` can find it whether the install is editable
or a built wheel.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any


def _resource_root() -> resources.abc.Traversable:
    return resources.files("system_one_decisions") / "config"


@lru_cache(maxsize=1)
def load_thresholds() -> dict[str, Any]:
    """Load and cache `config/thresholds.json`. Raises if the file is
    missing or malformed -- a packaging mistake should fail loud, not fall
    back to a hardcoded value that would defeat the point of this module."""
    text = (_resource_root() / "thresholds.json").read_text(encoding="utf-8")
    return json.loads(text)


DEFAULT_ACT_FLOOR: float = load_thresholds()["defaults"]["act_floor"]
DEFAULT_APPROVE_FLOOR: float = load_thresholds()["defaults"]["approve_floor"]
