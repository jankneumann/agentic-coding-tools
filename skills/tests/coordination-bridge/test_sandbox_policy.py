"""Bridge helpers expose the exact sandbox policy/audit HTTP contract."""

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "coordination-bridge" / "scripts" / "coordination_bridge.py"
spec = importlib.util.spec_from_file_location("coordination_bridge_sandbox", SCRIPT)
bridge = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(bridge)


def test_export_network_policy_uses_exact_agent(monkeypatch):
    calls = []

    def request(**kwargs):
        calls.append(kwargs)
        return {"status_code": 200, "data": {"policy_digest": "a" * 64}, "error": None}

    monkeypatch.setattr(bridge, "_http_request", request)
    result = bridge.export_network_policy(
        "codex-local", http_url="http://localhost:3000", api_key="key"
    )
    assert result["policy_digest"] == "a" * 64
    assert calls[0]["path"] == "/policies/network/export?agent_id=codex-local"


def test_record_sandbox_event_preserves_permanent_error(monkeypatch):
    monkeypatch.setattr(
        bridge,
        "_http_request",
        lambda **_kwargs: {"status_code": 403, "data": {"detail": "denied"}, "error": None},
    )
    result = bridge.record_sandbox_event(
        {"event_id": "id"}, http_url="http://localhost:3000", api_key="k"
    )
    assert result["status_code"] == 403
    assert result["error_kind"] == "permanent_rejection"
