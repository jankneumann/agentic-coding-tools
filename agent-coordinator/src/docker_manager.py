"""Docker / Podman container lifecycle management.

Detects available container runtimes, auto-starts the ParadeDB container from
a profile's ``docker`` block, and waits for health checks to pass.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def detect_runtime(preferred: str = "auto") -> str | None:
    """Detect an available container runtime.

    Args:
        preferred: ``"auto"`` (try docker then podman), ``"docker"``, or
            ``"podman"``.

    Returns:
        The runtime name (``"docker"`` or ``"podman"``), or ``None`` when
        no usable runtime is found.
    """
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

    runtime = detect_runtime(str(docker_config.get("container_runtime", "auto")))
    if runtime is None:
        return {"started": False, "error": "no container runtime available"}

    container_name = str(docker_config.get("container_name", "paradedb"))
    if is_container_running(runtime, container_name):
        return {"already_running": True, "runtime": runtime}

    compose_file = base_dir / str(docker_config.get("compose_file", "docker-compose.yml"))
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

    return {"started": True, "runtime": runtime}


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
