"""Shared fixtures for smoke tests.

All connection details are parametrized via environment variables —
no hardcoded URLs or credentials.
"""

import os

import httpx
import pytest


@pytest.fixture
def api_base_url():
    """Base URL of the live service under test."""
    url = os.environ.get("API_BASE_URL")
    if not url:
        pytest.skip("API_BASE_URL not set")
    return url.rstrip("/")


@pytest.fixture
def api_client(api_base_url):
    """httpx client pointed at the live service."""
    with httpx.Client(base_url=api_base_url, timeout=10.0) as client:
        yield client


@pytest.fixture
def api_key():
    """API key for authenticated requests."""
    return os.environ.get("API_KEY", "e2e-test-key")


@pytest.fixture
def postgres_dsn():
    """PostgreSQL connection string for the live database."""
    dsn = os.environ.get("POSTGRES_DSN")
    if not dsn:
        pytest.skip("POSTGRES_DSN not set")
    return dsn
