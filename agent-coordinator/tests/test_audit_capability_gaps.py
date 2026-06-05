"""Tests for coordinator-side audit-triage LLM classifier (Task 2.5).

Fixture-driven tests with mocked LLM responses covering:
(i)   ring-buffer push from log_operation adds zero latency (no LLM on hot path)
(ii)  background task drains buffer on cadence (mocked clock)
(iii) classifier model resolved via agents_config.resolve_model
(iv)  system prompt composed via agents_config.compose_prompt
(v)   valid schema output produces memory entries with source:coordinator-emitted + prompt_version:N
(vi)  invalid schema output is dropped with warning
(vii) archetype defaults to analyst, provider to claude_code, both overridable
"""

import logging
import time
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.audit import AuditEntry

# ---------------------------------------------------------------------------
# Fixtures: audit entries representing various agent operations
# ---------------------------------------------------------------------------

SAMPLE_AUDIT_ENTRIES: list[dict[str, Any]] = [
    {
        "id": "entry-001",
        "agent_id": "agent-alpha",
        "agent_type": "claude_code",
        "operation": "claim_task",
        "parameters": {"task_types": ["implement"]},
        "result": {"task_id": "task-123"},
        "duration_ms": 45,
        "success": True,
        "error_message": None,
        "created_at": "2026-06-05T10:00:00+00:00",
    },
    {
        "id": "entry-002",
        "agent_id": "agent-alpha",
        "agent_type": "claude_code",
        "operation": "acquire_lock",
        "parameters": {"file_path": "src/foo.py"},
        "result": {"success": False, "reason": "locked_by_other"},
        "duration_ms": 12,
        "success": False,
        "error_message": "Lock held by agent-beta",
        "created_at": "2026-06-05T10:01:00+00:00",
    },
    {
        "id": "entry-003",
        "agent_id": "agent-alpha",
        "agent_type": "claude_code",
        "operation": "acquire_lock",
        "parameters": {"file_path": "src/foo.py"},
        "result": {"success": False, "reason": "locked_by_other"},
        "duration_ms": 15,
        "success": False,
        "error_message": "Lock held by agent-beta",
        "created_at": "2026-06-05T10:02:00+00:00",
    },
]

# Valid classifier LLM output
VALID_CLASSIFIER_OUTPUT: list[dict[str, Any]] = [
    {
        "failure_type": "lock_unavailable",
        "capability_gap": "no-retry-backoff-for-lock-contention",
        "affected_skill": "implement-feature",
        "severity": "medium",
        "summary": "Agent repeatedly tried to acquire a lock without backoff",
    },
]

# Invalid classifier output (wrong schema)
INVALID_CLASSIFIER_OUTPUT: str = "This is not valid JSON schema output"


# ---------------------------------------------------------------------------
# Ring buffer tests
# ---------------------------------------------------------------------------

class TestRingBufferHotPath:
    """Ring buffer push from log_operation adds zero latency on hot path."""

    def test_ring_buffer_push_is_synchronous_and_cheap(self):
        """Pushing to the ring buffer is a microsecond-level operation."""
        from src.audit_triage import AuditTriageBuffer

        buffer = AuditTriageBuffer(max_size=1000)

        entry = AuditEntry.from_dict(SAMPLE_AUDIT_ENTRIES[0])

        t0 = time.monotonic()
        buffer.push(entry, session_id="session-001")
        elapsed_us = (time.monotonic() - t0) * 1_000_000

        # Must complete in under 1ms (1000 microseconds)
        assert elapsed_us < 1000, f"Ring buffer push took {elapsed_us:.0f}us, expected <1000us"

    def test_ring_buffer_keyed_by_agent_and_session(self):
        """Buffer entries are keyed by (agent_id, session_id)."""
        from src.audit_triage import AuditTriageBuffer

        buffer = AuditTriageBuffer(max_size=100)

        entry1 = AuditEntry.from_dict(SAMPLE_AUDIT_ENTRIES[0])
        entry2 = AuditEntry.from_dict({**SAMPLE_AUDIT_ENTRIES[0], "agent_id": "agent-beta"})

        buffer.push(entry1, session_id="session-001")
        buffer.push(entry2, session_id="session-002")

        assert len(buffer.drain_all()) == 2

    def test_ring_buffer_max_size_respected(self):
        """Buffer respects max_size limit per key."""
        from src.audit_triage import AuditTriageBuffer

        buffer = AuditTriageBuffer(max_size=2)

        for i in range(5):
            entry = AuditEntry.from_dict({
                **SAMPLE_AUDIT_ENTRIES[0],
                "id": f"entry-{i}",
            })
            buffer.push(entry, session_id="session-001")

        batches = buffer.drain_all()
        # Should have exactly 1 key
        assert len(batches) == 1
        key, entries = batches[0]
        # Max 2 entries retained
        assert len(entries) <= 2

    def test_drain_all_clears_buffer(self):
        """drain_all returns all entries and empties the buffer."""
        from src.audit_triage import AuditTriageBuffer

        buffer = AuditTriageBuffer(max_size=100)

        for entry_data in SAMPLE_AUDIT_ENTRIES:
            buffer.push(AuditEntry.from_dict(entry_data), session_id="session-001")

        batches = buffer.drain_all()
        assert len(batches) > 0

        # Second drain should be empty
        assert len(buffer.drain_all()) == 0


# ---------------------------------------------------------------------------
# Background task tests
# ---------------------------------------------------------------------------

class TestBackgroundTaskDrain:
    """Background task drains buffer on cadence."""

    @pytest.mark.asyncio
    async def test_drain_processes_buffered_entries(self):
        """The triage drain function processes buffered audit entries."""
        from src.audit_triage import AuditTriageBuffer, drain_and_classify

        buffer = AuditTriageBuffer(max_size=100)
        for entry_data in SAMPLE_AUDIT_ENTRIES:
            buffer.push(AuditEntry.from_dict(entry_data), session_id="session-001")

        # Create a mock classifier that returns valid output
        mock_classify = AsyncMock(return_value=VALID_CLASSIFIER_OUTPUT)
        mock_remember = AsyncMock()

        await drain_and_classify(
            buffer=buffer,
            classify_fn=mock_classify,
            remember_fn=mock_remember,
            prompt_version=1,
        )

        # Classifier should have been called with the batch
        assert mock_classify.called
        # Findings should produce memory entries
        assert mock_remember.called

    @pytest.mark.asyncio
    async def test_drain_on_empty_buffer_is_noop(self):
        """Draining an empty buffer does nothing."""
        from src.audit_triage import AuditTriageBuffer, drain_and_classify

        buffer = AuditTriageBuffer(max_size=100)
        mock_classify = AsyncMock(return_value=[])
        mock_remember = AsyncMock()

        await drain_and_classify(
            buffer=buffer,
            classify_fn=mock_classify,
            remember_fn=mock_remember,
            prompt_version=1,
        )

        # Should not call classifier on empty buffer
        assert not mock_classify.called
        assert not mock_remember.called


# ---------------------------------------------------------------------------
# Model resolution tests
# ---------------------------------------------------------------------------

class TestClassifierModelResolution:
    """Classifier model resolved via agents_config.resolve_model."""

    def test_resolve_model_with_analyst_archetype(self):
        """resolve_model with analyst archetype returns the expected model."""
        from src.agents_config import ArchetypeConfig, resolve_model

        analyst = ArchetypeConfig(
            name="analyst",
            model="standard",
            system_prompt="You are a codebase analyst.",
        )

        model = resolve_model(analyst, package_metadata={}, provider="claude_code")
        # standard tier for claude_code maps to "sonnet"
        assert model == "sonnet"

    def test_resolve_model_with_provider_override(self):
        """resolve_model respects provider parameter for model mapping."""
        from src.agents_config import ArchetypeConfig, resolve_model

        analyst = ArchetypeConfig(
            name="analyst",
            model="standard",
            system_prompt="You are a codebase analyst.",
        )

        model = resolve_model(analyst, package_metadata={}, provider="codex")
        assert model == "gpt-5.4"

    def test_compose_prompt_includes_archetype_base(self):
        """compose_prompt layers archetype system prompt with task prompt."""
        from src.agents_config import ArchetypeConfig, compose_prompt

        analyst = ArchetypeConfig(
            name="analyst",
            model="standard",
            system_prompt="You are a codebase analyst. Read thoroughly.",
        )

        task_prompt = "Classify the following audit entries for capability gaps."
        composed = compose_prompt(analyst, task_prompt)

        assert "You are a codebase analyst" in composed
        assert "Classify the following audit entries" in composed
        assert "---" in composed  # separator


# ---------------------------------------------------------------------------
# Valid schema output tests
# ---------------------------------------------------------------------------

class TestValidClassifierOutput:
    """Valid schema output produces memory entries with correct tags."""

    @pytest.mark.asyncio
    async def test_valid_output_produces_memory_entries(self):
        """Valid classifier output creates memory entries with source:coordinator-emitted."""
        from src.audit_triage import AuditTriageBuffer, drain_and_classify

        buffer = AuditTriageBuffer(max_size=100)
        for entry_data in SAMPLE_AUDIT_ENTRIES:
            buffer.push(AuditEntry.from_dict(entry_data), session_id="session-001")

        mock_classify = AsyncMock(return_value=VALID_CLASSIFIER_OUTPUT)

        remember_calls: list[dict[str, Any]] = []

        async def mock_remember(**kwargs: Any) -> None:
            remember_calls.append(kwargs)

        await drain_and_classify(
            buffer=buffer,
            classify_fn=mock_classify,
            remember_fn=mock_remember,
            prompt_version=1,
        )

        assert len(remember_calls) > 0
        call = remember_calls[0]
        tags = call.get("tags", [])
        assert "source:coordinator-emitted" in tags
        assert "prompt_version:1" in tags
        assert any(t.startswith("failure_type:") for t in tags)
        assert any(t.startswith("capability_gap:") for t in tags)
        assert any(t.startswith("affected_skill:") for t in tags)
        assert any(t.startswith("severity:") for t in tags)

    @pytest.mark.asyncio
    async def test_valid_output_uses_correct_event_type(self):
        """Memory entries use event_type 'capability_gap'."""
        from src.audit_triage import AuditTriageBuffer, drain_and_classify

        buffer = AuditTriageBuffer(max_size=100)
        for entry_data in SAMPLE_AUDIT_ENTRIES:
            buffer.push(AuditEntry.from_dict(entry_data), session_id="session-001")

        mock_classify = AsyncMock(return_value=VALID_CLASSIFIER_OUTPUT)

        remember_calls: list[dict[str, Any]] = []

        async def mock_remember(**kwargs: Any) -> None:
            remember_calls.append(kwargs)

        await drain_and_classify(
            buffer=buffer,
            classify_fn=mock_classify,
            remember_fn=mock_remember,
            prompt_version=1,
        )

        assert len(remember_calls) > 0
        assert remember_calls[0].get("event_type") == "capability_gap"


# ---------------------------------------------------------------------------
# Invalid schema output tests
# ---------------------------------------------------------------------------

class TestInvalidClassifierOutput:
    """Invalid schema output is dropped with warning."""

    @pytest.mark.asyncio
    async def test_invalid_output_not_written_to_memory(self, caplog):
        """Invalid classifier output is not written to memory."""
        from src.audit_triage import AuditTriageBuffer, drain_and_classify

        buffer = AuditTriageBuffer(max_size=100)
        for entry_data in SAMPLE_AUDIT_ENTRIES:
            buffer.push(AuditEntry.from_dict(entry_data), session_id="session-001")

        # Classifier returns something that's not a valid list of findings
        mock_classify = AsyncMock(return_value=None)
        mock_remember = AsyncMock()

        with caplog.at_level(logging.WARNING):
            await drain_and_classify(
                buffer=buffer,
                classify_fn=mock_classify,
                remember_fn=mock_remember,
                prompt_version=1,
            )

        # Memory should NOT have been called
        assert not mock_remember.called

    @pytest.mark.asyncio
    async def test_invalid_output_logs_warning(self, caplog):
        """Invalid classifier output produces a warning log."""
        from src.audit_triage import AuditTriageBuffer, drain_and_classify

        buffer = AuditTriageBuffer(max_size=100)
        for entry_data in SAMPLE_AUDIT_ENTRIES:
            buffer.push(AuditEntry.from_dict(entry_data), session_id="session-001")

        mock_classify = AsyncMock(return_value="not a list")
        mock_remember = AsyncMock()

        with caplog.at_level(logging.WARNING):
            await drain_and_classify(
                buffer=buffer,
                classify_fn=mock_classify,
                remember_fn=mock_remember,
                prompt_version=1,
            )

        assert any("invalid" in record.message.lower() or "drop" in record.message.lower()
                    for record in caplog.records)

    @pytest.mark.asyncio
    async def test_exception_in_classifier_does_not_crash(self, caplog):
        """An exception in the classifier is caught and logged."""
        from src.audit_triage import AuditTriageBuffer, drain_and_classify

        buffer = AuditTriageBuffer(max_size=100)
        for entry_data in SAMPLE_AUDIT_ENTRIES:
            buffer.push(AuditEntry.from_dict(entry_data), session_id="session-001")

        mock_classify = AsyncMock(side_effect=RuntimeError("LLM API error"))
        mock_remember = AsyncMock()

        with caplog.at_level(logging.WARNING):
            # Should not raise
            await drain_and_classify(
                buffer=buffer,
                classify_fn=mock_classify,
                remember_fn=mock_remember,
                prompt_version=1,
            )

        assert not mock_remember.called


# ---------------------------------------------------------------------------
# Default configuration tests
# ---------------------------------------------------------------------------

class TestTriageConfigDefaults:
    """Archetype defaults to analyst, provider to claude_code, both overridable."""

    def test_default_archetype_is_analyst(self):
        """Default archetype for audit triage is 'analyst'."""
        from src.audit_triage import AuditTriageConfig

        config = AuditTriageConfig()
        assert config.archetype == "analyst"

    def test_default_provider_is_claude_code(self):
        """Default provider for audit triage is 'claude_code'."""
        from src.audit_triage import AuditTriageConfig

        config = AuditTriageConfig()
        assert config.provider == "claude_code"

    def test_archetype_is_overridable(self):
        """Archetype can be overridden."""
        from src.audit_triage import AuditTriageConfig

        config = AuditTriageConfig(archetype="reviewer")
        assert config.archetype == "reviewer"

    def test_provider_is_overridable(self):
        """Provider can be overridden."""
        from src.audit_triage import AuditTriageConfig

        config = AuditTriageConfig(provider="codex")
        assert config.provider == "codex"

    def test_default_enabled_is_false(self):
        """Default-off in CI (enabled=False)."""
        from src.audit_triage import AuditTriageConfig

        config = AuditTriageConfig()
        assert config.enabled is False

    def test_default_batch_interval_minutes(self):
        """Default batch interval is 10 minutes."""
        from src.audit_triage import AuditTriageConfig

        config = AuditTriageConfig()
        assert config.batch_interval_minutes == 10

    def test_default_prompt_version(self):
        """Default prompt version is 1."""
        from src.audit_triage import AuditTriageConfig

        config = AuditTriageConfig()
        assert config.prompt_version == 1


class TestFindingValidation:
    """Tests for finding schema validation."""

    def test_valid_finding_accepted(self):
        """A finding with all required fields is accepted."""
        from src.audit_triage import validate_finding

        finding = VALID_CLASSIFIER_OUTPUT[0]
        assert validate_finding(finding) is True

    def test_finding_missing_failure_type_rejected(self):
        """A finding missing failure_type is rejected."""
        from src.audit_triage import validate_finding

        finding = {k: v for k, v in VALID_CLASSIFIER_OUTPUT[0].items() if k != "failure_type"}
        assert validate_finding(finding) is False

    def test_finding_missing_capability_gap_rejected(self):
        """A finding missing capability_gap is rejected."""
        from src.audit_triage import validate_finding

        finding = {k: v for k, v in VALID_CLASSIFIER_OUTPUT[0].items() if k != "capability_gap"}
        assert validate_finding(finding) is False

    def test_non_dict_finding_rejected(self):
        """A non-dict value is rejected."""
        from src.audit_triage import validate_finding

        assert validate_finding("not a dict") is False
        assert validate_finding(42) is False
        assert validate_finding(None) is False
