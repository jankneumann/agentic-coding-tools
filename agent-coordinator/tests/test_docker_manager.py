"""Tests for docker_manager — container runtime detection and lifecycle."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.docker_manager import (
    detect_runtime,
    is_container_running,
    start_container,
    wait_for_healthy,
)


# ---------------------------------------------------------------------------
# detect_runtime
# ---------------------------------------------------------------------------


class TestDetectRuntime:
    def test_docker_detected(self) -> None:
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value.returncode = 0
            assert detect_runtime() == "docker"

    def test_only_podman_available(self) -> None:
        def _which(name: str) -> str | None:
            return "/usr/bin/podman" if name == "podman" else None

        with (
            patch("shutil.which", side_effect=_which),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value.returncode = 0
            assert detect_runtime() == "podman"

    def test_no_runtime(self) -> None:
        with patch("shutil.which", return_value=None):
            assert detect_runtime() is None

    def test_docker_info_fails(self) -> None:
        import subprocess

        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch(
                "subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "docker info"),
            ),
        ):
            assert detect_runtime("docker") is None


# ---------------------------------------------------------------------------
# is_container_running
# ---------------------------------------------------------------------------


class TestIsContainerRunning:
    def test_running(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "true\n"
            assert is_container_running("docker", "paradedb") is True

    def test_not_running(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ""
            assert is_container_running("docker", "paradedb") is False


# ---------------------------------------------------------------------------
# start_container
# ---------------------------------------------------------------------------


class TestStartContainer:
    def test_docker_disabled(self) -> None:
        result = start_container({"enabled": False})
        assert result == {"started": False, "error": "docker disabled in profile"}

    def test_already_running(self, tmp_path: Path) -> None:
        compose = tmp_path / "docker-compose.yml"
        compose.write_text("version: '3'\n")
        with (
            patch("src.docker_manager.detect_runtime", return_value="docker"),
            patch("src.docker_manager.is_container_running", return_value=True),
        ):
            result = start_container(
                {"enabled": True, "container_name": "paradedb", "compose_file": "docker-compose.yml"},
                base_dir=tmp_path,
            )
            assert result["already_running"] is True

    def test_compose_file_missing(self, tmp_path: Path) -> None:
        with (
            patch("src.docker_manager.detect_runtime", return_value="docker"),
            patch("src.docker_manager.is_container_running", return_value=False),
        ):
            result = start_container(
                {"enabled": True, "container_name": "paradedb", "compose_file": "missing.yml"},
                base_dir=tmp_path,
            )
            assert result["started"] is False
            assert "not found" in result["error"]

    def test_no_runtime_available(self) -> None:
        with patch("src.docker_manager.detect_runtime", return_value=None):
            result = start_container({"enabled": True})
            assert result["started"] is False
            assert "no container runtime" in result["error"]

    def test_successful_start(self, tmp_path: Path) -> None:
        compose = tmp_path / "docker-compose.yml"
        compose.write_text("version: '3'\n")
        with (
            patch("src.docker_manager.detect_runtime", return_value="docker"),
            patch("src.docker_manager.is_container_running", return_value=False),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value.returncode = 0
            result = start_container(
                {"enabled": True, "container_name": "paradedb", "compose_file": "docker-compose.yml"},
                base_dir=tmp_path,
            )
            assert result == {"started": True, "runtime": "docker"}


# ---------------------------------------------------------------------------
# wait_for_healthy
# ---------------------------------------------------------------------------


class TestWaitForHealthy:
    def test_becomes_healthy(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "healthy\n"
            assert wait_for_healthy("docker", "paradedb", timeout=5) is True

    def test_timeout(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "starting\n"
            assert wait_for_healthy("docker", "paradedb", timeout=2, poll_interval=1) is False
