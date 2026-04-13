"""Smoke tests: CORS preflight behaviour."""

import pytest


@pytest.mark.timeout(30)
def test_preflight_headers(api_client):
    """OPTIONS / with an allowed origin includes CORS headers (if CORS configured)."""
    resp = api_client.options(
        "/",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    # CORS may not be configured on all deployments.
    # If no CORS headers present, skip rather than fail — CORS is
    # an optional security feature for browser clients.
    if "access-control-allow-origin" not in resp.headers:
        pytest.skip("CORS not configured on this API — no Access-Control-Allow-Origin header")
    assert "access-control-allow-methods" in resp.headers


@pytest.mark.timeout(30)
def test_disallowed_origin(api_client):
    """OPTIONS / with a disallowed origin omits or mismatches Allow-Origin."""
    resp = api_client.options(
        "/",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    acao = resp.headers.get("access-control-allow-origin", "")
    assert acao != "http://evil.example.com"
