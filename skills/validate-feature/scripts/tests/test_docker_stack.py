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

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


@pytest.fixture(autouse=True)
def _assume_runtime_usable(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):
    """Non-detection tests must not invoke a real `docker info` / `podman info`.

    TestRuntimeDetection owns the usability probe and so skips this stub.
    Patching ``_runtime_info_ok`` (not ``subprocess.run``) leaves compose /
    pg_isready mocks in start/wait/teardown tests undisturbed.
    """
    if getattr(request, "cls", None) is TestRuntimeDetection:
        return
    from environments import docker_stack

    monkeypatch.setattr(
        docker_stack, "_runtime_info_ok", lambda name, timeout=5.0: True
    )


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
    """DockerStackEnvironment must detect a *usable* docker or podman.

    PATH presence is not enough: a docker binary with a dead daemon must
    fall through to a working podman (issue #433).
    """

    def _patch(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        present: dict[str, str],
        usable: dict[str, bool],
        timeout_for: frozenset[str] | None = None,
    ) -> None:
        from environments import docker_stack

        monkeypatch.setattr("shutil.which", lambda cmd: present.get(cmd))

        timeouts = timeout_for or frozenset()

        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs
            name = cmd[0] if cmd else ""
            if name in timeouts:
                raise docker_stack.subprocess.TimeoutExpired(cmd=cmd, timeout=1)
            rc = 0 if usable.get(name, False) else 1
            return MagicMock(returncode=rc, stdout="", stderr="")

        monkeypatch.setattr(docker_stack.subprocess, "run", fake_run)

    def test_detects_usable_docker(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from environments.docker_stack import DockerStackEnvironment

        self._patch(
            monkeypatch,
            present={"docker": "/usr/bin/docker"},
            usable={"docker": True},
        )
        env = DockerStackEnvironment(compose_file="docker-compose.yml")
        assert env.runtime == "docker"

    def test_falls_back_to_podman_when_docker_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from environments.docker_stack import DockerStackEnvironment

        self._patch(
            monkeypatch,
            present={"podman": "/usr/bin/podman"},
            usable={"podman": True},
        )
        env = DockerStackEnvironment(compose_file="docker-compose.yml")
        assert env.runtime == "podman"

    def test_dead_docker_falls_through_to_live_podman(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The configuration that produced #433: docker on PATH, daemon down, podman works."""
        from environments.docker_stack import DockerStackEnvironment

        self._patch(
            monkeypatch,
            present={"docker": "/usr/bin/docker", "podman": "/usr/bin/podman"},
            usable={"docker": False, "podman": True},
        )
        env = DockerStackEnvironment(compose_file="docker-compose.yml")
        assert env.runtime == "podman"

    def test_prefers_docker_when_both_usable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from environments.docker_stack import DockerStackEnvironment

        self._patch(
            monkeypatch,
            present={"docker": "/usr/bin/docker", "podman": "/usr/bin/podman"},
            usable={"docker": True, "podman": True},
        )
        env = DockerStackEnvironment(compose_file="docker-compose.yml")
        assert env.runtime == "docker"

    def test_raises_when_neither_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from environments.docker_stack import DockerStackEnvironment

        self._patch(monkeypatch, present={}, usable={})
        with pytest.raises(RuntimeError, match="not installed"):
            DockerStackEnvironment(compose_file="docker-compose.yml")

    def test_raises_naming_unusable_vs_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from environments.docker_stack import DockerStackEnvironment

        self._patch(
            monkeypatch,
            present={"docker": "/usr/bin/docker"},
            usable={"docker": False},
        )
        with pytest.raises(RuntimeError, match="daemon is not responding") as exc:
            DockerStackEnvironment(compose_file="docker-compose.yml")
        message = str(exc.value)
        assert "docker" in message
        assert "podman not installed" in message

    def test_info_timeout_counts_as_unusable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from environments.docker_stack import DockerStackEnvironment

        self._patch(
            monkeypatch,
            present={"docker": "/usr/bin/docker", "podman": "/usr/bin/podman"},
            usable={"podman": True},
            timeout_for=frozenset({"docker"}),
        )
        env = DockerStackEnvironment(compose_file="docker-compose.yml")
        assert env.runtime == "podman"


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

        env = DockerStackEnvironment(compose_file="docker-compose.yml", session_id="test-session")
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
    """Self-contained localhost port allocation."""

    @patch("shutil.which", return_value="/usr/bin/docker")
    @patch("socket.socket")
    def test_local_allocator_persists_distinct_ports_across_instances(
        self, mock_socket: MagicMock, _w: MagicMock, monkeypatch, tmp_path
    ) -> None:
        from environments import docker_stack
        from environments.docker_stack import DockerStackEnvironment

        monkeypatch.setattr(docker_stack, "PORT_REGISTRY_DIR", tmp_path / "ports")

        env = DockerStackEnvironment(compose_file="docker-compose.yml", session_id="test-session")
        allocation = env._allocate_ports()
        try:
            assert (
                len(
                    {
                        allocation[key]
                        for key in ("db_port", "rest_port", "realtime_port", "api_port")
                    }
                )
                == 4
            )
            second = DockerStackEnvironment(
                compose_file="docker-compose.yml", session_id="second-session"
            )
            second_allocation = second._allocate_ports()
            assert {
                allocation[key] for key in ("db_port", "rest_port", "realtime_port", "api_port")
            }.isdisjoint(
                {
                    second_allocation[key]
                    for key in ("db_port", "rest_port", "realtime_port", "api_port")
                }
            )
            second._release_ports()
            assert mock_socket.return_value.__enter__.return_value.bind.call_count == 8
        finally:
            env._release_ports()

    @patch("shutil.which", return_value="/usr/bin/docker")
    @patch("subprocess.run")
    def test_start_runs_docker_compose_up(self, mock_run: MagicMock, _w: MagicMock) -> None:
        from environments.docker_stack import DockerStackEnvironment

        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        env = DockerStackEnvironment(compose_file="docker-compose.yml", session_id="test-session")
        allocation = {
            "session_id": "test-session",
            "db_port": 10000,
            "rest_port": 10001,
            "realtime_port": 10002,
            "api_port": 10003,
            "compose_project_name": "validate-test-session",
        }
        with patch.object(env, "_allocate_ports", return_value=allocation):
            env.start()

        compose_call = mock_run.call_args_list[0]
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

        env = DockerStackEnvironment(compose_file="docker-compose.yml", session_id="test-session")
        with patch.object(
            env, "_allocate_ports", side_effect=RuntimeError("Port allocation failed")
        ):
            with pytest.raises(RuntimeError, match="[Pp]ort allocation"):
                env.start()
        mock_run.assert_not_called()

    @patch("shutil.which", return_value="/usr/bin/docker")
    @patch("subprocess.run")
    def test_start_raises_on_compose_failure(self, mock_run: MagicMock, _w: MagicMock) -> None:
        from environments.docker_stack import DockerStackEnvironment

        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="compose error")

        env = DockerStackEnvironment(compose_file="docker-compose.yml", session_id="test-session")
        allocation = {
            "session_id": "test-session",
            "db_port": 10000,
            "rest_port": 10001,
            "realtime_port": 10002,
            "api_port": 10003,
            "compose_project_name": "validate-test-session",
        }
        with patch.object(env, "_allocate_ports", return_value=allocation):
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

        env = DockerStackEnvironment(compose_file="docker-compose.yml", session_id="test-session")
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

        env = DockerStackEnvironment(compose_file="docker-compose.yml", session_id="test-session")
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

        env = DockerStackEnvironment(compose_file="docker-compose.yml", session_id="test-session")
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
    def test_teardown_runs_compose_down(self, mock_run: MagicMock, _w: MagicMock) -> None:
        from environments.docker_stack import DockerStackEnvironment

        env = DockerStackEnvironment(compose_file="docker-compose.yml", session_id="test-session")
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
    def test_teardown_is_idempotent(self, mock_run: MagicMock, _w: MagicMock) -> None:
        from environments.docker_stack import DockerStackEnvironment

        env = DockerStackEnvironment(compose_file="docker-compose.yml", session_id="test-session")
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
    def test_teardown_catches_exceptions(self, mock_run: MagicMock, _w: MagicMock) -> None:
        from environments.docker_stack import DockerStackEnvironment

        env = DockerStackEnvironment(compose_file="docker-compose.yml", session_id="test-session")
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

        env = DockerStackEnvironment(compose_file="docker-compose.yml", session_id="test-session")
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

        env = DockerStackEnvironment(compose_file="docker-compose.yml", session_id="test-session")
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

        env = DockerStackEnvironment(compose_file="docker-compose.yml", session_id="test-session")
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

        env = DockerStackEnvironment(compose_file="docker-compose.yml", session_id="test-session")
        # No allocation set
        with pytest.raises((RuntimeError, AttributeError)):
            env.env_vars()
