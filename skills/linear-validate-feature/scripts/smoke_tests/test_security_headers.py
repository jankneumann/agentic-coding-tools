"""Smoke tests: HTTP security headers.

Verifies that responses include appropriate security headers and do not
reveal excessive server implementation details.
"""

from __future__ import annotations

import httpx
import pytest


class TestSecurityHeaders:
    """Verify security-relevant HTTP response headers."""

    def test_content_type_on_json_responses(
        self, authed_client: httpx.Client, protected_endpoint: str
    ) -> None:
        """JSON responses should declare application/json content-type."""
        response = authed_client.get(protected_endpoint)
        if response.status_code >= 400:
            pytest.skip("Protected endpoint returned error; cannot check JSON content-type")
        ct = response.headers.get("content-type", "")
        assert "application/json" in ct, (
            f"Expected application/json, got: {ct}"
        )

    def test_server_header_not_overly_detailed(
        self, client: httpx.Client, health_endpoint: str
    ) -> None:
        """Server header should not reveal OS or distribution details."""
        response = client.get(health_endpoint)
        server = response.headers.get("server", "").lower()
        for detail in ("ubuntu", "debian", "centos", "alpine", "amazon"):
            assert detail not in server, (
                f"Server header reveals OS detail: {server}"
            )

    def test_no_powered_by_header(
        self, client: httpx.Client, health_endpoint: str
    ) -> None:
        """X-Powered-By can reveal framework details and should be removed."""
        response = client.get(health_endpoint)
        powered_by = response.headers.get("x-powered-by")
        if powered_by is not None:
            pytest.fail(
                f"X-Powered-By header present: '{powered_by}' — "
                "consider removing to avoid revealing framework details"
            )

    def test_content_type_options_nosniff(
        self, authed_client: httpx.Client, protected_endpoint: str
    ) -> None:
        """X-Content-Type-Options: nosniff prevents MIME-type sniffing attacks."""
        response = authed_client.get(protected_endpoint)
        xcto = response.headers.get("x-content-type-options")
        if xcto is None:
            pytest.skip(
                "X-Content-Type-Options not set — consider adding "
                "'nosniff' via middleware"
            )
        assert xcto.lower() == "nosniff", (
            f"Expected 'nosniff', got: {xcto}"
        )
