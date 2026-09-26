"""Scoped SDK credential lookup."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from api_key_resolver import ApiKeyResolver
from openbao_credentials import BaoCredentialError, ErrorCode


PRINCIPAL = "spiffe://coordinator.rotkohl.ai/agent/claude-remote"
SCOPES = {PRINCIPAL: ("anthropic",)}
ENV = {(PRINCIPAL, "anthropic"): "ANTHROPIC_API_KEY"}


def test_non_bao_uses_configured_environment_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BAO_ADDR", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "development-key")
    assert ApiKeyResolver(SCOPES, ENV).resolve(PRINCIPAL, "anthropic") == "development-key"


def test_non_bao_missing_key_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BAO_ADDR", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert ApiKeyResolver(SCOPES, ENV).resolve(PRINCIPAL, "anthropic") is None


def test_configured_bao_reads_authorized_vendor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BAO_ADDR", "http://localhost:8200")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ambient-key")
    client = MagicMock()
    client.read_vendor_key.return_value = "bao-key"
    with patch("openbao_credentials.OpenBaoClient", return_value=client) as client_type:
        with patch("openbao_credentials.PrincipalOpenBaoConfig.from_env"):
            assert ApiKeyResolver(SCOPES, ENV).resolve(PRINCIPAL, "anthropic") == "bao-key"
    client.ensure_session.assert_called_once_with(PRINCIPAL, "agent-claude-remote")
    client.read_vendor_key.assert_called_once_with("anthropic")
    client_type.assert_called_once()


def test_undeclared_vendor_is_rejected_before_bao_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BAO_ADDR", "http://localhost:8200")
    with patch("openbao_credentials.OpenBaoClient") as client_type:
        with pytest.raises(BaoCredentialError) as exc:
            ApiKeyResolver(SCOPES, ENV).resolve(PRINCIPAL, "openai")
    assert exc.value.code == ErrorCode.AUTHORIZATION_DENIED
    client_type.assert_not_called()


def test_bao_failure_cannot_fall_back_to_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BAO_ADDR", "http://localhost:8200")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ambient-key")
    with patch("openbao_credentials.OpenBaoClient", side_effect=BaoCredentialError(ErrorCode.BACKEND_UNAVAILABLE)):
        with patch("openbao_credentials.PrincipalOpenBaoConfig.from_env"):
            with pytest.raises(BaoCredentialError) as exc:
                ApiKeyResolver(SCOPES, ENV).resolve(PRINCIPAL, "anthropic")
    assert exc.value.code == ErrorCode.BACKEND_UNAVAILABLE


def test_bao_requires_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BAO_ADDR", "http://localhost:8200")
    with pytest.raises(BaoCredentialError):
        ApiKeyResolver(SCOPES, ENV).resolve(None, "anthropic")


def test_non_bao_keyless_local_endpoint_needs_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BAO_ADDR", raising=False)
    assert ApiKeyResolver({}, {}).resolve(None, "local") is None
