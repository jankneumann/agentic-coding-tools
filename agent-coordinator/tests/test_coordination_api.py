"""Tests for verification gateway coordination API endpoints."""

import importlib

from fastapi import HTTPException
from fastapi.testclient import TestClient


class DummyDB:
    """In-memory stub for API endpoint DB calls."""

    def __init__(self):
        self.rpc_calls: list[tuple[str, dict]] = []
        self.query_calls: list[tuple[str, str]] = []
        self.rpc_response: dict = {"success": True}
        self.query_response: list[dict] = []

    async def rpc(self, function_name: str, params: dict) -> dict:
        self.rpc_calls.append((function_name, params))
        return self.rpc_response

    async def query(self, table: str, query: str = "") -> list[dict]:
        self.query_calls.append((table, query))
        return self.query_response


def _make_client():
    module = importlib.import_module("verification_gateway.coordination_api")
    dummy_db = DummyDB()
    module.db = dummy_db
    module.COORDINATION_API_KEYS = ["test-key"]
    module.API_KEY_IDENTITIES = {}
    app = module.create_coordination_api()
    return TestClient(app), dummy_db


def test_locks_acquire_uses_core_rpc_name():
    client, db = _make_client()
    db.rpc_response = {"success": True, "action": "acquired"}

    response = client.post(
        "/locks/acquire",
        headers={"X-API-Key": "test-key"},
        json={
            "file_path": "src/main.py",
            "agent_id": "agent-1",
            "agent_type": "codex",
            "session_id": "s1",
            "reason": "refactor",
            "ttl_minutes": 30,
        },
    )

    assert response.status_code == 200
    assert db.rpc_calls[0][0] == "acquire_lock"


def test_locks_acquire_requires_api_key():
    client, _ = _make_client()

    response = client.post(
        "/locks/acquire",
        json={
            "file_path": "src/main.py",
            "agent_id": "agent-1",
            "agent_type": "codex",
        },
    )

    assert response.status_code == 401


def test_work_endpoints_use_core_rpcs():
    client, db = _make_client()
    db.rpc_response = {"success": True, "task_id": "abc"}

    claim_resp = client.post(
        "/work/claim",
        headers={"X-API-Key": "test-key"},
        json={"agent_id": "agent-1", "agent_type": "codex", "task_types": ["test"]},
    )
    assert claim_resp.status_code == 200
    assert db.rpc_calls[0][0] == "claim_task"

    db.rpc_response = {"success": True, "status": "completed", "task_id": "abc"}
    complete_resp = client.post(
        "/work/complete",
        headers={"X-API-Key": "test-key"},
        json={
            "task_id": "abc",
            "agent_id": "agent-1",
            "success": True,
            "result": {"ok": True},
            "error_message": None,
        },
    )
    assert complete_resp.status_code == 200
    assert db.rpc_calls[1][0] == "complete_task"

    db.rpc_response = {"success": True, "task_id": "new-task"}
    submit_resp = client.post(
        "/work/submit",
        headers={"X-API-Key": "test-key"},
        json={
            "task_type": "test",
            "task_description": "Run tests",
            "input_data": {"files": ["src/a.py"]},
            "priority": 4,
            "depends_on": None,
        },
    )
    assert submit_resp.status_code == 200
    assert db.rpc_calls[2][0] == "submit_task"
    assert db.rpc_calls[2][1]["p_description"] == "Run tests"


def test_locks_status_returns_locked_false_when_no_rows():
    client, db = _make_client()
    db.query_response = []

    response = client.get("/locks/status/src/main.py")
    assert response.status_code == 200
    assert response.json()["locked"] is False
    assert db.query_calls[0][0] == "file_locks"


def test_locks_status_returns_lock_payload():
    client, db = _make_client()
    db.query_response = [{"file_path": "src/main.py", "locked_by": "agent-1"}]

    response = client.get("/locks/status/src/main.py")
    assert response.status_code == 200
    payload = response.json()
    assert payload["locked"] is True
    assert payload["lock"]["locked_by"] == "agent-1"


def test_acquire_lock_rejects_identity_spoofing():
    client, db = _make_client()
    db.rpc_response = {"success": True}

    module = importlib.import_module("verification_gateway.coordination_api")
    module.API_KEY_IDENTITIES = {
        "test-key": {"agent_id": "bound-agent", "agent_type": "codex"}
    }

    response = client.post(
        "/locks/acquire",
        headers={"X-API-Key": "test-key"},
        json={
            "file_path": "src/main.py",
            "agent_id": "different-agent",
            "agent_type": "codex",
        },
    )

    assert response.status_code == 403
    assert "agent_id" in response.json()["detail"]


def test_work_claim_returns_403_when_policy_denies(monkeypatch):
    client, _ = _make_client()
    module = importlib.import_module("verification_gateway.coordination_api")

    async def deny(*_args, **_kwargs):
        raise HTTPException(status_code=403, detail="denied-by-policy")

    monkeypatch.setattr(module, "authorize_operation", deny)

    response = client.post(
        "/work/claim",
        headers={"X-API-Key": "test-key"},
        json={"agent_id": "agent-1", "agent_type": "codex", "task_types": ["test"]},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "denied-by-policy"
