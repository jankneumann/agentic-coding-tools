"""E2E tests for memory store/recall endpoints via DirectPostgresClient."""

import pytest


@pytest.mark.e2e
class TestMemoryStoreLive:
    """Memory store endpoint against live database."""

    def test_store_memory(self, api_client, auth_headers) -> None:
        response = api_client.post(
            "/memory/store",
            headers=auth_headers,
            json={
                "agent_id": "e2e-agent",
                "event_type": "discovery",
                "summary": "Found a critical bug in auth module",
                "tags": ["bug", "auth"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["memory_id"] is not None

    def test_store_and_recall(self, api_client, auth_headers) -> None:
        # Store
        api_client.post(
            "/memory/store",
            headers=auth_headers,
            json={
                "agent_id": "e2e-agent",
                "event_type": "decision",
                "summary": "Chose PostgreSQL over SQLite",
                "tags": ["architecture", "database"],
            },
        )

        # Recall
        response = api_client.post(
            "/memory/query",
            headers=auth_headers,
            json={"agent_id": "e2e-agent", "tags": ["database"], "limit": 10},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["memories"] is not None
        assert len(data["memories"]) >= 1
        assert any(
            "PostgreSQL" in m["summary"] for m in data["memories"]
        )

    def test_recall_empty(self, api_client, auth_headers) -> None:
        response = api_client.post(
            "/memory/query",
            headers=auth_headers,
            json={"agent_id": "e2e-agent", "tags": ["nonexistent-tag"], "limit": 10},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["memories"] == []
