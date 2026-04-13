"""Docker compose-based test environment implementation.

Design decisions:
- D3: Port allocator accessed via subprocess to agent-coordinator/.venv/bin/python
  (separate venvs — cannot import directly).
- D3a: Coordination API runs on host via uvicorn, not inside Docker.
  Docker compose only provides PostgreSQL.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


def _find_git_root() -> Path:
    """Walk up from this file to find the git root."""
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / ".git").exists():
            return parent
    raise RuntimeError("Could not find git root from " + str(current))


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
        """Detect docker or podman on PATH. Prefer docker."""
        if shutil.which("docker"):
            return "docker"
        if shutil.which("podman"):
            return "podman"
        raise RuntimeError(
            "Neither docker nor podman found on PATH. "
            "Install one to use DockerStackEnvironment."
        )

    def _allocate_ports(self) -> dict[str, object]:
        """Allocate ports via subprocess to agent-coordinator venv.

        Design decision D3: separate venvs, so we call the port allocator
        via subprocess rather than importing directly.
        """
        git_root = _find_git_root()
        venv_python = git_root / "agent-coordinator" / ".venv" / "bin" / "python"

        allocator_script = (
            "import json; "
            "from src.port_allocator import get_port_allocator; "
            f"alloc = get_port_allocator().allocate('{self.session_id}'); "
            "print(json.dumps({"
            "'session_id': alloc.session_id, "
            "'db_port': alloc.db_port, "
            "'rest_port': alloc.rest_port, "
            "'realtime_port': alloc.realtime_port, "
            "'api_port': alloc.api_port, "
            "'compose_project_name': alloc.compose_project_name"
            "}) if alloc else 'null')"
        )

        try:
            result = subprocess.run(
                [str(venv_python), "-c", allocator_script],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(git_root / "agent-coordinator"),
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(
                f"Port allocation subprocess failed: {exc}. "
                "Ensure agent-coordinator venv is set up: "
                "cd agent-coordinator && uv sync --all-extras"
            ) from exc

        if result.returncode != 0:
            raise RuntimeError(
                f"Port allocation failed (rc={result.returncode}): {result.stderr}"
            )

        data = json.loads(result.stdout.strip())
        if data is None:
            raise RuntimeError(
                "Port allocation returned null — all port ranges exhausted"
            )
        return data

    def _release_ports(self) -> None:
        """Release allocated ports via subprocess."""
        git_root = _find_git_root()
        venv_python = git_root / "agent-coordinator" / ".venv" / "bin" / "python"

        release_script = (
            "from src.port_allocator import get_port_allocator; "
            f"get_port_allocator().release('{self.session_id}')"
        )

        try:
            subprocess.run(
                [str(venv_python), "-c", release_script],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=str(git_root / "agent-coordinator"),
            )
        except Exception:
            logger.warning("Failed to release ports for session %s", self.session_id)

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

        import os

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

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            env=compose_env,
        )

        if result.returncode != 0:
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
                raise TimeoutError(
                    f"Database not ready after {timeout_seconds}s on port {db_port}"
                )

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
            logger.warning(
                "Failed to stop compose for project %s", project_name, exc_info=True
            )

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
