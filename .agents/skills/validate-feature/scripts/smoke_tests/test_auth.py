"""Smoke tests: authentication enforcement.

Uses POST /memory/store as the auth-protected endpoint since it requires
X-API-Key. GET endpoints like /health and /locks/status are intentionally
unauthenticated.
"""

import pytest


# POST endpoint that requires X-API-Key authentication
_AUTH_ENDPOINT = "/memory/store"
_AUTH_PAYLOAD = {"event_type": "smoke_test", "summary": "auth check"}


@pytest.mark.timeout(30)
def test_no_credentials_rejected(api_client):
    """Request without X-API-Key is rejected with 401 or 403."""
    resp = api_client.post(_AUTH_ENDPOINT, json=_AUTH_PAYLOAD)
    assert resp.status_code in (401, 403)


@pytest.mark.timeout(30)
def test_valid_credentials_accepted(api_client, api_key):
    """Request with a valid X-API-Key is accepted (not 401/403)."""
    resp = api_client.post(
        _AUTH_ENDPOINT,
        json=_AUTH_PAYLOAD,
        headers={"X-API-Key": api_key},
    )
    # 200 or 422 (validation error on payload) — either means auth passed
    assert resp.status_code not in (401, 403)


@pytest.mark.timeout(30)
def test_malformed_credentials_rejected(api_client):
    """Request with a garbage API key is rejected with 401."""
    resp = api_client.post(
        _AUTH_ENDPOINT,
        json=_AUTH_PAYLOAD,
        headers={"X-API-Key": "garbage-invalid-key"},
    )
    assert resp.status_code == 401
