"""Smoke tests: Service health and readiness."""

from __future__ import annotations

import httpx
import pytest


class TestHealthEndpoint:
    """Verify the health endpoint is reachable and well-formed."""

    def test_health_returns_2xx(
        self, client: httpx.Client, health_endpoint: str
    ) -> None:
        response = client.get(health_endpoint)
        assert 200 <= response.status_code < 300, (
            f"Health endpoint {health_endpoint} returned {response.status_code}"
        )

    def test_health_content_type_is_sensible(
        self, client: httpx.Client, health_endpoint: str
    ) -> None:
        """Response should be JSON or plain text, not HTML error pages."""
        response = client.get(health_endpoint)
        ct = response.headers.get("content-type", "")
        assert "json" in ct or "text/plain" in ct or "text/html" not in ct, (
            f"Unexpected content-type on health endpoint: {ct}"
        )


class TestReadyEndpoint:
    """Verify the readiness endpoint (if configured)."""

    def test_ready_returns_2xx(
        self, client: httpx.Client, ready_endpoint: str
    ) -> None:
        if not ready_endpoint:
            pytest.skip("API_READY_ENDPOINT not configured")
        response = client.get(ready_endpoint)
        assert 200 <= response.status_code < 300, (
            f"Ready endpoint {ready_endpoint} returned {response.status_code}"
        )
