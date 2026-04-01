"""Test environment protocols for live service testing.

Design decision D1: typing.Protocol with @runtime_checkable (not ABC).
This allows structural subtyping — implementations don't need to inherit.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TestEnvironment(Protocol):
    """Protocol for test environment lifecycle management.

    Implementations manage the full lifecycle of a test environment:
    start -> wait_ready -> (run tests) -> teardown

    Environment variables are communicated via .test-env files (D2).
    """

    def start(self) -> None:
        """Provision and start the test environment.

        Allocates ports, starts services (e.g., docker compose up).
        Raises RuntimeError on failure.
        """
        ...

    def wait_ready(self, timeout_seconds: int = 120) -> None:
        """Block until the environment is ready to accept connections.

        Raises TimeoutError if not ready within timeout_seconds.
        """
        ...

    def teardown(self) -> None:
        """Stop and clean up the test environment.

        Releases ports, stops services. Must be idempotent —
        calling teardown multiple times must not raise.
        """
        ...

    def env_vars(self) -> dict[str, str]:
        """Return environment variables for connecting to this environment.

        Returns a dict suitable for writing to a .test-env file.
        Must include at minimum: POSTGRES_DSN, DB_PORT, API_PORT,
        COMPOSE_PROJECT_NAME, API_BASE_URL.

        Raises RuntimeError if called before start().
        """
        ...


@runtime_checkable
class SeedableEnvironment(TestEnvironment, Protocol):
    """Extended protocol for environments that support database seeding.

    Adds a seed() method for applying migrations or restoring dumps
    after the environment is ready.
    """

    def seed(self, strategy: str = "migrations") -> None:
        """Seed the database with initial data.

        Args:
            strategy: Seeding approach — "migrations" or "dump_restore".

        Raises RuntimeError if seeding fails.
        """
        ...
