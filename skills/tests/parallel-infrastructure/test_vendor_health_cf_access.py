"""vendor_health reads dispatch configs from the coordinator, which sits behind
Cloudflare Access: without the service token the edge refuses the request and
the lookup silently falls back to a local file."""

from __future__ import annotations

from typing import Any

import pytest
import vendor_health


def test_dispatch_config_request_carries_the_service_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    monkeypatch.delenv("AGENTS_YAML", raising=False)
    monkeypatch.setenv("COORDINATION_API_URL", "https://coord.example")
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "id.access")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "s3cret")
    monkeypatch.chdir(tmp_path)
    sent: list[Any] = []

    def fake_urlopen(req: Any, timeout: float) -> Any:
        sent.append(req)
        raise OSError("not sending in a test")

    monkeypatch.setattr(vendor_health, "urlopen", fake_urlopen)
    vendor_health.load_agents_yaml()

    headers = {k.lower(): v for k, v in sent[0].header_items()}
    assert headers["cf-access-client-id"] == "id.access"
    assert headers["cf-access-client-secret"] == "s3cret"
