"""Smoke tests: CORS header verification.

Verifies that CORS headers are correctly set on preflight and actual
requests, ensuring browser-based clients can interact with the API.
"""

from __future__ import annotations

import httpx
import pytest


class TestCorsPreflight:
    """OPTIONS preflight requests should return correct CORS headers."""

    def test_options_does_not_500(
        self,
        client: httpx.Client,
        protected_endpoint: str,
        cors_origin: str,
    ) -> None:
        """Preflight request must not cause a server error."""
        response = client.options(
            protected_endpoint,
            headers={
                "Origin": cors_origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code < 500, (
            f"OPTIONS preflight returned server error {response.status_code}"
        )

    def test_cors_allows_configured_origin(
        self,
        client: httpx.Client,
        protected_endpoint: str,
        cors_origin: str,
    ) -> None:
        """If CORS is configured, Access-Control-Allow-Origin should be present."""
        response = client.options(
            protected_endpoint,
            headers={
                "Origin": cors_origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        acao = response.headers.get("access-control-allow-origin")
        if acao is None:
            pytest.skip("CORS not configured on this API (no ACAO header)")
        assert acao in ("*", cors_origin), (
            f"ACAO header is '{acao}', expected '*' or '{cors_origin}'"
        )

    def test_cors_allows_common_methods(
        self,
        client: httpx.Client,
        protected_endpoint: str,
        cors_origin: str,
    ) -> None:
        """Preflight should allow at least GET and POST."""
        response = client.options(
            protected_endpoint,
            headers={
                "Origin": cors_origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        acam = response.headers.get("access-control-allow-methods", "")
        if not acam:
            pytest.skip("CORS not configured (no Allow-Methods header)")
        for method in ("GET", "POST"):
            assert method in acam, (
                f"CORS Allow-Methods missing {method}: {acam}"
            )

    def test_cors_allows_auth_header(
        self,
        client: httpx.Client,
        protected_endpoint: str,
        cors_origin: str,
        auth_header_name: str,
    ) -> None:
        """Preflight should allow the auth header used by the API."""
        response = client.options(
            protected_endpoint,
            headers={
                "Origin": cors_origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": auth_header_name,
            },
        )
        acah = response.headers.get("access-control-allow-headers", "")
        if not acah:
            pytest.skip("CORS not configured (no Allow-Headers header)")
        assert auth_header_name.lower() in acah.lower(), (
            f"CORS Allow-Headers missing {auth_header_name}: {acah}"
        )


class TestCorsActualRequest:
    """Actual requests with Origin should reflect CORS headers."""

    def test_origin_reflected_in_response(
        self,
        authed_client: httpx.Client,
        health_endpoint: str,
        cors_origin: str,
    ) -> None:
        """GET with Origin header should get ACAO in response (if CORS configured)."""
        response = authed_client.get(
            health_endpoint, headers={"Origin": cors_origin}
        )
        acao = response.headers.get("access-control-allow-origin")
        if acao is None:
            pytest.skip("CORS not configured on actual requests")
        assert acao in ("*", cors_origin)
