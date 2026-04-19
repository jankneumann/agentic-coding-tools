"""Tests for skills.shared.environment_profile."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from shared import environment_profile as ep


# ---------------------------------------------------------------------------
# Env-var layer
# ---------------------------------------------------------------------------


class TestEnvVarLayer:
    """Precedence layer 1: AGENT_EXECUTION_ENV and legacy CLAUDE_CODE_CLOUD."""

    def test_agent_execution_env_cloud_maps_to_isolation_provided(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AGENT_EXECUTION_ENV", "cloud")
        profile = ep.detect(_skip_coordinator=True, _skip_heuristic=True)
        assert profile.isolation_provided is True
        assert profile.source == "env_var"
        assert profile.details["var"] == "AGENT_EXECUTION_ENV"
        assert profile.details["value"] == "cloud"

    def test_agent_execution_env_local_forces_no_isolation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AGENT_EXECUTION_ENV", "local")
        profile = ep.detect(_skip_coordinator=True, _skip_heuristic=True)
        assert profile.isolation_provided is False
        assert profile.source == "env_var"

    def test_legacy_claude_code_cloud_true_maps_to_cloud(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AGENT_EXECUTION_ENV", raising=False)
        monkeypatch.setenv("CLAUDE_CODE_CLOUD", "1")
        profile = ep.detect(_skip_coordinator=True, _skip_heuristic=True)
        assert profile.isolation_provided is True
        assert profile.source == "env_var"
        assert profile.details["var"] == "CLAUDE_CODE_CLOUD"

    def test_agent_execution_env_beats_legacy_var(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AGENT_EXECUTION_ENV", "local")
        monkeypatch.setenv("CLAUDE_CODE_CLOUD", "1")
        profile = ep.detect(_skip_coordinator=True, _skip_heuristic=True)
        assert profile.isolation_provided is False
        assert profile.source == "env_var"
        assert profile.details["var"] == "AGENT_EXECUTION_ENV"

    def test_unrecognized_value_falls_through(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("AGENT_EXECUTION_ENV", "banana")
        profile = ep.detect(_skip_coordinator=True, _skip_heuristic=True)
        # No env_var decision -> falls through to default
        assert profile.source == "default"
        captured = capsys.readouterr()
        assert "banana" in captured.err
        assert "AGENT_EXECUTION_ENV" in captured.err

    def test_empty_env_var_is_ignored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AGENT_EXECUTION_ENV", "")
        monkeypatch.delenv("CLAUDE_CODE_CLOUD", raising=False)
        profile = ep.detect(_skip_coordinator=True, _skip_heuristic=True)
        assert profile.source == "default"


# ---------------------------------------------------------------------------
# Coordinator layer
# ---------------------------------------------------------------------------


class TestCoordinatorLayer:
    """Precedence layer 2: coordinator discovery query."""

    def test_coordinator_reports_isolation_provided_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AGENT_EXECUTION_ENV", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_CLOUD", raising=False)

        with patch.object(
            ep, "_query_coordinator", return_value={"isolation_provided": True}
        ):
            profile = ep.detect(agent_id="agent-42", _skip_heuristic=True)

        assert profile.isolation_provided is True
        assert profile.source == "coordinator"
        assert profile.details["agent_id"] == "agent-42"

    def test_coordinator_reports_isolation_provided_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AGENT_EXECUTION_ENV", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_CLOUD", raising=False)

        with patch.object(
            ep, "_query_coordinator", return_value={"isolation_provided": False}
        ):
            profile = ep.detect(agent_id="agent-42", _skip_heuristic=True)

        assert profile.isolation_provided is False
        assert profile.source == "coordinator"

    def test_coordinator_missing_field_falls_through_to_heuristic(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("AGENT_EXECUTION_ENV", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_CLOUD", raising=False)
        monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
        monkeypatch.delenv("CODESPACES", raising=False)

        # No /.dockerenv at custom path
        monkeypatch.setattr(ep, "_DOCKERENV_PATH", str(tmp_path / "nope"))

        with patch.object(
            ep, "_query_coordinator", return_value={"some_other_field": "foo"}
        ):
            profile = ep.detect(agent_id="agent-42")

        assert profile.source == "default"

    def test_coordinator_error_falls_through_silently(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("AGENT_EXECUTION_ENV", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_CLOUD", raising=False)
        monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
        monkeypatch.delenv("CODESPACES", raising=False)
        monkeypatch.setattr(ep, "_DOCKERENV_PATH", str(tmp_path / "nope"))

        def boom(*args: object, **kwargs: object) -> None:
            raise TimeoutError("coordinator unreachable")

        with patch.object(ep, "_query_coordinator", side_effect=boom):
            profile = ep.detect(agent_id="agent-42")

        # Error falls through — does not raise
        assert profile.source == "default"

    def test_coordinator_layer_skipped_when_no_agent_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AGENT_EXECUTION_ENV", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_CLOUD", raising=False)

        with patch.object(ep, "_query_coordinator") as mock_query:
            profile = ep.detect(agent_id=None, _skip_heuristic=True)

        # No agent-id -> coordinator query not attempted
        mock_query.assert_not_called()
        assert profile.source == "default"


# ---------------------------------------------------------------------------
# Heuristic layer
# ---------------------------------------------------------------------------


class TestHeuristicLayer:
    """Precedence layer 3: container heuristics."""

    def test_dockerenv_marker_triggers_cloud(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("AGENT_EXECUTION_ENV", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_CLOUD", raising=False)
        monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
        monkeypatch.delenv("CODESPACES", raising=False)

        fake_dockerenv = tmp_path / ".dockerenv"
        fake_dockerenv.touch()
        monkeypatch.setattr(ep, "_DOCKERENV_PATH", str(fake_dockerenv))

        profile = ep.detect(_skip_coordinator=True)
        assert profile.isolation_provided is True
        assert profile.source == "heuristic"
        assert profile.details["marker"] == "dockerenv"

    def test_kubernetes_env_triggers_cloud(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("AGENT_EXECUTION_ENV", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_CLOUD", raising=False)
        monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "svc.cluster.local")
        monkeypatch.delenv("CODESPACES", raising=False)
        monkeypatch.setattr(ep, "_DOCKERENV_PATH", str(tmp_path / "nope"))

        profile = ep.detect(_skip_coordinator=True)
        assert profile.isolation_provided is True
        assert profile.source == "heuristic"
        assert profile.details["marker"] == "kubernetes"

    def test_codespaces_env_triggers_cloud(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("AGENT_EXECUTION_ENV", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_CLOUD", raising=False)
        monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
        monkeypatch.setenv("CODESPACES", "true")
        monkeypatch.setattr(ep, "_DOCKERENV_PATH", str(tmp_path / "nope"))

        profile = ep.detect(_skip_coordinator=True)
        assert profile.isolation_provided is True
        assert profile.source == "heuristic"
        assert profile.details["marker"] == "codespaces"

    def test_no_heuristic_falls_through_to_default(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("AGENT_EXECUTION_ENV", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_CLOUD", raising=False)
        monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
        monkeypatch.delenv("CODESPACES", raising=False)
        monkeypatch.setattr(ep, "_DOCKERENV_PATH", str(tmp_path / "nope"))

        profile = ep.detect(_skip_coordinator=True)
        assert profile.isolation_provided is False
        assert profile.source == "default"


# ---------------------------------------------------------------------------
# Precedence — integration across layers
# ---------------------------------------------------------------------------


class TestPrecedence:
    """Verifies that env var beats coordinator beats heuristic beats default."""

    def test_env_var_overrides_coordinator_and_heuristic(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("AGENT_EXECUTION_ENV", "local")
        fake_dockerenv = tmp_path / ".dockerenv"
        fake_dockerenv.touch()
        monkeypatch.setattr(ep, "_DOCKERENV_PATH", str(fake_dockerenv))

        with patch.object(
            ep, "_query_coordinator", return_value={"isolation_provided": True}
        ):
            profile = ep.detect(agent_id="agent-42")

        assert profile.isolation_provided is False
        assert profile.source == "env_var"

    def test_coordinator_overrides_heuristic(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("AGENT_EXECUTION_ENV", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_CLOUD", raising=False)
        fake_dockerenv = tmp_path / ".dockerenv"
        fake_dockerenv.touch()
        monkeypatch.setattr(ep, "_DOCKERENV_PATH", str(fake_dockerenv))

        with patch.object(
            ep, "_query_coordinator", return_value={"isolation_provided": False}
        ):
            profile = ep.detect(agent_id="agent-42")

        assert profile.isolation_provided is False
        assert profile.source == "coordinator"

    def test_heuristic_fires_when_env_and_coordinator_silent(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("AGENT_EXECUTION_ENV", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_CLOUD", raising=False)
        monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "svc.cluster.local")
        monkeypatch.setattr(ep, "_DOCKERENV_PATH", str(tmp_path / "nope"))

        with patch.object(ep, "_query_coordinator", return_value=None):
            profile = ep.detect(agent_id="agent-42")

        assert profile.isolation_provided is True
        assert profile.source == "heuristic"


# ---------------------------------------------------------------------------
# Debug output
# ---------------------------------------------------------------------------


class TestDebugOutput:
    def test_worktree_debug_emits_profile_dump(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("WORKTREE_DEBUG", "1")
        monkeypatch.setenv("AGENT_EXECUTION_ENV", "cloud")
        profile = ep.detect(_skip_coordinator=True, _skip_heuristic=True)

        captured = capsys.readouterr()
        assert "environment_profile" in captured.err
        assert "isolation_provided=True" in captured.err
        assert profile.isolation_provided is True
