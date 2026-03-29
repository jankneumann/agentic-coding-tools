"""Tests for agents_config — declarative agent configuration from YAML."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

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

    def test_unresolved_api_key_kept_as_placeholder(self, tmp_path: Path) -> None:
        """Unresolved ${VAR} placeholders are preserved for OpenBao lookup."""
        agents_file = tmp_path / "agents.yaml"
        _write(agents_file, VALID_AGENTS_YAML)
        agents = load_agents_config(agents_file, secrets_path=tmp_path / "none")
        cloud = next(a for a in agents if a.name == "test-cloud")
        assert cloud.api_key == "${TEST_API_KEY}"

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

    def test_duplicate_key_warns(self) -> None:
        """Two agents sharing the same API key: last one wins with a warning."""
        agents = [
            AgentEntry(
                name="a1", type="codex", profile="p", trust_level=2,
                transport="http", capabilities=[], description="d",
                api_key="same-key",
            ),
            AgentEntry(
                name="a2", type="gemini", profile="p", trust_level=2,
                transport="http", capabilities=[], description="d",
                api_key="same-key",
            ),
        ]
        result = get_api_key_identities(agents)
        assert result["same-key"]["agent_id"] == "a2"  # last wins


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


class TestGetMcpEnvMissingVars:
    def test_omits_missing_db_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing DB env vars are omitted, not set to empty string."""
        monkeypatch.delenv("DB_BACKEND", raising=False)
        monkeypatch.delenv("POSTGRES_DSN", raising=False)
        monkeypatch.delenv("POSTGRES_POOL_MIN", raising=False)
        monkeypatch.delenv("POSTGRES_POOL_MAX", raising=False)
        agents = [
            AgentEntry(
                name="local", type="claude_code", profile="p", trust_level=3,
                transport="mcp", capabilities=[], description="d",
            ),
        ]
        result = get_mcp_env("local", agents)
        assert "POSTGRES_DSN" not in result
        assert "DB_BACKEND" not in result


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

    def test_graceful_fallback_when_missing(self, tmp_path: Path) -> None:
        """agents.yaml not found → returns empty list, no error."""
        from src.agents_config import get_agents_config
        reset_agents_config()
        result = get_agents_config(tmp_path / "nonexistent.yaml")
        assert result == []
        reset_agents_config()

    def test_partial_interpolation_preserved(self, tmp_path: Path) -> None:
        """api_key with embedded unresolved ${VAR} is preserved for OpenBao."""
        yaml_content = """\
agents:
  test-partial:
    type: codex
    profile: p
    trust_level: 2
    transport: http
    api_key: "prefix-${UNRESOLVED_KEY}"
    capabilities: [lock]
    description: Test partial interpolation
"""
        agents_file = tmp_path / "agents.yaml"
        _write(agents_file, yaml_content)
        agents = load_agents_config(agents_file, secrets_path=tmp_path / "none")
        assert agents[0].api_key == "prefix-${UNRESOLVED_KEY}"


# ---------------------------------------------------------------------------
# OpenBao AppRole integration
# ---------------------------------------------------------------------------


class TestOpenbaoRoleId:
    def test_openbao_role_id_loaded(self, tmp_path: Path) -> None:
        yaml_content = """\
agents:
  test-cloud:
    type: codex
    profile: p
    trust_level: 2
    transport: http
    api_key: "${API_KEY}"
    openbao_role_id: test-cloud
    capabilities: [lock]
    description: Agent with OpenBao role
"""
        agents_file = tmp_path / "agents.yaml"
        _write(agents_file, yaml_content)
        agents = load_agents_config(agents_file, secrets_path=tmp_path / "none")
        assert agents[0].openbao_role_id == "test-cloud"

    def test_openbao_role_id_optional(self, tmp_path: Path) -> None:
        agents_file = tmp_path / "agents.yaml"
        _write(agents_file, VALID_AGENTS_YAML)
        agents = load_agents_config(agents_file, secrets_path=tmp_path / "none")
        assert agents[0].openbao_role_id is None
        assert agents[1].openbao_role_id is None


class TestOpenbaoApiKeyResolution:
    def test_identities_without_openbao(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without BAO_ADDR, uses static api_key resolution."""
        monkeypatch.delenv("BAO_ADDR", raising=False)
        agents = [
            AgentEntry(
                name="c1", type="codex", profile="p", trust_level=2,
                transport="http", capabilities=[], description="d",
                api_key="static-key", openbao_role_id="c1",
            ),
        ]
        result = get_api_key_identities(agents)
        assert result == {"static-key": {"agent_id": "c1", "agent_type": "codex"}}

    @patch("src.agents_config._resolve_api_key_from_openbao")
    def test_identities_with_openbao(
        self, mock_resolve: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With BAO_ADDR, resolves keys from OpenBao for agents with role_id."""
        monkeypatch.setenv("BAO_ADDR", "http://localhost:8200")
        mock_resolve.return_value = "openbao-key"
        agents = [
            AgentEntry(
                name="c1", type="codex", profile="p", trust_level=2,
                transport="http", capabilities=[], description="d",
                api_key="${CODEX_KEY}", openbao_role_id="c1",
            ),
        ]
        result = get_api_key_identities(agents)
        assert "openbao-key" in result
        assert result["openbao-key"]["agent_id"] == "c1"

    def test_agent_without_role_uses_shared(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Agent without openbao_role_id uses static key even with BAO_ADDR set."""
        monkeypatch.delenv("BAO_ADDR", raising=False)
        agents = [
            AgentEntry(
                name="no-role", type="codex", profile="p", trust_level=2,
                transport="http", capabilities=[], description="d",
                api_key="shared-key",
            ),
        ]
        result = get_api_key_identities(agents)
        assert result == {"shared-key": {"agent_id": "no-role", "agent_type": "codex"}}

    def test_resolve_uses_agent_role_id(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """_resolve_api_key_from_openbao authenticates with the agent's own role_id."""
        from src.agents_config import _resolve_api_key_from_openbao

        mock_config = MagicMock()
        mock_config.is_enabled.return_value = True
        mock_config.addr = "http://localhost:8200"
        mock_config.timeout = 5
        mock_config.secret_id = "shared-secret"
        mock_config.secret_path = "coordinator"
        mock_config.mount_path = "secret"

        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"MY_KEY": "resolved-value"}}
        }

        mock_hvac = MagicMock()
        mock_hvac.Client.return_value = mock_client

        with patch("src.config.OpenBaoConfig.from_env", return_value=mock_config), \
             patch.dict("sys.modules", {"hvac": mock_hvac}):
            agent = AgentEntry(
                name="c1", type="codex", profile="p", trust_level=2,
                transport="http", capabilities=[], description="d",
                api_key="${MY_KEY}", openbao_role_id="agent-c1-role",
            )
            result = _resolve_api_key_from_openbao(agent)
            assert result == "resolved-value"
            # Verify it used the agent's role_id, not the global one
            mock_client.auth.approle.login.assert_called_once_with(
                role_id="agent-c1-role", secret_id="shared-secret",
            )

    @patch("src.agents_config._resolve_api_key_from_openbao")
    def test_openbao_failure_falls_back(
        self, mock_resolve: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OpenBao failure falls back to static key."""
        monkeypatch.setenv("BAO_ADDR", "http://localhost:8200")
        mock_resolve.return_value = "fallback-key"
        agents = [
            AgentEntry(
                name="c1", type="codex", profile="p", trust_level=2,
                transport="http", capabilities=[], description="d",
                api_key="fallback-key", openbao_role_id="c1",
            ),
        ]
        result = get_api_key_identities(agents)
        assert "fallback-key" in result


# ---------------------------------------------------------------------------
# ApiConfig auto-population of api_keys from agents.yaml
# ---------------------------------------------------------------------------


class TestApiKeysAutoPopulation:
    """Verify that api_keys list is derived from identity map when not set."""

    def test_api_keys_derived_from_identities(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When COORDINATION_API_KEYS is empty, keys come from identities."""
        from src.config import ApiConfig

        monkeypatch.delenv("COORDINATION_API_KEYS", raising=False)
        monkeypatch.delenv("COORDINATION_API_KEY_IDENTITIES", raising=False)
        identities = {"key-a": {"agent_id": "a1", "agent_type": "codex"}}
        with patch("src.agents_config.get_api_key_identities", return_value=identities):
            config = ApiConfig.from_env()
        assert "key-a" in config.api_keys
        assert config.api_key_identities == identities

    def test_explicit_keys_not_overridden(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When COORDINATION_API_KEYS is set explicitly, it is used as-is."""
        from src.config import ApiConfig

        monkeypatch.setenv("COORDINATION_API_KEYS", "explicit-key")
        monkeypatch.delenv("COORDINATION_API_KEY_IDENTITIES", raising=False)
        identities = {"other-key": {"agent_id": "a1", "agent_type": "codex"}}
        with patch("src.agents_config.get_api_key_identities", return_value=identities):
            config = ApiConfig.from_env()
        assert config.api_keys == ["explicit-key"]

    def test_empty_identities_no_keys(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When both env vars are empty and agents.yaml has no HTTP agents, keys stay empty."""
        from src.config import ApiConfig

        monkeypatch.delenv("COORDINATION_API_KEYS", raising=False)
        monkeypatch.delenv("COORDINATION_API_KEY_IDENTITIES", raising=False)
        with patch("src.agents_config.get_api_key_identities", return_value={}):
            config = ApiConfig.from_env()
        assert config.api_keys == []
        assert config.api_key_identities == {}


# ---------------------------------------------------------------------------
# CLI config tests
# ---------------------------------------------------------------------------

AGENTS_WITH_CLI_YAML = """\
agents:
  test-with-cli:
    type: codex
    profile: codex_local_worker
    trust_level: 3
    transport: mcp
    capabilities: [lock, queue]
    description: Agent with CLI config
    cli:
      command: codex
      dispatch_modes:
        review:
          args: ["exec", "-s", "read-only"]
        alternative:
          args: ["exec", "-s", "workspace-write"]
      model_flag: "-m"
      model: null
      model_fallbacks: ["o3", "gpt-4.1"]

  test-without-cli:
    type: claude_code
    profile: claude_code_cli
    trust_level: 3
    transport: mcp
    capabilities: [lock, queue]
    description: Agent without CLI config
"""


class TestCliConfig:
    """Tests for CLI dispatch configuration in agents.yaml."""

    def test_load_agent_with_cli_section(self, tmp_path: Path) -> None:
        """Agent with cli section parses CliConfig correctly."""
        agents_file = tmp_path / "agents.yaml"
        agents_file.write_text(AGENTS_WITH_CLI_YAML)
        secrets_file = tmp_path / ".secrets.yaml"
        secrets_file.write_text("{}")

        entries = load_agents_config(agents_file, secrets_path=secrets_file)

        with_cli = next(e for e in entries if e.name == "test-with-cli")
        assert with_cli.cli is not None
        assert with_cli.cli.command == "codex"
        assert with_cli.cli.model_flag == "-m"
        assert with_cli.cli.model is None
        assert with_cli.cli.model_fallbacks == ["o3", "gpt-4.1"]

    def test_cli_dispatch_modes_parsed(self, tmp_path: Path) -> None:
        """Dispatch modes are parsed as ModeConfig with args lists."""
        agents_file = tmp_path / "agents.yaml"
        agents_file.write_text(AGENTS_WITH_CLI_YAML)
        secrets_file = tmp_path / ".secrets.yaml"
        secrets_file.write_text("{}")

        entries = load_agents_config(agents_file, secrets_path=secrets_file)

        with_cli = next(e for e in entries if e.name == "test-with-cli")
        assert with_cli.cli is not None
        assert "review" in with_cli.cli.dispatch_modes
        assert "alternative" in with_cli.cli.dispatch_modes
        review_args = with_cli.cli.dispatch_modes["review"].args
        assert review_args == ["exec", "-s", "read-only"]
        impl_args = with_cli.cli.dispatch_modes["alternative"].args
        assert impl_args == ["exec", "-s", "workspace-write"]

    def test_agent_without_cli_section_has_none(self, tmp_path: Path) -> None:
        """Agent without cli section has cli=None."""
        agents_file = tmp_path / "agents.yaml"
        agents_file.write_text(AGENTS_WITH_CLI_YAML)
        secrets_file = tmp_path / ".secrets.yaml"
        secrets_file.write_text("{}")

        entries = load_agents_config(agents_file, secrets_path=secrets_file)

        without_cli = next(e for e in entries if e.name == "test-without-cli")
        assert without_cli.cli is None

    def test_real_agents_yaml_loads_cli(self) -> None:
        """The real agents.yaml loads with CLI sections for local agents."""
        entries = load_agents_config()
        local_with_cli = [e for e in entries if e.cli is not None]
        assert len(local_with_cli) >= 3, "Expected at least 3 agents with CLI config"
        vendors = {e.type for e in local_with_cli}
        assert vendors == {"claude_code", "codex", "gemini"}

    def test_cli_model_with_explicit_value(self, tmp_path: Path) -> None:
        """Agent with explicit model value (not null) parses correctly."""
        yaml_content = """\
agents:
  test-explicit-model:
    type: codex
    profile: codex_local_worker
    trust_level: 3
    transport: mcp
    capabilities: [lock, queue]
    description: Agent with explicit model
    cli:
      command: codex
      dispatch_modes:
        review:
          args: ["exec", "-s", "read-only"]
      model_flag: "-m"
      model: "o3"
      model_fallbacks: []
"""
        agents_file = tmp_path / "agents.yaml"
        agents_file.write_text(yaml_content)
        secrets_file = tmp_path / ".secrets.yaml"
        secrets_file.write_text("{}")

        entries = load_agents_config(agents_file, secrets_path=secrets_file)
        assert entries[0].cli is not None
        assert entries[0].cli.model == "o3"
        assert entries[0].cli.model_fallbacks == []


# ---------------------------------------------------------------------------
# SDK config tests
# ---------------------------------------------------------------------------

AGENTS_WITH_SDK_YAML = """\
agents:
  test-remote:
    type: codex
    profile: codex_cloud_worker
    trust_level: 2
    transport: http
    capabilities: [lock, queue]
    description: Agent with SDK config
    sdk:
      package: openai
      method: chat.completions.create
      model: gpt-5.4
      model_fallbacks: [gpt-5.4-mini]
      api_key_env: OPENAI_API_KEY
      max_tokens: 8192

  test-no-sdk:
    type: claude_code
    profile: claude_code_cli
    trust_level: 3
    transport: mcp
    capabilities: [lock, queue]
    description: Agent without SDK config
"""


class TestSdkConfig:
    """Tests for SDK dispatch configuration in agents.yaml."""

    def test_load_agent_with_sdk_section(self, tmp_path: Path) -> None:
        """Agent with sdk section parses SdkConfig correctly."""
        agents_file = tmp_path / "agents.yaml"
        agents_file.write_text(AGENTS_WITH_SDK_YAML)
        secrets_file = tmp_path / ".secrets.yaml"
        secrets_file.write_text("{}")

        entries = load_agents_config(agents_file, secrets_path=secrets_file)

        with_sdk = next(e for e in entries if e.name == "test-remote")
        assert with_sdk.sdk is not None
        assert with_sdk.sdk.package == "openai"
        assert with_sdk.sdk.model == "gpt-5.4"
        assert with_sdk.sdk.method == "chat.completions.create"
        assert with_sdk.sdk.model_fallbacks == ["gpt-5.4-mini"]
        assert with_sdk.sdk.api_key_env == "OPENAI_API_KEY"
        assert with_sdk.sdk.max_tokens == 8192

    def test_agent_without_sdk_section_has_none(self, tmp_path: Path) -> None:
        """Agent without sdk section has sdk=None."""
        agents_file = tmp_path / "agents.yaml"
        agents_file.write_text(AGENTS_WITH_SDK_YAML)
        secrets_file = tmp_path / ".secrets.yaml"
        secrets_file.write_text("{}")

        entries = load_agents_config(agents_file, secrets_path=secrets_file)

        without_sdk = next(e for e in entries if e.name == "test-no-sdk")
        assert without_sdk.sdk is None

    def test_real_agents_yaml_loads_sdk(self) -> None:
        """The real agents.yaml loads with SDK sections for remote agents."""
        entries = load_agents_config()
        remote_with_sdk = [e for e in entries if e.sdk is not None]
        assert len(remote_with_sdk) >= 3, "Expected at least 3 agents with SDK config"
        packages = {e.sdk.package for e in remote_with_sdk}
        assert packages == {"anthropic", "openai", "google-generativeai"}

    def test_sdk_defaults_applied(self, tmp_path: Path) -> None:
        """SDK section with only required fields gets correct defaults."""
        yaml_content = """\
agents:
  test-minimal-sdk:
    type: codex
    profile: p
    trust_level: 2
    transport: http
    capabilities: [lock]
    description: Minimal SDK
    sdk:
      package: openai
      model: gpt-5.4
"""
        agents_file = tmp_path / "agents.yaml"
        agents_file.write_text(yaml_content)
        secrets_file = tmp_path / ".secrets.yaml"
        secrets_file.write_text("{}")

        entries = load_agents_config(agents_file, secrets_path=secrets_file)
        sdk = entries[0].sdk
        assert sdk is not None
        assert sdk.method == "messages.create"  # default
        assert sdk.model_fallbacks == []
        assert sdk.api_key_env == ""
        assert sdk.max_tokens == 16384
