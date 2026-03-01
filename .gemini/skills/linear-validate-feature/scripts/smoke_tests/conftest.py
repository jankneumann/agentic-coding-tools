"""Reusable smoke test fixtures for validating deployed HTTP APIs.

Smoke tests verify deployed behavior that unit tests with mocked dependencies
miss: routing, middleware, CORS headers, actual HTTP status codes, auth
enforcement, and error response sanitization.

Configuration via environment variables:

    API_BASE_URL           Base URL of the deployed API (default: http://localhost:8000)
    API_HEALTH_ENDPOINT    Health check path (default: /health)
    API_READY_ENDPOINT     Readiness path, empty to skip (default: /ready)
    API_AUTH_HEADER        Auth header name (default: X-Admin-Key)
    API_AUTH_VALUE         Valid auth credential (default: test-validate-key)
    API_PROTECTED_ENDPOINT Endpoint requiring auth (default: /api/v1/settings/prompts)
    API_CORS_ORIGIN        Origin for CORS tests (default: http://localhost:5173)

Run:
    pytest skills/validate-feature/scripts/smoke_tests/ -v
"""

from __future__ import annotations

import os

import httpx
import pytest


# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@pytest.fixture(scope="session")
def base_url() -> str:
    """Base URL of the deployed API."""
    return _env("API_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def health_endpoint() -> str:
    return _env("API_HEALTH_ENDPOINT", "/health")


@pytest.fixture(scope="session")
def ready_endpoint() -> str:
    return _env("API_READY_ENDPOINT", "/ready")


@pytest.fixture(scope="session")
def auth_header_name() -> str:
    return _env("API_AUTH_HEADER", "X-Admin-Key")


@pytest.fixture(scope="session")
def auth_header_value() -> str:
    return _env("API_AUTH_VALUE", "test-validate-key")


@pytest.fixture(scope="session")
def protected_endpoint() -> str:
    return _env("API_PROTECTED_ENDPOINT", "/api/v1/settings/prompts")


@pytest.fixture(scope="session")
def cors_origin() -> str:
    return _env("API_CORS_ORIGIN", "http://localhost:5173")


# ---------------------------------------------------------------------------
# Derived fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def auth_headers(auth_header_name: str, auth_header_value: str) -> dict[str, str]:
    """Headers dict with the configured auth credential."""
    return {auth_header_name: auth_header_value}


# ---------------------------------------------------------------------------
# Service availability — auto-skip when API is not reachable
# ---------------------------------------------------------------------------

def _is_api_running(url: str, path: str) -> bool:
    try:
        r = httpx.get(f"{url}{path}", timeout=3.0)
        return r.status_code < 500
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


@pytest.fixture(autouse=True, scope="session")
def require_api(base_url: str, health_endpoint: str) -> None:
    """Skip the entire smoke suite when the API is unreachable."""
    if not _is_api_running(base_url, health_endpoint):
        pytest.skip(
            f"Smoke tests require a running API at {base_url}{health_endpoint} "
            "(set API_BASE_URL / API_HEALTH_ENDPOINT to override)"
        )


# ---------------------------------------------------------------------------
# HTTP clients (synchronous — smoke tests are simple request/response checks)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def client(base_url: str) -> httpx.Client:
    """Unauthenticated HTTP client."""
    return httpx.Client(base_url=base_url, timeout=10.0)


@pytest.fixture(scope="session")
def authed_client(
    base_url: str,
    auth_headers: dict[str, str],
) -> httpx.Client:
    """Authenticated HTTP client with the configured credential."""
    return httpx.Client(
        base_url=base_url,
        headers=auth_headers,
        timeout=10.0,
    )
