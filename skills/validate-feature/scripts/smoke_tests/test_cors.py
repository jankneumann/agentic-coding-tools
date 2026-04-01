"""Smoke tests: CORS preflight behaviour."""

import pytest


@pytest.mark.timeout(30)
def test_preflight_headers(api_client):
    """OPTIONS / with an allowed origin includes CORS headers."""
    resp = api_client.options(
        "/",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" in resp.headers
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
