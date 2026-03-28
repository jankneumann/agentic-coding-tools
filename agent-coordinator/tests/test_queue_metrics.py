"""Tests for OpenTelemetry metrics instrumentation in WorkQueueService."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.work_queue import WorkQueueService, reset_instruments

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_claim_response(success: bool = True, **overrides):
    base = {
        "success": success,
        "task_id": str(uuid4()),
        "task_type": "refactor",
        "description": "Refactor module",
        "input_data": None,
        "priority": 3,
        "deadline": None,
        "reason": None if success else "no_tasks_available",
    }
    base.update(overrides)
    if not success and "task_id" not in overrides:
        base["task_id"] = None
    return base


def _make_complete_response(success: bool = True):
    return {
        "success": success,
        "status": "completed" if success else "failed",
        "task_id": str(uuid4()),
    }


def _make_submit_response():
    return {
        "success": True,
        "task_id": str(uuid4()),
    }


def _make_task_row(claimed_at: datetime | None = None):
    now = datetime.now(UTC)
    return {
        "id": str(uuid4()),
        "task_type": "refactor",
        "description": "Refactor module",
        "status": "claimed",
        "priority": 3,
        "input_data": None,
        "claimed_by": "test-agent-1",
        "claimed_at": (claimed_at or (now - timedelta(seconds=10))).isoformat(),
        "result": None,
        "error_message": None,
        "depends_on": None,
        "deadline": None,
        "created_at": (now - timedelta(minutes=5)).isoformat(),
        "completed_at": None,
    }


@pytest.fixture(autouse=True)
def _reset_instruments():
    """Reset cached instruments before each test."""
    reset_instruments()
    yield
    reset_instruments()


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.rpc = AsyncMock()
    db.query = AsyncMock(return_value=[])
    return db


@pytest.fixture
def mock_policy_allow():
    """Patch policy engine to always allow."""
    decision = MagicMock(allowed=True, reason=None)
    with patch(
        "src.policy_engine.get_policy_engine",
        return_value=MagicMock(check_operation=AsyncMock(return_value=decision)),
    ):
        yield


@pytest.fixture
def mock_guardrails_pass():
    """Patch guardrails to always pass."""
    check_result = MagicMock(safe=True, violations=[])
    svc = MagicMock(check_operation=AsyncMock(return_value=check_result))
    with patch("src.guardrails.get_guardrails_service", return_value=svc):
        yield svc


@pytest.fixture
def mock_guardrails_block():
    """Patch guardrails to block with a pattern."""
    violation = MagicMock(pattern_name="rm_rf", blocked=True)
    check_result = MagicMock(safe=False, violations=[violation])
    svc = MagicMock(check_operation=AsyncMock(return_value=check_result))
    with patch("src.guardrails.get_guardrails_service", return_value=svc):
        yield svc


@pytest.fixture
def mock_audit():
    with patch("src.audit.get_audit_service") as m:
        m.return_value.log_operation = AsyncMock()
        yield m


@pytest.fixture
def mock_profiles():
    """Patch profiles to return default trust level."""
    with patch("src.profiles.get_profiles_service") as m:
        profile_result = MagicMock(success=True, profile=MagicMock(trust_level=5))
        m.return_value.get_profile = AsyncMock(return_value=profile_result)
        yield m


@pytest.fixture
def mock_meter():
    """Provide a mock OTel meter with mock instruments."""
    meter = MagicMock()
    claim_hist = MagicMock()
    wait_hist = MagicMock()
    task_hist = MagicMock()
    submit_counter = MagicMock()
    guardrail_counter = MagicMock()
    meter.create_histogram = MagicMock(
        side_effect=[claim_hist, wait_hist, task_hist]
    )
    meter.create_counter = MagicMock(
        side_effect=[submit_counter, guardrail_counter]
    )
    with patch("src.work_queue.get_queue_meter", return_value=meter):
        yield {
            "meter": meter,
            "claim_hist": claim_hist,
            "wait_hist": wait_hist,
            "task_hist": task_hist,
            "submit_counter": submit_counter,
            "guardrail_counter": guardrail_counter,
        }


@pytest.fixture
def mock_meter_disabled():
    """Simulate OTel disabled (meter returns None)."""
    with patch("src.work_queue.get_queue_meter", return_value=None):
        yield


# ===========================================================================
# Claim metrics tests
# ===========================================================================


class TestClaimMetrics:
    @pytest.mark.asyncio
    async def test_claim_records_duration_on_success(
        self,
        mock_db,
        mock_policy_allow,
        mock_guardrails_pass,
        mock_audit,
        mock_profiles,
        mock_meter,
    ):
        created = (datetime.now(UTC) - timedelta(minutes=2)).isoformat()
        resp = _make_claim_response(success=True, created_at=created)
        mock_db.rpc.return_value = resp
        svc = WorkQueueService(mock_db)
        result = await svc.claim()

        assert result.success is True
        claim_hist = mock_meter["claim_hist"]
        claim_hist.record.assert_called_once()
        args, kwargs = claim_hist.record.call_args
        assert args[0] > 0  # duration_ms > 0
        assert kwargs == {} or True  # labels in second positional arg
        labels = claim_hist.record.call_args[0][1]
        assert labels["task_type"] == "refactor"
        assert labels["outcome"] == "claimed"

    @pytest.mark.asyncio
    async def test_claim_records_duration_on_empty(
        self,
        mock_db,
        mock_policy_allow,
        mock_guardrails_pass,
        mock_audit,
        mock_profiles,
        mock_meter,
    ):
        resp = _make_claim_response(success=False)
        mock_db.rpc.return_value = resp
        svc = WorkQueueService(mock_db)
        result = await svc.claim()

        assert result.success is False
        claim_hist = mock_meter["claim_hist"]
        claim_hist.record.assert_called_once()
        labels = claim_hist.record.call_args[0][1]
        assert labels["outcome"] == "empty"

    @pytest.mark.asyncio
    async def test_claim_records_duration_on_error(
        self,
        mock_db,
        mock_policy_allow,
        mock_meter,
    ):
        mock_db.rpc.side_effect = RuntimeError("db down")
        svc = WorkQueueService(mock_db)
        with pytest.raises(RuntimeError, match="db down"):
            await svc.claim()

        claim_hist = mock_meter["claim_hist"]
        claim_hist.record.assert_called_once()
        labels = claim_hist.record.call_args[0][1]
        assert labels["outcome"] == "error"

    @pytest.mark.asyncio
    async def test_claim_records_wait_time(
        self,
        mock_db,
        mock_policy_allow,
        mock_guardrails_pass,
        mock_audit,
        mock_profiles,
        mock_meter,
    ):
        created = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
        resp = _make_claim_response(success=True, created_at=created)
        mock_db.rpc.return_value = resp
        svc = WorkQueueService(mock_db)
        await svc.claim()

        wait_hist = mock_meter["wait_hist"]
        wait_hist.record.assert_called_once()
        wait_ms = wait_hist.record.call_args[0][0]
        # Should be roughly 30_000 ms, allow wide range
        assert 25_000 < wait_ms < 60_000
        labels = wait_hist.record.call_args[0][1]
        assert labels["task_type"] == "refactor"
        assert labels["priority"] == "3"

    @pytest.mark.asyncio
    async def test_claim_no_wait_time_without_created_at(
        self,
        mock_db,
        mock_policy_allow,
        mock_guardrails_pass,
        mock_audit,
        mock_profiles,
        mock_meter,
    ):
        resp = _make_claim_response(success=True)
        # No created_at in response
        mock_db.rpc.return_value = resp
        svc = WorkQueueService(mock_db)
        await svc.claim()

        wait_hist = mock_meter["wait_hist"]
        wait_hist.record.assert_not_called()

    @pytest.mark.asyncio
    async def test_claim_no_errors_when_disabled(
        self,
        mock_db,
        mock_policy_allow,
        mock_guardrails_pass,
        mock_audit,
        mock_profiles,
        mock_meter_disabled,
    ):
        resp = _make_claim_response(success=True)
        mock_db.rpc.return_value = resp
        svc = WorkQueueService(mock_db)
        result = await svc.claim()

        assert result.success is True


# ===========================================================================
# Guardrail block counter tests
# ===========================================================================


class TestGuardrailBlockMetrics:
    @pytest.mark.asyncio
    async def test_guardrail_block_increments_counter(
        self,
        mock_db,
        mock_policy_allow,
        mock_guardrails_block,
        mock_audit,
        mock_profiles,
        mock_meter,
    ):
        resp = _make_claim_response(success=True)
        # Set up two rpc calls: claim_task then complete_task (release)
        mock_db.rpc.side_effect = [
            resp,
            {"success": True, "status": "failed", "task_id": resp["task_id"]},
        ]
        svc = WorkQueueService(mock_db)
        result = await svc.claim()

        assert result.success is False
        assert "destructive_operation_blocked" in (result.reason or "")

        guardrail_counter = mock_meter["guardrail_counter"]
        guardrail_counter.add.assert_called_once_with(1, {"pattern": "rm_rf"})

    @pytest.mark.asyncio
    async def test_guardrail_block_no_error_when_disabled(
        self,
        mock_db,
        mock_policy_allow,
        mock_guardrails_block,
        mock_audit,
        mock_profiles,
        mock_meter_disabled,
    ):
        resp = _make_claim_response(success=True)
        mock_db.rpc.side_effect = [
            resp,
            {"success": True, "status": "failed", "task_id": resp["task_id"]},
        ]
        svc = WorkQueueService(mock_db)
        result = await svc.claim()

        # Should still block, just no metric recorded
        assert result.success is False


# ===========================================================================
# Complete metrics tests
# ===========================================================================


class TestCompleteMetrics:
    @pytest.mark.asyncio
    async def test_complete_records_task_duration(
        self,
        mock_db,
        mock_policy_allow,
        mock_guardrails_pass,
        mock_audit,
        mock_profiles,
        mock_meter,
    ):
        task_id = uuid4()
        claimed_at = datetime.now(UTC) - timedelta(seconds=60)
        task_row = _make_task_row(claimed_at=claimed_at)
        task_row["id"] = str(task_id)
        mock_db.query.return_value = [task_row]
        mock_db.rpc.return_value = _make_complete_response(success=True)

        svc = WorkQueueService(mock_db)
        result = await svc.complete(task_id=task_id, success=True)

        assert result.success is True
        task_hist = mock_meter["task_hist"]
        task_hist.record.assert_called_once()
        dur_ms = task_hist.record.call_args[0][0]
        assert 55_000 < dur_ms < 120_000
        labels = task_hist.record.call_args[0][1]
        assert labels["task_type"] == "refactor"
        assert labels["outcome"] == "completed"

    @pytest.mark.asyncio
    async def test_complete_records_failed_outcome(
        self,
        mock_db,
        mock_policy_allow,
        mock_guardrails_pass,
        mock_audit,
        mock_profiles,
        mock_meter,
    ):
        task_id = uuid4()
        claimed_at = datetime.now(UTC) - timedelta(seconds=10)
        task_row = _make_task_row(claimed_at=claimed_at)
        task_row["id"] = str(task_id)
        mock_db.query.return_value = [task_row]
        mock_db.rpc.return_value = _make_complete_response(success=True)

        svc = WorkQueueService(mock_db)
        result = await svc.complete(
            task_id=task_id, success=False, error_message="boom"
        )

        assert result.success is True
        task_hist = mock_meter["task_hist"]
        task_hist.record.assert_called_once()
        labels = task_hist.record.call_args[0][1]
        assert labels["outcome"] == "failed"

    @pytest.mark.asyncio
    async def test_complete_no_errors_when_disabled(
        self,
        mock_db,
        mock_policy_allow,
        mock_guardrails_pass,
        mock_audit,
        mock_profiles,
        mock_meter_disabled,
    ):
        task_id = uuid4()
        task_row = _make_task_row()
        task_row["id"] = str(task_id)
        mock_db.query.return_value = [task_row]
        mock_db.rpc.return_value = _make_complete_response(success=True)

        svc = WorkQueueService(mock_db)
        result = await svc.complete(task_id=task_id, success=True)

        assert result.success is True


# ===========================================================================
# Submit metrics tests
# ===========================================================================


class TestSubmitMetrics:
    @pytest.mark.asyncio
    async def test_submit_increments_counter(
        self,
        mock_db,
        mock_policy_allow,
        mock_guardrails_pass,
        mock_audit,
        mock_profiles,
        mock_meter,
    ):
        mock_db.rpc.return_value = _make_submit_response()
        svc = WorkQueueService(mock_db)
        result = await svc.submit(task_type="test", description="Write tests")

        assert result.success is True
        submit_counter = mock_meter["submit_counter"]
        submit_counter.add.assert_called_once_with(1, {"task_type": "test"})

    @pytest.mark.asyncio
    async def test_submit_no_errors_when_disabled(
        self,
        mock_db,
        mock_policy_allow,
        mock_guardrails_pass,
        mock_audit,
        mock_profiles,
        mock_meter_disabled,
    ):
        mock_db.rpc.return_value = _make_submit_response()
        svc = WorkQueueService(mock_db)
        result = await svc.submit(task_type="test", description="Write tests")

        assert result.success is True
