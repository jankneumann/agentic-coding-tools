"""Tests for profile_loader — YAML profiles with inheritance and interpolation."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.profile_loader import (
    _load_secrets,
    _load_secrets_file,
    _load_secrets_openbao,
    apply_profile,
    deep_merge,
    interpolate,
    load_profile,
    resolve_dynamic_dsn,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# ---------------------------------------------------------------------------
# deep_merge
# ---------------------------------------------------------------------------


class TestDeepMerge:
    def test_scalar_override(self) -> None:
        assert deep_merge({"a": 1}, {"a": 2}) == {"a": 2}

    def test_nested_merge(self) -> None:
        base = {"x": {"a": 1, "b": 2}}
        override = {"x": {"b": 3, "c": 4}}
        assert deep_merge(base, override) == {"x": {"a": 1, "b": 3, "c": 4}}

    def test_list_replace(self) -> None:
        assert deep_merge({"a": [1, 2]}, {"a": [3]}) == {"a": [3]}

    def test_new_key_added(self) -> None:
        assert deep_merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}


# ---------------------------------------------------------------------------
# interpolate
# ---------------------------------------------------------------------------


class TestInterpolate:
    def test_simple_var(self) -> None:
        assert interpolate("${FOO}", {"FOO": "bar"}) == "bar"

    def test_default_used(self) -> None:
        assert interpolate("${MISSING:-fallback}", {}) == "fallback"

    def test_empty_default(self) -> None:
        assert interpolate("${MISSING:-}", {}) == ""

    def test_env_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FROM_ENV", "envval")
        assert interpolate("${FROM_ENV}", {}) == "envval"

    def test_secrets_wins_over_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KEY", "env")
        assert interpolate("${KEY}", {"KEY": "secret"}) == "secret"

    def test_escape(self) -> None:
        assert interpolate("$${ESCAPED}", {}) == "${ESCAPED}"

    def test_unresolvable_left_as_is(self) -> None:
        assert interpolate("${NOPE}", {}) == "${NOPE}"

    def test_mixed(self) -> None:
        result = interpolate("host=${HOST:-localhost}:${PORT}", {"PORT": "5432"})
        assert result == "host=localhost:5432"

    def test_empty_string_secret_honoured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An empty-string secret should NOT fall through to env."""
        monkeypatch.setenv("KEY", "env_value")
        assert interpolate("${KEY}", {"KEY": ""}) == ""


# ---------------------------------------------------------------------------
# load_profile
# ---------------------------------------------------------------------------


class TestLoadProfile:
    def test_local_profile_inherits_base(self, tmp_path: Path) -> None:
        profiles = tmp_path / "profiles"
        _write(
            profiles / "base.yaml",
            "settings:\n  db_backend: postgres\n  lock_ttl: 120\n",
        )
        _write(
            profiles / "local.yaml",
            "extends: base\nsettings:\n  lock_ttl: 60\n",
        )
        result = load_profile("local", profiles_dir=profiles, secrets_path=tmp_path / "none")
        assert result["settings"]["db_backend"] == "postgres"
        assert result["settings"]["lock_ttl"] == 60

    def test_circular_inheritance_detected(self, tmp_path: Path) -> None:
        profiles = tmp_path / "profiles"
        _write(profiles / "a.yaml", "extends: b\n")
        _write(profiles / "b.yaml", "extends: a\n")
        with pytest.raises(ValueError, match="Circular"):
            load_profile("a", profiles_dir=profiles, secrets_path=tmp_path / "none")

    def test_secret_interpolation(self, tmp_path: Path) -> None:
        profiles = tmp_path / "profiles"
        _write(profiles / "test.yaml", 'settings:\n  dsn: "pg://${DB_PASS}@host"\n')
        secrets = tmp_path / ".secrets.yaml"
        _write(secrets, "DB_PASS: mypass\n")
        result = load_profile("test", profiles_dir=profiles, secrets_path=secrets)
        assert result["settings"]["dsn"] == "pg://mypass@host"

    def test_profile_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_profile("ghost", profiles_dir=tmp_path, secrets_path=tmp_path / "none")


# ---------------------------------------------------------------------------
# apply_profile
# ---------------------------------------------------------------------------


class TestApplyProfile:
    def test_no_profiles_dir_returns_none(self, tmp_path: Path) -> None:
        result = apply_profile(profiles_dir=tmp_path / "nope")
        assert result is None

    def test_env_injection(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        profiles = tmp_path / "profiles"
        _write(
            profiles / "base.yaml",
            "settings:\n  db_backend: postgres\n  agent_id: test-agent\n",
        )
        # Ensure env vars are clean
        monkeypatch.delenv("DB_BACKEND", raising=False)
        monkeypatch.delenv("AGENT_ID", raising=False)
        apply_profile("base", profiles_dir=profiles, secrets_path=tmp_path / "none")
        assert os.environ["DB_BACKEND"] == "postgres"
        assert os.environ["AGENT_ID"] == "test-agent"
        # Clean up injected values
        monkeypatch.delenv("DB_BACKEND", raising=False)
        monkeypatch.delenv("AGENT_ID", raising=False)

    def test_env_var_overrides_profile(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        profiles = tmp_path / "profiles"
        _write(profiles / "base.yaml", "settings:\n  db_backend: postgres\n")
        monkeypatch.setenv("DB_BACKEND", "supabase")
        apply_profile("base", profiles_dir=profiles, secrets_path=tmp_path / "none")
        assert os.environ["DB_BACKEND"] == "supabase"

    def test_docker_block_not_mapped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        profiles = tmp_path / "profiles"
        _write(profiles / "base.yaml", "docker:\n  enabled: true\n")
        monkeypatch.delenv("DOCKER_ENABLED", raising=False)
        apply_profile("base", profiles_dir=profiles, secrets_path=tmp_path / "none")
        assert "DOCKER_ENABLED" not in os.environ

    def test_transport_mapped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        profiles = tmp_path / "profiles"
        _write(profiles / "base.yaml", "transport: mcp\n")
        monkeypatch.delenv("COORDINATION_TRANSPORT", raising=False)
        apply_profile("base", profiles_dir=profiles, secrets_path=tmp_path / "none")
        assert os.environ["COORDINATION_TRANSPORT"] == "mcp"
        monkeypatch.delenv("COORDINATION_TRANSPORT", raising=False)

    def test_apply_via_coordinator_profile_env_var(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """COORDINATOR_PROFILE env var activates profile loading."""
        profiles = tmp_path / "profiles"
        _write(profiles / "base.yaml", "settings:\n  db_backend: postgres\n")
        monkeypatch.setenv("COORDINATOR_PROFILE", "base")
        monkeypatch.delenv("DB_BACKEND", raising=False)
        result = apply_profile(profiles_dir=profiles, secrets_path=tmp_path / "none")
        assert result is not None
        assert os.environ["DB_BACKEND"] == "postgres"
        monkeypatch.delenv("DB_BACKEND", raising=False)

    def test_coordinator_profile_env_but_no_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """COORDINATOR_PROFILE set but profiles/ dir missing returns None."""
        monkeypatch.setenv("COORDINATOR_PROFILE", "local")
        result = apply_profile(profiles_dir=tmp_path / "nonexistent")
        assert result is None

    def test_load_profile_defaults_to_local(self, tmp_path: Path) -> None:
        """load_profile with no name defaults to 'local'."""
        profiles = tmp_path / "profiles"
        _write(profiles / "local.yaml", "transport: mcp\n")
        result = load_profile(profiles_dir=profiles, secrets_path=tmp_path / "none")
        assert result["transport"] == "mcp"

    def test_malformed_secrets_file(self, tmp_path: Path) -> None:
        """Non-dict secrets file is silently ignored."""
        profiles = tmp_path / "profiles"
        _write(profiles / "test.yaml", 'settings:\n  dsn: "pg://${X}@h"\n')
        secrets = tmp_path / ".secrets.yaml"
        _write(secrets, "not a dict\n")
        result = load_profile("test", profiles_dir=profiles, secrets_path=secrets)
        # ${X} left unresolved since secrets are invalid
        assert result["settings"]["dsn"] == "pg://${X}@h"

    def test_empty_secrets_file(self, tmp_path: Path) -> None:
        """Empty secrets file is handled gracefully."""
        profiles = tmp_path / "profiles"
        _write(profiles / "test.yaml", 'settings:\n  val: "${MISSING:-ok}"\n')
        secrets = tmp_path / ".secrets.yaml"
        _write(secrets, "")
        result = load_profile("test", profiles_dir=profiles, secrets_path=secrets)
        assert result["settings"]["val"] == "ok"


# ---------------------------------------------------------------------------
# OpenBao secret loading
# ---------------------------------------------------------------------------


class TestLoadSecretsOpenbao:
    def _mock_openbao(self, kv_data: dict, **config_overrides: str) -> MagicMock:
        """Helper to create a mock OpenBaoConfig with KV v2 response."""
        mock_config = MagicMock()
        mock_config.addr = config_overrides.get("addr", "http://bao:8200")
        mock_config.mount_path = config_overrides.get("mount_path", "secret")
        mock_config.secret_path = config_overrides.get("secret_path", "coordinator")
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": kv_data}
        }
        mock_config.create_client.return_value = mock_client
        return mock_config

    @patch("src.config.OpenBaoConfig.from_env")
    def test_success(self, mock_from_env: MagicMock) -> None:
        """Successful secret load from OpenBao KV v2."""
        mock_config = self._mock_openbao({"DB_PASSWORD": "vault-pass", "API_KEY": "key-123"})
        mock_from_env.return_value = mock_config

        result = _load_secrets_openbao()
        assert result == {"DB_PASSWORD": "vault-pass", "API_KEY": "key-123"}
        mock_config.create_client.return_value.secrets.kv.v2.read_secret_version.assert_called_once_with(
            path="coordinator", mount_point="secret"
        )

    @patch("src.config.OpenBaoConfig.from_env")
    def test_non_string_values_filtered(self, mock_from_env: MagicMock) -> None:
        """Non-string values in OpenBao are skipped with a warning."""
        mock_from_env.return_value = self._mock_openbao(
            {"GOOD": "value", "BAD_INT": 42, "BAD_LIST": [1, 2]}
        )
        result = _load_secrets_openbao()
        assert result == {"GOOD": "value"}

    @patch("src.config.OpenBaoConfig.from_env")
    def test_auth_failure(self, mock_from_env: MagicMock) -> None:
        """Authentication failure raises RuntimeError via create_client."""
        mock_config = MagicMock()
        mock_config.create_client.side_effect = RuntimeError("auth failed")
        mock_from_env.return_value = mock_config

        with pytest.raises(RuntimeError, match="auth failed"):
            _load_secrets_openbao()

    @patch("src.config.OpenBaoConfig.from_env")
    def test_missing_credentials(self, mock_from_env: MagicMock) -> None:
        """Missing BAO_ROLE_ID raises ValueError."""
        mock_config = MagicMock()
        mock_config.create_client.side_effect = ValueError("BAO_ROLE_ID required")
        mock_from_env.return_value = mock_config

        with pytest.raises(ValueError, match="BAO_ROLE_ID"):
            _load_secrets_openbao()

    @patch("src.config.OpenBaoConfig.from_env")
    def test_unreachable(self, mock_from_env: MagicMock) -> None:
        """Unreachable OpenBao raises ConnectionError."""
        mock_config = MagicMock()
        mock_config.create_client.side_effect = ConnectionError("unreachable")
        mock_from_env.return_value = mock_config

        with pytest.raises(ConnectionError, match="unreachable"):
            _load_secrets_openbao()

    @patch("src.config.OpenBaoConfig.from_env")
    def test_read_failure(self, mock_from_env: MagicMock) -> None:
        """KV read failure wraps into RuntimeError."""
        mock_config = MagicMock()
        mock_config.addr = "http://bao:8200"
        mock_config.mount_path = "secret"
        mock_config.secret_path = "coordinator"
        mock_client = MagicMock()
        mock_client.secrets.kv.v2.read_secret_version.side_effect = Exception("403")
        mock_config.create_client.return_value = mock_client
        mock_from_env.return_value = mock_config

        with pytest.raises(RuntimeError, match="Failed to read secrets"):
            _load_secrets_openbao()


class TestLoadSecretsDispatch:
    def test_fallback_to_file_without_bao_addr(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without BAO_ADDR, _load_secrets uses .secrets.yaml file."""
        monkeypatch.delenv("BAO_ADDR", raising=False)
        secrets = tmp_path / ".secrets.yaml"
        _write(secrets, "MY_SECRET: file-value\n")
        result = _load_secrets(secrets)
        assert result == {"MY_SECRET": "file-value"}

    @patch("src.profile_loader._load_secrets_openbao")
    def test_uses_openbao_when_bao_addr_set(
        self,
        mock_openbao: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With BAO_ADDR set, _load_secrets dispatches to OpenBao backend."""
        monkeypatch.setenv("BAO_ADDR", "http://localhost:8200")
        mock_openbao.return_value = {"KEY": "from-openbao"}
        result = _load_secrets(tmp_path / ".secrets.yaml")
        assert result == {"KEY": "from-openbao"}
        mock_openbao.assert_called_once()

    def test_file_backend_no_file(self, tmp_path: Path) -> None:
        """_load_secrets_file returns empty dict when file doesn't exist."""
        result = _load_secrets_file(tmp_path / "nonexistent.yaml")
        assert result == {}


# ---------------------------------------------------------------------------
# Dynamic DSN resolution
# ---------------------------------------------------------------------------


class TestResolveDynamicDsn:
    @patch("src.config.OpenBaoConfig.from_env")
    def test_returns_none_when_disabled(self, mock_from_env: MagicMock) -> None:
        """No dynamic DSN when OpenBao is not enabled."""
        mock_config = MagicMock()
        mock_config.is_enabled.return_value = False
        mock_from_env.return_value = mock_config

        assert resolve_dynamic_dsn() is None

    @patch("src.config.OpenBaoConfig.from_env")
    def test_success(
        self, mock_from_env: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dynamic DSN generated from database secrets engine."""
        monkeypatch.setenv("POSTGRES_HOST", "dbhost")
        monkeypatch.setenv("POSTGRES_PORT", "5432")
        monkeypatch.setenv("POSTGRES_DB", "mydb")

        mock_config = MagicMock()
        mock_config.is_enabled.return_value = True
        mock_client = MagicMock()
        mock_client.secrets.database.generate_credentials.return_value = {
            "data": {"username": "v-agent-abc", "password": "dynamic-pass"},
            "lease_id": "database/creds/coordinator-agent/abc",
            "lease_duration": 3600,
        }
        mock_config.create_client.return_value = mock_client
        mock_from_env.return_value = mock_config

        result = resolve_dynamic_dsn("test-agent")
        assert result == "postgresql://v-agent-abc:dynamic-pass@dbhost:5432/mydb"

    @patch("src.config.OpenBaoConfig.from_env")
    def test_engine_not_configured(self, mock_from_env: MagicMock) -> None:
        """Returns None when database engine is not configured."""
        mock_config = MagicMock()
        mock_config.is_enabled.return_value = True
        mock_client = MagicMock()
        mock_client.secrets.database.generate_credentials.side_effect = Exception("no route")
        mock_config.create_client.return_value = mock_client
        mock_from_env.return_value = mock_config

        assert resolve_dynamic_dsn() is None

    @patch("src.config.OpenBaoConfig.from_env")
    def test_empty_credentials_fallback(self, mock_from_env: MagicMock) -> None:
        """Returns None when generated credentials are empty."""
        mock_config = MagicMock()
        mock_config.is_enabled.return_value = True
        mock_client = MagicMock()
        mock_client.secrets.database.generate_credentials.return_value = {
            "data": {"username": "", "password": ""},
        }
        mock_config.create_client.return_value = mock_client
        mock_from_env.return_value = mock_config

        assert resolve_dynamic_dsn() is None
