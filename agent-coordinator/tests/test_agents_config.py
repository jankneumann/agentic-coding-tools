"""Tests for agents_config — declarative agent configuration from YAML."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.agents_config import (
    ALL_MODEL_TIERS as ALL_TIERS,
)
from src.agents_config import (
    AgentEntry,
    DuplicateApiKeyError,
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

    def test_duplicate_profile_rejected_naming_both_agents(
        self, tmp_path: Path,
    ) -> None:
        """Two agents sharing a profile is a silent privilege escalation.

        ``sync_profiles()`` upserts by profile name in file order, so the later
        entry overwrites the earlier one's trust level and operations. Here
        ``test-local`` declares ``trust_level: 3`` but would end up owning a
        profile row projected at 4 — promoted to admin without its own
        ``trust_level`` line changing, and invisible to orphan disabling and to
        the registry invariant check (both of which key on profile name).
        """
        agents_file = tmp_path / "agents.yaml"
        _write(
            agents_file,
            VALID_AGENTS_YAML
            + """
  test-shadow:
    type: claude_code
    profile: claude_code_cli
    trust_level: 4
    transport: mcp
    capabilities: [lock]
    description: Squats on test-local's profile
""",
        )
        with pytest.raises(ValueError, match="Duplicate profile") as excinfo:
            load_agents_config(agents_file, secrets_path=tmp_path / "none")

        message = str(excinfo.value)
        assert "claude_code_cli" in message
        assert "test-local" in message
        assert "test-shadow" in message

    def test_distinct_profiles_still_load(self, tmp_path: Path) -> None:
        """The duplicate-profile guard must not reject a well-formed roster."""
        agents_file = tmp_path / "agents.yaml"
        _write(agents_file, VALID_AGENTS_YAML)
        agents = load_agents_config(agents_file, secrets_path=tmp_path / "none")
        profiles = [a.profile for a in agents]
        assert len(profiles) == len(set(profiles))

    def test_shipped_registry_has_no_duplicate_profiles(self) -> None:
        """The real agents.yaml must satisfy the one-agent-one-profile rule."""
        agents = load_agents_config()
        profiles = [a.profile for a in agents]
        assert len(profiles) == len(set(profiles))


# ---------------------------------------------------------------------------
# get_api_key_identities
# ---------------------------------------------------------------------------


class TestGetApiKeyIdentities:
    def test_generates_for_agents_with_keys(self) -> None:
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
        # m1 has no api_key at all, so it contributes nothing.
        assert result == {"key1": {"agent_id": "c1", "agent_type": "codex"}}

    def test_mcp_transport_agent_receives_identity(self) -> None:
        """Transport does not gate identity (design D5).

        The MCP server's HTTP-proxy fallback makes local agents HTTP
        principals in practice, so an `mcp` agent with a resolvable key
        must appear in the identity map.
        """
        agents = [
            AgentEntry(
                name="grok-local", type="grok", profile="grok_local",
                trust_level=3, transport="mcp", capabilities=[],
                description="d", api_key="grok-key",
            ),
        ]
        result = get_api_key_identities(agents)
        assert result == {
            "grok-key": {"agent_id": "grok-local", "agent_type": "grok"}
        }

    def test_full_roster_identity_map(self) -> None:
        """Every agent with a resolvable key gets an entry, any transport."""
        transports = ["mcp", "mcp", "mcp", "http", "http", "mcp", "http"]
        agents = [
            AgentEntry(
                name=f"a{i}", type=f"t{i}", profile="p", trust_level=2,
                transport=transport, capabilities=[], description="d",
                api_key=f"key-{i}",
            )
            for i, transport in enumerate(transports)
        ]
        result = get_api_key_identities(agents)
        assert len(result) == 7
        assert result["key-0"]["agent_id"] == "a0"

    def test_skips_agents_without_key(self) -> None:
        agents = [
            AgentEntry(
                name="no-key", type="codex", profile="p", trust_level=2,
                transport="http", capabilities=[], description="d",
            ),
        ]
        assert get_api_key_identities(agents) == {}

    def test_unresolved_placeholder_excluded(self) -> None:
        agents = [
            AgentEntry(
                name="unresolved", type="codex", profile="p", trust_level=2,
                transport="mcp", capabilities=[], description="d",
                api_key="${NEVER_SET}",
            ),
        ]
        assert get_api_key_identities(agents) == {}

    def test_duplicate_key_raises_naming_both_agents(self) -> None:
        """Duplicate resolved keys are a load error (design D6).

        Previously the last writer won with a warning, which silently
        misattributed one principal's operations to the other in audit logs.
        """
        agents = [
            AgentEntry(
                name="a1", type="codex", profile="p", trust_level=2,
                transport="http", capabilities=[], description="d",
                api_key="same-key",
            ),
            AgentEntry(
                name="a2", type="gemini", profile="p", trust_level=2,
                transport="mcp", capabilities=[], description="d",
                api_key="same-key",
            ),
        ]
        with pytest.raises(DuplicateApiKeyError) as excinfo:
            get_api_key_identities(agents)
        message = str(excinfo.value)
        assert "a1" in message
        assert "a2" in message

    def test_explicit_env_var_overrides_registry(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """COORDINATION_API_KEY_IDENTITIES still wins (design D8 rollback lever)."""
        from src.config import ApiConfig

        explicit = {"pinned": {"agent_id": "pinned-agent", "agent_type": "codex"}}
        monkeypatch.setenv("COORDINATION_API_KEY_IDENTITIES", json.dumps(explicit))
        monkeypatch.delenv("COORDINATION_API_KEYS", raising=False)
        with patch(
            "src.agents_config.get_api_key_identities",
            side_effect=AssertionError("registry must not be consulted"),
        ):
            config = ApiConfig.from_env()
        assert config.api_key_identities == explicit

    def test_duplicate_key_not_swallowed_by_config(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A duplicate-key load error must reach the operator, not warn-and-empty."""
        from src.config import ApiConfig

        monkeypatch.delenv("COORDINATION_API_KEYS", raising=False)
        monkeypatch.delenv("COORDINATION_API_KEY_IDENTITIES", raising=False)
        with patch(
            "src.agents_config.get_api_key_identities",
            side_effect=DuplicateApiKeyError("a1", "a2"),
        ), pytest.raises(DuplicateApiKeyError):
            ApiConfig.from_env()


# ---------------------------------------------------------------------------
# Trust-scale wiring (design D4)
# ---------------------------------------------------------------------------


class TestTrustLevelSchemaBounds:
    def test_schema_bounds_derive_from_trust_module(self) -> None:
        from src.agents_config import AGENTS_SCHEMA
        from src.trust_levels import MAX_TRUST, MIN_TRUST

        trust_schema = (
            AGENTS_SCHEMA["properties"]["agents"]["additionalProperties"]
            ["properties"]["trust_level"]
        )
        assert trust_schema["minimum"] == MIN_TRUST
        assert trust_schema["maximum"] == MAX_TRUST

    def test_out_of_scale_trust_level_rejected(self, tmp_path: Path) -> None:
        agents_file = tmp_path / "agents.yaml"
        _write(agents_file, VALID_AGENTS_YAML.replace("trust_level: 3", "trust_level: 5"))
        with pytest.raises(Exception):  # noqa: B017, PT011 — ValidationError
            load_agents_config(agents_file, secrets_path=tmp_path / "none")


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
        """The real agents.yaml loads with CLI sections for local agents.

        Roster per ``contracts/roster.md`` (add-agy-grok-pi-harnesses): the five
        first-class local CLI vendors are claude_code, codex, antigravity, grok,
        and pi. ``gemini`` is retired and MUST NOT appear.
        """
        entries = load_agents_config()
        local_with_cli = [e for e in entries if e.cli is not None]
        assert len(local_with_cli) >= 3, "Expected at least 3 agents with CLI config"
        vendors = {e.type for e in local_with_cli}
        assert vendors == {"claude_code", "codex", "antigravity", "grok", "pi"}
        assert "gemini" not in vendors

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
        """The real agents.yaml loads with SDK sections for remote agents.

        After the roster change (add-agy-grok-pi-harnesses) the SDK-dispatch
        agents are the two remote API workers, claude-remote (anthropic) and
        codex-remote (openai). The retired remote Gemini API worker was the only
        google-generativeai SDK entry; the new antigravity/grok/pi harnesses are
        local CLI agents with no SDK block.
        """
        entries = load_agents_config()
        remote_with_sdk = [e for e in entries if e.sdk is not None]
        assert len(remote_with_sdk) >= 2, "Expected at least 2 agents with SDK config"
        packages = {e.sdk.package for e in remote_with_sdk}
        assert packages == {"anthropic", "openai"}
        assert "google-generativeai" not in packages

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


# ---------------------------------------------------------------------------
# Provider model-map roster (add-agy-grok-pi-harnesses)
# ---------------------------------------------------------------------------

# The canonical provider roster (contracts/roster.md, extended by
# add-local-model-provider-tier). Derived from the contract's provider-key
# column, NOT from model-id literals (feedback: tests-derive-from-config).
# `gemini` is retired and MUST NOT be a provider key.
CLOUD_ROSTER_PROVIDER_KEYS = frozenset(
    {"claude_code", "codex", "antigravity", "grok", "pi"}
)
ROSTER_PROVIDER_KEYS = CLOUD_ROSTER_PROVIDER_KEYS | {"local"}
BASE_MODEL_TIERS = frozenset({"premium", "standard", "economy"})


def _tier_model(value: Any) -> str:
    """A tier entry is a bare model id or a {model, thinking} pair."""
    return value["model"] if isinstance(value, dict) else value


class TestProviderModelMapRoster:
    """DEFAULT_PROVIDER_MODEL_MAP reflects the vendor roster.

    Spec: configuration.2 (provider map includes all first-class providers;
    pi maps to OpenRouter slugs). Contract: contracts/roster.md.
    """

    def test_providers_are_exactly_the_roster(self) -> None:
        from src.agents_config import DEFAULT_PROVIDER_MODEL_MAP

        providers = set(DEFAULT_PROVIDER_MODEL_MAP["providers"])
        assert providers == set(ROSTER_PROVIDER_KEYS)

    def test_gemini_is_retired(self) -> None:
        from src.agents_config import DEFAULT_PROVIDER_MODEL_MAP

        assert "gemini" not in DEFAULT_PROVIDER_MODEL_MAP["providers"]

    def test_every_cloud_provider_defines_base_tiers(self) -> None:
        from src.agents_config import DEFAULT_PROVIDER_MODEL_MAP

        for provider in CLOUD_ROSTER_PROVIDER_KEYS:
            mapping = DEFAULT_PROVIDER_MODEL_MAP["providers"][provider]
            assert BASE_MODEL_TIERS <= set(mapping), (
                f"{provider} must define {sorted(BASE_MODEL_TIERS)}; got {sorted(mapping)}"
            )

    def test_local_provider_defines_its_required_tiers(self) -> None:
        """agent-archetypes.1: `local` defines at minimum standard + economy.

        Omitted tiers (frontier/premium) resolve through graceful degradation,
        so the local roster is NOT held to the full base-tier requirement.
        """
        from src.agents_config import (
            DEFAULT_PROVIDER_MODEL_MAP,
            LOCAL_PROVIDER,
            LOCAL_REQUIRED_TIERS,
        )

        mapping = DEFAULT_PROVIDER_MODEL_MAP["providers"][LOCAL_PROVIDER]
        assert set(LOCAL_REQUIRED_TIERS) <= set(mapping)

    def test_pi_tiers_are_openrouter_slugs(self) -> None:
        # Spec configuration.2 "pi maps to OpenRouter slugs": every tier value is
        # a `<publisher>/<model>` slug. The `standard` == `qwen/qwen3-coder`
        # assertion below is the spec's own SHALL, not an incidental literal.
        from src.agents_config import DEFAULT_PROVIDER_MODEL_MAP

        pi = DEFAULT_PROVIDER_MODEL_MAP["providers"]["pi"]
        for tier, value in pi.items():
            slug = _tier_model(value)
            assert slug.count("/") == 1, (
                f"pi {tier}={slug!r} is not <publisher>/<model> form"
            )
        assert _tier_model(pi["standard"]) == "qwen/qwen3-coder"


# ---------------------------------------------------------------------------
# `local` provider tier (OpenSpec change add-local-model-provider-tier)
#
# Spec: openspec/changes/add-local-model-provider-tier/specs/agent-archetypes/
#       spec.md — "Local Roster Hardware Matching", "Local Provider Archetype
#       Trust Boundary", and the MODIFIED "Archetype Definition Schema".
# Contract: contracts/local-roster-entry.schema.json
# Design: D3 (trust boundary in the resolver), D4 (hardware matching is
#         validated roster metadata), D6 (byte-identical regression), D7.
# ---------------------------------------------------------------------------

_LOCAL_ARCHETYPES_YAML = """\
schema_version: 3

local_host_class:
  name: gb10
  active_params_ceiling_b: 12
  dense_params_limit_b: 30

model_aliases:
  claude_code:
    frontier: fable
    premium: opus
    standard: sonnet
    economy: haiku
  local:
    standard:
      model: big-moe
      total_params_b: 117
      active_params_b: 5.1
      reviewed: "2026-08-16"
    economy:
      model: small-moe
      total_params_b: 30.5
      active_params_b: 3.3
      reviewed: "2026-08-16"

archetypes:
  runner:
    write_capable: false
    model: economy
    system_prompt: Run it.
  analyst:
    write_capable: false
    model: frontier
    system_prompt: Analyze it.
  documenter:
    write_capable: true
    model: standard
    system_prompt: Document it.
  validator:
    write_capable: true
    model: premium
    system_prompt: Validate it.
  architect:
    write_capable: true
    model: frontier
    system_prompt: Design it.
  reviewer:
    write_capable: true
    model: premium
    system_prompt: Review it.
  gatekeeper:
    write_capable: false
    model: premium
    system_prompt: Judge it.
  implementer:
    write_capable: true
    model: standard
    system_prompt: Implement it.

phase_mapping:
  INIT:        {archetype: runner}
  SUBMIT_PR:   {archetype: analyst}
  VALIDATE:    {archetype: validator}
  VAL_FIX:     {archetype: documenter}
  PLAN:        {archetype: architect}
  PLAN_REVIEW: {archetype: reviewer}
  GATEKEEPER:  {archetype: gatekeeper}
  IMPLEMENT:   {archetype: implementer}
"""

_REAL_ARCHETYPES_YAML = Path(__file__).resolve().parent.parent / "archetypes.yaml"


@pytest.fixture()
def _clean_archetypes() -> Any:
    from src.agents_config import reset_archetypes_config

    reset_archetypes_config()
    yield
    reset_archetypes_config()


def _write_local_yaml(
    tmp_path: Path,
    mutate: Any = None,
    *,
    name: str = "archetypes.yaml",
) -> Path:
    """Write the local-roster test config, optionally mutating the raw dict."""
    import yaml as _yaml

    raw = _yaml.safe_load(_LOCAL_ARCHETYPES_YAML)
    if mutate is not None:
        mutate(raw)
    path = tmp_path / name
    path.write_text(_yaml.safe_dump(raw, sort_keys=False))
    return path


# ---------------------------------------------------------------------------
# 1.1 — roster loading + hardware-matching validation (D4)
# ---------------------------------------------------------------------------


class TestLocalRosterValidation:
    """Startup validation of the `local` roster's hardware-matching rules."""

    def test_extended_entry_form_accepted(
        self, tmp_path: Path, _clean_archetypes: None,
    ) -> None:
        """agent-archetypes.4: MoE entries under the ceiling load cleanly."""
        from src.agents_config import (
            LOCAL_PROVIDER,
            get_provider_model_map,
            load_archetypes_config,
        )

        load_archetypes_config(_write_local_yaml(tmp_path))
        roster = get_provider_model_map()["providers"][LOCAL_PROVIDER]

        # The extended form loads, and the *served* map carries the contract's
        # tierEntry shape (see test_served_local_roster_is_stripped_to_tier_entries).
        assert _tier_model(roster["economy"]) == "small-moe"
        assert _tier_model(roster["standard"]) == "big-moe"

    def test_served_local_roster_is_stripped_to_tier_entries(
        self, tmp_path: Path, _clean_archetypes: None,
    ) -> None:
        """Hardware metadata is load-time validation input, not served map data.

        ``provider-model-map.schema.json`` admits only a bare model id or
        ``{model, thinking}`` per tier, so ``total_params_b`` /
        ``active_params_b`` / ``reviewed`` must not survive normalization.
        """
        from src.agents_config import (
            LOCAL_PROVIDER,
            get_provider_model_map,
            load_archetypes_config,
        )

        load_archetypes_config(_write_local_yaml(tmp_path))
        roster = get_provider_model_map()["providers"][LOCAL_PROVIDER]

        for tier, entry in roster.items():
            assert not isinstance(entry, dict) or set(entry) <= {"model", "thinking"}, (
                f"local {tier} entry leaks non-contract fields: {entry!r}"
            )

    def test_served_map_conforms_to_canonical_provider_model_map_schema(
        self, _clean_archetypes: None,
    ) -> None:
        """The runtime map is the contract's map (F-05).

        Validates against the canonical schema at its stable home — never a copy
        inside a change directory, which moves on archive.
        """
        import json as _json

        from jsonschema import Draft202012Validator

        from src.agents_config import get_provider_model_map, load_archetypes_config

        schema_path = (
            Path(__file__).resolve().parents[2]
            / "openspec" / "schemas" / "provider-model-map.schema.json"
        )
        schema = _json.loads(schema_path.read_text())

        load_archetypes_config(_REAL_ARCHETYPES_YAML)

        Draft202012Validator(schema).validate(get_provider_model_map())

    def test_extended_entry_resolves_to_its_model_id(
        self, tmp_path: Path, _clean_archetypes: None,
    ) -> None:
        """agent-archetypes.1: the extended form still dispatches a model id."""
        from src.agents_config import load_archetypes_config, resolve_archetype_for_phase

        load_archetypes_config(_write_local_yaml(tmp_path))
        resolved = resolve_archetype_for_phase("INIT", {}, provider="local")

        assert resolved.archetype == "runner"
        assert resolved.model == "small-moe"
        assert resolved.thinking is None

    def test_active_params_over_host_ceiling_rejected(
        self, tmp_path: Path, _clean_archetypes: None,
    ) -> None:
        """A MoE whose active params exceed the host-class ceiling is refused."""
        from src.agents_config import LocalRosterConfigError, load_archetypes_config

        def _mutate(raw: dict[str, Any]) -> None:
            raw["model_aliases"]["local"]["standard"]["active_params_b"] = 24.0

        with pytest.raises(LocalRosterConfigError) as exc_info:
            load_archetypes_config(_write_local_yaml(tmp_path, _mutate))

        err = exc_info.value
        assert isinstance(err, ValueError)
        assert err.tier == "standard"
        assert "active" in err.rule
        message = str(err)
        assert "24" in message
        assert "12" in message  # the configured ceiling

    def test_dense_large_model_rejected(
        self, tmp_path: Path, _clean_archetypes: None,
    ) -> None:
        """agent-archetypes.5: dense >= 30B is refused even if it fits in RAM."""
        from src.agents_config import LocalRosterConfigError, load_archetypes_config

        def _mutate(raw: dict[str, Any]) -> None:
            raw["model_aliases"]["local"]["standard"] = {
                "model": "dense-32b",
                "total_params_b": 32,
                "active_params_b": 32,
                "reviewed": "2026-08-16",
            }

        with pytest.raises(LocalRosterConfigError) as exc_info:
            load_archetypes_config(_write_local_yaml(tmp_path, _mutate))

        err = exc_info.value
        assert err.tier == "standard"
        assert "dense" in err.rule
        assert "32" in str(err)

    def test_missing_review_date_rejected(
        self, tmp_path: Path, _clean_archetypes: None,
    ) -> None:
        """Roster entries carry an operator-signed review date (D4)."""
        from src.agents_config import LocalRosterConfigError, load_archetypes_config

        def _mutate(raw: dict[str, Any]) -> None:
            del raw["model_aliases"]["local"]["economy"]["reviewed"]

        with pytest.raises(LocalRosterConfigError) as exc_info:
            load_archetypes_config(_write_local_yaml(tmp_path, _mutate))

        err = exc_info.value
        assert err.tier == "economy"
        assert "reviewed" in str(err)

    def test_malformed_review_date_rejected(
        self, tmp_path: Path, _clean_archetypes: None,
    ) -> None:
        from src.agents_config import LocalRosterConfigError, load_archetypes_config

        def _mutate(raw: dict[str, Any]) -> None:
            raw["model_aliases"]["local"]["economy"]["reviewed"] = "last tuesday"

        with pytest.raises(LocalRosterConfigError):
            load_archetypes_config(_write_local_yaml(tmp_path, _mutate))

    @pytest.mark.parametrize(
        "reviewed",
        [
            "2026-13-45",  # impossible month AND day
            "2026-02-30",  # right shape, no such calendar date
            "20260816",    # ISO basic form is not the signed YYYY-MM-DD shape
        ],
    )
    def test_impossible_review_date_rejected(
        self, tmp_path: Path, reviewed: str, _clean_archetypes: None,
    ) -> None:
        """A date-shaped string is not enough — it must be a real date (F-16)."""
        from src.agents_config import LocalRosterConfigError, load_archetypes_config

        def _mutate(raw: dict[str, Any]) -> None:
            raw["model_aliases"]["local"]["economy"]["reviewed"] = reviewed

        with pytest.raises(LocalRosterConfigError) as exc_info:
            load_archetypes_config(_write_local_yaml(tmp_path, _mutate))

        assert exc_info.value.rule == "operator-review-date"
        assert exc_info.value.tier == "economy"

    def test_missing_parameter_metadata_rejected(
        self, tmp_path: Path, _clean_archetypes: None,
    ) -> None:
        """The extended entry form is mandatory for `local` (contract required)."""
        from src.agents_config import LocalRosterConfigError, load_archetypes_config

        def _mutate(raw: dict[str, Any]) -> None:
            del raw["model_aliases"]["local"]["economy"]["active_params_b"]

        with pytest.raises(LocalRosterConfigError) as exc_info:
            load_archetypes_config(_write_local_yaml(tmp_path, _mutate))
        assert "active_params_b" in str(exc_info.value)

    def test_active_params_over_total_rejected(
        self, tmp_path: Path, _clean_archetypes: None,
    ) -> None:
        from src.agents_config import LocalRosterConfigError, load_archetypes_config

        def _mutate(raw: dict[str, Any]) -> None:
            raw["model_aliases"]["local"]["economy"]["total_params_b"] = 2.0

        with pytest.raises(LocalRosterConfigError):
            load_archetypes_config(_write_local_yaml(tmp_path, _mutate))

    def test_no_local_roster_means_no_local_validation(
        self, tmp_path: Path, _clean_archetypes: None,
    ) -> None:
        """Nothing requires the local provider to be configured (Rule 4)."""
        from src.agents_config import load_archetypes_config

        def _mutate(raw: dict[str, Any]) -> None:
            del raw["model_aliases"]["local"]
            del raw["local_host_class"]

        archetypes = load_archetypes_config(_write_local_yaml(tmp_path, _mutate))
        assert "runner" in archetypes

    def test_real_archetypes_yaml_local_roster_is_valid(
        self, _clean_archetypes: None,
    ) -> None:
        """The shipped roster obeys its own host-class ceiling (D7)."""
        import yaml as _yaml

        from src.agents_config import (
            LOCAL_PROVIDER,
            LOCAL_REQUIRED_TIERS,
            load_archetypes_config,
        )

        # Loading is itself the assertion: validation raises on violation.
        load_archetypes_config(_REAL_ARCHETYPES_YAML)

        raw = _yaml.safe_load(_REAL_ARCHETYPES_YAML.read_text())
        host_class = raw["local_host_class"]
        roster = raw["model_aliases"][LOCAL_PROVIDER]

        assert set(LOCAL_REQUIRED_TIERS) <= set(roster)
        for tier, entry in roster.items():
            assert entry["active_params_b"] <= host_class["active_params_ceiling_b"], tier
            assert entry["active_params_b"] < entry["total_params_b"], tier
            assert isinstance(entry["reviewed"], str), tier

    def test_default_map_local_tiers_match_the_yaml_roster(self) -> None:
        """1.4: DEFAULT_PROVIDER_MODEL_MAP is the tier->model-id view of the roster."""
        import yaml as _yaml

        from src.agents_config import DEFAULT_PROVIDER_MODEL_MAP, LOCAL_PROVIDER

        raw = _yaml.safe_load(_REAL_ARCHETYPES_YAML.read_text())
        yaml_roster = raw["model_aliases"][LOCAL_PROVIDER]
        default_roster = DEFAULT_PROVIDER_MODEL_MAP["providers"][LOCAL_PROVIDER]

        assert set(default_roster) == set(yaml_roster)
        for tier, entry in yaml_roster.items():
            assert _tier_model(default_roster[tier]) == entry["model"]


class TestLocalTierDegradation:
    """agent-archetypes.2: omitted local tiers degrade to the best defined tier."""

    def test_frontier_request_degrades_with_recorded_reason(
        self, tmp_path: Path, _clean_archetypes: None,
    ) -> None:
        from src.agents_config import load_archetypes_config, resolve_archetype_for_phase

        load_archetypes_config(_write_local_yaml(tmp_path))
        # SUBMIT_PR -> analyst, whose tier is `frontier` (absent from the roster).
        resolved = resolve_archetype_for_phase("SUBMIT_PR", {}, provider="local")

        assert resolved.model == "big-moe"  # best defined tier == standard
        assert any(
            "frontier" in reason and "standard" in reason for reason in resolved.reasons
        ), f"degradation not recorded in reasons: {resolved.reasons}"

    def test_premium_request_degrades_with_recorded_reason(
        self, tmp_path: Path, _clean_archetypes: None,
    ) -> None:
        from src.agents_config import load_archetypes_config, resolve_archetype_for_phase

        load_archetypes_config(_write_local_yaml(tmp_path))
        # VALIDATE -> validator, whose tier is `premium` (absent from the roster).
        resolved = resolve_archetype_for_phase("VALIDATE", {}, provider="local")

        assert resolved.model == "big-moe"
        assert any(
            "premium" in reason and "standard" in reason for reason in resolved.reasons
        ), f"degradation not recorded in reasons: {resolved.reasons}"

    def test_local_frontier_degrades_to_defined_premium_with_reason(
        self, tmp_path: Path, _clean_archetypes: None,
    ) -> None:
        """F-13: the optional-tier (frontier->premium) path also records a reason.

        A local roster that DOES define premium but not frontier used to take
        the pre-existing optional-tier fallback and return silently, so the
        degradation never reached the caller's reasons.
        """
        from src.agents_config import load_archetypes_config, resolve_archetype_for_phase

        def _mutate(raw: dict[str, Any]) -> None:
            raw["model_aliases"]["local"]["premium"] = {
                "model": "mid-moe",
                "total_params_b": 80,
                "active_params_b": 4.5,
                "reviewed": "2026-08-16",
            }

        load_archetypes_config(_write_local_yaml(tmp_path, _mutate))
        # SUBMIT_PR -> analyst, whose tier is `frontier` (still absent).
        resolved = resolve_archetype_for_phase("SUBMIT_PR", {}, provider="local")

        assert resolved.model == "mid-moe"
        assert any(
            "frontier" in reason and "premium" in reason for reason in resolved.reasons
        ), f"degradation not recorded in reasons: {resolved.reasons}"

    def test_cloud_provider_frontier_fallback_is_silent(
        self, tmp_path: Path, _clean_archetypes: None,
    ) -> None:
        """The pre-existing frontier->premium fallback records no new reason."""
        from src.agents_config import load_archetypes_config, resolve_archetype_for_phase

        def _mutate(raw: dict[str, Any]) -> None:
            del raw["model_aliases"]["claude_code"]["frontier"]

        load_archetypes_config(_write_local_yaml(tmp_path, _mutate))
        resolved = resolve_archetype_for_phase("PLAN", {}, provider="claude_code")

        assert resolved.model == "opus"
        assert not any("degrad" in reason.lower() for reason in resolved.reasons)

    def test_best_defined_tier_degradation_is_local_only(self) -> None:
        """Rule 4: a cloud provider missing a base tier still fails loudly.

        Best-defined-tier degradation exists for the `local` roster; extending
        it to every provider would silently downgrade a misconfigured cloud
        roster instead of raising.
        """
        from src.agents_config import (
            ProviderModelMappingError,
            resolve_provider_model,
        )

        partial_map = {
            "schema_version": 2,
            "tiers": list(ALL_TIERS),
            "providers": {
                "codex": {"standard": "s", "economy": "e"},
                "local": {"standard": "s", "economy": "e"},
            },
        }
        with pytest.raises(ProviderModelMappingError):
            resolve_provider_model("premium", provider="codex", model_map=partial_map)
        assert (
            resolve_provider_model("premium", provider="local", model_map=partial_map)
            == "s"
        )


# ---------------------------------------------------------------------------
# 1.2 — byte-identical regression guard (D6, agent-archetypes.3)
# ---------------------------------------------------------------------------


def _snapshot_resolutions(
    config_path: Path, providers: list[str],
) -> dict[tuple[str, str, str], Any]:
    """Resolve every (archetype x provider) and (phase x provider) pair.

    Archetypes are snapshotted directly (some are not reachable through
    ``phase_mapping``); phases are snapshotted too so the full resolver path —
    boundary checks, escalation, reasons — is compared, not just the map.
    """
    from src.agents_config import (
        _resolve_model_spec,
        get_phase_mapping,
        load_archetypes_config,
        reset_archetypes_config,
        resolve_archetype_for_phase,
    )

    reset_archetypes_config()
    archetypes = load_archetypes_config(config_path)
    snapshot: dict[tuple[str, str, str], Any] = {}
    for name in sorted(archetypes):
        for provider in providers:
            spec, reasons = _resolve_model_spec(
                archetypes[name], {}, provider=provider,
            )
            snapshot[("archetype", name, provider)] = (spec, reasons)
    for phase in sorted(get_phase_mapping()):
        for provider in providers:
            snapshot[("phase", phase, provider)] = resolve_archetype_for_phase(
                phase, {}, provider=provider,
            )
    reset_archetypes_config()
    return snapshot


class TestExistingProvidersAreByteIdentical:
    """agent-archetypes.3: the `local` roster changes nothing for other providers."""

    def test_resolution_identical_with_and_without_local_roster(
        self, tmp_path: Path, _clean_archetypes: None,
    ) -> None:
        import yaml as _yaml

        from src.agents_config import LOCAL_PROVIDER

        raw = _yaml.safe_load(_REAL_ARCHETYPES_YAML.read_text())
        assert LOCAL_PROVIDER in raw["model_aliases"], (
            "guard: the real config must carry the local roster for this test to mean anything"
        )

        existing_providers = sorted(
            p for p in raw["model_aliases"] if p != LOCAL_PROVIDER
        )
        assert set(existing_providers) == set(CLOUD_ROSTER_PROVIDER_KEYS)

        # "Before": the same config with the local roster + host class removed.
        del raw["model_aliases"][LOCAL_PROVIDER]
        raw.pop("local_host_class", None)
        before_path = tmp_path / "archetypes-before.yaml"
        before_path.write_text(_yaml.safe_dump(raw, sort_keys=False))

        before = _snapshot_resolutions(before_path, existing_providers)
        after = _snapshot_resolutions(_REAL_ARCHETYPES_YAML, existing_providers)

        # Every archetype x existing-provider pair must be in the snapshot.
        covered = {key[1] for key in before if key[0] == "archetype"}
        assert covered == set(raw["archetypes"])
        assert len(before) == (
            len(raw["archetypes"]) + len(raw["phase_mapping"])
        ) * len(existing_providers)

        assert set(before) == set(after)
        for key in sorted(before):
            assert before[key] == after[key], f"resolution changed for {key}"


# ---------------------------------------------------------------------------
# 2.1 — local provider archetype trust boundary (D3)
# ---------------------------------------------------------------------------


class TestLocalProviderTrustBoundary:
    """agent-archetypes.6 / .7 — only cheap-to-discard archetypes go local."""

    @pytest.mark.parametrize(
        ("phase", "archetype"),
        [
            ("INIT", "runner"),
            ("SUBMIT_PR", "analyst"),
            ("VAL_FIX", "documenter"),
            ("VALIDATE", "validator"),
        ],
    )
    def test_permitted_archetype_resolves_locally(
        self, phase: str, archetype: str, tmp_path: Path, _clean_archetypes: None,
    ) -> None:
        from src.agents_config import (
            LOCAL_TRUSTED_ARCHETYPES,
            load_archetypes_config,
            resolve_archetype_for_phase,
        )

        assert archetype in LOCAL_TRUSTED_ARCHETYPES
        load_archetypes_config(_write_local_yaml(tmp_path))
        resolved = resolve_archetype_for_phase(phase, {}, provider="local")

        assert resolved.archetype == archetype
        assert resolved.provider == "local"
        assert any("trust boundary" in r.lower() for r in resolved.reasons), (
            f"boundary check not noted in reasons: {resolved.reasons}"
        )

    @pytest.mark.parametrize(
        ("phase", "archetype"),
        [
            ("PLAN", "architect"),
            ("PLAN_REVIEW", "reviewer"),
            ("GATEKEEPER", "gatekeeper"),
            # `implementer` is not on the permitted list either: the requirement
            # is an allowlist ("permit ... only for runner, analyst, documenter,
            # validator"), not merely a denylist of the three named archetypes.
            ("IMPLEMENT", "implementer"),
        ],
    )
    def test_boundary_archetype_refused(
        self, phase: str, archetype: str, tmp_path: Path, _clean_archetypes: None,
    ) -> None:
        from src.agents_config import (
            LOCAL_TRUSTED_ARCHETYPES,
            LocalProviderTrustBoundaryError,
            load_archetypes_config,
            resolve_archetype_for_phase,
        )

        load_archetypes_config(_write_local_yaml(tmp_path))
        with pytest.raises(LocalProviderTrustBoundaryError) as exc_info:
            resolve_archetype_for_phase(phase, {}, provider="local")

        err = exc_info.value
        assert isinstance(err, ValueError)
        assert err.archetype == archetype
        assert err.provider == "local"
        assert set(err.permitted) == set(LOCAL_TRUSTED_ARCHETYPES)

        message = str(err)
        assert "trust boundary" in message.lower()
        assert archetype in message
        for permitted in LOCAL_TRUSTED_ARCHETYPES:
            assert permitted in message, f"permitted list incomplete in {message!r}"

    @pytest.mark.parametrize(
        "phase", ["PLAN", "PLAN_REVIEW", "GATEKEEPER", "IMPLEMENT"],
    )
    def test_same_phases_resolve_for_cloud_providers(
        self, phase: str, tmp_path: Path, _clean_archetypes: None,
    ) -> None:
        """The boundary is local-only — cloud providers are untouched."""
        from src.agents_config import load_archetypes_config, resolve_archetype_for_phase

        load_archetypes_config(_write_local_yaml(tmp_path))
        resolved = resolve_archetype_for_phase(phase, {}, provider="claude_code")
        assert resolved.model
        assert not any("trust boundary" in r.lower() for r in resolved.reasons)

    def test_boundary_holds_without_a_provider(
        self, tmp_path: Path, _clean_archetypes: None,
    ) -> None:
        """No provider selected → no local boundary, no boundary reason."""
        from src.agents_config import load_archetypes_config, resolve_archetype_for_phase

        load_archetypes_config(_write_local_yaml(tmp_path))
        resolved = resolve_archetype_for_phase("PLAN", {})
        assert resolved.archetype == "architect"
        assert not any("trust boundary" in r.lower() for r in resolved.reasons)

    def test_real_config_boundary_phases_refuse_local(
        self, _clean_archetypes: None,
    ) -> None:
        """The shipped phase_mapping refuses `local` for its judgment phases."""
        from src.agents_config import (
            LOCAL_TRUSTED_ARCHETYPES,
            LocalProviderTrustBoundaryError,
            get_phase_mapping,
            load_archetypes_config,
            resolve_archetype_for_phase,
        )

        load_archetypes_config(_REAL_ARCHETYPES_YAML)
        refused: set[str] = set()
        for phase, entry in get_phase_mapping().items():
            if entry.archetype in LOCAL_TRUSTED_ARCHETYPES:
                continue
            with pytest.raises(LocalProviderTrustBoundaryError):
                resolve_archetype_for_phase(phase, {}, provider="local")
            refused.add(entry.archetype)

        assert {"architect", "reviewer", "gatekeeper"} <= refused
