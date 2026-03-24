"""E2E tests for work queue submit/claim/complete endpoints via DirectPostgresClient."""

import pytest


@pytest.mark.e2e
class TestWorkQueueSubmitLive:
    """Work queue submit endpoint against live database."""

    def test_submit_task(self, api_client, auth_headers) -> None:
        response = api_client.post(
            "/work/submit",
            headers=auth_headers,
            json={
                "task_type": "test",
                "task_description": "Write unit tests for cache module",
                "priority": 3,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["task_id"] is not None


@pytest.mark.e2e
class TestWorkQueueLifecycleLive:
    """Full work queue lifecycle against live database."""

    def test_submit_claim_complete(self, api_client, auth_headers) -> None:
        # Submit
        submit_resp = api_client.post(
            "/work/submit",
            headers=auth_headers,
            json={
                "task_type": "refactor",
                "task_description": "Simplify error handling in locks.py",
                "priority": 5,
            },
        )
        assert submit_resp.status_code == 200
        task_id = submit_resp.json()["task_id"]

        # Claim
        claim_resp = api_client.post(
            "/work/claim",
            headers=auth_headers,
            json={
                "agent_id": "e2e-agent",
                "agent_type": "test_agent",
                "task_types": ["refactor"],
            },
        )
        assert claim_resp.status_code == 200
        claim_data = claim_resp.json()
        assert claim_data["success"] is True
        assert claim_data["task_id"] == task_id

        # Complete
        complete_resp = api_client.post(
            "/work/complete",
            headers=auth_headers,
            json={
                "task_id": task_id,
                "agent_id": "e2e-agent",
                "success": True,
                "result": {"files_modified": ["src/locks.py"]},
            },
        )
        assert complete_resp.status_code == 200
        assert complete_resp.json()["success"] is True

    def test_claim_empty_queue(self, api_client, auth_headers) -> None:
        response = api_client.post(
            "/work/claim",
            headers=auth_headers,
            json={
                "agent_id": "e2e-agent",
                "agent_type": "test_agent",
                "task_types": ["nonexistent"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
