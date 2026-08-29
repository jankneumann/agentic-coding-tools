"""Docker compose-based test environment implementation.

Design decisions:
- D3: Port allocation is self-contained so installed skills do not require the
  coordinator package or its virtual environment.
- D3a: Coordination API runs on host via uvicorn, not inside Docker.
  Docker compose only provides PostgreSQL.
"""

from __future__ import annotations

import logging
import os
import random
import json
import socket
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import fcntl

logger = logging.getLogger(__name__)
PORT_REGISTRY_DIR = Path(tempfile.gettempdir()) / "agentic-coding-tools-ports"

_RUNTIME_CANDIDATES = ("docker", "podman")
_RUNTIME_INFO_TIMEOUT_SECONDS = 5.0


def _runtime_info_ok(name: str, timeout: float = _RUNTIME_INFO_TIMEOUT_SECONDS) -> bool:
    """Return True iff ``<name> info`` exits 0 within *timeout* seconds."""
    try:
        result = subprocess.run(
            [name, "info"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def detect_container_runtime() -> str:
    """Return the first usable container runtime, preferring docker.

    A runtime is usable only when its binary is on PATH and ``<runtime> info``
    succeeds. Presence without a responding daemon is treated as unusable so a
    dead docker does not hide a working podman (issue #433).
    """
    unusable: list[str] = []
    absent: list[str] = []
    for name in _RUNTIME_CANDIDATES:
        if not shutil.which(name):
            absent.append(name)
            continue
        if _runtime_info_ok(name):
            return name
        unusable.append(name)

    parts: list[str] = []
    for name in unusable:
        parts.append(f"{name} present but its daemon is not responding")
    for name in absent:
        parts.append(f"{name} not installed")
    detail = "; ".join(parts) if parts else "no candidates considered"
    raise RuntimeError(
        "No usable container runtime. " + detail + ". "
        "Install docker or podman, or start the matching daemon, "
        "to use DockerStackEnvironment."
    )


@contextmanager
def _locked_port_registry() -> Iterator[dict[str, dict[str, Any]]]:
    """Lock, load, and atomically persist cross-process port reservations."""
    PORT_REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(PORT_REGISTRY_DIR / ".registry.lock", os.O_CREAT | os.O_RDWR, 0o600)
    registry_path = PORT_REGISTRY_DIR / "registry.json"
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            raw = json.loads(registry_path.read_text()) if registry_path.exists() else {}
        except (json.JSONDecodeError, OSError):
            raw = {}
        registry: dict[str, dict[str, Any]] = (
            {
                key: value
                for key, value in raw.items()
                if isinstance(key, str) and isinstance(value, dict)
            }
            if isinstance(raw, dict)
            else {}
        )
        yield registry
        pending = registry_path.with_suffix(".json.tmp")
        pending.write_text(json.dumps(registry, sort_keys=True))
        pending.replace(registry_path)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


class DockerStackEnvironment:
    """Manage a Docker compose test environment with isolated port allocation.

    Implements the TestEnvironment protocol (structural subtyping via D1).
    """

    def __init__(
        self,
        compose_file: str,
        session_id: str | None = None,
    ) -> None:
        self.compose_file = compose_file
        self.session_id = session_id or f"test-{uuid.uuid4().hex[:12]}"
        self.runtime = self._detect_runtime()
        self._allocation: dict[str, object] | None = None
        self._torn_down = False

    @staticmethod
    def _detect_runtime() -> str:
        """Return the first usable container runtime, preferring docker.

        Usable means the binary is on PATH *and* ``<runtime> info`` succeeds.
        A docker binary with a dead daemon must not mask a working podman.
        """
        return detect_container_runtime()

    def _allocate_ports(self) -> dict[str, object]:
        """Reserve four available ports in a persistent cross-session registry.

        The locked registry prevents parallel validate-feature processes from
        choosing the same ports after their launch commands exit. Each candidate
        is also bind-probed to avoid ports held by unrelated local processes.
        """
        with _locked_port_registry() as registry:
            existing = registry.get(self.session_id)
            if isinstance(existing, dict) and isinstance(existing.get("ports"), list):
                existing_ports = existing["ports"]
                if len(existing_ports) == 4 and all(
                    isinstance(port, int) for port in existing_ports
                ):
                    return {
                        "session_id": self.session_id,
                        "db_port": existing_ports[0],
                        "rest_port": existing_ports[1],
                        "realtime_port": existing_ports[2],
                        "api_port": existing_ports[3],
                        "compose_project_name": existing.get(
                            "compose_project_name", f"validate-{self.session_id}"[:63]
                        ),
                    }

            reserved = {
                port
                for entry in registry.values()
                if isinstance(entry, dict)
                for port in entry.get("ports", [])
                if isinstance(port, int)
            }
            candidates = [port for port in range(15432, 25432) if port not in reserved]
            random.SystemRandom().shuffle(candidates)
            ports: list[int] = []
            for port in candidates:
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                        sock.bind(("127.0.0.1", port))
                except OSError:
                    continue
                ports.append(port)
                if len(ports) == 4:
                    break
            if len(ports) != 4:
                raise RuntimeError("Port allocation failed: fewer than four ports available")
            project_name = f"validate-{self.session_id}"[:63]
            registry[self.session_id] = {
                "ports": ports,
                "compose_project_name": project_name,
            }
            return {
                "session_id": self.session_id,
                "db_port": ports[0],
                "rest_port": ports[1],
                "realtime_port": ports[2],
                "api_port": ports[3],
                "compose_project_name": project_name,
            }

    def _release_ports(self) -> None:
        """Remove this session's persistent reservation under the registry lock."""
        with _locked_port_registry() as registry:
            registry.pop(self.session_id, None)

    def start(self) -> None:
        """Allocate ports and start docker compose stack."""
        # Step 1: Allocate ports
        self._allocation = self._allocate_ports()

        # Step 2: Start docker compose with allocated ports
        db_port = str(self._allocation["db_port"])
        project_name = str(self._allocation["compose_project_name"])

        env_overrides = {
            "AGENT_COORDINATOR_DB_PORT": db_port,
            "COMPOSE_PROJECT_NAME": project_name,
        }

        compose_env = {**os.environ, **env_overrides}

        cmd = [
            self.runtime,
            "compose",
            "-f",
            self.compose_file,
            "-p",
            project_name,
            "up",
            "-d",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                env=compose_env,
            )
        except Exception:
            self._release_ports()
            raise

        if result.returncode != 0:
            self._release_ports()
            logger.error("Compose up failed: %s", result.stderr)
            raise RuntimeError(
                f"Docker compose up failed (rc={result.returncode}): {result.stderr}"
            )

        logger.info(
            "Docker compose started: project=%s db_port=%s",
            project_name,
            db_port,
        )

    def wait_ready(self, timeout_seconds: int = 120) -> None:
        """Poll pg_isready until the database is accepting connections."""
        if self._allocation is None:
            raise RuntimeError("Cannot wait_ready before start()")

        db_port = str(self._allocation["db_port"])
        deadline = time.monotonic() + timeout_seconds

        while True:
            try:
                result = subprocess.run(
                    ["pg_isready", "-h", "localhost", "-p", db_port],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    logger.info("Database ready on port %s", db_port)
                    return
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

            if time.monotonic() >= deadline:
                raise TimeoutError(f"Database not ready after {timeout_seconds}s on port {db_port}")

            time.sleep(2)

    def teardown(self) -> None:
        """Stop compose stack, release ports. Idempotent."""
        if self._allocation is None:
            return

        project_name = str(self._allocation.get("compose_project_name", ""))

        # Step 1: Compose down
        try:
            cmd = [
                self.runtime,
                "compose",
                "-f",
                self.compose_file,
            ]
            if project_name:
                cmd.extend(["-p", project_name])
            cmd.extend(["down", "-v"])

            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            logger.info("Docker compose stopped: project=%s", project_name)
        except Exception:
            logger.warning("Failed to stop compose for project %s", project_name, exc_info=True)

        # Step 2: Release ports
        try:
            self._release_ports()
        except Exception:
            logger.warning(
                "Failed to release ports for session %s",
                self.session_id,
                exc_info=True,
            )

        self._torn_down = True

    def env_vars(self) -> dict[str, str]:
        """Return environment variables for this test environment."""
        if self._allocation is None:
            raise RuntimeError("Cannot get env_vars before start()")

        db_port = str(self._allocation["db_port"])
        api_port = str(self._allocation["api_port"])
        project_name = str(self._allocation["compose_project_name"])

        return {
            "POSTGRES_DSN": f"postgresql://postgres:postgres@localhost:{db_port}/postgres",
            "DB_PORT": db_port,
            "API_PORT": api_port,
            "API_BASE_URL": f"http://localhost:{api_port}",
            "COMPOSE_PROJECT_NAME": project_name,
            "SESSION_ID": self.session_id,
            "ENV_TYPE": "docker",
            "AGENT_COORDINATOR_DB_PORT": db_port,
        }


def main() -> None:
    """CLI: ``python docker_stack.py --detect`` prints the usable runtime."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Detect a usable container runtime (docker or podman).",
    )
    parser.add_argument(
        "--detect",
        action="store_true",
        help="Print the first usable runtime and exit 0; exit 1 if none is usable.",
    )
    args = parser.parse_args()
    if not args.detect:
        parser.print_help()
        sys.exit(2)
    try:
        print(detect_container_runtime())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
