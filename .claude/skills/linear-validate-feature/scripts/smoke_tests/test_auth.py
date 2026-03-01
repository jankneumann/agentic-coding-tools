"""Smoke tests: Authentication enforcement.

Verifies that the API correctly enforces authentication on protected
endpoints — rejecting missing/invalid credentials and accepting valid ones.
"""

from __future__ import annotations

import httpx


class TestAuthRequired:
    """Protected endpoints must reject unauthenticated requests."""

    def test_no_credentials_rejected(
        self, client: httpx.Client, protected_endpoint: str
    ) -> None:
        """Request without auth credentials should get 401 or 403."""
        response = client.get(protected_endpoint)
        assert response.status_code in (401, 403), (
            f"Expected 401/403 without credentials, got {response.status_code}"
        )

    def test_valid_credentials_accepted(
        self, authed_client: httpx.Client, protected_endpoint: str
    ) -> None:
        """Request with valid credentials should succeed."""
        response = authed_client.get(protected_endpoint)
        assert 200 <= response.status_code < 300, (
            f"Expected 2xx with valid credentials, got {response.status_code}"
        )

    def test_empty_credentials_rejected(
        self,
        client: httpx.Client,
        protected_endpoint: str,
        auth_header_name: str,
    ) -> None:
        """Auth header present but empty should be rejected."""
        response = client.get(
            protected_endpoint, headers={auth_header_name: ""}
        )
        assert response.status_code in (401, 403), (
            f"Expected 401/403 with empty credential, got {response.status_code}"
        )

    def test_garbage_credentials_rejected(
        self,
        client: httpx.Client,
        protected_endpoint: str,
        auth_header_name: str,
    ) -> None:
        """Random string as credential should be rejected."""
        response = client.get(
            protected_endpoint,
            headers={auth_header_name: "not-a-real-credential-xyz-999"},
        )
        assert response.status_code in (401, 403), (
            f"Expected 401/403 with garbage credential, got {response.status_code}"
        )


class TestAuthResponseShape:
    """Auth error responses should be safe and informative."""

    def test_rejection_returns_json_error(
        self, client: httpx.Client, protected_endpoint: str
    ) -> None:
        """401/403 should return a JSON body (not an HTML error page)."""
        response = client.get(protected_endpoint)
        ct = response.headers.get("content-type", "")
        assert "json" in ct, (
            f"Auth rejection should return JSON, got content-type: {ct}"
        )

    def test_rejection_does_not_leak_valid_keys(
        self,
        client: httpx.Client,
        protected_endpoint: str,
        auth_header_value: str,
    ) -> None:
        """The error response must never contain the valid credential."""
        response = client.get(protected_endpoint)
        assert auth_header_value not in response.text, (
            "Auth error response contains the valid credential value"
        )
