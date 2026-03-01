"""Tests for profile_loader — YAML profiles with inheritance and interpolation."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.profile_loader import (
    apply_profile,
    deep_merge,
    interpolate,
    load_profile,
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
