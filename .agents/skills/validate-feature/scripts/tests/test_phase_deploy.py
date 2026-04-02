"""Tests for phase_deploy.py — the deploy phase runner.

TDD tests written before implementation (task 5.1).
Tests cover:
- --env docker creates DockerStackEnvironment
- --env neon creates NeonBranchEnvironment
- .test-env file is written with required fields
- Failure produces JSON error on stderr
- --timeout is passed to wait_ready
- All environment classes are mocked — no actual Docker/Neon interaction
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure scripts dir is importable
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from phase_deploy import create_environment, main, write_test_env_file


class TestCreateEnvironment:
    """Test environment factory based on --env flag."""

    @patch("phase_deploy.DockerStackEnvironment")
    def test_env_docker_creates_docker_environment(self, mock_docker_cls: MagicMock) -> None:
        """--env docker should instantiate DockerStackEnvironment."""
        mock_instance = MagicMock()
        mock_docker_cls.return_value = mock_instance

        env = create_environment(
            env_type="docker",
            seed_strategy="migrations",
            compose_file="/path/to/compose.yml",
        )

        mock_docker_cls.assert_called_once_with(compose_file="/path/to/compose.yml")
        assert env is mock_instance

    @patch("phase_deploy.NeonBranchEnvironment")
    def test_env_neon_creates_neon_environment(self, mock_neon_cls: MagicMock) -> None:
        """--env neon should instantiate NeonBranchEnvironment."""
        mock_instance = MagicMock()
        mock_neon_cls.return_value = mock_instance

        env = create_environment(
            env_type="neon",
            seed_strategy="dump_restore",
        )

        mock_neon_cls.assert_called_once_with(seed_strategy="dump_restore")
        assert env is mock_instance

    def test_invalid_env_raises_value_error(self) -> None:
        """Unknown --env value should raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported environment type"):
            create_environment(env_type="invalid")


class TestWriteTestEnvFile:
    """Test .test-env file writing with required fields."""

    def test_writes_required_fields(self, tmp_path: Path) -> None:
        """The .test-env file must contain all required fields per contract."""
        env_vars = {
            "POSTGRES_DSN": "postgresql://postgres:postgres@localhost:10000/postgres",
            "API_BASE_URL": "http://localhost:10003",
            "DB_PORT": "10000",
            "API_PORT": "10003",
            "COMPOSE_PROJECT_NAME": "ac-test123",
            "SESSION_ID": "test-abc",
            "ENV_TYPE": "docker",
        }

        test_env_path = str(tmp_path / ".test-env")
        write_test_env_file(
            path=test_env_path,
            env_vars=env_vars,
            env_type="docker",
            seed_strategy="migrations",
        )

        content = Path(test_env_path).read_text()

        # Required fields per contract
        assert "TEST_ENV_TYPE=docker" in content
        assert "POSTGRES_DSN=" in content
        assert "API_BASE_URL=" in content
        assert "SEED_STRATEGY=migrations" in content
        assert "STARTED_AT=" in content

    def test_docker_includes_compose_fields(self, tmp_path: Path) -> None:
        """Docker env should include COMPOSE_PROJECT_NAME."""
        env_vars = {
            "POSTGRES_DSN": "postgresql://postgres:postgres@localhost:10000/postgres",
            "API_BASE_URL": "http://localhost:10003",
            "DB_PORT": "10000",
            "API_PORT": "10003",
            "COMPOSE_PROJECT_NAME": "ac-test123",
        }

        test_env_path = str(tmp_path / ".test-env")
        write_test_env_file(
            path=test_env_path,
            env_vars=env_vars,
            env_type="docker",
            seed_strategy="migrations",
        )

        content = Path(test_env_path).read_text()
        assert "COMPOSE_PROJECT_NAME=ac-test123" in content

    def test_neon_includes_branch_fields(self, tmp_path: Path) -> None:
        """Neon env should include NEON_BRANCH_ID."""
        env_vars = {
            "POSTGRES_DSN": "postgresql://user:pass@host/db",
            "NEON_BRANCH_ID": "br-abc123",
            "NEON_PROJECT_ID": "proj-xyz",
            "NEON_HOST": "host.neon.tech",
            "TEST_ENV_TYPE": "neon",
        }

        test_env_path = str(tmp_path / ".test-env")
        write_test_env_file(
            path=test_env_path,
            env_vars=env_vars,
            env_type="neon",
            seed_strategy="dump_restore",
        )

        content = Path(test_env_path).read_text()
        assert "NEON_BRANCH_ID=br-abc123" in content
        assert "TEST_ENV_TYPE=neon" in content


class TestMainCLI:
    """Test the main() CLI entry point."""

    @patch("phase_deploy.create_environment")
    def test_timeout_passed_to_wait_ready(
        self, mock_create_env: MagicMock, tmp_path: Path
    ) -> None:
        """--timeout should be forwarded to wait_ready()."""
        mock_env = MagicMock()
        mock_env.env_vars.return_value = {
            "POSTGRES_DSN": "postgresql://localhost/test",
            "API_BASE_URL": "http://localhost:8000",
        }
        mock_create_env.return_value = mock_env

        test_env_path = str(tmp_path / ".test-env")

        with patch(
            "sys.argv",
            ["phase_deploy.py", "--env", "docker", "--timeout", "60", "--test-env", test_env_path],
        ):
            main()

        mock_env.wait_ready.assert_called_once_with(timeout_seconds=60)

    @patch("phase_deploy.create_environment")
    def test_start_and_wait_ready_called(
        self, mock_create_env: MagicMock, tmp_path: Path
    ) -> None:
        """main() should call start() then wait_ready()."""
        mock_env = MagicMock()
        mock_env.env_vars.return_value = {
            "POSTGRES_DSN": "postgresql://localhost/test",
            "API_BASE_URL": "http://localhost:8000",
        }
        mock_create_env.return_value = mock_env

        test_env_path = str(tmp_path / ".test-env")

        with patch(
            "sys.argv",
            ["phase_deploy.py", "--env", "docker", "--test-env", test_env_path],
        ):
            main()

        mock_env.start.assert_called_once()
        mock_env.wait_ready.assert_called_once()

    @patch("phase_deploy.create_environment")
    def test_test_env_file_written(
        self, mock_create_env: MagicMock, tmp_path: Path
    ) -> None:
        """main() should write .test-env file on success."""
        mock_env = MagicMock()
        mock_env.env_vars.return_value = {
            "POSTGRES_DSN": "postgresql://localhost/test",
            "API_BASE_URL": "http://localhost:8000",
        }
        mock_create_env.return_value = mock_env

        test_env_path = str(tmp_path / ".test-env")

        with patch(
            "sys.argv",
            ["phase_deploy.py", "--env", "docker", "--test-env", test_env_path],
        ):
            main()

        assert Path(test_env_path).exists()

    @patch("phase_deploy.create_environment")
    def test_failure_produces_json_error_on_stderr(
        self, mock_create_env: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """On failure, exit code 1 and JSON error on stderr."""
        mock_env = MagicMock()
        mock_env.start.side_effect = RuntimeError("Docker not available")
        mock_create_env.return_value = mock_env

        with patch(
            "sys.argv",
            ["phase_deploy.py", "--env", "docker"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        error_data = json.loads(captured.err)
        assert error_data["error"] == "Docker not available"
        assert error_data["env"] == "docker"
        assert error_data["phase"] == "deploy"

    @patch("phase_deploy.create_environment")
    def test_timeout_failure_produces_json_error(
        self, mock_create_env: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """TimeoutError also produces JSON error on stderr."""
        mock_env = MagicMock()
        mock_env.wait_ready.side_effect = TimeoutError("Timed out waiting")
        mock_create_env.return_value = mock_env

        with patch(
            "sys.argv",
            ["phase_deploy.py", "--env", "neon"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        error_data = json.loads(captured.err)
        assert error_data["env"] == "neon"
        assert error_data["phase"] == "deploy"

    @patch("phase_deploy.create_environment")
    def test_default_timeout_is_120(
        self, mock_create_env: MagicMock, tmp_path: Path
    ) -> None:
        """Default timeout should be 120 seconds."""
        mock_env = MagicMock()
        mock_env.env_vars.return_value = {
            "POSTGRES_DSN": "postgresql://localhost/test",
            "API_BASE_URL": "http://localhost:8000",
        }
        mock_create_env.return_value = mock_env

        test_env_path = str(tmp_path / ".test-env")

        with patch(
            "sys.argv",
            ["phase_deploy.py", "--env", "docker", "--test-env", test_env_path],
        ):
            main()

        mock_env.wait_ready.assert_called_once_with(timeout_seconds=120)

    @patch("phase_deploy.create_environment")
    def test_compose_file_passed_to_create_environment(
        self, mock_create_env: MagicMock, tmp_path: Path
    ) -> None:
        """--compose-file should be forwarded to create_environment."""
        mock_env = MagicMock()
        mock_env.env_vars.return_value = {
            "POSTGRES_DSN": "postgresql://localhost/test",
            "API_BASE_URL": "http://localhost:8000",
        }
        mock_create_env.return_value = mock_env

        test_env_path = str(tmp_path / ".test-env")

        with patch(
            "sys.argv",
            [
                "phase_deploy.py",
                "--env",
                "docker",
                "--compose-file",
                "/custom/compose.yml",
                "--test-env",
                test_env_path,
            ],
        ):
            main()

        mock_create_env.assert_called_once_with(
            env_type="docker",
            seed_strategy="migrations",
            compose_file="/custom/compose.yml",
        )
