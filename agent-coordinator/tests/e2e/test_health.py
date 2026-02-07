"""E2E health check tests for the PostgREST API.

These tests verify that the REST API is running and responding.
Requires: docker-compose up -d
Run with: pytest tests/e2e/ -m e2e
"""

import pytest
import httpx


@pytest.mark.e2e
class TestRestApiHealth:
    """Verify the PostgREST API is reachable and responding."""

    async def test_root_responds(self, base_url: str) -> None:
        """The PostgREST root endpoint should return an OpenAPI schema."""
        async with httpx.AsyncClient(base_url=base_url) as client:
            response = await client.get("/")

        assert response.status_code == 200
        # PostgREST returns an OpenAPI spec at the root
        body = response.json()
        assert "paths" in body or "definitions" in body or "swagger" in body

    async def test_health_responds_to_unknown_table(self, base_url: str) -> None:
        """Querying a non-existent table should return 404, proving the API routes requests."""
        async with httpx.AsyncClient(base_url=base_url) as client:
            response = await client.get("/nonexistent_table_xyz")

        # PostgREST returns 404 for unknown relations
        assert response.status_code == 404
