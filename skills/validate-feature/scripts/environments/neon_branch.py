"""Neon branch-based test environment implementation.

Design decisions:
- D4: Use neonctl CLI via subprocess, not Neon Python SDK (no new dependency).
- D5: pg_dump --format=custom --no-owner --no-privileges --exclude-extension=pg_search.

Creates ephemeral Neon branches for isolated test environments. Supports
two seeding strategies: `migrations` (apply SQL files via psql) and
`dump_restore` (pg_dump from source, pg_restore into branch).
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Migration files follow the naming convention: NNN_<description>.sql
_MIGRATION_RE = re.compile(r"^(\d+)_.+\.sql$")


class NeonBranchEnvironment:
    """Manage a Neon branch test environment with CLI-based lifecycle.

    Implements the TestEnvironment protocol (structural subtyping via D1).
    """

    def __init__(
        self,
        seed_strategy: str = "migrations",
        source_branch_id: str | None = None,
        source_dsn: str | None = None,
        migrations_dir: str | None = None,
        seed_file: str | None = None,
    ) -> None:
        self.seed_strategy = seed_strategy
        self.source_branch_id = source_branch_id
        self.source_dsn = source_dsn
        self.migrations_dir = migrations_dir
        self.seed_file = seed_file
        self._project_id: str | None = os.environ.get("NEON_PROJECT_ID")
        self._api_key: str | None = os.environ.get("NEON_API_KEY")
        self._branch_id: str | None = None
        self._connection_uri: str | None = None
        self._neon_host: str | None = None
        self._env: dict[str, str] = {}

    def _check_prerequisites(self) -> None:
        """Verify neonctl exists and credentials are set.

        Raises RuntimeError if any prerequisite is missing.
        """
        if not self._project_id:
            raise RuntimeError(
                "NEON_PROJECT_ID environment variable is required"
            )
        if not self._api_key:
            raise RuntimeError(
                "NEON_API_KEY environment variable is required"
            )
        if not shutil.which("neonctl"):
            raise RuntimeError(
                "neonctl CLI not found on PATH. "
                "Install it: npm install -g neonctl"
            )
        # Validate dump_restore prerequisites
        if (
            self.seed_strategy == "dump_restore"
            and not self.source_branch_id
            and not self.source_dsn
        ):
            raise RuntimeError(
                "source_dsn is required for dump_restore seed strategy "
                "when source_branch_id is not set"
            )

    def _create_branch(self) -> None:
        """Create a Neon branch via neonctl CLI.

        Parses JSON output for branch_id and connection_uri.
        Sets self._branch_id, self._connection_uri, and self._neon_host.
        """
        cmd = [
            "neonctl",
            "branches",
            "create",
            "--project-id",
            self._project_id or "",
            "--output",
            "json",
        ]

        if self.source_branch_id:
            cmd.extend(["--parent", self.source_branch_id])

        env = {**os.environ, "NEON_API_KEY": self._api_key or ""}

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"neonctl branch creation timed out: {exc}"
            ) from exc

        if result.returncode != 0:
            raise RuntimeError(
                f"neonctl branch creation failed (rc={result.returncode}): "
                f"{result.stderr}"
            )

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Failed to parse neonctl output: {result.stdout}"
            ) from exc

        self._branch_id = data["branch"]["id"]
        self._connection_uri = data.get("connection_uri", "")

        # Extract host from endpoints
        endpoints = data.get("endpoints", [])
        if endpoints:
            self._neon_host = endpoints[0].get("host", "")

        logger.info(
            "Neon branch created: id=%s host=%s",
            self._branch_id,
            self._neon_host,
        )

    def _seed_dump_restore(self) -> None:
        """Seed via pg_dump from source, pg_restore into Neon branch.

        Design decision D5: pg_dump --format=custom --no-owner
        --no-privileges --exclude-extension=pg_search.
        """
        if not self.source_dsn:
            raise RuntimeError(
                "source_dsn is required for dump_restore seed strategy"
            )

        # Create a temp file for the dump
        dump_fd, dump_path = tempfile.mkstemp(suffix=".dump")
        os.close(dump_fd)

        try:
            # pg_dump
            dump_cmd = [
                "pg_dump",
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                "--exclude-extension=pg_search",
                "-f",
                dump_path,
                "-d",
                self.source_dsn,
            ]

            result = subprocess.run(
                dump_cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"pg_dump failed (rc={result.returncode}): {result.stderr}"
                )

            logger.info("pg_dump completed: %s", dump_path)

            # pg_restore
            restore_cmd = [
                "pg_restore",
                "--no-owner",
                "--no-privileges",
                "-d",
                self._connection_uri or "",
                dump_path,
            ]

            result = subprocess.run(
                restore_cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"pg_restore failed (rc={result.returncode}): {result.stderr}"
                )

            logger.info("pg_restore completed into Neon branch %s", self._branch_id)

        finally:
            # Clean up temp file
            try:
                os.unlink(dump_path)
            except OSError:
                pass

    def _seed_migrations(self) -> None:
        """Seed via applying SQL migration files then seed.sql.

        Applies each .sql file from migrations_dir in sorted order via psql,
        then applies seed_file if provided.
        """
        if self.migrations_dir:
            migrations_path = Path(self.migrations_dir)
            if migrations_path.is_dir():
                migration_files: list[tuple[int, str, Path]] = []
                for entry in sorted(migrations_path.iterdir()):
                    m = _MIGRATION_RE.match(entry.name)
                    if m and entry.is_file():
                        migration_files.append(
                            (int(m.group(1)), entry.name, entry)
                        )
                migration_files.sort(key=lambda x: x[0])

                for seq, name, path in migration_files:
                    self._run_psql_file(path, f"Migration {name}")

        if self.seed_file:
            seed_path = Path(self.seed_file)
            if seed_path.is_file():
                self._run_psql_file(seed_path, "Seed data")

    def _run_psql_file(self, sql_file: Path, description: str) -> None:
        """Execute a SQL file against the Neon branch via psql."""
        cmd = [
            "psql",
            "-d",
            self._connection_uri or "",
            "-f",
            str(sql_file),
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Migration {sql_file.name} failed (rc={result.returncode}): "
                f"{result.stderr}"
            )

        logger.info("%s applied: %s", description, sql_file.name)

    def start(self) -> None:
        """Check prerequisites, create branch, seed database.

        Raises RuntimeError on failure.
        """
        self._check_prerequisites()
        self._create_branch()

        # Build env vars
        self._env = {
            "POSTGRES_DSN": self._connection_uri or "",
            "NEON_BRANCH_ID": self._branch_id or "",
            "NEON_PROJECT_ID": self._project_id or "",
            "NEON_HOST": self._neon_host or "",
            "TEST_ENV_TYPE": "neon",
        }

        # Skip seeding when branching from an existing Neon branch
        # (the parent branch data is inherited)
        if self.source_branch_id:
            logger.info(
                "Skipping seeding: branched from %s (data inherited)",
                self.source_branch_id,
            )
            return

        # Apply seeding strategy
        if self.seed_strategy == "dump_restore":
            self._seed_dump_restore()
        elif self.seed_strategy == "migrations":
            self._seed_migrations()

    def wait_ready(self, timeout_seconds: int = 60) -> None:
        """Poll psql -c 'SELECT 1' at 2-second intervals until ready.

        Raises TimeoutError if not ready within timeout_seconds.
        Raises RuntimeError if called before start().
        """
        if self._connection_uri is None:
            raise RuntimeError("Cannot wait_ready before start()")

        deadline = time.monotonic() + timeout_seconds

        while True:
            try:
                result = subprocess.run(
                    [
                        "psql",
                        "-c",
                        "SELECT 1",
                        "-d",
                        self._connection_uri,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    logger.info(
                        "Neon branch %s is ready", self._branch_id
                    )
                    return
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Neon branch {self._branch_id} not ready "
                    f"after {timeout_seconds}s"
                )

            time.sleep(2)

    def teardown(self) -> None:
        """Delete the Neon branch. Idempotent -- safe to call multiple times."""
        if self._branch_id is None:
            return

        branch_id = self._branch_id
        # Clear state first so second call is a no-op
        self._branch_id = None
        self._connection_uri = None
        self._env = {}

        try:
            env = {**os.environ}
            if self._api_key:
                env["NEON_API_KEY"] = self._api_key

            cmd = [
                "neonctl",
                "branches",
                "delete",
                branch_id,
                "--project-id",
                self._project_id or "",
            ]

            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )
            logger.info("Neon branch deleted: %s", branch_id)
        except Exception:
            logger.warning(
                "Failed to delete Neon branch %s",
                branch_id,
                exc_info=True,
            )

    def env_vars(self) -> dict[str, str]:
        """Return environment variables for connecting to this environment.

        Returns empty dict before start().
        """
        return dict(self._env)
