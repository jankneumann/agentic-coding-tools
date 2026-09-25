"""D1 and the principal-topology contract, including negative scope cases."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from openbao_credentials import ProjectionError, project_principals


CONTRACT = (
    Path(__file__).resolve().parents[3]
    / "openspec/changes/restructure-openbao-per-agent-secrets/contracts/principal-topology.schema.json"
)


def registry() -> dict:
    return {
        "credential_vendors": ["openai", "anthropic"],
        "agents": {
            "codex-local": {"api_key": "${CODEX_KEY}", "vendor_credentials": ["openai"]},
            "claude-local": {"api_key": "${CLAUDE_KEY}", "vendor_credentials": ["anthropic"]},
            "local-endpoint": {"vendor_credentials": []},
        },
    }


def test_projection_validates_schema_and_exact_scopes() -> None:
    topology = project_principals(registry(), mount="vault")
    Draft202012Validator(json.loads(CONTRACT.read_text())).validate(topology.to_dict())
    assert topology.vendors == ("anthropic", "openai")
    assert len(topology.principals) == 4
    codex = topology.by_id("spiffe://coordinator.rotkohl.ai/agent/codex-local")
    assert codex.role_name == codex.policy_name == "agent-codex-local"
    assert codex.agent_kv_path == "agents/codex-local"
    assert codex.read_paths == (
        "vault/data/agents/codex-local", "vault/data/vendors/openai"
    )
    identity = topology.by_id("spiffe://coordinator.rotkohl.ai/service/identity-reader")
    assert identity.read_paths == (
        "vault/data/agents/claude-local", "vault/data/agents/codex-local"
    )
    gateway = topology.by_id("spiffe://coordinator.rotkohl.ai/service/egress-gateway")
    assert gateway.read_paths == ("vault/data/vendors/anthropic", "vault/data/vendors/openai")


@pytest.mark.parametrize("mutation", [
    lambda r: r["agents"]["codex-local"].update(openbao_role_id="custom"),
    lambda r: r["agents"]["codex-local"].update(vendor_credentials=["unknown"]),
    lambda r: r["agents"]["codex-local"].update(vendor_credentials=["openai", "openai"]),
    lambda r: r["agents"].update({"bad_name": {"api_key": "key"}}),
    lambda r: r["agents"]["local-endpoint"].update(vendor_credentials=["openai"]),
    lambda r: r.update(credential_vendors=["openai", "openai"]),
])
def test_projection_rejects_unsafe_registry(mutation) -> None:
    raw = registry()
    mutation(raw)
    with pytest.raises(ProjectionError):
        project_principals(raw)


def test_projection_is_order_independent() -> None:
    first = registry()
    second = registry()
    second["agents"] = dict(reversed(list(second["agents"].items())))
    second["credential_vendors"].reverse()
    assert project_principals(first).to_dict() == project_principals(second).to_dict()


def test_mount_must_be_single_valid_segment() -> None:
    with pytest.raises(ProjectionError):
        project_principals(registry(), mount="secret/data")
