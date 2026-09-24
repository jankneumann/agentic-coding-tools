"""Tests for isolation capability in agent profiles."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml
from jsonschema import ValidationError

from src.agents_config import (
    AgentEntry,
    CliConfig,
    ModeConfig,
    get_agent_isolation,
    get_dispatch_configs,
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


def test_mode_config_accepts_an_optional_isolation_override() -> None:
    mode = ModeConfig(args=["--print"], isolation="sandbox")
    assert mode.isolation == "sandbox"


def _mode_aware_agents_yaml(tmp_path: Path) -> Path:
    path = tmp_path / "agents.yaml"
    path.write_text(textwrap.dedent("""\
        agents:
          codex-local:
            type: codex
            profile: local
            trust_level: 3
            transport: mcp
            isolation: worktree
            capabilities: [lock]
            description: Local Codex
            cli:
              command: codex
              dispatch_modes:
                review:
                  args: [exec]
                  isolation: sandbox
                  enforcement_scope: execution
                  write_capable: false
                alternative:
                  args: [exec]
                  enforcement_scope: execution
                  write_capable: true
              model_flag: -m
              state_env_keys: []
          codex-remote:
            type: codex
            profile: remote
            trust_level: 2
            transport: http
            isolation: none
            capabilities: [lock]
            description: Remote Codex
            cli:
              command: codex
              dispatch_modes:
                review:
                  args: [exec]
                  enforcement_scope: submission
                  write_capable: false
              model_flag: -m
              state_env_keys: []
    """))
    return path


def test_get_agent_isolation_prefers_mode_override_and_preserves_legacy_call(
    tmp_path: Path,
    dummy_secrets: Path,
) -> None:
    agents = load_agents_config(
        _mode_aware_agents_yaml(tmp_path), secrets_path=dummy_secrets
    )
    import src.agents_config as mod
    mod._agents = agents

    assert get_agent_isolation("codex") == "worktree"
    assert get_agent_isolation("codex", "review", agent_id="codex-local") == "sandbox"
    assert get_agent_isolation("codex", "alternative", agent_id="codex-local") == "worktree"


def test_get_agent_isolation_uses_exact_agent_id_for_repeated_types(
    tmp_path: Path,
    dummy_secrets: Path,
) -> None:
    agents = load_agents_config(
        _mode_aware_agents_yaml(tmp_path), secrets_path=dummy_secrets
    )
    import src.agents_config as mod
    mod._agents = agents

    assert get_agent_isolation("codex", "review", agent_id="codex-remote") == "none"
    assert get_agent_isolation("codex", "review", agent_id="missing") is None
    assert get_agent_isolation("claude_code", "review", agent_id="codex-local") is None


def test_dispatch_config_serializes_mode_isolation(
    tmp_path: Path,
    dummy_secrets: Path,
) -> None:
    agents = load_agents_config(
        _mode_aware_agents_yaml(tmp_path), secrets_path=dummy_secrets
    )
    import src.agents_config as mod
    mod._agents = agents

    output = get_dispatch_configs()
    local = next(agent for agent in output["agents"] if agent["agent_id"] == "codex-local")
    assert local["cli"]["dispatch_modes"]["review"]["isolation"] == "sandbox"
    assert local["cli"]["dispatch_modes"]["alternative"]["isolation"] == "worktree"
    assert local["cli"]["dispatch_modes"]["review"]["enforcement_scope"] == "execution"
    assert local["cli"]["dispatch_modes"]["review"]["write_capable"] is False
    assert local["cli"]["state_env_keys"] == []


def test_invalid_per_mode_isolation_is_rejected_at_load(
    tmp_path: Path,
    dummy_secrets: Path,
) -> None:
    path = _mode_aware_agents_yaml(tmp_path)
    path.write_text(path.read_text().replace("isolation: sandbox", "isolation: container"))

    with pytest.raises(ValidationError, match="container"):
        load_agents_config(path, secrets_path=dummy_secrets)


def test_mode_enforcement_and_cli_state_keys_are_parsed(
    tmp_path: Path,
    dummy_secrets: Path,
) -> None:
    agents = load_agents_config(
        _mode_aware_agents_yaml(tmp_path), secrets_path=dummy_secrets
    )
    local = next(agent for agent in agents if agent.name == "codex-local")
    assert local.cli is not None
    assert local.cli.state_env_keys == []
    assert local.cli.dispatch_modes["review"].enforcement_scope == "execution"
    assert local.cli.dispatch_modes["review"].write_capable is False
    assert local.cli.dispatch_modes["alternative"].write_capable is True


@pytest.mark.parametrize(
    "missing_field",
    [
        "enforcement_scope",
        "write_capable",
        "state_env_keys",
    ],
)
def test_cli_sandbox_contract_fields_are_explicitly_required(
    tmp_path: Path,
    dummy_secrets: Path,
    missing_field: str,
) -> None:
    path = _mode_aware_agents_yaml(tmp_path)
    data = yaml.safe_load(path.read_text())
    cli = data["agents"]["codex-local"]["cli"]
    if missing_field == "state_env_keys":
        del cli[missing_field]
    else:
        del cli["dispatch_modes"]["review"][missing_field]
    path.write_text(yaml.safe_dump(data))

    with pytest.raises(ValidationError, match="required property"):
        load_agents_config(path, secrets_path=dummy_secrets)


def test_dispatch_config_projects_full_standalone_assignment(
    tmp_path: Path,
    dummy_secrets: Path,
) -> None:
    agents = load_agents_config(
        _mode_aware_agents_yaml(tmp_path), secrets_path=dummy_secrets
    )

    output = get_dispatch_configs(agents)
    local = next(agent for agent in output["agents"] if agent["agent_id"] == "codex-local")
    assert local["location"] == "unknown"
    assert local["isolation"] == "worktree"
    assert local["policy_vendor"] == "codex"
    assert local["catalog_vendor"] is None


@pytest.mark.parametrize("state_keys", ["[VENDOR_HOME, VENDOR_HOME]", "[not-valid]"])
def test_state_env_keys_reject_duplicates_and_invalid_names(
    tmp_path: Path,
    dummy_secrets: Path,
    state_keys: str,
) -> None:
    path = _mode_aware_agents_yaml(tmp_path)
    path.write_text(
        path.read_text().replace(
            "state_env_keys: []", f"state_env_keys: {state_keys}", 1
        )
    )

    with pytest.raises((ValidationError, ValueError), match="state_env_keys"):
        load_agents_config(path, secrets_path=dummy_secrets)


def test_sandbox_cli_without_environment_auth_is_rollout_ineligible() -> None:
    cli = CliConfig(
        command="codex",
        dispatch_modes={
            "review": ModeConfig(
                args=["exec"],
                isolation="sandbox",
                enforcement_scope="execution",
                write_capable=False,
            )
        },
        model_flag="-m",
        state_env_keys=[],
    )

    assert cli.sandbox_rollout_eligible("review") is False
    cli.api_key_env = "OPENAI_API_KEY"
    assert cli.sandbox_rollout_eligible("review") is True
