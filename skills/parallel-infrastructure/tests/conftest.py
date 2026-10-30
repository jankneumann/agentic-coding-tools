"""Isolate the vendor-probe cache from the real XDG cache directory."""

import pytest


@pytest.fixture(autouse=True)
def _isolated_probe_cache(tmp_path_factory, monkeypatch):
    cache = tmp_path_factory.mktemp("probe-cache") / "vendor-probe.json"
    monkeypatch.setenv("AGENTIC_PROBE_CACHE", str(cache))
