"""Tests for OpenBaoConfig — dataclass, from_env, is_enabled, create_client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.config import OpenBaoConfig


class TestOpenBaoConfigFromEnv:
    def test_all_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BAO_ADDR", raising=False)
        monkeypatch.delenv("BAO_ROLE_ID", raising=False)
        monkeypatch.delenv("BAO_SECRET_ID", raising=False)
        cfg = OpenBaoConfig.from_env()
        assert cfg.addr == ""
        assert cfg.role_id == ""
        assert cfg.secret_id == ""
        assert cfg.mount_path == "secret"
        assert cfg.secret_path == "coordinator"
        assert cfg.timeout == 5
        assert cfg.token_ttl == 3600

    def test_all_vars_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BAO_ADDR", "http://bao:8200")
        monkeypatch.setenv("BAO_ROLE_ID", "role-1")
        monkeypatch.setenv("BAO_SECRET_ID", "secret-1")
        monkeypatch.setenv("BAO_MOUNT_PATH", "kv")
        monkeypatch.setenv("BAO_SECRET_PATH", "myapp")
        monkeypatch.setenv("BAO_TIMEOUT", "10")
        monkeypatch.setenv("BAO_TOKEN_TTL", "7200")
        cfg = OpenBaoConfig.from_env()
        assert cfg.addr == "http://bao:8200"
        assert cfg.role_id == "role-1"
        assert cfg.secret_id == "secret-1"
        assert cfg.mount_path == "kv"
        assert cfg.secret_path == "myapp"
        assert cfg.timeout == 10
        assert cfg.token_ttl == 7200


class TestOpenBaoConfigIsEnabled:
    def test_enabled_when_addr_set(self) -> None:
        cfg = OpenBaoConfig(addr="http://localhost:8200")
        assert cfg.is_enabled() is True

    def test_disabled_when_addr_empty(self) -> None:
        cfg = OpenBaoConfig(addr="")
        assert cfg.is_enabled() is False

    def test_disabled_by_default(self) -> None:
        cfg = OpenBaoConfig()
        assert cfg.is_enabled() is False


class TestOpenBaoConfigCreateClient:
    def test_raises_when_not_configured(self) -> None:
        cfg = OpenBaoConfig()
        with pytest.raises(RuntimeError, match="not configured"):
            cfg.create_client()

    def test_raises_when_role_id_missing(self) -> None:
        cfg = OpenBaoConfig(addr="http://localhost:8200", secret_id="s1")
        with pytest.raises(ValueError, match="BAO_ROLE_ID"):
            cfg.create_client()

    def test_raises_when_secret_id_missing(self) -> None:
        cfg = OpenBaoConfig(addr="http://localhost:8200", role_id="r1")
        with pytest.raises(ValueError, match="BAO_SECRET_ID"):
            cfg.create_client()

    @patch("hvac.Client")
    def test_creates_authenticated_client(self, mock_client_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        mock_client_cls.return_value = mock_client

        cfg = OpenBaoConfig(
            addr="http://localhost:8200",
            role_id="r1",
            secret_id="s1",
            timeout=10,
        )
        client = cfg.create_client()

        mock_client_cls.assert_called_once_with(url="http://localhost:8200", timeout=10)
        mock_client.auth.approle.login.assert_called_once_with(
            role_id="r1", secret_id="s1"
        )
        assert client is mock_client

    @patch("hvac.Client")
    def test_connection_error_wrapped(self, mock_client_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.auth.approle.login.side_effect = Exception("Connection refused")
        mock_client_cls.return_value = mock_client

        cfg = OpenBaoConfig(addr="http://bad:8200", role_id="r1", secret_id="s1")
        with pytest.raises(ConnectionError, match="unreachable"):
            cfg.create_client()

    @patch("hvac.Client")
    def test_auth_error_wrapped(self, mock_client_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.auth.approle.login.side_effect = Exception("permission denied")
        mock_client_cls.return_value = mock_client

        cfg = OpenBaoConfig(addr="http://localhost:8200", role_id="bad", secret_id="s1")
        with pytest.raises(RuntimeError, match="authentication failed"):
            cfg.create_client()

    @patch("hvac.Client")
    def test_unauthenticated_after_login(self, mock_client_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = False
        mock_client_cls.return_value = mock_client

        cfg = OpenBaoConfig(addr="http://localhost:8200", role_id="r1", secret_id="s1")
        with pytest.raises(RuntimeError, match="unauthenticated"):
            cfg.create_client()
