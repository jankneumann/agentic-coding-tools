"""Tests for bao-seed.py — OpenBao bootstrap seeding script."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts directory to path for import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bao_seed import seed_approles, seed_db_engine, seed_secrets


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# ---------------------------------------------------------------------------
# seed_secrets
# ---------------------------------------------------------------------------


class TestSeedSecrets:
    def test_writes_secrets_to_kv(self, tmp_path: Path) -> None:
        secrets = tmp_path / ".secrets.yaml"
        _write(secrets, "DB_PASSWORD: mypass\nAPI_KEY: key123\n")
        client = MagicMock()

        seed_secrets(client, secrets, "secret", "coordinator")

        client.secrets.kv.v2.create_or_update_secret.assert_called_once_with(
            path="coordinator",
            secret={"DB_PASSWORD": "mypass", "API_KEY": "key123"},
            mount_point="secret",
        )

    def test_filters_non_string_values(self, tmp_path: Path) -> None:
        secrets = tmp_path / ".secrets.yaml"
        _write(secrets, "GOOD: value\nBAD: 42\n")
        client = MagicMock()

        seed_secrets(client, secrets, "secret", "coordinator")

        call_args = client.secrets.kv.v2.create_or_update_secret.call_args
        assert call_args.kwargs["secret"] == {"GOOD": "value"}

    def test_missing_file_exits(self, tmp_path: Path) -> None:
        client = MagicMock()
        with pytest.raises(SystemExit):
            seed_secrets(client, tmp_path / "missing.yaml", "secret", "coordinator")

    def test_invalid_yaml_exits(self, tmp_path: Path) -> None:
        secrets = tmp_path / ".secrets.yaml"
        _write(secrets, "just a string\n")
        client = MagicMock()
        with pytest.raises(SystemExit):
            seed_secrets(client, secrets, "secret", "coordinator")

    def test_dry_run_no_writes(self, tmp_path: Path) -> None:
        secrets = tmp_path / ".secrets.yaml"
        _write(secrets, "DB_PASSWORD: mypass\n")
        client = MagicMock()

        seed_secrets(client, secrets, "secret", "coordinator", dry_run=True)

        client.secrets.kv.v2.create_or_update_secret.assert_not_called()

    def test_idempotent_rerun(self, tmp_path: Path) -> None:
        """Running twice with same data calls create_or_update (not create)."""
        secrets = tmp_path / ".secrets.yaml"
        _write(secrets, "KEY: value\n")
        client = MagicMock()

        seed_secrets(client, secrets, "secret", "coordinator")
        seed_secrets(client, secrets, "secret", "coordinator")

        assert client.secrets.kv.v2.create_or_update_secret.call_count == 2


# ---------------------------------------------------------------------------
# seed_approles
# ---------------------------------------------------------------------------


class TestSeedApproles:
    AGENTS_YAML = """\
agents:
  claude-web:
    type: claude_code
    profile: p
    trust_level: 2
    transport: http
    api_key: "${KEY}"
    openbao_role_id: claude-web
    capabilities: [lock]
    description: Web agent
  local-agent:
    type: claude_code
    profile: p
    trust_level: 3
    transport: mcp
    capabilities: [lock]
    description: Local agent
"""

    def test_creates_approles_for_http_agents(self, tmp_path: Path) -> None:
        agents = tmp_path / "agents.yaml"
        _write(agents, self.AGENTS_YAML)
        client = MagicMock()
        client.sys.list_auth_methods.return_value = {"approle/": {}}

        seed_approles(client, agents, "secret", "coordinator", 3600)

        client.sys.create_or_update_policy.assert_called_once()
        client.auth.approle.create_or_update_approle.assert_called_once_with(
            role_name="claude-web",
            token_policies=["coordinator-read"],
            token_ttl="3600s",
            token_max_ttl="86400s",
        )

    def test_enables_approle_auth_if_missing(self, tmp_path: Path) -> None:
        agents = tmp_path / "agents.yaml"
        _write(agents, self.AGENTS_YAML)
        client = MagicMock()
        client.sys.list_auth_methods.return_value = {}

        seed_approles(client, agents, "secret", "coordinator", 3600)

        client.sys.enable_auth_method.assert_called_once_with("approle")

    def test_skips_mcp_agents(self, tmp_path: Path) -> None:
        agents_yaml = """\
agents:
  local-only:
    type: claude_code
    profile: p
    trust_level: 3
    transport: mcp
    capabilities: [lock]
    description: MCP only
"""
        agents = tmp_path / "agents.yaml"
        _write(agents, agents_yaml)
        client = MagicMock()

        seed_approles(client, agents, "secret", "coordinator", 3600)

        client.auth.approle.create_or_update_approle.assert_not_called()

    def test_missing_agents_file_warns(self, tmp_path: Path) -> None:
        client = MagicMock()
        seed_approles(client, tmp_path / "missing.yaml", "secret", "coordinator", 3600)
        client.auth.approle.create_or_update_approle.assert_not_called()

    def test_dry_run_no_writes(self, tmp_path: Path) -> None:
        agents = tmp_path / "agents.yaml"
        _write(agents, self.AGENTS_YAML)
        client = MagicMock()

        seed_approles(client, agents, "secret", "coordinator", 3600, dry_run=True)

        client.sys.create_or_update_policy.assert_not_called()
        client.auth.approle.create_or_update_approle.assert_not_called()


# ---------------------------------------------------------------------------
# seed_db_engine
# ---------------------------------------------------------------------------


class TestSeedDbEngine:
    def test_enables_and_configures(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POSTGRES_DSN", "postgresql://user:pass@host:5432/db")
        client = MagicMock()
        client.sys.list_mounted_secrets_engines.return_value = {}

        seed_db_engine(client)

        client.sys.enable_secrets_engine.assert_called_once_with("database")
        client.secrets.database.configure.assert_called_once()
        # Verify the connection URL is built correctly from the DSN
        configure_call = client.secrets.database.configure.call_args
        assert configure_call.kwargs["connection_url"] == "postgresql://{{username}}:{{password}}@host:5432/db"
        assert configure_call.kwargs["username"] == "user"
        assert configure_call.kwargs["password"] == "pass"
        client.secrets.database.create_role.assert_called_once()
        role_call = client.secrets.database.create_role.call_args
        assert role_call.kwargs["name"] == "coordinator-agent"
        assert role_call.kwargs["default_ttl"] == "1h"
        assert role_call.kwargs["max_ttl"] == "24h"

    def test_skips_enable_if_already_mounted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POSTGRES_DSN", "postgresql://user:pass@host:5432/db")
        client = MagicMock()
        client.sys.list_mounted_secrets_engines.return_value = {"database/": {}}

        seed_db_engine(client)

        client.sys.enable_secrets_engine.assert_not_called()

    def test_dry_run_no_writes(self) -> None:
        client = MagicMock()

        seed_db_engine(client, dry_run=True)

        client.sys.enable_secrets_engine.assert_not_called()
        client.secrets.database.configure.assert_not_called()
        client.secrets.database.create_role.assert_not_called()
