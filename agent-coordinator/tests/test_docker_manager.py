"""Tests for docker_manager — container runtime detection and lifecycle."""

from __future__ import annotations

import subprocess as sp
from pathlib import Path
from unittest.mock import patch

from src.docker_manager import (
    _ensure_colima_vm,
    detect_runtime,
    is_colima_installed,
    is_colima_running,
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

    def test_unsupported_runtime_rejected(self) -> None:
        assert detect_runtime("malicious") is None

    def test_auto_falls_back_to_podman(self) -> None:
        """Docker info fails but podman succeeds → returns podman."""
        import subprocess as sp

        call_count = 0

        def _which(name: str) -> str | None:
            return f"/usr/bin/{name}"

        def _run(*args: object, **kwargs: object) -> sp.CompletedProcess[str]:
            nonlocal call_count
            call_count += 1
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd[0] == "docker":
                raise sp.CalledProcessError(1, "docker info")
            result = sp.CompletedProcess(cmd, 0)  # type: ignore[arg-type]
            return result

        with (
            patch("shutil.which", side_effect=_which),
            patch("subprocess.run", side_effect=_run),
        ):
            assert detect_runtime("auto") == "podman"


# ---------------------------------------------------------------------------
# detect_runtime — Colima integration
# ---------------------------------------------------------------------------


class TestDetectRuntimeColima:
    """Integration tests for detect_runtime's Colima auto-start path."""

    def test_auto_mode_colima_fallback_on_macos(self) -> None:
        """Auto mode: docker fails → Colima starts → docker works → returns docker."""
        docker_info_calls = 0

        def _which(name: str) -> str | None:
            return f"/usr/bin/{name}"

        def _run(*args: object, **kwargs: object) -> sp.CompletedProcess[str]:
            nonlocal docker_info_calls
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd[0] == "docker":
                docker_info_calls += 1
                if docker_info_calls == 1:
                    raise sp.CalledProcessError(1, "docker info")
                return sp.CompletedProcess(cmd, 0)  # type: ignore[arg-type]
            return sp.CompletedProcess(cmd, 0)  # type: ignore[arg-type]

        with (
            patch("shutil.which", side_effect=_which),
            patch("subprocess.run", side_effect=_run),
            patch("sys.platform", "darwin"),
            patch("src.docker_manager.is_colima_installed", return_value=True),
            patch("src.docker_manager._ensure_colima_vm", return_value=True),
        ):
            result = detect_runtime("auto", docker_config={"colima": {}})
            assert result == "docker"

    def test_auto_mode_no_colima_on_linux(self) -> None:
        """Auto mode on Linux: docker fails → skips Colima → falls back to podman."""

        def _which(name: str) -> str | None:
            return f"/usr/bin/{name}"

        def _run(*args: object, **kwargs: object) -> sp.CompletedProcess[str]:
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd[0] == "docker":
                raise sp.CalledProcessError(1, "docker info")
            return sp.CompletedProcess(cmd, 0)  # type: ignore[arg-type]

        with (
            patch("shutil.which", side_effect=_which),
            patch("subprocess.run", side_effect=_run),
            patch("sys.platform", "linux"),
        ):
            assert detect_runtime("auto") == "podman"

    def test_explicit_colima_on_macos(self) -> None:
        """Explicit 'colima' preferred: ensures VM and returns docker."""
        with (
            patch("sys.platform", "darwin"),
            patch("src.docker_manager.is_colima_installed", return_value=True),
            patch("src.docker_manager._ensure_colima_vm", return_value=True),
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = sp.CompletedProcess([], 0)
            result = detect_runtime("colima", docker_config={"colima": {}})
            assert result == "docker"

    def test_explicit_colima_not_installed(self) -> None:
        """Explicit 'colima' but not installed → returns None."""
        with (
            patch("sys.platform", "darwin"),
            patch("src.docker_manager.is_colima_installed", return_value=False),
        ):
            assert detect_runtime("colima") is None

    def test_explicit_colima_on_non_macos(self) -> None:
        """Explicit 'colima' on Linux → falls back to auto behavior."""

        def _which(name: str) -> str | None:
            return f"/usr/bin/{name}"

        with (
            patch("sys.platform", "linux"),
            patch("shutil.which", side_effect=_which),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = sp.CompletedProcess([], 0)
            result = detect_runtime("colima")
            assert result == "docker"

    def test_backward_compatible_no_docker_config(self) -> None:
        """Calling detect_runtime without docker_config still works."""
        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value.returncode = 0
            assert detect_runtime() == "docker"

    def test_colima_ensure_fails_falls_back_to_podman(self) -> None:
        """Colima VM start fails → falls through to podman."""

        def _which(name: str) -> str | None:
            return f"/usr/bin/{name}"

        def _run(*args: object, **kwargs: object) -> sp.CompletedProcess[str]:
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd[0] == "docker":
                raise sp.CalledProcessError(1, "docker info")
            return sp.CompletedProcess(cmd, 0)  # type: ignore[arg-type]

        with (
            patch("shutil.which", side_effect=_which),
            patch("subprocess.run", side_effect=_run),
            patch("sys.platform", "darwin"),
            patch("src.docker_manager.is_colima_installed", return_value=True),
            patch("src.docker_manager._ensure_colima_vm", return_value=False),
        ):
            assert detect_runtime("auto", docker_config={"colima": {}}) == "podman"


# ---------------------------------------------------------------------------
# is_colima_installed / is_colima_running
# ---------------------------------------------------------------------------


class TestIsColimaInstalled:
    def test_colima_on_path(self) -> None:
        with patch("shutil.which", return_value="/usr/local/bin/colima"):
            assert is_colima_installed() is True

    def test_colima_not_on_path(self) -> None:
        with patch("shutil.which", return_value=None):
            assert is_colima_installed() is False


class TestIsColimaRunning:
    def test_vm_running(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = sp.CompletedProcess(["colima", "status"], 0)
            assert is_colima_running() is True

    def test_vm_stopped(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = sp.CompletedProcess(["colima", "status"], 1)
            assert is_colima_running() is False

    def test_colima_not_installed_returns_false(self) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert is_colima_running() is False

    def test_timeout_returns_false(self) -> None:
        with patch("subprocess.run", side_effect=sp.TimeoutExpired("colima", 10)):
            assert is_colima_running() is False


# ---------------------------------------------------------------------------
# _ensure_colima_vm
# ---------------------------------------------------------------------------


class TestEnsureColimaVm:
    def test_already_running_is_noop(self) -> None:
        """Idempotent: returns True without starting if VM is already running."""
        with patch("src.docker_manager.is_colima_running", return_value=True):
            assert _ensure_colima_vm({}) is True

    def test_auto_start_disabled(self) -> None:
        """Returns False without starting when auto_start is false."""
        with patch("src.docker_manager.is_colima_running", return_value=False):
            assert _ensure_colima_vm({"auto_start": False}) is False

    def test_start_success(self) -> None:
        """Starts VM and verifies docker info succeeds."""
        with (
            patch("src.docker_manager.is_colima_running", return_value=False),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = sp.CompletedProcess([], 0)
            assert _ensure_colima_vm({}) is True
            # First call: colima start, second call: docker info
            assert mock_run.call_count == 2
            start_cmd = mock_run.call_args_list[0][0][0]
            assert start_cmd[0] == "colima"
            assert start_cmd[1] == "start"

    def test_start_with_custom_resources(self) -> None:
        config = {"cpu": 4, "memory": 8, "disk": 60}
        with (
            patch("src.docker_manager.is_colima_running", return_value=False),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = sp.CompletedProcess([], 0)
            _ensure_colima_vm(config)
            start_cmd = mock_run.call_args_list[0][0][0]
            assert "--cpu" in start_cmd
            idx = start_cmd.index("--cpu")
            assert start_cmd[idx + 1] == "4"
            idx = start_cmd.index("--memory")
            assert start_cmd[idx + 1] == "8"
            idx = start_cmd.index("--disk")
            assert start_cmd[idx + 1] == "60"

    def test_default_resources(self) -> None:
        with (
            patch("src.docker_manager.is_colima_running", return_value=False),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = sp.CompletedProcess([], 0)
            _ensure_colima_vm({})
            start_cmd = mock_run.call_args_list[0][0][0]
            idx = start_cmd.index("--cpu")
            assert start_cmd[idx + 1] == "2"
            idx = start_cmd.index("--memory")
            assert start_cmd[idx + 1] == "4"
            idx = start_cmd.index("--disk")
            assert start_cmd[idx + 1] == "30"

    def test_apple_silicon_virt_flags(self) -> None:
        """Apple Virt flags added on arm64 when apple_virt is true."""
        with (
            patch("src.docker_manager.is_colima_running", return_value=False),
            patch("platform.machine", return_value="arm64"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = sp.CompletedProcess([], 0)
            _ensure_colima_vm({"apple_virt": True})
            start_cmd = mock_run.call_args_list[0][0][0]
            assert "--arch" in start_cmd
            assert "--vm-type=vz" in start_cmd
            assert "--vz-rosetta" in start_cmd

    def test_intel_mac_skips_virt_flags(self) -> None:
        """Apple Virt flags NOT added on x86_64 even when apple_virt is true."""
        with (
            patch("src.docker_manager.is_colima_running", return_value=False),
            patch("platform.machine", return_value="x86_64"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = sp.CompletedProcess([], 0)
            _ensure_colima_vm({"apple_virt": True})
            start_cmd = mock_run.call_args_list[0][0][0]
            assert "--arch" not in start_cmd
            assert "--vm-type=vz" not in start_cmd
            assert "--vz-rosetta" not in start_cmd

    def test_start_failure(self) -> None:
        with (
            patch("src.docker_manager.is_colima_running", return_value=False),
            patch(
                "subprocess.run",
                side_effect=sp.CalledProcessError(1, "colima start"),
            ),
        ):
            assert _ensure_colima_vm({}) is False

    def test_start_timeout(self) -> None:
        with (
            patch("src.docker_manager.is_colima_running", return_value=False),
            patch(
                "subprocess.run",
                side_effect=sp.TimeoutExpired("colima start", 120),
            ),
        ):
            assert _ensure_colima_vm({}) is False

    def test_docker_info_fails_after_start(self) -> None:
        """VM starts but docker info fails → returns False."""
        call_count = 0

        def _run(*args: object, **kwargs: object) -> sp.CompletedProcess[str]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # colima start succeeds
                return sp.CompletedProcess([], 0)
            # docker info fails
            raise sp.CalledProcessError(1, "docker info")

        with (
            patch("src.docker_manager.is_colima_running", return_value=False),
            patch("subprocess.run", side_effect=_run),
        ):
            assert _ensure_colima_vm({}) is False


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

    def test_timeout_returns_false(self) -> None:
        import subprocess as sp

        with patch("subprocess.run", side_effect=sp.TimeoutExpired("docker", 10)):
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
        cfg = {
            "enabled": True,
            "container_name": "paradedb",
            "compose_file": "docker-compose.yml",
        }
        with (
            patch("src.docker_manager.detect_runtime", return_value="docker"),
            patch("src.docker_manager.is_container_running", return_value=True),
        ):
            result = start_container(cfg, base_dir=tmp_path)
            assert result["already_running"] is True
            assert result["started"] is False

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
        cfg = {
            "enabled": True,
            "container_name": "paradedb",
            "compose_file": "docker-compose.yml",
        }
        with (
            patch("src.docker_manager.detect_runtime", return_value="docker"),
            patch("src.docker_manager.is_container_running", return_value=False),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value.returncode = 0
            result = start_container(cfg, base_dir=tmp_path)
            assert result == {"started": True, "runtime": "docker"}

    def test_compose_up_fails(self, tmp_path: Path) -> None:
        import subprocess as sp

        compose = tmp_path / "docker-compose.yml"
        compose.write_text("version: '3'\n")
        cfg = {
            "enabled": True,
            "container_name": "paradedb",
            "compose_file": "docker-compose.yml",
        }
        with (
            patch("src.docker_manager.detect_runtime", return_value="docker"),
            patch("src.docker_manager.is_container_running", return_value=False),
            patch(
                "subprocess.run",
                side_effect=sp.CalledProcessError(1, "compose", stderr="image not found"),
            ),
        ):
            result = start_container(cfg, base_dir=tmp_path)
            assert result["started"] is False
            assert "compose up failed" in result["error"]

    def test_compose_up_timeout(self, tmp_path: Path) -> None:
        import subprocess as sp

        compose = tmp_path / "docker-compose.yml"
        compose.write_text("version: '3'\n")
        cfg = {
            "enabled": True,
            "container_name": "paradedb",
            "compose_file": "docker-compose.yml",
        }
        with (
            patch("src.docker_manager.detect_runtime", return_value="docker"),
            patch("src.docker_manager.is_container_running", return_value=False),
            patch(
                "subprocess.run",
                side_effect=sp.TimeoutExpired("compose", 120),
            ),
        ):
            result = start_container(cfg, base_dir=tmp_path)
            assert result["started"] is False
            assert "timed out" in result["error"]

    def test_colima_started_in_result(self, tmp_path: Path) -> None:
        """start_container includes colima_started when VM was auto-started."""
        compose = tmp_path / "docker-compose.yml"
        compose.write_text("version: '3'\n")
        cfg = {
            "enabled": True,
            "container_name": "paradedb",
            "compose_file": "docker-compose.yml",
        }
        colima_call_count = 0

        def _is_colima_running() -> bool:
            nonlocal colima_call_count
            colima_call_count += 1
            # First call (before detect): not running; second call (after): running
            return colima_call_count > 1

        with (
            patch("sys.platform", "darwin"),
            patch("src.docker_manager.sys") as mock_sys,
            patch("src.docker_manager.detect_runtime", return_value="docker"),
            patch("src.docker_manager.is_colima_running", side_effect=_is_colima_running),
            patch("src.docker_manager.is_container_running", return_value=False),
            patch("subprocess.run") as mock_run,
        ):
            mock_sys.platform = "darwin"
            mock_run.return_value = sp.CompletedProcess([], 0)
            result = start_container(cfg, base_dir=tmp_path)
            assert result["started"] is True
            assert result["colima_started"] is True

    def test_compose_file_path_traversal(self, tmp_path: Path) -> None:
        with (
            patch("src.docker_manager.detect_runtime", return_value="docker"),
            patch("src.docker_manager.is_container_running", return_value=False),
        ):
            result = start_container(
                {"enabled": True, "container_name": "paradedb", "compose_file": "../../etc/passwd"},
                base_dir=tmp_path,
            )
            assert result["started"] is False
            assert "escapes" in result["error"]


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
