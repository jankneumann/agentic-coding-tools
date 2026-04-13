"""Smoke tests: error responses do not leak internal details."""

import re

import pytest


def _error_body(api_client) -> str:
    """Fetch a guaranteed-error response body."""
    resp = api_client.get("/nonexistent-triggering-error")
    return resp.text


@pytest.mark.timeout(30)
def test_no_path_leaks(api_client):
    """Error body must not reveal server filesystem paths."""
    body = _error_body(api_client)
    assert not re.search(r"/Users/|/home/|/var/", body)


@pytest.mark.timeout(30)
def test_no_stacktrace_leaks(api_client):
    """Error body must not contain Python tracebacks."""
    body = _error_body(api_client)
    assert "Traceback (most recent" not in body


@pytest.mark.timeout(30)
def test_no_ip_leaks(api_client):
    """Error body must not reveal RFC 1918 private IP addresses."""
    body = _error_body(api_client)
    pattern = r"10\.\d|172\.(1[6-9]|2\d|3[01])\.|192\.168\."
    assert not re.search(pattern, body)


@pytest.mark.timeout(30)
def test_no_credential_leaks(api_client):
    """Error body must not contain database connection strings."""
    body = _error_body(api_client)
    assert "postgresql://" not in body
