"""Tests for agents_config — declarative agent configuration from YAML."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agents_config import (
    AgentEntry,
    get_agent_config,
    get_api_key_identities,
    get_mcp_env,
    load_agents_config,
    reset_agents_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_AGENTS_YAML = """\
agents:
  test-local:
    type: claude_code
    profile: claude_code_cli
    trust_level: 3
    transport: mcp
    capabilities: [lock, queue, memory]
    description: Test local agent

  test-cloud:
    type: codex
    profile: codex_cloud_worker
    trust_level: 2
    transport: http
    api_key: "${TEST_API_KEY}"
    capabilities: [lock, queue]
    description: Test cloud agent
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_agents_config()


# ---------------------------------------------------------------------------
# load_agents_config
# ---------------------------------------------------------------------------


class TestLoadAgentsConfig:
    def test_loads_valid_file(self, tmp_path: Path) -> None:
        agents_file = tmp_path / "agents.yaml"
        _write(agents_file, VALID_AGENTS_YAML)
        agents = load_agents_config(agents_file, secrets_path=tmp_path / "none")
        assert len(agents) == 2
        assert agents[0].name == "test-local"
        assert agents[0].transport == "mcp"
        assert agents[1].name == "test-cloud"
        assert agents[1].transport == "http"

    def test_api_key_resolved_from_secrets(self, tmp_path: Path) -> None:
        agents_file = tmp_path / "agents.yaml"
        _write(agents_file, VALID_AGENTS_YAML)
        secrets_file = tmp_path / ".secrets.yaml"
        _write(secrets_file, "TEST_API_KEY: secret123\n")
        agents = load_agents_config(agents_file, secrets_path=secrets_file)
        cloud = next(a for a in agents if a.name == "test-cloud")
        assert cloud.api_key == "secret123"

    def test_unresolved_api_key_is_none(self, tmp_path: Path) -> None:
        agents_file = tmp_path / "agents.yaml"
        _write(agents_file, VALID_AGENTS_YAML)
        agents = load_agents_config(agents_file, secrets_path=tmp_path / "none")
        cloud = next(a for a in agents if a.name == "test-cloud")
        assert cloud.api_key is None

    def test_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_agents_config(tmp_path / "ghost.yaml")

    def test_empty_file_raises(self, tmp_path: Path) -> None:
        agents_file = tmp_path / "agents.yaml"
        _write(agents_file, "")
        with pytest.raises(ValueError, match="Empty"):
            load_agents_config(agents_file)

    def test_schema_validation(self, tmp_path: Path) -> None:
        agents_file = tmp_path / "agents.yaml"
        _write(agents_file, "agents:\n  bad:\n    type: x\n")
        with pytest.raises(Exception):  # noqa: B017, PT011 — jsonschema.ValidationError
            load_agents_config(agents_file)

    def test_mcp_agent_has_no_api_key(self, tmp_path: Path) -> None:
        agents_file = tmp_path / "agents.yaml"
        _write(agents_file, VALID_AGENTS_YAML)
        agents = load_agents_config(agents_file, secrets_path=tmp_path / "none")
        local = next(a for a in agents if a.name == "test-local")
        assert local.api_key is None


# ---------------------------------------------------------------------------
# get_api_key_identities
# ---------------------------------------------------------------------------


class TestGetApiKeyIdentities:
    def test_generates_from_http_agents(self) -> None:
        agents = [
            AgentEntry(
                name="c1", type="codex", profile="p", trust_level=2,
                transport="http", capabilities=[], description="d",
                api_key="key1",
            ),
            AgentEntry(
                name="m1", type="claude_code", profile="p", trust_level=3,
                transport="mcp", capabilities=[], description="d",
            ),
        ]
        result = get_api_key_identities(agents)
        assert result == {"key1": {"agent_id": "c1", "agent_type": "codex"}}

    def test_skips_agents_without_key(self) -> None:
        agents = [
            AgentEntry(
                name="no-key", type="codex", profile="p", trust_level=2,
                transport="http", capabilities=[], description="d",
            ),
        ]
        assert get_api_key_identities(agents) == {}


# ---------------------------------------------------------------------------
# get_mcp_env
# ---------------------------------------------------------------------------


class TestGetMcpEnv:
    def test_generates_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DB_BACKEND", "postgres")
        monkeypatch.setenv("POSTGRES_DSN", "postgresql://localhost/test")
        agents = [
            AgentEntry(
                name="local", type="claude_code", profile="p", trust_level=3,
                transport="mcp", capabilities=[], description="d",
            ),
        ]
        result = get_mcp_env("local", agents)
        assert result["AGENT_ID"] == "local"
        assert result["AGENT_TYPE"] == "claude_code"
        assert result["DB_BACKEND"] == "postgres"
        assert result["POSTGRES_DSN"] == "postgresql://localhost/test"

    def test_unknown_agent_raises(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            get_mcp_env("ghost", [])


# ---------------------------------------------------------------------------
# get_agent_config (singleton)
# ---------------------------------------------------------------------------


class TestGetAgentConfig:
    def test_returns_none_for_unknown(self, tmp_path: Path) -> None:
        agents_file = tmp_path / "agents.yaml"
        _write(agents_file, VALID_AGENTS_YAML)
        reset_agents_config()
        # Load from explicit path first to populate singleton
        from src.agents_config import get_agents_config
        get_agents_config(agents_file)
        assert get_agent_config("nonexistent") is None
        reset_agents_config()
