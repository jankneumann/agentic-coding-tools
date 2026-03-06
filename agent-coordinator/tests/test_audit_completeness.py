"""Audit completeness tests (Task 4.6).

Verifies that every mutation operation emits immutable audit records:
- Lock acquire/release
- Work queue claim/complete/submit
- Policy decisions (allow and deny)
- Guardrail violations

Tests both success and failure paths to ensure comprehensive coverage.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.audit import AuditResult, AuditService
from src.locks import LockService
from src.policy_engine import NativePolicyEngine, PolicyDecision
from src.work_queue import WorkQueueService

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def audit_tracker():
    """AuditService that tracks all log_operation calls."""
    service = AsyncMock(spec=AuditService)
    service.log_operation = AsyncMock(return_value=AuditResult(success=True, entry_id="test-entry"))
    return service


@pytest.fixture
def success_db():
    """Database that returns successful responses."""
    db = AsyncMock()
    db.rpc = AsyncMock(return_value={
        "success": True,
        "action": "acquired",
        "file_path": "src/main.py",
        "expires_at": "2026-12-31T00:00:00Z",
    })
    db.insert = AsyncMock(return_value={"id": str(uuid4())})
    db.query = AsyncMock(return_value=[])
    return db


@pytest.fixture
def allow_policy():
    engine = AsyncMock(spec=NativePolicyEngine)
    engine.check_operation = AsyncMock(
        return_value=PolicyDecision.allow("test_allow")
    )
    return engine


@pytest.fixture
def deny_policy():
    engine = AsyncMock(spec=NativePolicyEngine)
    engine.check_operation = AsyncMock(
        return_value=PolicyDecision.deny("test_deny")
    )
    return engine


# =============================================================================
# Lock Operations: Audit Completeness
# =============================================================================


class TestLockAuditCompleteness:
    """Every lock mutation must produce an audit record."""

    @pytest.mark.asyncio
    async def test_successful_acquire_audited(self, success_db, audit_tracker, allow_policy):
        """Successful lock acquire emits audit record."""
        service = LockService(db=success_db)

        with (
            patch("src.policy_engine.get_policy_engine", return_value=allow_policy),
            patch("src.locks.get_audit_service", return_value=audit_tracker),
        ):
            result = await service.acquire(file_path="src/main.py", reason="test")

        assert result.success is True
        audit_tracker.log_operation.assert_called()

        # Verify audit call includes correct operation
        audit_call = audit_tracker.log_operation.call_args
        assert audit_call.kwargs.get("operation") == "acquire_lock"

    @pytest.mark.asyncio
    async def test_successful_release_audited(self, audit_tracker, allow_policy):
        """Successful lock release emits audit record."""
        db = AsyncMock()
        db.rpc = AsyncMock(return_value={
            "success": True,
            "action": "released",
            "file_path": "src/main.py",
        })

        service = LockService(db=db)

        with (
            patch("src.policy_engine.get_policy_engine", return_value=allow_policy),
            patch("src.locks.get_audit_service", return_value=audit_tracker),
        ):
            result = await service.release(file_path="src/main.py")

        assert result.success is True
        audit_tracker.log_operation.assert_called()

    @pytest.mark.asyncio
    async def test_failed_acquire_audited(self, audit_tracker, allow_policy):
        """Failed lock acquire (conflict) still emits audit record."""
        db = AsyncMock()
        db.rpc = AsyncMock(return_value={
            "success": False,
            "reason": "locked_by_other",
            "locked_by": "other-agent",
        })

        service = LockService(db=db)

        with (
            patch("src.policy_engine.get_policy_engine", return_value=allow_policy),
            patch("src.locks.get_audit_service", return_value=audit_tracker),
        ):
            result = await service.acquire(file_path="src/main.py")

        assert result.success is False
        audit_tracker.log_operation.assert_called()


# =============================================================================
# Work Queue Operations: Audit Completeness
# =============================================================================


class TestWorkQueueAuditCompleteness:
    """Every work queue mutation must produce an audit record."""

    @pytest.mark.asyncio
    async def test_successful_claim_audited(self, audit_tracker, allow_policy):
        """Successful task claim emits audit record."""
        db = AsyncMock()
        db.rpc = AsyncMock(return_value={
            "success": True,
            "task_id": str(uuid4()),
            "task_type": "test",
            "description": "safe task description",
            "input_data": None,
            "priority": 5,
            "deadline": None,
        })
        db.query = AsyncMock(return_value=[])
        db.insert = AsyncMock(return_value={})

        service = WorkQueueService(db=db)

        with (
            patch("src.policy_engine.get_policy_engine", return_value=allow_policy),
            patch("src.work_queue.get_audit_service", return_value=audit_tracker),
        ):
            result = await service.claim()

        assert result.success is True
        audit_tracker.log_operation.assert_called()

        # Verify the audit includes task_id in result
        audit_calls = audit_tracker.log_operation.call_args_list
        claim_audit = [c for c in audit_calls if c.kwargs.get("operation") == "claim_task"]
        assert len(claim_audit) >= 1

    @pytest.mark.asyncio
    async def test_successful_complete_audited(self, audit_tracker, allow_policy):
        """Successful task completion emits audit record."""
        task_id = uuid4()
        db = AsyncMock()
        db.rpc = AsyncMock(return_value={
            "success": True,
            "status": "completed",
            "task_id": str(task_id),
        })
        db.query = AsyncMock(return_value=[])
        db.insert = AsyncMock(return_value={})

        service = WorkQueueService(db=db)

        with (
            patch("src.policy_engine.get_policy_engine", return_value=allow_policy),
            patch("src.work_queue.get_audit_service", return_value=audit_tracker),
        ):
            result = await service.complete(task_id=task_id, success=True)

        assert result.success is True
        audit_tracker.log_operation.assert_called()

    @pytest.mark.asyncio
    async def test_successful_submit_audited(self, audit_tracker, allow_policy):
        """Successful task submission emits audit record."""
        db = AsyncMock()
        db.rpc = AsyncMock(return_value={
            "success": True,
            "task_id": str(uuid4()),
        })
        db.query = AsyncMock(return_value=[])
        db.insert = AsyncMock(return_value={})

        service = WorkQueueService(db=db)

        with (
            patch("src.policy_engine.get_policy_engine", return_value=allow_policy),
            patch("src.work_queue.get_audit_service", return_value=audit_tracker),
        ):
            result = await service.submit(
                task_type="test",
                description="safe task",
            )

        assert result.success is True
        audit_tracker.log_operation.assert_called()

    @pytest.mark.asyncio
    async def test_no_tasks_claim_audited(self, audit_tracker, allow_policy):
        """Claim with no available tasks still emits audit record."""
        db = AsyncMock()
        db.rpc = AsyncMock(return_value={
            "success": False,
            "reason": "no_tasks_available",
        })
        db.query = AsyncMock(return_value=[])

        service = WorkQueueService(db=db)

        with (
            patch("src.policy_engine.get_policy_engine", return_value=allow_policy),
            patch("src.work_queue.get_audit_service", return_value=audit_tracker),
        ):
            result = await service.claim()

        assert result.success is False
        audit_tracker.log_operation.assert_called()


# =============================================================================
# Policy Decision Audit Completeness
# =============================================================================


class TestPolicyDecisionAudit:
    """Policy decisions (allow/deny) must be logged to audit trail.

    NativePolicyEngine._log_policy_decision does a local import of
    get_audit_service, so we patch src.audit.get_audit_service.
    """

    @pytest.mark.asyncio
    async def test_allow_decision_logged(self, mock_supabase, db_client, audit_tracker):
        """Allow decisions generate policy_decision audit entry."""
        engine = NativePolicyEngine(db=db_client)

        with patch("src.audit.get_audit_service", return_value=audit_tracker):
            decision = await engine.check_operation(
                agent_id="test-agent",
                agent_type="test_agent",
                operation="check_locks",
                context={"trust_level": 2},
            )

        assert decision.allowed is True
        audit_tracker.log_operation.assert_called()
        audit_call = audit_tracker.log_operation.call_args
        assert audit_call.kwargs.get("operation") == "policy_decision"
        assert audit_call.kwargs["result"]["allowed"] is True

    @pytest.mark.asyncio
    async def test_deny_decision_logged(self, mock_supabase, db_client, audit_tracker):
        """Deny decisions generate policy_decision audit entry."""
        engine = NativePolicyEngine(db=db_client)

        with patch("src.audit.get_audit_service", return_value=audit_tracker):
            decision = await engine.check_operation(
                agent_id="test-agent",
                agent_type="test_agent",
                operation="acquire_lock",
                context={"trust_level": 1},
            )

        assert decision.allowed is False
        audit_tracker.log_operation.assert_called()
        audit_call = audit_tracker.log_operation.call_args
        assert audit_call.kwargs.get("operation") == "policy_decision"
        assert audit_call.kwargs["result"]["allowed"] is False

    @pytest.mark.asyncio
    async def test_suspended_agent_denial_logged(self, mock_supabase, db_client, audit_tracker):
        """Suspended agent denial generates audit entry with reason."""
        engine = NativePolicyEngine(db=db_client)

        with patch("src.audit.get_audit_service", return_value=audit_tracker):
            decision = await engine.check_operation(
                agent_id="suspended-agent",
                agent_type="test_agent",
                operation="acquire_lock",
                context={"trust_level": 0},
            )

        assert decision.allowed is False
        audit_tracker.log_operation.assert_called()
        audit_call = audit_tracker.log_operation.call_args
        assert "suspended" in audit_call.kwargs["result"]["reason"]

    @pytest.mark.asyncio
    async def test_policy_decision_includes_engine_metadata(
        self, mock_supabase, db_client, audit_tracker
    ):
        """Policy audit entry includes engine name in parameters."""
        engine = NativePolicyEngine(db=db_client)

        with patch("src.audit.get_audit_service", return_value=audit_tracker):
            await engine.check_operation(
                agent_id="test-agent",
                agent_type="test_agent",
                operation="check_locks",
                context={"trust_level": 2},
            )

        audit_call = audit_tracker.log_operation.call_args
        assert audit_call.kwargs["parameters"]["engine"] == "native"


# =============================================================================
# Guardrail Violation Audit Completeness
# =============================================================================


class TestGuardrailViolationAudit:
    """Guardrail violations must be logged to both audit trail and violations table."""

    @pytest.mark.asyncio
    async def test_guardrail_violation_audited(self, audit_tracker):
        """Detected guardrail violation emits audit record."""
        from src.guardrails import GuardrailsService

        db = AsyncMock()
        db.query = AsyncMock(side_effect=Exception("DB unavailable"))  # Trigger fallback patterns
        db.insert = AsyncMock(return_value={})

        service = GuardrailsService(db=db)

        with patch("src.guardrails.get_audit_service", return_value=audit_tracker):
            result = await service.check_operation(
                operation_text="git push --force origin main",
                trust_level=1,
                agent_id="test-agent",
                agent_type="test_agent",
            )

        assert result.safe is False
        assert len(result.violations) > 0
        audit_tracker.log_operation.assert_called()

    @pytest.mark.asyncio
    async def test_guardrail_violation_persisted_to_violations_table(self):
        """Violations are written to guardrail_violations table."""
        from src.guardrails import GuardrailsService

        db = AsyncMock()
        db.query = AsyncMock(side_effect=Exception("DB unavailable"))  # Trigger fallback patterns
        db.insert = AsyncMock(return_value={})

        service = GuardrailsService(db=db)

        audit_mock = AsyncMock()
        audit_mock.log_operation = AsyncMock(return_value=AuditResult(success=True))

        with patch("src.guardrails.get_audit_service", return_value=audit_mock):
            result = await service.check_operation(
                operation_text="rm -rf /important",
                trust_level=1,
                agent_id="test-agent",
                agent_type="test_agent",
            )

        assert result.safe is False
        # Verify insert was called for guardrail_violations
        insert_calls = [
            c for c in db.insert.call_args_list
            if c.args[0] == "guardrail_violations"
        ]
        assert len(insert_calls) >= 1, "Violation should be persisted to guardrail_violations table"

        # Verify the violation data structure
        violation_data = insert_calls[0].args[1]
        assert "pattern_name" in violation_data
        assert "agent_id" in violation_data
        assert "matched_text" in violation_data
        assert "blocked" in violation_data

    @pytest.mark.asyncio
    async def test_safe_operation_no_violation_audit(self, audit_tracker):
        """Safe operations don't emit guardrail violation audit entries."""
        from src.guardrails import GuardrailsService

        db = AsyncMock()
        db.query = AsyncMock(side_effect=Exception("DB unavailable"))  # Trigger fallback patterns

        service = GuardrailsService(db=db)

        with patch("src.guardrails.get_audit_service", return_value=audit_tracker):
            result = await service.check_operation(
                operation_text="echo hello world",
                trust_level=2,
                agent_id="test-agent",
            )

        assert result.safe is True
        # No violations means no audit call for guardrail_violation
        audit_tracker.log_operation.assert_not_called()


# =============================================================================
# Cross-Cutting: Mutation Surface Coverage
# =============================================================================


class TestMutationSurfaceCoverage:
    """Verify that every documented mutation operation has audit coverage."""

    MUTATION_SURFACE = {
        "acquire_lock": "locks.py",
        "release_lock": "locks.py",
        "claim_task": "work_queue.py",
        "complete_task": "work_queue.py",
        "submit_task": "work_queue.py",
    }

    @pytest.mark.asyncio
    async def test_all_mutation_operations_have_audit(self):
        """Verify all mutation operations in the surface inventory have audit calls."""
        from pathlib import Path

        src_dir = Path(__file__).parent.parent / "src"

        for operation, filename in self.MUTATION_SURFACE.items():
            filepath = src_dir / filename
            source = filepath.read_text()

            assert "get_audit_service" in source, (
                f"{filename} should import get_audit_service for {operation}"
            )
            assert "log_operation" in source, (
                f"{filename} should call log_operation for {operation}"
            )

    def test_policy_engine_logs_decisions(self):
        """Verify policy_engine.py logs all decisions."""
        from pathlib import Path

        source = (Path(__file__).parent.parent / "src" / "policy_engine.py").read_text()

        assert "_log_policy_decision" in source
        assert "get_audit_service" in source

    def test_guardrails_logs_violations(self):
        """Verify guardrails.py logs violations to both audit and violations table."""
        from pathlib import Path

        source = (Path(__file__).parent.parent / "src" / "guardrails.py").read_text()

        assert "get_audit_service" in source
        assert "guardrail_violations" in source
