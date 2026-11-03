"""``CoordinatorHttpClient``: the shared raw-HTTP client for coordinator scripts.

The review worker and ``agent_lane``'s cross-host rounds both call coordinator
routes that have no ``try_*`` operation. The client must keep the bridge's
SSRF allowlist rather than reach a host the environment did not allow.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_BRIDGE_DIR = Path(__file__).resolve().parents[2] / "coordination-bridge" / "scripts"
if str(_BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_DIR))

import coordination_bridge  # noqa: E402


def test_a_host_outside_the_allowlist_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COORDINATION_ALLOWED_HOSTS", raising=False)

    with pytest.raises(ValueError, match="no allowed coordinator URL"):
        coordination_bridge.CoordinatorHttpClient("https://coord.example.com")


def test_request_goes_through_the_bridge_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COORDINATION_ALLOWED_HOSTS", "coord.example.com")
    calls: list[dict[str, Any]] = []

    def fake(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"status_code": 200, "data": {"ok": True}, "error": None}

    monkeypatch.setattr(coordination_bridge, "_http_request", fake)
    client = coordination_bridge.CoordinatorHttpClient(
        "https://coord.example.com/", api_key="k", timeout=30.0
    )

    resp = client.request("GET", "/reviews/rounds?pr=1")

    assert resp["data"] == {"ok": True}
    assert calls == [{
        "method": "GET", "path": "/reviews/rounds?pr=1", "payload": None,
        "http_url": "https://coord.example.com", "api_key": "k", "timeout": 30.0,
    }]
