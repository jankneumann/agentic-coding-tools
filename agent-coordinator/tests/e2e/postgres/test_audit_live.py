"""E2E tests for audit trail logging and query via DirectPostgresClient."""

import pytest


@pytest.mark.e2e
class TestAuditTrailLive:
    """Audit trail endpoint against live database."""

    def test_operations_generate_audit_entries(self, api_client, auth_headers) -> None:
        """Performing operations should generate audit log entries."""
        # Perform an operation that generates audit entries
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

        # Query audit trail
        response = api_client.get(
            "/audit",
            headers=auth_headers,
            params={"limit": 10},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["entries"] is not None
        assert len(data["entries"]) >= 1

    def test_audit_query_with_operation_filter(
        self, api_client, auth_headers
    ) -> None:
        """Audit queries should support filtering by operation."""
        # Create some activity
        api_client.post(
            "/memory/store",
            headers=auth_headers,
            json={
                "agent_id": "e2e-agent",
                "event_type": "test",
                "summary": "Another audit test",
                "tags": ["audit-filter"],
            },
        )

        response = api_client.get(
            "/audit",
            headers=auth_headers,
            params={"operation": "store_memory", "limit": 5},
        )
        assert response.status_code == 200
        data = response.json()
        # All returned entries should be for the filtered operation
        for entry in data["entries"]:
            assert entry["operation"] == "store_memory"

    def test_audit_requires_auth(self, api_client) -> None:
        """Audit endpoint should require authentication."""
        response = api_client.get("/audit", params={"limit": 5})
        assert response.status_code == 401
