"""Pytest fixtures and configuration for E2E tests.

E2E tests run against live services started via docker-compose.
They require `docker-compose up -d` before running.
"""

import pytest


def pytest_collection_modifyitems(items):
    """Automatically mark all tests in the e2e directory with the e2e marker."""
    for item in items:
        if "/e2e/" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)


@pytest.fixture(scope="session")
def base_url() -> str:
    """Base URL for the PostgREST API.

    Defaults to http://localhost:3000, matching the docker-compose.yml configuration.
    Override via the BASE_URL environment variable if needed.
    """
    import os

    return os.environ.get("BASE_URL", "http://localhost:3000")
