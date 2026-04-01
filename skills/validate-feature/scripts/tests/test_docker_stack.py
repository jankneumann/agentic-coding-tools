"""Tests for TestEnvironment protocol and DockerStackEnvironment.

TDD test-first: these tests define the expected behavior for:
- TestEnvironment protocol compliance (D1: typing.Protocol, @runtime_checkable)
- SeedableEnvironment protocol compliance
- DockerStackEnvironment lifecycle: init, start, wait_ready, teardown
- Runtime detection (docker vs podman fallback)
- Port allocation via subprocess
- Environment variable generation
- Error handling: no runtime, port conflict, timeout
"""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, call, mock_open, patch

import pytest


# ---------------------------------------------------------------------------
# Protocol compliance tests
# ---------------------------------------------------------------------------


class TestProtocolCompliance:
    """Verify TestEnvironment and SeedableEnvironment are runtime_checkable protocols."""

    def test_test_environment_is_runtime_checkable(self) -> None:
        from environments.protocol import TestEnvironment

        # Must be a Protocol with @runtime_checkable
        assert hasattr(TestEnvironment, "__protocol_attrs__") or hasattr(
            TestEnvironment, "_is_runtime_protocol"
        )

    def test_docker_stack_satisfies_test_environment(self) -> None:
        from environments.docker_stack import DockerStackEnvironment
        from environments.protocol import TestEnvironment

        assert isinstance(DockerStackEnvironment.__mro__, tuple)
        # runtime_checkable protocol isinstance check
        env = DockerStackEnvironment.__new__(DockerStackEnvironment)
        # Verify required methods exist
        assert callable(getattr(env, "start", None))
        assert callable(getattr(env, "wait_ready", None))
        assert callable(getattr(env, "teardown", None))
        assert callable(getattr(env, "env_vars", None))

    def test_docker_stack_isinstance_test_environment(self) -> None:
        from environments.docker_stack import DockerStackEnvironment
        from environments.protocol import TestEnvironment

        env = DockerStackEnvironment.__new__(DockerStackEnvironment)
        assert isinstance(env, TestEnvironment)

    def test_seedable_environment_protocol(self) -> None:
        from environments.protocol import SeedableEnvironment

        # SeedableEnvironment extends TestEnvironment with seed()
        assert hasattr(SeedableEnvironment, "__protocol_attrs__") or hasattr(
            SeedableEnvironment, "_is_runtime_protocol"
        )


# ---------------------------------------------------------------------------
# Runtime detection tests
# ---------------------------------------------------------------------------


class TestRuntimeDetection:
    """DockerStackEnvironment must detect docker or podman on PATH."""

    @patch("shutil.which")
    def test_detects_docker(self, mock_which: MagicMock) -> None:
        from environments.docker_stack import DockerStackEnvironment

        mock_which.side_effect = lambda cmd: "/usr/bin/docker" if cmd == "docker" else None
        env = DockerStackEnvironment(compose_file="docker-compose.yml")
        assert env.runtime == "docker"

    @patch("shutil.which")
    def test_falls_back_to_podman(self, mock_which: MagicMock) -> None:
        from environments.docker_stack import DockerStackEnvironment

        mock_which.side_effect = lambda cmd: "/usr/bin/podman" if cmd == "podman" else None
        env = DockerStackEnvironment(compose_file="docker-compose.yml")
        assert env.runtime == "podman"

    @patch("shutil.which")
    def test_raises_when_no_runtime(self, mock_which: MagicMock) -> None:
        from environments.docker_stack import DockerStackEnvironment

        mock_which.return_value = None
        with pytest.raises(RuntimeError, match="[Nn]either docker nor podman"):
            DockerStackEnvironment(compose_file="docker-compose.yml")

    @patch("shutil.which")
    def test_prefers_docker_over_podman(self, mock_which: MagicMock) -> None:
        from environments.docker_stack import DockerStackEnvironment

        mock_which.side_effect = lambda cmd: f"/usr/bin/{cmd}"
        env = DockerStackEnvironment(compose_file="docker-compose.yml")
        assert env.runtime == "docker"


# ---------------------------------------------------------------------------
# Initialization tests
# ---------------------------------------------------------------------------


class TestInit:
    """DockerStackEnvironment __init__ stores compose_file and session_id."""

    @patch("shutil.which", return_value="/usr/bin/docker")
    def test_stores_compose_file(self, _w: MagicMock) -> None:
        from environments.docker_stack import DockerStackEnvironment

        env = DockerStackEnvironment(compose_file="/path/to/docker-compose.yml")
        assert env.compose_file == "/path/to/docker-compose.yml"

    @patch("shutil.which", return_value="/usr/bin/docker")
    def test_stores_session_id(self, _w: MagicMock) -> None:
        from environments.docker_stack import DockerStackEnvironment

        env = DockerStackEnvironment(
            compose_file="docker-compose.yml", session_id="test-session"
        )
        assert env.session_id == "test-session"

    @patch("shutil.which", return_value="/usr/bin/docker")
    def test_generates_session_id_if_none(self, _w: MagicMock) -> None:
        from environments.docker_stack import DockerStackEnvironment

        env = DockerStackEnvironment(compose_file="docker-compose.yml")
        assert env.session_id is not None
        assert len(env.session_id) > 0


# ---------------------------------------------------------------------------
# Port allocation tests
# ---------------------------------------------------------------------------


class TestPortAllocation:
    """Port allocation via subprocess to agent-coordinator venv."""

    @patch("shutil.which", return_value="/usr/bin/docker")
    @patch("subprocess.run")
    def test_start_allocates_ports_via_subprocess(
        self, mock_run: MagicMock, _w: MagicMock
    ) -> None:
        from environments.docker_stack import DockerStackEnvironment

        port_result = json.dumps(
            {
                "session_id": "test-session",
                "db_port": 10000,
                "rest_port": 10001,
                "realtime_port": 10002,
                "api_port": 10003,
                "compose_project_name": "ac-abcd1234",
            }
        )
        # First call = port allocation subprocess, second = docker compose up
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=port_result, stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]

        env = DockerStackEnvironment(
            compose_file="docker-compose.yml", session_id="test-session"
        )
        env.start()

        # Verify port allocation subprocess was called
        first_call = mock_run.call_args_list[0]
        assert "port_allocator" in str(first_call) or "allocate" in str(first_call)

    @patch("shutil.which", return_value="/usr/bin/docker")
    @patch("subprocess.run")
    def test_start_runs_docker_compose_up(
        self, mock_run: MagicMock, _w: MagicMock
    ) -> None:
        from environments.docker_stack import DockerStackEnvironment

        port_result = json.dumps(
            {
                "session_id": "test-session",
                "db_port": 10000,
                "rest_port": 10001,
                "realtime_port": 10002,
                "api_port": 10003,
                "compose_project_name": "ac-abcd1234",
            }
        )
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=port_result, stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]

        env = DockerStackEnvironment(
            compose_file="docker-compose.yml", session_id="test-session"
        )
        env.start()

        # Second subprocess call should be docker compose up
        compose_call = mock_run.call_args_list[1]
        cmd = compose_call[0][0] if compose_call[0] else compose_call[1].get("args", [])
        assert "compose" in cmd
        assert "up" in cmd
        assert "-d" in cmd

    @patch("shutil.which", return_value="/usr/bin/docker")
    @patch("subprocess.run")
    def test_start_raises_on_port_allocation_failure(
        self, mock_run: MagicMock, _w: MagicMock
    ) -> None:
        from environments.docker_stack import DockerStackEnvironment

        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="allocation failed"
        )

        env = DockerStackEnvironment(
            compose_file="docker-compose.yml", session_id="test-session"
        )
        with pytest.raises(RuntimeError, match="[Pp]ort allocation"):
            env.start()

    @patch("shutil.which", return_value="/usr/bin/docker")
    @patch("subprocess.run")
    def test_start_raises_on_compose_failure(
        self, mock_run: MagicMock, _w: MagicMock
    ) -> None:
        from environments.docker_stack import DockerStackEnvironment

        port_result = json.dumps(
            {
                "session_id": "test-session",
                "db_port": 10000,
                "rest_port": 10001,
                "realtime_port": 10002,
                "api_port": 10003,
                "compose_project_name": "ac-abcd1234",
            }
        )
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=port_result, stderr=""),
            MagicMock(returncode=1, stdout="", stderr="compose error"),
        ]

        env = DockerStackEnvironment(
            compose_file="docker-compose.yml", session_id="test-session"
        )
        with pytest.raises(RuntimeError, match="[Cc]ompose.*failed|[Ff]ailed.*compose"):
            env.start()


# ---------------------------------------------------------------------------
# wait_ready tests
# ---------------------------------------------------------------------------


class TestWaitReady:
    """wait_ready polls pg_isready until success or timeout."""

    @patch("shutil.which", return_value="/usr/bin/docker")
    @patch("subprocess.run")
    @patch("time.sleep")
    @patch("time.monotonic")
    def test_wait_ready_succeeds(
        self,
        mock_time: MagicMock,
        mock_sleep: MagicMock,
        mock_run: MagicMock,
        _w: MagicMock,
    ) -> None:
        from environments.docker_stack import DockerStackEnvironment

        env = DockerStackEnvironment(
            compose_file="docker-compose.yml", session_id="test-session"
        )
        # Simulate allocated ports
        env._allocation = {
            "db_port": 10000,
            "api_port": 10003,
            "compose_project_name": "ac-abcd1234",
        }

        mock_time.side_effect = [0.0, 1.0]  # Within timeout
        mock_run.return_value = MagicMock(returncode=0)

        env.wait_ready(timeout_seconds=30)
        # Should have called pg_isready
        assert mock_run.called

    @patch("shutil.which", return_value="/usr/bin/docker")
    @patch("subprocess.run")
    @patch("time.sleep")
    @patch("time.monotonic")
    def test_wait_ready_times_out(
        self,
        mock_time: MagicMock,
        mock_sleep: MagicMock,
        mock_run: MagicMock,
        _w: MagicMock,
    ) -> None:
        from environments.docker_stack import DockerStackEnvironment

        env = DockerStackEnvironment(
            compose_file="docker-compose.yml", session_id="test-session"
        )
        env._allocation = {
            "db_port": 10000,
            "api_port": 10003,
            "compose_project_name": "ac-abcd1234",
        }

        # Time goes past timeout
        mock_time.side_effect = [0.0, 2.0, 4.0, 130.0]
        mock_run.return_value = MagicMock(returncode=1)

        with pytest.raises(TimeoutError, match="[Tt]imeout|not ready"):
            env.wait_ready(timeout_seconds=120)

    @patch("shutil.which", return_value="/usr/bin/docker")
    @patch("subprocess.run")
    @patch("time.sleep")
    @patch("time.monotonic")
    def test_wait_ready_polls_at_2_second_intervals(
        self,
        mock_time: MagicMock,
        mock_sleep: MagicMock,
        mock_run: MagicMock,
        _w: MagicMock,
    ) -> None:
        from environments.docker_stack import DockerStackEnvironment

        env = DockerStackEnvironment(
            compose_file="docker-compose.yml", session_id="test-session"
        )
        env._allocation = {
            "db_port": 10000,
            "api_port": 10003,
            "compose_project_name": "ac-abcd1234",
        }

        # Fail twice then succeed
        mock_time.side_effect = [0.0, 2.0, 4.0, 6.0]
        mock_run.side_effect = [
            MagicMock(returncode=1),
            MagicMock(returncode=1),
            MagicMock(returncode=0),
        ]

        env.wait_ready(timeout_seconds=30)
        # Check sleep was called with 2
        for c in mock_sleep.call_args_list:
            assert c[0][0] == 2


# ---------------------------------------------------------------------------
# teardown tests
# ---------------------------------------------------------------------------


class TestTeardown:
    """Teardown runs docker compose down -v and releases ports."""

    @patch("shutil.which", return_value="/usr/bin/docker")
    @patch("subprocess.run")
    def test_teardown_runs_compose_down(
        self, mock_run: MagicMock, _w: MagicMock
    ) -> None:
        from environments.docker_stack import DockerStackEnvironment

        env = DockerStackEnvironment(
            compose_file="docker-compose.yml", session_id="test-session"
        )
        env._allocation = {
            "db_port": 10000,
            "api_port": 10003,
            "compose_project_name": "ac-abcd1234",
        }

        mock_run.side_effect = [
            MagicMock(returncode=0),  # compose down
            MagicMock(returncode=0),  # port release
        ]

        env.teardown()

        # First call should be compose down -v
        compose_call = mock_run.call_args_list[0]
        cmd = compose_call[0][0] if compose_call[0] else compose_call[1].get("args", [])
        assert "down" in cmd
        assert "-v" in cmd

    @patch("shutil.which", return_value="/usr/bin/docker")
    @patch("subprocess.run")
    def test_teardown_is_idempotent(
        self, mock_run: MagicMock, _w: MagicMock
    ) -> None:
        from environments.docker_stack import DockerStackEnvironment

        env = DockerStackEnvironment(
            compose_file="docker-compose.yml", session_id="test-session"
        )
        env._allocation = {
            "db_port": 10000,
            "api_port": 10003,
            "compose_project_name": "ac-abcd1234",
        }

        # First teardown
        mock_run.return_value = MagicMock(returncode=0)
        env.teardown()

        # Second teardown should not raise
        mock_run.reset_mock()
        env.teardown()

    @patch("shutil.which", return_value="/usr/bin/docker")
    @patch("subprocess.run")
    def test_teardown_catches_exceptions(
        self, mock_run: MagicMock, _w: MagicMock
    ) -> None:
        from environments.docker_stack import DockerStackEnvironment

        env = DockerStackEnvironment(
            compose_file="docker-compose.yml", session_id="test-session"
        )
        env._allocation = {
            "db_port": 10000,
            "api_port": 10003,
            "compose_project_name": "ac-abcd1234",
        }

        mock_run.side_effect = OSError("docker not found")

        # Should NOT raise
        env.teardown()


# ---------------------------------------------------------------------------
# env_vars tests
# ---------------------------------------------------------------------------


class TestEnvVars:
    """env_vars returns required environment variables."""

    @patch("shutil.which", return_value="/usr/bin/docker")
    def test_env_vars_returns_required_keys(self, _w: MagicMock) -> None:
        from environments.docker_stack import DockerStackEnvironment

        env = DockerStackEnvironment(
            compose_file="docker-compose.yml", session_id="test-session"
        )
        env._allocation = {
            "db_port": 10000,
            "rest_port": 10001,
            "realtime_port": 10002,
            "api_port": 10003,
            "compose_project_name": "ac-abcd1234",
        }

        result = env.env_vars()

        assert "POSTGRES_DSN" in result
        assert "COMPOSE_PROJECT_NAME" in result
        assert "DB_PORT" in result
        assert "API_PORT" in result
        assert result["DB_PORT"] == "10000"
        assert result["API_PORT"] == "10003"
        assert result["COMPOSE_PROJECT_NAME"] == "ac-abcd1234"

    @patch("shutil.which", return_value="/usr/bin/docker")
    def test_env_vars_postgres_dsn_format(self, _w: MagicMock) -> None:
        from environments.docker_stack import DockerStackEnvironment

        env = DockerStackEnvironment(
            compose_file="docker-compose.yml", session_id="test-session"
        )
        env._allocation = {
            "db_port": 10000,
            "rest_port": 10001,
            "realtime_port": 10002,
            "api_port": 10003,
            "compose_project_name": "ac-abcd1234",
        }

        result = env.env_vars()
        dsn = result["POSTGRES_DSN"]
        assert "localhost" in dsn
        assert "10000" in dsn
        assert dsn.startswith("postgresql://")

    @patch("shutil.which", return_value="/usr/bin/docker")
    def test_env_vars_includes_api_base_url(self, _w: MagicMock) -> None:
        from environments.docker_stack import DockerStackEnvironment

        env = DockerStackEnvironment(
            compose_file="docker-compose.yml", session_id="test-session"
        )
        env._allocation = {
            "db_port": 10000,
            "rest_port": 10001,
            "realtime_port": 10002,
            "api_port": 10003,
            "compose_project_name": "ac-abcd1234",
        }

        result = env.env_vars()
        assert "API_BASE_URL" in result
        assert "10003" in result["API_BASE_URL"]

    @patch("shutil.which", return_value="/usr/bin/docker")
    def test_env_vars_raises_before_start(self, _w: MagicMock) -> None:
        from environments.docker_stack import DockerStackEnvironment

        env = DockerStackEnvironment(
            compose_file="docker-compose.yml", session_id="test-session"
        )
        # No allocation set
        with pytest.raises((RuntimeError, AttributeError)):
            env.env_vars()
