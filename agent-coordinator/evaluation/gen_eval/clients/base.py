"""Base protocol and shared dataclasses for transport clients."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from evaluation.gen_eval.models import ActionStep


@dataclass
class StepResult:
    """Result of executing a single scenario step."""

    status_code: int | None = None
    body: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    exit_code: int | None = None
    error: str | None = None
    duration_ms: float = 0.0


@dataclass
class StepContext:
    """Execution context passed to each step.

    Carries captured variables from prior steps, descriptor metadata,
    and the per-step timeout.
    """

    variables: dict[str, Any] = field(default_factory=dict)
    descriptor_info: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 30.0


@runtime_checkable
class TransportClient(Protocol):
    """Protocol that all transport clients must implement."""

    async def execute(self, step: ActionStep, context: StepContext) -> StepResult:
        """Execute a scenario step and return the result."""
        ...

    async def health_check(self) -> bool:
        """Return True if the client's backend is reachable."""
        ...

    async def cleanup(self) -> None:
        """Release any resources held by the client."""
        ...


class TransportClientRegistry:
    """Maps transport names to client instances.

    Usage::

        registry = TransportClientRegistry()
        registry.register("http", http_client)
        result = await registry.execute("http", step, context)
    """

    def __init__(self) -> None:
        self._clients: dict[str, TransportClient] = {}

    def register(self, transport: str, client: TransportClient) -> None:
        """Register a client for a transport name."""
        self._clients[transport] = client

    def get(self, transport: str) -> TransportClient | None:
        """Look up the client for *transport*, or None."""
        return self._clients.get(transport)

    async def execute(self, transport: str, step: ActionStep, context: StepContext) -> StepResult:
        """Dispatch a step to the appropriate client."""
        client = self._clients.get(transport)
        if client is None:
            return StepResult(error=f"No client registered for transport: {transport}")
        return await client.execute(step, context)

    async def health_check_all(self) -> dict[str, bool]:
        """Run health checks on every registered client."""
        results: dict[str, bool] = {}
        for name, client in self._clients.items():
            try:
                results[name] = await client.health_check()
            except Exception:
                results[name] = False
        return results

    async def cleanup_all(self) -> None:
        """Cleanup every registered client."""
        for client in self._clients.values():
            try:
                await client.cleanup()
            except Exception:
                pass

    @property
    def transports(self) -> list[str]:
        """Return registered transport names."""
        return list(self._clients.keys())
