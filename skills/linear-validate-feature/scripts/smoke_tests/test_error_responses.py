"""Smoke tests: Error response sanitization.

Verifies that error responses (404, 401, 405, malformed body) do not leak
sensitive information such as filesystem paths, stack traces, internal IPs,
or credential values.
"""

from __future__ import annotations

import re

import httpx

# Patterns that should never appear in error responses shown to clients.
SENSITIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("filesystem path (/var/lib/)", re.compile(r"/var/lib/\S+")),
    ("filesystem path (/usr/local/)", re.compile(r"/usr/local/\S+")),
    ("filesystem path (/home/)", re.compile(r"/home/\S+")),
    ("Python traceback", re.compile(r"Traceback \(most recent call last\)")),
    ("Python file reference", re.compile(r'File "/.+\.py"')),
    ("internal IPv4 (10.x)", re.compile(r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")),
    ("internal IPv4 (172.x)", re.compile(r"\b172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b")),
    ("internal IPv4 (192.168.x)", re.compile(r"\b192\.168\.\d{1,3}\.\d{1,3}\b")),
    ("Django/Flask settings reference", re.compile(r"settings\.py|DJANGO_SETTINGS_MODULE")),
    ("SQL syntax in error", re.compile(r"(SELECT|INSERT|UPDATE|DELETE)\s+.+\s+FROM\s+", re.I)),
]


def _assert_no_sensitive_info(body: str, context: str) -> None:
    """Check that response body does not contain sensitive patterns."""
    for label, pattern in SENSITIVE_PATTERNS:
        assert not pattern.search(body), (
            f"{context}: response body contains {label}"
        )


class TestErrorSanitization:
    """Error responses must not leak sensitive server information."""

    def test_404_no_sensitive_info(
        self, authed_client: httpx.Client
    ) -> None:
        """404 response should not leak internals."""
        response = authed_client.get(
            "/nonexistent-path-smoke-test-xyz-404"
        )
        _assert_no_sensitive_info(response.text, "404 response")

    def test_auth_error_no_sensitive_info(
        self,
        client: httpx.Client,
        protected_endpoint: str,
    ) -> None:
        """Auth rejection should not leak internals."""
        response = client.get(protected_endpoint)
        _assert_no_sensitive_info(response.text, "Auth error response")

    def test_method_not_allowed_no_sensitive_info(
        self, authed_client: httpx.Client, health_endpoint: str
    ) -> None:
        """DELETE on health endpoint (likely 405) should not leak internals."""
        response = authed_client.delete(health_endpoint)
        _assert_no_sensitive_info(
            response.text, f"DELETE {health_endpoint} response"
        )

    def test_malformed_body_no_sensitive_info(
        self, authed_client: httpx.Client, protected_endpoint: str
    ) -> None:
        """POST with invalid JSON should not leak internals."""
        response = authed_client.post(
            protected_endpoint,
            content=b"this is not valid json {{{",
            headers={"Content-Type": "application/json"},
        )
        _assert_no_sensitive_info(
            response.text, "Malformed JSON body response"
        )
