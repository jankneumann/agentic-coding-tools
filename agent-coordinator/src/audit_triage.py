"""Coordinator-side audit-triage LLM classifier.

Classifies capability-gap signals from audit log batches using an LLM.
The hot path (``AuditService.log_operation``) pushes entries into an
in-memory ring buffer with zero LLM involvement.  A background task
drains the buffer on a configurable cadence and invokes the classifier.

Design reference: D9 in openspec/changes/harness-engineering-features/design.md
"""

from __future__ import annotations

import json
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from .audit import AuditEntry

logger = logging.getLogger(__name__)

# Per system_one_decisions.testing's documented stubbing rule: import the
# module, never a pre-bound name, so a monkeypatched `decide` attribute is
# what this code actually calls.
system_one_decisions: ModuleType | None
try:
    import system_one_decisions
except ImportError:
    system_one_decisions = None

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

# Ordered lowest-to-highest, for the stage-one Score(severity, [...]) question.
_SEVERITY_LEVELS = ("low", "medium", "high", "critical")

DEFAULT_CAPABILITY_GAP_RECALL_FLOOR = 0.3
_AUDIT_TRIAGE_JUDGMENT_CONFIG_PATH = (
    Path(__file__).parent / "audit-triage-judgment.json"
)


def load_capability_gap_recall_floor(config_path: Path | None = None) -> float:
    """Read the optional sidecar JSON, falling back to the module default.

    Mirrors the threshold-loading precedent used across this roadmap's
    other judged call sites: a malformed or missing sidecar degrades to
    the default rather than raising. Deliberately low (0.3, not 0.5): the
    prompt's own guideline is "prefer recall over precision", so the floor
    is a recall-oriented screen, not a symmetric confidence gate.
    """
    path = config_path or _AUDIT_TRIAGE_JUDGMENT_CONFIG_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_CAPABILITY_GAP_RECALL_FLOOR
    if not isinstance(raw, dict):
        return DEFAULT_CAPABILITY_GAP_RECALL_FLOOR
    try:
        return float(raw.get("recall_floor", DEFAULT_CAPABILITY_GAP_RECALL_FLOOR))
    except (TypeError, ValueError):
        return DEFAULT_CAPABILITY_GAP_RECALL_FLOOR


def _answer_field(answer: Any, name: str, default: Any = None) -> Any:
    """Read a field off a real SDK answer object or a plain dict/mapping."""
    if isinstance(answer, dict):
        return answer.get(name, default)
    return getattr(answer, name, default)


def screen_session(
    serialized_entries: list[dict[str, Any]],
    dry_run: bool = False,
) -> dict[str, Any] | None:
    """Ask one calibrated judgment for whether this session's audit batch
    shows a capability gap, plus a suggested failure_type/severity.

    Returns `None` on any unavailability (module missing, `decide()`
    returns no usable answer) -- never raises. Callers fall back to
    invoking the existing classifier unconditionally, exactly as
    `drain_and_classify` behaved before this screen existed.
    """
    if system_one_decisions is None:
        return None

    state: dict[str, Any] = {"entries": serialized_entries}
    questions = {
        "capability_gap": {
            "type": "noul",
            "instructions": "This session shows a capability gap in the harness.",
            "criteria": {
                "true": (
                    "The audit entries show the agent struggling, failing, "
                    "or working around a missing harness capability."
                ),
                "false": (
                    "The audit entries show ordinary, successful operation "
                    "with no sign of a capability gap."
                ),
            },
        },
        "failure_type": {
            "type": "choice",
            "instructions": (
                "Which failure type best matches this session's audit "
                "entries, if any?"
            ),
            "criteria": {ft: None for ft in sorted(_VALID_FAILURE_TYPES)} | {
                "none": "No capability-gap failure type applies.",
            },
        },
        "severity": {
            "type": "score",
            "instructions": (
                "If this session shows a capability gap, how severe is it, "
                "from lowest to highest?"
            ),
            "criteria": list(_SEVERITY_LEVELS),
        },
    }

    answers = system_one_decisions.decide(
        state, questions, site="agent-coordinator.audit_triage",
        dry_run=dry_run,
    )
    if not answers:
        return None

    gap_answer = answers.get("capability_gap") if hasattr(answers, "get") else None
    if gap_answer is None:
        return None
    noul = _answer_field(gap_answer, "noul")
    if not isinstance(noul, (int, float)):
        return None

    failure_type_answer = answers.get("failure_type") if hasattr(answers, "get") else None
    failure_type = _answer_field(failure_type_answer, "choice") if failure_type_answer is not None else None
    if failure_type not in _VALID_FAILURE_TYPES:
        failure_type = None

    severity_answer = answers.get("severity") if hasattr(answers, "get") else None
    severity_score = _answer_field(severity_answer, "score") if severity_answer is not None else None
    severity = None
    if isinstance(severity_score, (int, float)):
        index = round(severity_score)
        if 0 <= index < len(_SEVERITY_LEVELS):
            severity = _SEVERITY_LEVELS[index]

    return {
        "capability_gap_probability": noul,
        "failure_type": failure_type,
        "severity": severity,
    }


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
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Drain the buffer and classify findings.

    This is the core triage loop called by the background task on each
    cadence tick.

    A judged first stage screens each session batch (`screen_session`)
    before the existing classifier runs: a batch whose capability-gap
    probability is below the configured recall floor never reaches
    `classify_fn` (zero LLM calls for ordinary sessions). A batch that
    clears the floor still runs the existing classifier unchanged, seeded
    with the stage-one failure_type/severity via `stage_one_hint` so its
    own findings can be backfilled with those labels when it omits them.
    When the screen is unavailable, every batch reaches `classify_fn`
    exactly as `drain_and_classify` behaved before this screen existed.

    Args:
        buffer: The ring buffer to drain.
        classify_fn: Async callable that receives a list of serialized
            audit entries and returns a list of finding dicts (or invalid
            output that will be dropped). Also receives a keyword-only
            `stage_one_hint` (a `{"failure_type", "severity"}` dict, or
            `None`) -- existing callers that ignore extra kwargs are
            unaffected.
        remember_fn: Async callable to write a memory entry.  Called with
            keyword arguments matching ``MemoryService.remember``.
        prompt_version: Version tag to attach to emitted findings.
        dry_run: Threaded into the stage-one screen's `decide()` call
            unchanged -- see `system_one_decisions.decide`'s contract.

    Returns:
        List of valid findings that were written to memory.
    """
    batches = buffer.drain_all()
    if not batches:
        return []

    all_findings: list[dict[str, Any]] = []
    floor = load_capability_gap_recall_floor()

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

        screen = screen_session(serialized, dry_run=dry_run)
        stage_one_hint: dict[str, Any] | None = None
        if screen is not None:
            if screen["capability_gap_probability"] < floor:
                # Screened out -- the recall-oriented floor means this
                # batch never reaches the existing classifier.
                continue
            stage_one_hint = {
                "failure_type": screen["failure_type"],
                "severity": screen["severity"],
            }

        try:
            raw_output = await classify_fn(serialized, stage_one_hint=stage_one_hint)
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
            if (
                stage_one_hint is not None
                and isinstance(finding, dict)
                and "failure_type" not in finding
                and stage_one_hint.get("failure_type") is not None
            ):
                finding["failure_type"] = stage_one_hint["failure_type"]
            if (
                stage_one_hint is not None
                and isinstance(finding, dict)
                and "severity" not in finding
                and stage_one_hint.get("severity") is not None
            ):
                finding["severity"] = stage_one_hint["severity"]

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
