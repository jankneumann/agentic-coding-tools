"""Tests for stack_launcher.py CLI.

TDD test-first: these tests define the expected behavior for:
- CLI argument parsing (start, teardown, status subcommands)
- .test-env file writing and reading
- Integration with DockerStackEnvironment
- Error handling and exit codes
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest


# ---------------------------------------------------------------------------
# Argument parsing tests
# ---------------------------------------------------------------------------


class TestArgParsing:
    """CLI accepts start, teardown, status subcommands."""

    def test_start_subcommand_default_env(self) -> None:
        from stack_launcher import build_parser

        parser = build_parser()
        args = parser.parse_args(["start"])
        assert args.subcommand == "start"
        assert args.env == "docker"

    def test_start_subcommand_with_env(self) -> None:
        from stack_launcher import build_parser

        parser = build_parser()
        args = parser.parse_args(["start", "--env", "neon"])
        assert args.env == "neon"

    def test_start_subcommand_with_seed_strategy(self) -> None:
        from stack_launcher import build_parser

        parser = build_parser()
        args = parser.parse_args(["start", "--seed-strategy", "dump_restore"])
        assert args.seed_strategy == "dump_restore"

    def test_start_subcommand_default_seed_strategy(self) -> None:
        from stack_launcher import build_parser

        parser = build_parser()
        args = parser.parse_args(["start"])
        assert args.seed_strategy is None or args.seed_strategy == "migrations"

    def test_start_subcommand_with_timeout(self) -> None:
        from stack_launcher import build_parser

        parser = build_parser()
        args = parser.parse_args(["start", "--timeout", "60"])
        assert args.timeout == 60

    def test_start_subcommand_default_timeout(self) -> None:
        from stack_launcher import build_parser

        parser = build_parser()
        args = parser.parse_args(["start"])
        assert args.timeout == 120

    def test_teardown_subcommand(self) -> None:
        from stack_launcher import build_parser

        parser = build_parser()
        args = parser.parse_args(["teardown"])
        assert args.subcommand == "teardown"

    def test_status_subcommand(self) -> None:
        from stack_launcher import build_parser

        parser = build_parser()
        args = parser.parse_args(["status"])
        assert args.subcommand == "status"

    def test_start_with_compose_file(self) -> None:
        from stack_launcher import build_parser

        parser = build_parser()
        args = parser.parse_args(["start", "--compose-file", "/path/to/compose.yml"])
        assert args.compose_file == "/path/to/compose.yml"

    def test_start_with_test_env_path(self) -> None:
        from stack_launcher import build_parser

        parser = build_parser()
        args = parser.parse_args(["start", "--test-env", "/tmp/.test-env"])
        assert args.test_env == "/tmp/.test-env"


# ---------------------------------------------------------------------------
# .test-env file tests
# ---------------------------------------------------------------------------


class TestTestEnvFile:
    """stack_launcher writes and reads .test-env files in dotenv format."""

    def test_write_test_env(self) -> None:
        from stack_launcher import write_test_env

        with tempfile.NamedTemporaryFile(mode="w", suffix=".test-env", delete=False) as f:
            path = f.name

        try:
            env_vars = {
                "POSTGRES_DSN": "postgresql://postgres:postgres@localhost:10000/postgres",
                "DB_PORT": "10000",
                "API_PORT": "10003",
                "COMPOSE_PROJECT_NAME": "ac-abcd1234",
                "API_BASE_URL": "http://localhost:10003",
                "SESSION_ID": "test-session",
                "ENV_TYPE": "docker",
            }
            write_test_env(path, env_vars)

            content = Path(path).read_text()
            assert "POSTGRES_DSN=" in content
            assert "DB_PORT=10000" in content
            assert "ENV_TYPE=docker" in content
            # Should be parseable as dotenv
            for line in content.strip().splitlines():
                if line and not line.startswith("#"):
                    assert "=" in line
        finally:
            os.unlink(path)

    def test_read_test_env(self) -> None:
        from stack_launcher import read_test_env

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".test-env", delete=False
        ) as f:
            f.write("POSTGRES_DSN=postgresql://postgres:postgres@localhost:10000/postgres\n")
            f.write("DB_PORT=10000\n")
            f.write("API_PORT=10003\n")
            f.write("# comment line\n")
            f.write("ENV_TYPE=docker\n")
            path = f.name

        try:
            result = read_test_env(path)
            assert result["POSTGRES_DSN"] == "postgresql://postgres:postgres@localhost:10000/postgres"
            assert result["DB_PORT"] == "10000"
            assert result["ENV_TYPE"] == "docker"
            assert "#" not in str(result.keys())
        finally:
            os.unlink(path)

    def test_read_test_env_missing_file(self) -> None:
        from stack_launcher import read_test_env

        with pytest.raises(FileNotFoundError):
            read_test_env("/nonexistent/.test-env")


# ---------------------------------------------------------------------------
# start command integration tests
# ---------------------------------------------------------------------------


class TestStartCommand:
    """start command creates environment, starts it, writes .test-env."""

    @patch("stack_launcher.DockerStackEnvironment")
    def test_start_creates_and_starts_environment(
        self, mock_env_cls: MagicMock
    ) -> None:
        from stack_launcher import cmd_start

        mock_env = MagicMock()
        mock_env.env_vars.return_value = {
            "POSTGRES_DSN": "postgresql://postgres:postgres@localhost:10000/postgres",
            "DB_PORT": "10000",
            "API_PORT": "10003",
            "COMPOSE_PROJECT_NAME": "ac-abcd1234",
            "API_BASE_URL": "http://localhost:10003",
        }
        mock_env.session_id = "test-session"
        mock_env_cls.return_value = mock_env

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".test-env", delete=False
        ) as f:
            test_env_path = f.name

        try:
            cmd_start(
                env_type="docker",
                compose_file="docker-compose.yml",
                test_env_path=test_env_path,
                timeout=30,
                seed_strategy=None,
            )

            mock_env.start.assert_called_once()
            mock_env.wait_ready.assert_called_once_with(timeout_seconds=30)
            # .test-env file should be written
            assert Path(test_env_path).exists()
            content = Path(test_env_path).read_text()
            assert "POSTGRES_DSN=" in content
        finally:
            if os.path.exists(test_env_path):
                os.unlink(test_env_path)

    @patch("stack_launcher.DockerStackEnvironment")
    def test_start_tears_down_on_failure(self, mock_env_cls: MagicMock) -> None:
        from stack_launcher import cmd_start

        mock_env = MagicMock()
        mock_env.start.side_effect = RuntimeError("port conflict")
        mock_env_cls.return_value = mock_env

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".test-env", delete=False
        ) as f:
            test_env_path = f.name

        try:
            with pytest.raises((RuntimeError, SystemExit)):
                cmd_start(
                    env_type="docker",
                    compose_file="docker-compose.yml",
                    test_env_path=test_env_path,
                    timeout=30,
                    seed_strategy=None,
                )
            # Teardown should have been attempted
            mock_env.teardown.assert_called_once()
        finally:
            if os.path.exists(test_env_path):
                os.unlink(test_env_path)


# ---------------------------------------------------------------------------
# teardown command tests
# ---------------------------------------------------------------------------


class TestTeardownCommand:
    """teardown reads .test-env and calls appropriate teardown."""

    @patch("stack_launcher.DockerStackEnvironment")
    def test_teardown_reads_env_and_tears_down(
        self, mock_env_cls: MagicMock
    ) -> None:
        from stack_launcher import cmd_teardown

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".test-env", delete=False
        ) as f:
            f.write("ENV_TYPE=docker\n")
            f.write("COMPOSE_PROJECT_NAME=ac-abcd1234\n")
            f.write("DB_PORT=10000\n")
            f.write("SESSION_ID=test-session\n")
            test_env_path = f.name

        mock_env = MagicMock()
        mock_env_cls.return_value = mock_env

        try:
            cmd_teardown(test_env_path=test_env_path, compose_file="docker-compose.yml")
            mock_env.teardown.assert_called_once()
        finally:
            if os.path.exists(test_env_path):
                os.unlink(test_env_path)

    def test_teardown_missing_env_file(self) -> None:
        from stack_launcher import cmd_teardown

        with pytest.raises(FileNotFoundError):
            cmd_teardown(
                test_env_path="/nonexistent/.test-env",
                compose_file="docker-compose.yml",
            )


# ---------------------------------------------------------------------------
# status command tests
# ---------------------------------------------------------------------------


class TestStatusCommand:
    """status reads .test-env and checks health."""

    @patch("subprocess.run")
    def test_status_checks_pg_isready(self, mock_run: MagicMock) -> None:
        from stack_launcher import cmd_status

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".test-env", delete=False
        ) as f:
            f.write("ENV_TYPE=docker\n")
            f.write("DB_PORT=10000\n")
            f.write("SESSION_ID=test-session\n")
            test_env_path = f.name

        mock_run.return_value = MagicMock(returncode=0)

        try:
            result = cmd_status(test_env_path=test_env_path)
            assert result["healthy"] is True
        finally:
            os.unlink(test_env_path)

    @patch("subprocess.run")
    def test_status_unhealthy(self, mock_run: MagicMock) -> None:
        from stack_launcher import cmd_status

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".test-env", delete=False
        ) as f:
            f.write("ENV_TYPE=docker\n")
            f.write("DB_PORT=10000\n")
            f.write("SESSION_ID=test-session\n")
            test_env_path = f.name

        mock_run.return_value = MagicMock(returncode=1)

        try:
            result = cmd_status(test_env_path=test_env_path)
            assert result["healthy"] is False
        finally:
            os.unlink(test_env_path)

    def test_status_missing_env_file(self) -> None:
        from stack_launcher import cmd_status

        with pytest.raises(FileNotFoundError):
            cmd_status(test_env_path="/nonexistent/.test-env")
