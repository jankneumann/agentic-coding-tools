"""Put this skill's ``scripts/`` directory on ``sys.path``.

The test modules here import their subjects by flat module name
(``from api_key_resolver import ApiKeyResolver``) without any path setup of
their own, which only resolves when ``scripts/`` is already importable. Nothing
put it there, so the whole directory failed to collect -- and because it was
absent from ``testpaths``, CI never surfaced that.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture(autouse=True)
def _isolated_probe_cache(tmp_path_factory, monkeypatch):
    """Give each test its own vendor-probe cache.

    ``review_dispatcher`` records runtime ``auth_required`` / ``vendor_unavailable``
    failures into the probe cache, and ``discover_reviewers`` filters on it, so a
    shared cache lets one test's simulated failure drop lanes in a later test.
    """
    cache = tmp_path_factory.mktemp("probe-cache") / "vendor-probe.json"
    monkeypatch.setenv("AGENTIC_PROBE_CACHE", str(cache))
