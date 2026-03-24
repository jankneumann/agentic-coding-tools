"""Tests for isolation capability in agent profiles."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.agents_config import (
    AgentEntry,
    get_agent_isolation,
    load_agents_config,
    reset_agents_config,
)


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:  # type: ignore[misc]
    """Reset the global agents config before each test."""
    reset_agents_config()
    yield  # type: ignore[misc]
    reset_agents_config()


@pytest.fixture()
def agents_yaml_with_isolation(tmp_path: Path) -> Path:
    """Create a minimal agents.yaml with isolation fields."""
    p = tmp_path / "agents.yaml"
    p.write_text(textwrap.dedent("""\
        agents:
          local-agent:
            type: claude_code
            profile: cli
            trust_level: 3
            transport: mcp
            isolation: worktree
            capabilities: [lock]
            description: A local agent

          cloud-agent:
            type: codex
            profile: cloud
            trust_level: 2
            transport: http
            isolation: sandbox
            capabilities: [lock]
            description: A cloud agent

          web-agent:
            type: gemini
            profile: web
            trust_level: 1
            transport: http
            isolation: none
            capabilities: [lock]
            description: A web agent
    """))
    return p


@pytest.fixture()
def agents_yaml_without_isolation(tmp_path: Path) -> Path:
    """Create agents.yaml without isolation fields (tests default)."""
    p = tmp_path / "agents.yaml"
    p.write_text(textwrap.dedent("""\
        agents:
          bare-agent:
            type: claude_code
            profile: bare
            trust_level: 3
            transport: mcp
            capabilities: [lock]
            description: Agent with no isolation field
    """))
    return p


@pytest.fixture()
def dummy_secrets(tmp_path: Path) -> Path:
    """Empty secrets file."""
    p = tmp_path / ".secrets.yaml"
    p.write_text("{}")
    return p


# -------------------------------------------------------------------
# Parsing isolation field
# -------------------------------------------------------------------

class TestIsolationParsing:
    """Test that the isolation field is parsed from agents.yaml."""

    def test_parses_worktree_isolation(
        self,
        agents_yaml_with_isolation: Path,
        dummy_secrets: Path,
    ) -> None:
        agents = load_agents_config(agents_yaml_with_isolation, secrets_path=dummy_secrets)
        local = next(a for a in agents if a.name == "local-agent")
        assert local.isolation == "worktree"

    def test_parses_sandbox_isolation(
        self,
        agents_yaml_with_isolation: Path,
        dummy_secrets: Path,
    ) -> None:
        agents = load_agents_config(agents_yaml_with_isolation, secrets_path=dummy_secrets)
        cloud = next(a for a in agents if a.name == "cloud-agent")
        assert cloud.isolation == "sandbox"

    def test_parses_none_isolation(
        self,
        agents_yaml_with_isolation: Path,
        dummy_secrets: Path,
    ) -> None:
        agents = load_agents_config(agents_yaml_with_isolation, secrets_path=dummy_secrets)
        web = next(a for a in agents if a.name == "web-agent")
        assert web.isolation == "none"


# -------------------------------------------------------------------
# Default when field is missing
# -------------------------------------------------------------------

class TestIsolationDefault:
    """Test that isolation defaults to 'none' when not specified."""

    def test_defaults_to_none_when_missing(
        self,
        agents_yaml_without_isolation: Path,
        dummy_secrets: Path,
    ) -> None:
        agents = load_agents_config(agents_yaml_without_isolation, secrets_path=dummy_secrets)
        assert len(agents) == 1
        assert agents[0].isolation == "none"

    def test_dataclass_default(self) -> None:
        entry = AgentEntry(
            name="test",
            type="claude_code",
            profile="test",
            trust_level=3,
            transport="mcp",
            capabilities=["lock"],
            description="test",
        )
        assert entry.isolation == "none"


# -------------------------------------------------------------------
# get_agent_isolation helper
# -------------------------------------------------------------------

class TestGetAgentIsolation:
    """Test the get_agent_isolation() helper function."""

    def test_returns_correct_value_for_known_type(
        self,
        agents_yaml_with_isolation: Path,
        dummy_secrets: Path,
    ) -> None:
        # Prime the singleton via load + re-get
        agents = load_agents_config(agents_yaml_with_isolation, secrets_path=dummy_secrets)
        # Manually set the singleton since get_agent_isolation uses get_agents_config
        import src.agents_config as mod
        mod._agents = agents

        assert get_agent_isolation("claude_code") == "worktree"
        assert get_agent_isolation("codex") == "sandbox"
        assert get_agent_isolation("gemini") == "none"

    def test_returns_none_for_unknown_type(
        self,
        agents_yaml_with_isolation: Path,
        dummy_secrets: Path,
    ) -> None:
        agents = load_agents_config(agents_yaml_with_isolation, secrets_path=dummy_secrets)
        import src.agents_config as mod
        mod._agents = agents

        assert get_agent_isolation("unknown_agent_type") is None

    def test_returns_none_when_no_agents_loaded(self) -> None:
        import src.agents_config as mod
        mod._agents = []
        assert get_agent_isolation("claude_code") is None
