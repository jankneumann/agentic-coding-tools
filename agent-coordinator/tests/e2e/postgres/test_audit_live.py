"""E2E tests for audit trail logging and query via DirectPostgresClient."""

import pytest


@pytest.mark.e2e
class TestAuditTrailLive:
    """Audit trail endpoint against live database."""

    def test_audit_endpoint_returns_entries_list(self, api_client, auth_headers) -> None:
        """Audit endpoint should return a valid entries list."""
        # Perform an operation that may generate audit entries
        api_client.post(
            "/memory/store",
            headers=auth_headers,
            json={
                "agent_id": "e2e-agent",
                "event_type": "test",
                "summary": "Audit trail test memory",
                "tags": ["audit-test"],
            },
        )

        # Query audit trail — entries may or may not exist depending on
        # whether audit logging succeeded (it's best-effort)
        response = api_client.get(
            "/audit",
            headers=auth_headers,
            params={"limit": 10},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["entries"], list)

    def test_audit_query_with_operation_filter(
        self, api_client, auth_headers
    ) -> None:
        """Audit queries should support filtering by operation."""
        response = api_client.get(
            "/audit",
            headers=auth_headers,
            params={"operation": "store_memory", "limit": 5},
        )
        assert response.status_code == 200
        data = response.json()
        # All returned entries (if any) should be for the filtered operation
        for entry in data["entries"]:
            assert entry["operation"] == "store_memory"

    def test_audit_requires_auth(self, api_client) -> None:
        """Audit endpoint should require authentication."""
        response = api_client.get("/audit", params={"limit": 5})
        assert response.status_code == 401
