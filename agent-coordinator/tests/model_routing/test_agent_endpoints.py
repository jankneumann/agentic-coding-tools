"""Agent registry contract for routable endpoint metadata."""

from __future__ import annotations

from pathlib import Path

import pytest
from jsonschema import ValidationError

from src.agents_config import AgentEntry, get_dispatch_configs, load_agents_config


def _write_agent(path: Path, *, endpoint_kind: str, base_url: str | None = None) -> None:
    base_url_line = f'    base_url: "{base_url}"\n' if base_url is not None else ""
    path.write_text(
        "agents:\n"
        "  test-agent:\n"
        "    type: codex\n"
        "    profile: test_profile\n"
        "    trust_level: 2\n"
        "    transport: http\n"
        "    capabilities: [queue]\n"
        "    description: Test routable endpoint\n"
        f"    endpoint_kind: {endpoint_kind}\n"
        f"{base_url_line}"
    )


@pytest.mark.parametrize(
    "endpoint_kind", ["vendor-cli", "vendor-sdk", "openrouter", "local"]
)
def test_registry_accepts_known_endpoint_kinds(
    tmp_path: Path, endpoint_kind: str
) -> None:
    path = tmp_path / "agents.yaml"
    _write_agent(
        path,
        endpoint_kind=endpoint_kind,
        base_url="http://localhost:11434/v1" if endpoint_kind == "local" else None,
    )

    [agent] = load_agents_config(path, secrets_path=tmp_path / "none")

    assert agent.endpoint_kind == endpoint_kind
    assert agent.base_url == (
        "http://localhost:11434/v1" if endpoint_kind == "local" else None
    )


def test_registry_rejects_unknown_endpoint_kind(tmp_path: Path) -> None:
    path = tmp_path / "agents.yaml"
    _write_agent(path, endpoint_kind="mystery")

    with pytest.raises(ValidationError):
        load_agents_config(path, secrets_path=tmp_path / "none")


def test_dispatch_config_includes_endpoint_only_agent() -> None:
    agent = AgentEntry(
        name="local-openai",
        type="local",
        profile="local_openai",
        trust_level=1,
        transport="http",
        capabilities=["discover"],
        description="OpenAI-compatible local endpoint",
        endpoint_kind="local",
        base_url="http://127.0.0.1:11434/v1",
    )

    assert get_dispatch_configs([agent]) == {
        "agents": [
            {
                "agent_id": "local-openai",
                "type": "local",
                "transport": "http",
                "openbao_role_id": None,
                "endpoint_kind": "local",
                "base_url": "http://127.0.0.1:11434/v1",
                "cli": None,
                "sdk": None,
            }
        ]
    }
