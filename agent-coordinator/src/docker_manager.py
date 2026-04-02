"""Docker / Podman container lifecycle management.

Detects available container runtimes, auto-starts the ParadeDB container from
a profile's ``docker`` block, and waits for health checks to pass.  On macOS,
Colima VM lifecycle is managed transparently when no Docker daemon is available.
"""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ALLOWED_RUNTIMES = {"auto", "docker", "podman", "colima"}


# ---------------------------------------------------------------------------
# Colima VM helpers
# ---------------------------------------------------------------------------


def is_colima_installed() -> bool:
    """Return ``True`` if the ``colima`` binary is on PATH."""
    return shutil.which("colima") is not None


def is_colima_running() -> bool:
    """Return ``True`` if the Colima VM is currently running."""
    try:
        result = subprocess.run(
            ["colima", "status"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _ensure_colima_vm(colima_config: dict[str, Any]) -> bool:
    """Ensure the Colima VM is running, starting it if necessary.

    Args:
        colima_config: The ``docker.colima`` block from a resolved profile.

    Returns:
        ``True`` if the VM is running after this call, ``False`` otherwise.
    """
    if is_colima_running():
        return True

    if not colima_config.get("auto_start", True):
        logger.info("Colima auto-start is disabled in profile")
        return False

    cpu = str(colima_config.get("cpu", 2))
    memory = str(colima_config.get("memory", 4))
    disk = str(colima_config.get("disk", 30))

    cmd = ["colima", "start", "--cpu", cpu, "--memory", memory, "--disk", disk]

    apple_virt = colima_config.get("apple_virt", True)
    if apple_virt and platform.machine() in ("arm64", "aarch64"):
        cmd.extend(["--arch", "aarch64", "--vm-type=vz", "--vz-rosetta"])

    try:
        subprocess.run(cmd, capture_output=True, timeout=120, check=True)
    except FileNotFoundError:
        logger.warning("Colima binary not found")
        return False
    except subprocess.CalledProcessError as exc:
        logger.warning("Colima start failed: %s", exc)
        return False
    except subprocess.TimeoutExpired:
        logger.warning("Colima start timed out after 120s")
        return False

    # Verify Docker daemon is accessible through Colima's socket
    try:
        subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=15,
            check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        logger.warning("docker info failed after Colima start")
        return False

    return True


def detect_runtime(
    preferred: str = "auto",
    *,
    docker_config: dict[str, Any] | None = None,
) -> str | None:
    """Detect an available container runtime.

    Args:
        preferred: ``"auto"`` (try docker then podman), ``"docker"``,
            ``"podman"``, or ``"colima"`` (macOS only).
        docker_config: The ``docker`` block from a resolved profile.
            Used to pass ``colima`` sub-config for VM auto-start.

    Returns:
        The runtime name (``"docker"`` or ``"podman"``), or ``None`` when
        no usable runtime is found.
    """
    if preferred not in _ALLOWED_RUNTIMES:
        logger.warning("Unsupported container runtime: %r", preferred)
        return None

    # Handle explicit "colima" preference
    if preferred == "colima":
        if sys.platform != "darwin":
            logger.warning("Colima is macOS-only; falling back to auto detection")
            preferred = "auto"
        elif not is_colima_installed():
            logger.warning("Colima explicitly selected but not installed")
            return None
        else:
            colima_cfg = (docker_config or {}).get("colima", {})
            if _ensure_colima_vm(colima_cfg):
                # VM is running and docker info verified inside _ensure_colima_vm
                return "docker"
            return None

    candidates = (
        ["docker", "podman"]
        if preferred == "auto"
        else [preferred]
    )
    for candidate in candidates:
        if shutil.which(candidate) is None:
            continue
        try:
            subprocess.run(
                [candidate, "info"],
                capture_output=True,
                timeout=15,
                check=True,
            )
            return candidate
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            # On macOS in auto mode, try Colima before falling back to podman
            if (
                candidate == "docker"
                and preferred == "auto"
                and sys.platform == "darwin"
                and is_colima_installed()
            ):
                colima_cfg = (docker_config or {}).get("colima", {})
                if _ensure_colima_vm(colima_cfg):
                    # _ensure_colima_vm already verified docker info works
                    return "docker"
            continue
    return None


def is_container_running(runtime: str, container_name: str) -> bool:
    """Check whether *container_name* is currently running."""
    try:
        result = subprocess.run(
            [runtime, "inspect", "--format", "{{.State.Running}}", container_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0 and result.stdout.strip().lower() == "true"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def start_container(
    docker_config: dict[str, Any],
    *,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    """Start the coordinator's database container.

    Args:
        docker_config: The ``docker`` block from a resolved profile.
        base_dir: Working directory for compose commands (defaults to
            ``agent-coordinator/``).

    Returns:
        A status dict with keys like ``started``, ``already_running``,
        ``runtime``, and ``error``.
    """
    if not docker_config.get("enabled", False):
        return {"started": False, "error": "docker disabled in profile"}

    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent

    # Snapshot Colima state before detection (D5: infer auto-start).
    # Only check when on macOS and Colima is installed — avoids unnecessary
    # subprocess calls for Docker Desktop users.
    preferred_rt = str(docker_config.get("container_runtime", "auto"))
    colima_was_running = (
        sys.platform == "darwin"
        and preferred_rt in ("auto", "colima")
        and is_colima_installed()
        and is_colima_running()
    )

    runtime = detect_runtime(
        str(docker_config.get("container_runtime", "auto")),
        docker_config=docker_config,
    )
    if runtime is None:
        return {"started": False, "error": "no container runtime available"}

    colima_started = (
        sys.platform == "darwin"
        and runtime == "docker"
        and not colima_was_running
        and is_colima_running()
    )

    container_name = str(docker_config.get("container_name", "paradedb"))
    if is_container_running(runtime, container_name):
        result: dict[str, Any] = {"started": False, "already_running": True, "runtime": runtime}
        if colima_started:
            result["colima_started"] = True
        return result

    compose_file = base_dir / str(docker_config.get("compose_file", "docker-compose.yml"))
    try:
        compose_file.resolve().relative_to(base_dir.resolve())
    except ValueError:
        return {
            "started": False,
            "error": f"compose file path escapes base directory: {compose_file.name}",
        }
    if not compose_file.is_file():
        return {"started": False, "error": f"compose file not found: {compose_file}"}

    try:
        subprocess.run(
            [runtime, "compose", "-f", str(compose_file), "up", "-d"],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
            cwd=str(base_dir),
        )
    except subprocess.CalledProcessError as exc:
        return {"started": False, "error": f"compose up failed: {exc.stderr.strip()}"}
    except subprocess.TimeoutExpired:
        return {"started": False, "error": "compose up timed out after 120s"}

    result = {"started": True, "runtime": runtime}
    if colima_started:
        result["colima_started"] = True
    return result


def wait_for_healthy(
    runtime: str,
    container_name: str,
    *,
    timeout: int = 60,
    poll_interval: int = 2,
) -> bool:
    """Wait for *container_name* to report ``healthy``.

    Args:
        runtime: Container runtime (``docker`` or ``podman``).
        container_name: Name of the container to check.
        timeout: Maximum seconds to wait.
        poll_interval: Seconds between polls.

    Returns:
        ``True`` if the container became healthy within *timeout*.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = subprocess.run(
                [
                    runtime,
                    "inspect",
                    "--format",
                    "{{.State.Health.Status}}",
                    container_name,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip() == "healthy":
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        time.sleep(poll_interval)
    return False
