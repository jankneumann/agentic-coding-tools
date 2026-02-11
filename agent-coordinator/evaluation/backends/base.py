"""Agent backend protocol for evaluation.

Defines the interface that all agent backends must implement
to participate in benchmarking runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..config import AblationFlags, AgentBackendConfig
from ..metrics import TokenUsage


@dataclass
class BackendResult:
    """Standardized result from an agent backend execution."""

    success: bool
    output: str = ""  # Agent's produced output (patch, code, etc.)
    wall_clock_seconds: float = 0.0
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    tests_total: int = 0
    tests_passed: int = 0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class AgentBackend(Protocol):
    """Protocol for agent backends used in evaluation.

    Each backend wraps a specific agent implementation (CLI tool)
    and provides a uniform interface for task submission and result collection.
    """

    @property
    def name(self) -> str:
        """Backend identifier (e.g. 'claude_code', 'codex', 'gemini_jules')."""
        ...

    async def execute_task(
        self,
        task_description: str,
        affected_files: list[str],
        working_dir: str,
        ablation: AblationFlags,
        timeout_seconds: int = 300,
    ) -> BackendResult:
        """Execute a coding task and return the result.

        Args:
            task_description: Natural language description of the task.
            affected_files: Files the agent should work on.
            working_dir: Directory to execute in (git repo checkout).
            ablation: Which coordination mechanisms are enabled.
            timeout_seconds: Maximum execution time.

        Returns:
            BackendResult with output, timing, and token usage.
        """
        ...

    async def health_check(self) -> bool:
        """Check if the backend is available and configured."""
        ...

    @classmethod
    def from_config(cls, config: AgentBackendConfig) -> AgentBackend:
        """Create a backend instance from configuration."""
        ...
