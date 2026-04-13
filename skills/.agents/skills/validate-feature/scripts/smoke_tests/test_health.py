"""Smoke tests: health check endpoints."""

import pytest


@pytest.mark.timeout(30)
def test_health_endpoint(api_client):
    """GET /health returns 200."""
    resp = api_client.get("/health")
    assert resp.status_code == 200


@pytest.mark.timeout(30)
def test_ready_endpoint(api_client):
    """GET /ready returns 200, skip if the endpoint does not exist."""
    resp = api_client.get("/ready")
    if resp.status_code == 404:
        pytest.skip("/ready endpoint not implemented")
    assert resp.status_code == 200
