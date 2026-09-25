"""Contract tests for the dedicated coordinator identity reader."""

from __future__ import annotations

import asyncio
import json
import logging

import pytest
from openbao_credentials import BaoCredentialError, ErrorCode

from src.agents_config import AgentEntry
from src.openbao_identity import IdentityRuntime, build_identity_snapshot, run_reload_loop


def _agent(name: str, key: str | None, transport: str = "http") -> AgentEntry:
    return AgentEntry(name=name, type="codex", profile=name, trust_level=1,
                      transport=transport, capabilities=[], description="", api_key=key)


class _Reader:
    def __init__(self, keys: dict[str, str]) -> None:
        self.keys = keys
        self.paths: list[str] = []
        self.sessions: list[tuple[str, str]] = []

    def ensure_session(self, principal_id: str, role_name: str) -> None:
        self.sessions.append((principal_id, role_name))

    def read_agent_key(self, name: str) -> str:
        self.paths.append(name)
        return self.keys[name]


def test_complete_snapshot_includes_mcp_and_uses_reader_only() -> None:
    reader = _Reader({"alice": "bao-a", "bob": "bao-b"})
    snapshot = build_identity_snapshot(
        reader, [_agent("alice", "${ALICE_KEY}"),
                 _agent("bob", "static-wrong", "mcp"), _agent("unkeyed", None)]
    )
    assert snapshot == {
        "bao-a": {"agent_id": "alice", "agent_type": "codex"},
        "bao-b": {"agent_id": "bob", "agent_type": "codex"},
    }
    assert reader.paths == ["alice", "bob"]
    assert reader.sessions == [
        ("spiffe://coordinator.rotkohl.ai/service/identity-reader", "service-identity-reader")
    ]


@pytest.mark.parametrize("keys", [{"alice": ""}, {"alice": "same", "bob": "same"}])
def test_incomplete_or_duplicate_snapshot_rejected(keys: dict[str, str]) -> None:
    reader = _Reader(keys)
    agents = [_agent(name, "${KEY}") for name in keys]
    with pytest.raises(BaoCredentialError) as error:
        build_identity_snapshot(reader, agents)
    assert error.value.code == ErrorCode.SECRET_MALFORMED


def test_failed_candidate_never_replaces_snapshot_and_grace_is_monotonic(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    now = [100.0]
    monkeypatch.setattr("src.openbao_identity.time.monotonic", lambda: now[0])
    reader = _Reader({"alice": "first"})
    runtime = IdentityRuntime(lambda: reader, lambda: [_agent("alice", "${KEY}")])
    runtime.reload()
    assert runtime.lookup("first") == {"agent_id": "alice", "agent_type": "codex"}
    reader.keys = {"alice": ""}
    now[0] = 110.0
    with caplog.at_level(logging.WARNING):
        runtime.reload()
    assert runtime.identity_status == "degraded"
    assert runtime.usable is True
    assert runtime.lookup("first") is not None
    assert "first" not in caplog.text
    assert "SECRET_MALFORMED" in caplog.text
    now[0] = 221.0
    assert runtime.usable is False
    assert runtime.lookup("first") is None
    reader.keys = {"alice": "rotated"}
    runtime.reload()
    assert runtime.identity_status == "ready"
    assert runtime.lookup("first") is None
    assert runtime.lookup("rotated") is not None


def test_grace_expiry_emits_one_sanitized_contract_event(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    from jsonschema import Draft202012Validator
    from openspec_paths import change_dir, repo_root_from

    now = [100.0]
    monkeypatch.setattr("src.openbao_identity.time.monotonic", lambda: now[0])
    runtime = IdentityRuntime(lambda: _Reader({"alice": "private-key"}),
                              lambda: [_agent("alice", "${KEY}")])
    assert runtime.reload()
    now[0] = 220.0
    assert runtime.lookup("private-key") is not None  # inclusive boundary
    now[0] = 220.001
    with caplog.at_level(logging.WARNING):
        assert runtime.lookup("private-key") is None
        assert runtime.readiness() == ("degraded", False)
        assert runtime.lookup("private-key") is None
    records = [json.loads(line.split("OpenBao identity event ", 1)[1])
               for line in caplog.messages if "OpenBao identity event " in line]
    assert len(records) == 1
    assert records[0]["event"] == "openbao.identity.snapshot_expired"
    assert records[0]["action"] == "expire"
    assert "private-key" not in json.dumps(records)
    path = change_dir(repo_root_from(__file__, 2), "restructure-openbao-per-agent-secrets")
    Draft202012Validator(json.loads((path / "contracts/openbao-event.schema.json").read_text()))\
        .validate(records[0])


def test_startup_failure_has_no_usable_snapshot() -> None:
    runtime = IdentityRuntime(lambda: _Reader({"alice": ""}),
                              lambda: [_agent("alice", "${KEY}")])
    runtime.reload()
    assert runtime.identity_status == "degraded"
    assert runtime.usable is False


def test_cutover_preflight_reports_unbound_static_keys_without_disclosing_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    runtime = IdentityRuntime(
        lambda: _Reader({"alice": "bao-key"}),
        lambda: [_agent("alice", "${KEY}")],
        required_static_keys=("bao-key", "unbound-secret"),
    )
    with caplog.at_level(logging.WARNING):
        assert runtime.reload() is False
    assert runtime.preflight_blockers == ("COORDINATION_API_KEYS[1]",)
    assert runtime.lookup("bao-key") is None
    assert "unbound-secret" not in caplog.text
    assert "COORDINATION_API_KEYS[1]" in caplog.text


def test_audit_failure_matches_frozen_event_contract(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from jsonschema import Draft202012Validator
    from openspec_paths import change_dir, repo_root_from

    path = change_dir(repo_root_from(__file__, 2), "restructure-openbao-per-agent-secrets")
    schema = json.loads((path / "contracts/openbao-event.schema.json").read_text())
    runtime = IdentityRuntime(lambda: _Reader({"alice": ""}),
                              lambda: [_agent("alice", "${KEY}")])
    with caplog.at_level(logging.WARNING):
        runtime.reload()
    record = next(json.loads(line.split("OpenBao identity event ", 1)[1])
                  for line in caplog.messages if "OpenBao identity event " in line)
    Draft202012Validator(schema).validate(record)
    assert record["error_code"] == "SECRET_MALFORMED"
    assert "alice" not in json.dumps(record)


@pytest.mark.asyncio
async def test_reload_loop_observes_rotation_without_restart() -> None:
    reader = _Reader({"alice": "before"})
    runtime = IdentityRuntime(lambda: reader, lambda: [_agent("alice", "${KEY}")])
    assert runtime.reload()
    reader.keys = {"alice": "after"}
    task = asyncio.create_task(run_reload_loop(runtime, interval=0.01))
    try:
        for _ in range(30):
            if runtime.lookup("after") is not None:
                break
            await asyncio.sleep(0.01)
        assert runtime.lookup("before") is None
        assert runtime.lookup("after") is not None
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
