"""Tests for the GET /work/get HTTP endpoint."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.coordination_api import create_coordination_api
from src.work_queue import Task

_TEST_KEY = "test-key-001"


@pytest.fixture()
def _api_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import reset_config

    reset_config()
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("COORDINATION_API_KEYS", _TEST_KEY)
    monkeypatch.setenv("COORDINATION_API_KEY_IDENTITIES", "{}")
    reset_config()
    yield  # type: ignore[misc]
    reset_config()


@pytest.fixture()
def client(_api_config: None) -> TestClient:
    app = create_coordination_api()
    return TestClient(app)


def _auth_headers() -> dict[str, str]:
    return {"X-API-Key": _TEST_KEY}


def _make_task(**overrides: Any) -> Task:
    defaults = {
        "id": uuid4(),
        "task_type": "implement",
        "description": "Test task",
        "status": "pending",
        "priority": 5,
    }
    defaults.update(overrides)
    return Task(**defaults)


class TestGetTaskEndpoint:
    def test_get_task_found(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        task = _make_task(
            task_type="refactor",
            description="Refactor auth module",
            status="claimed",
            priority=3,
            claimed_by="agent-1",
            claimed_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

        mock_service = AsyncMock()
        mock_service.get_task.return_value = task
        monkeypatch.setattr("src.coordination_api.authorize_operation", AsyncMock())

        import src.work_queue

        monkeypatch.setattr(src.work_queue, "_work_queue_service", mock_service)

        response = client.post(
            "/work/get",
            headers=_auth_headers(),
            json={"task_id": str(task.id)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["task"]["id"] == str(task.id)
        assert data["task"]["task_type"] == "refactor"
        assert data["task"]["status"] == "claimed"
        assert data["task"]["claimed_by"] == "agent-1"
        mock_service.get_task.assert_called_once()

    def test_get_task_not_found(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_service = AsyncMock()
        mock_service.get_task.return_value = None
        monkeypatch.setattr("src.coordination_api.authorize_operation", AsyncMock())

        import src.work_queue

        monkeypatch.setattr(src.work_queue, "_work_queue_service", mock_service)

        response = client.post(
            "/work/get",
            headers=_auth_headers(),
            json={"task_id": str(uuid4())},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["reason"] == "task_not_found"

    def test_get_task_requires_auth(self, client: TestClient) -> None:
        response = client.post(
            "/work/get",
            json={"task_id": str(uuid4())},
        )
        assert response.status_code == 401

    def test_get_task_serializes_all_fields(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        now = datetime(2026, 2, 15, 12, 0, tzinfo=UTC)
        dep_id = uuid4()
        task = _make_task(
            input_data={"package": "wp-backend"},
            claimed_by="agent-2",
            claimed_at=now,
            result={"files_modified": ["src/api.py"]},
            error_message=None,
            depends_on=[dep_id],
            deadline=now,
            created_at=now,
            completed_at=now,
        )

        mock_service = AsyncMock()
        mock_service.get_task.return_value = task
        monkeypatch.setattr("src.coordination_api.authorize_operation", AsyncMock())

        import src.work_queue

        monkeypatch.setattr(src.work_queue, "_work_queue_service", mock_service)

        response = client.post(
            "/work/get",
            headers=_auth_headers(),
            json={"task_id": str(task.id)},
        )
        data = response.json()["task"]
        assert data["input_data"] == {"package": "wp-backend"}
        assert data["depends_on"] == [str(dep_id)]
        assert data["deadline"] is not None
        assert data["created_at"] is not None
        assert data["completed_at"] is not None
