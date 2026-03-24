"""E2E tests for handoff write/read endpoints via DirectPostgresClient."""

import pytest


@pytest.mark.e2e
class TestHandoffWriteLive:
    """Handoff write endpoint against live database."""

    def test_write_handoff(self, api_client, auth_headers) -> None:
        response = api_client.post(
            "/handoffs/write",
            headers=auth_headers,
            json={
                "agent_id": "e2e-agent",
                "agent_type": "test_agent",
                "summary": "Completed lock service refactoring",
                "completed_work": ["Refactored acquire_lock", "Added TTL cleanup"],
                "next_steps": ["Write integration tests"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["handoff_id"] is not None

    def test_write_and_read_handoff(self, api_client, auth_headers) -> None:
        # Write
        write_resp = api_client.post(
            "/handoffs/write",
            headers=auth_headers,
            json={
                "agent_id": "e2e-agent",
                "agent_type": "test_agent",
                "summary": "Session context for E2E test",
                "completed_work": ["item-a", "item-b"],
                "in_progress": ["item-c"],
                "decisions": ["decision-1"],
                "next_steps": ["next-1", "next-2"],
                "relevant_files": ["src/locks.py", "src/memory.py"],
            },
        )
        assert response_ok(write_resp)

        # Read
        read_resp = api_client.post(
            "/handoffs/read",
            headers=auth_headers,
            json={"limit": 1},
        )
        assert read_resp.status_code == 200
        data = read_resp.json()
        assert len(data["handoffs"]) >= 1

        handoff = data["handoffs"][0]
        assert handoff["summary"] == "Session context for E2E test"
        assert handoff["completed_work"] == ["item-a", "item-b"]
        assert handoff["in_progress"] == ["item-c"]
        assert handoff["decisions"] == ["decision-1"]
        assert handoff["next_steps"] == ["next-1", "next-2"]
        assert handoff["relevant_files"] == ["src/locks.py", "src/memory.py"]

    def test_write_handoff_requires_summary(self, api_client, auth_headers) -> None:
        response = api_client.post(
            "/handoffs/write",
            headers=auth_headers,
            json={
                "agent_id": "e2e-agent",
                "agent_type": "test_agent",
                "summary": "",
            },
        )
        assert response.status_code == 200
        data = response.json()
        # Empty summary should fail at the DB level
        assert data["success"] is False


def response_ok(resp) -> bool:
    """Check response is 200 and success."""
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    return resp.json()["success"] is True
