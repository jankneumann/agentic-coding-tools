"""Contract: TestEnvironment Protocol

Machine-readable interface definition for the TestEnvironment abstraction.
Implementations (DockerStackEnvironment, NeonBranchEnvironment) must satisfy
this protocol. Tests import this to type-check against the contract.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TestEnvironment(Protocol):
    """Protocol for live service test environments.

    Implementations manage the lifecycle of an isolated test stack
    (Docker containers, Neon branches, etc.) and expose connection
    details as environment variables.
    """

    def start(self) -> dict[str, str]:
        """Start the test environment and return connection env vars.

        Returns:
            Dictionary with at minimum:
            - POSTGRES_DSN: Full connection string to PostgreSQL
            - API_BASE_URL: Base URL for the coordination API
            Plus implementation-specific vars (COMPOSE_PROJECT_NAME, NEON_BRANCH_ID, etc.)

        Raises:
            RuntimeError: If the environment cannot be started (missing runtime, port conflict, etc.)
        """
        ...

    def wait_ready(self, timeout_seconds: int = 120) -> bool:
        """Wait for all services to become healthy.

        Args:
            timeout_seconds: Maximum time to wait. Default 120s.

        Returns:
            True if all services are ready, False if timeout exceeded.
        """
        ...

    def teardown(self) -> None:
        """Release all allocated resources.

        Safe to call multiple times (idempotent).
        Safe to call even if start() was never called or failed partway.
        """
        ...

    def env_vars(self) -> dict[str, str]:
        """Return current connection environment variables.

        Returns:
            Same dictionary as start() returned, or empty dict if not started.
        """
        ...


@runtime_checkable
class SeedableEnvironment(Protocol):
    """Extension protocol for environments that support data seeding."""

    def seed(self, strategy: str, source_dsn: str | None = None) -> None:
        """Apply seed data to the environment.

        Args:
            strategy: One of "dump_restore" or "migrations".
            source_dsn: For dump_restore, the source database DSN to dump from.
                        Ignored for migrations strategy.

        Raises:
            RuntimeError: If seeding fails.
            ValueError: If strategy is not recognized.
        """
        ...
