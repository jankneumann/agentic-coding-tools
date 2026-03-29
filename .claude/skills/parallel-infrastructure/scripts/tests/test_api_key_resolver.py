"""Tests for api_key_resolver — secure API key resolution."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from api_key_resolver import ApiKeyResolver


class TestApiKeyResolver:
    def test_resolve_from_env_var(self) -> None:
        """Resolve from environment variable when OpenBao unavailable."""
        resolver = ApiKeyResolver()
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-123"}, clear=False):
            key = resolver.resolve(None, "ANTHROPIC_API_KEY")
        assert key == "sk-test-123"

    def test_resolve_none_when_nothing_available(self) -> None:
        """Return None when neither OpenBao nor env var is available."""
        resolver = ApiKeyResolver()
        with patch.dict(os.environ, {}, clear=True):
            key = resolver.resolve(None, "NONEXISTENT_KEY")
        assert key is None

    def test_resolve_caches_result(self) -> None:
        """Subsequent calls return cached value."""
        resolver = ApiKeyResolver()
        with patch.dict(os.environ, {"MY_KEY": "val1"}, clear=False):
            key1 = resolver.resolve(None, "MY_KEY")
        # Even after removing env var, cache returns old value
        with patch.dict(os.environ, {}, clear=True):
            key2 = resolver.resolve(None, "MY_KEY")
        assert key1 == "val1"
        assert key2 == "val1"

    def test_resolve_openbao_preferred(self) -> None:
        """OpenBao is preferred over env var when available."""
        resolver = ApiKeyResolver()
        mock_hvac = MagicMock()
        mock_client = MagicMock()
        mock_hvac.Client.return_value = mock_client
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"ANTHROPIC_API_KEY": "bao-secret-key"}},
        }

        with patch.dict(os.environ, {
            "BAO_ADDR": "http://localhost:8200",
            "BAO_SECRET_ID": "test-secret",
            "ANTHROPIC_API_KEY": "env-key",
        }, clear=False):
            with patch.dict("sys.modules", {"hvac": mock_hvac}):
                # Need a fresh resolver to avoid cache
                resolver2 = ApiKeyResolver()
                key = resolver2.resolve("claude-code-web", "ANTHROPIC_API_KEY")
        assert key == "bao-secret-key"

    def test_resolve_falls_back_to_env_when_openbao_fails(self) -> None:
        """Falls back to env var when OpenBao resolution raises."""
        resolver = ApiKeyResolver()
        mock_hvac = MagicMock()
        mock_hvac.Client.side_effect = Exception("Connection refused")

        with patch.dict(os.environ, {
            "BAO_ADDR": "http://localhost:8200",
            "BAO_SECRET_ID": "test-secret",
            "ANTHROPIC_API_KEY": "env-fallback",
        }, clear=False):
            with patch.dict("sys.modules", {"hvac": mock_hvac}):
                resolver2 = ApiKeyResolver()
                key = resolver2.resolve("claude-code-web", "ANTHROPIC_API_KEY")
        assert key == "env-fallback"

    def test_resolve_with_empty_api_key_env(self) -> None:
        """Returns None when api_key_env is empty."""
        resolver = ApiKeyResolver()
        key = resolver.resolve(None, "")
        assert key is None
