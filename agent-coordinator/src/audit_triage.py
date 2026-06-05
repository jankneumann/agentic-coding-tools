"""Coordinator-side audit-triage LLM classifier.

Classifies capability-gap signals from audit log batches using an LLM.
The hot path (``AuditService.log_operation``) pushes entries into an
in-memory ring buffer with zero LLM involvement.  A background task
drains the buffer on a configurable cadence and invokes the classifier.

Design reference: D9 in openspec/changes/harness-engineering-features/design.md
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .audit import AuditEntry

logger = logging.getLogger(__name__)

# Required fields in a valid finding from the classifier
_REQUIRED_FINDING_FIELDS = frozenset({
    "failure_type",
    "capability_gap",
    "affected_skill",
    "severity",
})

# Valid failure_type values
_VALID_FAILURE_TYPES = frozenset({
    "scope_violation",
    "verification_failed",
    "lock_unavailable",
    "timeout",
    "convergence_failed",
    "context_exhaustion",
})

# Valid severity values
_VALID_SEVERITIES = frozenset({
    "low",
    "medium",
    "high",
    "critical",
})


@dataclass
class AuditTriageConfig:
    """Configuration for the audit-triage classifier.

    All settings correspond to ``config.yaml: audit.capability_gap_triage.*``.
    Default-off (``enabled=False``) for CI safety.
    """

    enabled: bool = False
    archetype: str = "analyst"
    provider: str = "claude_code"
    batch_size: int = 50
    batch_interval_minutes: int = 10
    prompt_version: int = 1


class AuditTriageBuffer:
    """Thread-safe in-memory ring buffer for audit entries.

    Keyed by ``(agent_id, session_id)`` so the classifier receives
    contextual windows per agent session.  The ``push`` method is the
    only thing called on the hot path and must be microsecond-fast.
    """

    def __init__(self, max_size: int = 200) -> None:
        self._max_size = max_size
        self._buffers: dict[tuple[str, str], deque[AuditEntry]] = {}

    def push(self, entry: AuditEntry, session_id: str | None = None) -> None:
        """Push an audit entry into the buffer.

        Args:
            entry: The audit entry to buffer.
            session_id: Session ID for keying.  Falls back to ``"unknown"``.
        """
        key = (entry.agent_id, session_id or "unknown")
        if key not in self._buffers:
            self._buffers[key] = deque(maxlen=self._max_size)
        self._buffers[key].append(entry)

    def drain_all(self) -> list[tuple[tuple[str, str], list[AuditEntry]]]:
        """Drain all buffered entries, returning them grouped by key.

        Returns:
            List of ``((agent_id, session_id), entries)`` tuples.
            The internal buffer is emptied after this call.
        """
        result: list[tuple[tuple[str, str], list[AuditEntry]]] = []
        for key, buf in self._buffers.items():
            if buf:
                result.append((key, list(buf)))
        self._buffers.clear()
        return result


def validate_finding(finding: Any) -> bool:
    """Validate a single classifier finding against the required schema.

    Args:
        finding: The finding dict to validate.

    Returns:
        True if the finding has all required fields with valid values.
    """
    if not isinstance(finding, dict):
        return False
    for field_name in _REQUIRED_FINDING_FIELDS:
        if field_name not in finding:
            return False
    return True


def load_prompt(version: int = 1) -> str:
    """Load the classifier task prompt from the versioned prompt file.

    Args:
        version: Prompt version number (maps to v{N}.md).

    Returns:
        The prompt text.

    Raises:
        FileNotFoundError: If the prompt file does not exist.
    """
    prompt_dir = Path(__file__).parent / "audit_triage_prompts"
    prompt_path = prompt_dir / f"v{version}.md"
    return prompt_path.read_text(encoding="utf-8")


async def drain_and_classify(
    *,
    buffer: AuditTriageBuffer,
    classify_fn: Callable[..., Awaitable[Any]],
    remember_fn: Callable[..., Awaitable[Any]],
    prompt_version: int = 1,
) -> list[dict[str, Any]]:
    """Drain the buffer and classify findings.

    This is the core triage loop called by the background task on each
    cadence tick.

    Args:
        buffer: The ring buffer to drain.
        classify_fn: Async callable that receives a list of serialized
            audit entries and returns a list of finding dicts (or invalid
            output that will be dropped).
        remember_fn: Async callable to write a memory entry.  Called with
            keyword arguments matching ``MemoryService.remember``.
        prompt_version: Version tag to attach to emitted findings.

    Returns:
        List of valid findings that were written to memory.
    """
    batches = buffer.drain_all()
    if not batches:
        return []

    all_findings: list[dict[str, Any]] = []

    for (agent_id, session_id), entries in batches:
        # Serialize entries for the classifier
        serialized = [
            {
                "operation": e.operation,
                "parameters": e.parameters,
                "result": e.result,
                "success": e.success,
                "error_message": e.error_message,
                "duration_ms": e.duration_ms,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ]

        try:
            raw_output = await classify_fn(serialized)
        except Exception:
            logger.warning(
                "Audit triage classifier failed for agent=%s session=%s",
                agent_id,
                session_id,
                exc_info=True,
            )
            continue

        # Validate output is a list of finding dicts
        if not isinstance(raw_output, list):
            logger.warning(
                "Audit triage classifier returned invalid output (not a list) "
                "for agent=%s session=%s — dropping",
                agent_id,
                session_id,
            )
            continue

        for finding in raw_output:
            if not validate_finding(finding):
                logger.warning(
                    "Dropping invalid finding from audit triage classifier: %s",
                    finding,
                )
                continue

            # Build tags following D4 tag schema
            tags = [
                f"failure_type:{finding['failure_type']}",
                f"capability_gap:{finding['capability_gap']}",
                f"affected_skill:{finding['affected_skill']}",
                f"severity:{finding['severity']}",
                "source:coordinator-emitted",
                f"prompt_version:{prompt_version}",
            ]

            try:
                await remember_fn(
                    event_type="capability_gap",
                    summary=finding.get("summary", finding["capability_gap"]),
                    details={
                        "failure_type": finding["failure_type"],
                        "capability_gap": finding["capability_gap"],
                        "affected_skill": finding["affected_skill"],
                        "severity": finding["severity"],
                        "agent_id": agent_id,
                        "session_id": session_id,
                        "prompt_version": prompt_version,
                    },
                    outcome="negative",
                    tags=tags,
                    agent_id=agent_id,
                    session_id=session_id,
                )
                all_findings.append(finding)
            except Exception:
                logger.warning(
                    "Failed to write audit triage finding to memory",
                    exc_info=True,
                )

    return all_findings


# ---------------------------------------------------------------------------
# Global buffer instance
# ---------------------------------------------------------------------------

_triage_buffer: AuditTriageBuffer | None = None


def get_triage_buffer() -> AuditTriageBuffer:
    """Get the global audit triage buffer instance."""
    global _triage_buffer
    if _triage_buffer is None:
        _triage_buffer = AuditTriageBuffer()
    return _triage_buffer


def reset_triage_buffer() -> None:
    """Reset the global buffer (for testing)."""
    global _triage_buffer
    _triage_buffer = None
