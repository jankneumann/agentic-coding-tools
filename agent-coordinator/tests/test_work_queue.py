"""Tests for the work queue service."""

from uuid import UUID, uuid4

import pytest
from httpx import Response

from src.policy_engine import PolicyDecision
from src.work_queue import ClaimResult, CompleteResult, SubmitResult, Task, WorkQueueService


def _allow_policy(monkeypatch):
    """Make the pre-queue authorization gate permit, so later stages are reachable.

    ``claim``/``submit`` call ``get_policy_engine().check_operation`` before
    touching the queue. Under the default native engine an unregistered test
    principal is denied there, so the guardrail block further down is never
    reached — which is why a test that only called the public method could pass
    whether or not the trust-failure path was fixed.
    """
    from unittest.mock import AsyncMock

    engine = AsyncMock()
    engine.check_operation.return_value = PolicyDecision.allow("test")
    monkeypatch.setattr("src.policy_engine.get_policy_engine", lambda: engine)
    return engine


class TestWorkQueueService:
    """Tests for WorkQueueService."""

    @pytest.mark.asyncio
    async def test_claim_task_success(
        self, mock_supabase, db_client, task_claimed_response
    ):
        """Test successful task claim."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/claim_task"
        ).mock(return_value=Response(200, json=task_claimed_response))

        service = WorkQueueService(db_client)
        result = await service.claim()

        assert result.success is True
        assert result.task_id is not None
        assert result.task_type == "refactor"
        assert result.description == "Refactor authentication module"
        assert result.priority == 3

    @pytest.mark.asyncio
    async def test_claim_task_with_types(
        self, mock_supabase, db_client, task_claimed_response
    ):
        """Test claiming a task with specific types."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/claim_task"
        ).mock(return_value=Response(200, json=task_claimed_response))

        service = WorkQueueService(db_client)
        result = await service.claim(task_types=["refactor", "test"])

        assert result.success is True

    @pytest.mark.asyncio
    async def test_claim_no_tasks_available(
        self, mock_supabase, db_client, no_tasks_response
    ):
        """Test claiming when no tasks are available."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/claim_task"
        ).mock(return_value=Response(200, json=no_tasks_response))

        service = WorkQueueService(db_client)
        result = await service.claim()

        assert result.success is False
        assert result.reason == "no_tasks_available"
        assert result.task_id is None

    @pytest.mark.asyncio
    async def test_complete_task_success(
        self, mock_supabase, db_client, task_completed_response
    ):
        """Test successful task completion."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/complete_task"
        ).mock(return_value=Response(200, json=task_completed_response))

        service = WorkQueueService(db_client)
        task_id = UUID(task_completed_response["task_id"])

        result = await service.complete(
            task_id=task_id,
            success=True,
            result={"files_modified": ["src/auth.py"]},
        )

        assert result.success is True
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_complete_task_failure(self, mock_supabase, db_client):
        """Test marking a task as failed."""
        response = {
            "success": True,
            "status": "failed",
            "task_id": str(UUID(int=1)),
        }
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/complete_task"
        ).mock(return_value=Response(200, json=response))

        service = WorkQueueService(db_client)

        result = await service.complete(
            task_id=UUID(int=1),
            success=False,
            error_message="Tests failed: 3 assertions",
        )

        assert result.success is True
        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_submit_task_success(
        self, mock_supabase, db_client, task_submitted_response
    ):
        """Test successful task submission."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/submit_task"
        ).mock(return_value=Response(200, json=task_submitted_response))

        service = WorkQueueService(db_client)
        result = await service.submit(
            task_type="test",
            description="Write tests for new feature",
            input_data={"files": ["src/feature.py"]},
            priority=3,
        )

        assert result.success is True
        assert result.task_id is not None

    @pytest.mark.asyncio
    async def test_submit_task_with_dependencies(
        self, mock_supabase, db_client, task_submitted_response
    ):
        """Test submitting a task with dependencies."""
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/submit_task"
        ).mock(return_value=Response(200, json=task_submitted_response))

        service = WorkQueueService(db_client)
        dep_id = UUID(int=99)

        result = await service.submit(
            task_type="deploy",
            description="Deploy to staging",
            depends_on=[dep_id],
            priority=2,
        )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_get_pending_tasks(
        self, mock_supabase, db_client, pending_tasks_response
    ):
        """Test getting pending tasks."""
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/work_queue"
        ).mock(return_value=Response(200, json=pending_tasks_response))

        service = WorkQueueService(db_client)
        tasks = await service.get_pending()

        assert len(tasks) == 2
        assert tasks[0].task_type == "test"
        assert tasks[0].priority == 2
        assert tasks[1].task_type == "refactor"
        assert tasks[1].priority == 5

    @pytest.mark.asyncio
    async def test_get_pending_with_types(
        self, mock_supabase, db_client, pending_tasks_response
    ):
        """Test getting pending tasks filtered by type."""
        # Return only test tasks
        filtered = [pending_tasks_response[0]]
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/work_queue"
        ).mock(return_value=Response(200, json=filtered))

        service = WorkQueueService(db_client)
        tasks = await service.get_pending(task_types=["test"])

        assert len(tasks) == 1
        assert tasks[0].task_type == "test"

    @pytest.mark.asyncio
    async def test_get_task_by_id(
        self, mock_supabase, db_client, pending_tasks_response
    ):
        """Test getting a specific task by ID."""
        task_data = pending_tasks_response[0]
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/work_queue"
        ).mock(return_value=Response(200, json=[task_data]))

        service = WorkQueueService(db_client)
        task_id = UUID(task_data["id"])
        task = await service.get_task(task_id)

        assert task is not None
        assert task.id == task_id
        assert task.task_type == "test"

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, mock_supabase, db_client):
        """Test getting a task that doesn't exist."""
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/work_queue"
        ).mock(return_value=Response(200, json=[]))

        service = WorkQueueService(db_client)
        task = await service.get_task(UUID(int=999))

        assert task is None

    @pytest.mark.asyncio
    async def test_claim_denied_by_policy(self, monkeypatch):
        """Claim is blocked when policy engine denies get_work."""

        class DenyPolicyEngine:
            async def check_operation(self, **_kwargs):
                return PolicyDecision.deny("operation_not_permitted")

        class FailDB:
            async def rpc(self, *_args, **_kwargs):
                raise AssertionError("DB RPC should not be called when denied")

        monkeypatch.setattr(
            "src.policy_engine.get_policy_engine",
            lambda: DenyPolicyEngine(),
        )

        service = WorkQueueService(FailDB())
        result = await service.claim()

        assert result.success is False
        assert result.reason == "operation_not_permitted"

    @pytest.mark.asyncio
    async def test_complete_denied_by_policy(self, monkeypatch):
        """Complete is blocked when policy engine denies complete_work."""

        class DenyPolicyEngine:
            async def check_operation(self, **_kwargs):
                return PolicyDecision.deny("insufficient_trust_level")

        class FailDB:
            async def rpc(self, *_args, **_kwargs):
                raise AssertionError("DB RPC should not be called when denied")

        monkeypatch.setattr(
            "src.policy_engine.get_policy_engine",
            lambda: DenyPolicyEngine(),
        )

        service = WorkQueueService(FailDB())
        result = await service.complete(task_id=UUID(int=1), success=True)

        assert result.success is False
        assert result.status == "blocked"
        assert result.reason == "insufficient_trust_level"

    @pytest.mark.asyncio
    async def test_submit_denied_by_policy(self, monkeypatch):
        """Submit is blocked when policy engine denies submit_work."""

        class DenyPolicyEngine:
            async def check_operation(self, **_kwargs):
                return PolicyDecision.deny("operation_not_permitted")

        class FailDB:
            async def rpc(self, *_args, **_kwargs):
                raise AssertionError("DB RPC should not be called when denied")

        monkeypatch.setattr(
            "src.policy_engine.get_policy_engine",
            lambda: DenyPolicyEngine(),
        )

        service = WorkQueueService(FailDB())
        result = await service.submit(
            task_type="test",
            description="Run unit tests",
        )

        assert result.success is False
        assert result.task_id is None


class TestTaskDataClasses:
    """Tests for Task and result dataclasses."""

    def test_task_from_dict(self, pending_tasks_response):
        """Test creating a Task from a dictionary."""
        task = Task.from_dict(pending_tasks_response[0])

        assert isinstance(task.id, UUID)
        assert task.task_type == "test"
        assert task.description == "Write unit tests for cache module"
        assert task.status == "pending"
        assert task.priority == 2
        assert task.input_data == {"files": ["src/cache.py"]}

    def test_task_from_dict_with_deadline(self, pending_tasks_response):
        """Test creating a Task with a deadline."""
        task = Task.from_dict(pending_tasks_response[1])

        assert task.deadline is not None
        assert task.task_type == "refactor"

    def test_claim_result_from_dict_success(self, task_claimed_response):
        """Test creating a ClaimResult from a success response."""
        result = ClaimResult.from_dict(task_claimed_response)

        assert result.success is True
        assert result.task_id is not None
        assert result.task_type == "refactor"
        assert result.priority == 3

    def test_claim_result_from_dict_failure(self, no_tasks_response):
        """Test creating a ClaimResult from a failure response."""
        result = ClaimResult.from_dict(no_tasks_response)

        assert result.success is False
        assert result.reason == "no_tasks_available"
        assert result.task_id is None

    def test_complete_result_from_dict(self, task_completed_response):
        """Test creating a CompleteResult from a response."""
        result = CompleteResult.from_dict(task_completed_response)

        assert result.success is True
        assert result.status == "completed"
        assert result.task_id is not None

    def test_submit_result_from_dict(self, task_submitted_response):
        """Test creating a SubmitResult from a response."""
        result = SubmitResult.from_dict(task_submitted_response)

        assert result.success is True
        assert result.task_id is not None


class TestWorkQueueAtomicity:
    """Tests for work queue atomicity and race conditions."""

    @pytest.mark.asyncio
    async def test_concurrent_claim_first_wins(self, mock_supabase, db_client):
        """Test that only one agent claims a task in concurrent requests."""
        task_id = str(UUID(int=1))

        # First request succeeds
        first_response = {
            "success": True,
            "task_id": task_id,
            "task_type": "test",
            "description": "Run tests",
            "priority": 5,
        }

        # Second request fails (no more tasks)
        second_response = {
            "success": False,
            "reason": "no_tasks_available",
        }

        call_count = [0]

        def response_callback(request):
            call_count[0] += 1
            if call_count[0] == 1:
                return Response(200, json=first_response)
            return Response(200, json=second_response)

        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/claim_task"
        ).mock(side_effect=response_callback)

        service = WorkQueueService(db_client)

        # First claim succeeds
        result1 = await service.claim()
        assert result1.success is True
        assert str(result1.task_id) == task_id

        # Second claim fails (task already claimed)
        result2 = await service.claim()
        assert result2.success is False
        assert result2.reason == "no_tasks_available"

    @pytest.mark.asyncio
    async def test_complete_wrong_agent_fails(self, mock_supabase, db_client):
        """Test that an agent can't complete another agent's task."""
        response = {
            "success": False,
            "reason": "task_not_found_or_not_claimed_by_agent",
        }
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/complete_task"
        ).mock(return_value=Response(200, json=response))

        service = WorkQueueService(db_client)

        result = await service.complete(
            task_id=UUID(int=1),
            success=True,
        )

        assert result.success is False
        assert "not_claimed_by_agent" in result.reason


class TestWorkQueueTrustResolution:
    """The guardrail paths must use the same resolver as the HTTP endpoints.

    ``WorkQueueService._resolve_trust_level`` used to be a verbatim copy of the
    pre-change resolver: no registry check, no ``enabled`` check, and
    ``except Exception:`` → default trust. The same broken projection therefore
    produced a fail-loud 500 on ``/work/claim`` and a silent grant of trust 2
    on the claim/complete/submit guardrail evaluations that run here.
    """

    @staticmethod
    def _entry():
        from src.agents_config import AgentEntry

        return AgentEntry(
            name="grok-local",
            type="grok",
            profile="grok_local",
            trust_level=3,
            transport="mcp",
            capabilities=["lock"],
            description="d",
        )

    @pytest.mark.asyncio
    async def test_registry_agent_with_disabled_profile_fails_loud(
        self, monkeypatch, db_client
    ):
        """A disabled profile row must not degrade to the default trust level."""
        from unittest.mock import AsyncMock

        from src.profiles import AgentProfile, ProfileResult
        from src.trust_resolution import TrustResolutionError

        monkeypatch.setattr(
            "src.agents_config.get_agent_config", lambda _agent_id: self._entry()
        )
        service = AsyncMock()
        service.get_profile.return_value = ProfileResult(
            success=True,
            profile=AgentProfile(
                id="p",
                name="grok_local",
                agent_type="grok",
                trust_level=3,
                enabled=False,
            ),
            source="assignment",
        )
        monkeypatch.setattr("src.profiles._profiles_service", service)
        monkeypatch.setattr("src.audit._audit_service", AsyncMock())

        with pytest.raises(TrustResolutionError):
            await WorkQueueService(db_client)._resolve_trust_level(
                "grok-local", "grok"
            )

    @pytest.mark.asyncio
    async def test_lookup_failure_for_registry_agent_fails_loud(
        self, monkeypatch, db_client
    ):
        """The old copy swallowed every exception and returned trust 2."""
        from unittest.mock import AsyncMock

        from src.trust_resolution import TrustResolutionError

        monkeypatch.setattr(
            "src.agents_config.get_agent_config", lambda _agent_id: self._entry()
        )
        service = AsyncMock()
        service.get_profile.side_effect = RuntimeError("db down")
        monkeypatch.setattr("src.profiles._profiles_service", service)
        monkeypatch.setattr("src.audit._audit_service", AsyncMock())

        with pytest.raises(TrustResolutionError):
            await WorkQueueService(db_client)._resolve_trust_level(
                "grok-local", "grok"
            )

    @pytest.mark.asyncio
    async def test_decommissioned_agent_does_not_inherit_sibling_trust(
        self, monkeypatch, db_client
    ):
        """The F1 escalation, on the queue path this time."""
        from unittest.mock import AsyncMock

        from src.config import reset_config
        from src.profiles import AgentProfile, ProfileResult

        monkeypatch.setenv("PROFILES_DEFAULT_TRUST", "2")
        reset_config()

        monkeypatch.setattr(
            "src.agents_config.get_agent_config", lambda _agent_id: None
        )
        service = AsyncMock()
        service.get_profile.return_value = ProfileResult(
            success=True,
            profile=AgentProfile(
                id="p",
                name="codex_local",
                agent_type="codex",
                trust_level=3,
                enabled=True,
            ),
            source="default",
        )
        monkeypatch.setattr("src.profiles._profiles_service", service)

        trust = await WorkQueueService(db_client)._resolve_trust_level(
            "codex-remote", "codex"
        )
        assert trust == 2
        reset_config()


@pytest.mark.asyncio
class TestTrustFailureNeverSkipsGuardrails:
    """A trust-resolution failure must not silently skip the guardrail scan.

    ``claim``/``complete``/``submit`` each wrap their guardrail block in
    ``except Exception`` so that a guardrail *service* outage cannot brick the
    queue. Once ``_resolve_trust_level`` began raising ``TrustResolutionError``
    for a broken projection, that broad handler swallowed it — and because the
    resolve call sits *before* ``guardrails.check_operation``, the scan was
    never reached at all.

    That is strictly worse than the fail-open it replaced: previously a broken
    projection yielded trust 2 and the scan still ran, blocking
    ``git push --force`` / ``git reset --hard`` / ``rm -rf`` (all
    ``min_trust_level: 3``). Afterwards nothing was blocked.

    ``TestWorkQueueTrustResolution`` above calls ``_resolve_trust_level``
    directly and asserts it raises; it never exercises ``claim()``, which is
    exactly why this gap survived. These tests drive the public method.
    """

    @staticmethod
    def _raising_resolver():
        from src.trust_resolution import TrustResolutionError

        async def _raise(agent_id: str, agent_type: str) -> int:
            raise TrustResolutionError(
                agent_id, agent_type, "no profile row named 'grok_local'"
            )

        return _raise

    async def test_claim_fails_closed_when_trust_cannot_be_resolved(
        self, monkeypatch, mock_supabase, db_client
    ):
        """The destructive task must not be handed over unscanned."""
        from src.trust_resolution import TrustResolutionError

        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/claim_task"
        ).mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "task_id": str(uuid4()),
                    "task_type": "refactor",
                    # Would be blocked by guardrails at trust < 3.
                    "description": "run git push --force origin main and rm -rf /",
                    "input_data": {},
                    "priority": 1,
                    "deadline": None,
                },
            )
        )

        # claim() authorizes before it touches the queue; that gate is not what
        # is under test here, so let it through and exercise the guardrail block.
        _allow_policy(monkeypatch)

        service = WorkQueueService(db_client)
        monkeypatch.setattr(
            service, "_resolve_trust_level", self._raising_resolver()
        )

        with pytest.raises(TrustResolutionError):
            await service.claim(agent_id="grok-local", agent_type="grok")

    async def test_submit_fails_closed_when_trust_cannot_be_resolved(
        self, monkeypatch, mock_supabase, db_client
    ):
        from src.trust_resolution import TrustResolutionError

        mock_supabase.post(
            "https://test.supabase.co/rest/v1/rpc/submit_task"
        ).mock(return_value=Response(200, json={"success": True, "task_id": str(uuid4())}))

        _allow_policy(monkeypatch)

        service = WorkQueueService(db_client)
        monkeypatch.setattr(
            service, "_resolve_trust_level", self._raising_resolver()
        )

        with pytest.raises(TrustResolutionError):
            await service.submit(
                task_type="refactor",
                description="rm -rf / --no-preserve-root",
            )
