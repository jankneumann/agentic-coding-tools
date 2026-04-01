"""Smoke tests: authentication enforcement."""

import pytest


_AUTH_ENDPOINT = "/api/v1/settings/prompts"


@pytest.mark.timeout(30)
def test_no_credentials_rejected(api_client):
    """Request without X-API-Key is rejected with 401 or 403."""
    resp = api_client.get(_AUTH_ENDPOINT)
    assert resp.status_code in (401, 403)


@pytest.mark.timeout(30)
def test_valid_credentials_accepted(api_client, api_key):
    """Request with a valid X-API-Key is accepted with 200."""
    resp = api_client.get(_AUTH_ENDPOINT, headers={"X-API-Key": api_key})
    assert resp.status_code == 200


@pytest.mark.timeout(30)
def test_malformed_credentials_rejected(api_client):
    """Request with a garbage API key is rejected with 401."""
    resp = api_client.get(
        _AUTH_ENDPOINT, headers={"X-API-Key": "garbage-invalid-key"}
    )
    assert resp.status_code == 401
