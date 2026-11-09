"""Guard: the suite must never write under the real XDG probe-cache path."""

from __future__ import annotations

import os
from pathlib import Path

import vendor_probe as vp


def test_cache_path_is_redirected_away_from_real_xdg():
    real_default = Path.home() / ".cache" / "agentic-coding-tools" / "vendor-probe.json"
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        real_default = Path(xdg) / "agentic-coding-tools" / "vendor-probe.json"
    assert os.environ.get("AGENTIC_PROBE_CACHE")
    assert vp.cache_path() != real_default


def test_runtime_failure_write_lands_in_redirected_cache():
    vp.record_runtime_failure("guard-agent", "auth_required")
    assert vp.cache_path().exists()
    assert str(vp.cache_path()) == os.environ["AGENTIC_PROBE_CACHE"]
