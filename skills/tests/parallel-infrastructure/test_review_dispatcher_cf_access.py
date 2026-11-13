"""The review dispatcher loads its dispatch configs from the coordinator, which
sits behind Cloudflare Access: without the service token the edge refuses the
request and, with no local agents.yaml, no reviewer is dispatched at all."""

from __future__ import annotations

from typing import Any

import pytest
import review_dispatcher


def _sent_headers(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    sent: list[Any] = []

    def fake_urlopen(req: Any, timeout: float) -> Any:
        sent.append(req)
        raise OSError("not sending in a test")

    monkeypatch.setenv("COORDINATION_API_URL", "https://coord.example")
    monkeypatch.setattr(review_dispatcher, "urlopen", fake_urlopen)
    assert review_dispatcher.ReviewOrchestrator._load_from_http() is None
    return {k.lower(): v for k, v in sent[0].header_items()}


def test_dispatch_config_request_carries_the_service_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "id.access")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "s3cret")
    headers = _sent_headers(monkeypatch)
    assert headers["cf-access-client-id"] == "id.access"
    assert headers["cf-access-client-secret"] == "s3cret"


def test_a_half_configured_token_sends_neither_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "id.access")
    monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)
    headers = _sent_headers(monkeypatch)
    assert "cf-access-client-id" not in headers
