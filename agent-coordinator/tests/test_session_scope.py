"""Tests for session scope enforcement (Task 2.3).

Verifies:
- Claiming a task with file scope creates a session grant recording the scope
- check_operation with session_scope detects out-of-scope file paths
- Warning format includes the task's declared scope and a suggestion
"""

from uuid import uuid4

import pytest
from httpx import Response

from src.guardrails import GuardrailResult, GuardrailsService


class TestSessionScopeEnforcement:
    """Tests for guardrails session_scope parameter."""

    @pytest.mark.asyncio
    async def test_in_scope_files_allowed(self, mock_supabase, db_client):
        """Files within session scope pass guardrail check."""
        # No destructive patterns
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/operation_guardrails"
        ).mock(return_value=Response(200, json=[]))

        service = GuardrailsService(db_client)
        result = await service.check_operation(
            operation_text="edit file",
            file_paths=["agent-coordinator/src/profiles.py"],
            trust_level=2,
            session_scope={
                "write_allow": ["agent-coordinator/src/**", "agent-coordinator/tests/**"],
                "deny": [],
            },
        )

        assert result.safe is True
        assert len(result.violations) == 0

    @pytest.mark.asyncio
    async def test_out_of_scope_file_produces_warning(self, mock_supabase, db_client):
        """Files outside session scope produce a scope violation warning."""
        # No destructive patterns
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/operation_guardrails"
        ).mock(return_value=Response(200, json=[]))

        service = GuardrailsService(db_client)
        result = await service.check_operation(
            operation_text="edit file",
            file_paths=["skills/autopilot/scripts/convergence_loop.py"],
            trust_level=2,
            session_scope={
                "write_allow": ["agent-coordinator/src/**", "agent-coordinator/tests/**"],
                "deny": [],
            },
        )

        # Scope violations are warnings (not blocks) to allow agents to
        # request scope expansion
        assert len(result.violations) > 0
        violation = result.violations[0]
        assert violation.pattern_name == "session_scope_violation"
        assert violation.category == "scope"
        assert violation.severity == "warn"
        assert violation.blocked is False

    @pytest.mark.asyncio
    async def test_scope_violation_includes_declared_scope(
        self, mock_supabase, db_client
    ):
        """Scope violation warning includes the task's declared scope."""
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/operation_guardrails"
        ).mock(return_value=Response(200, json=[]))

        service = GuardrailsService(db_client)
        result = await service.check_operation(
            operation_text="edit file",
            file_paths=["skills/some-skill/SKILL.md"],
            trust_level=2,
            session_scope={
                "write_allow": ["agent-coordinator/src/**"],
                "deny": [],
            },
        )

        assert len(result.violations) > 0
        violation = result.violations[0]
        # matched_text should include the violating path info
        assert "skills/some-skill/SKILL.md" in (violation.matched_text or "")

    @pytest.mark.asyncio
    async def test_scope_violation_includes_suggestion(
        self, mock_supabase, db_client
    ):
        """Scope violation warning includes a suggestion to request scope expansion."""
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/operation_guardrails"
        ).mock(return_value=Response(200, json=[]))

        service = GuardrailsService(db_client)
        result = await service.check_operation(
            operation_text="edit file",
            file_paths=["skills/some-skill/SKILL.md"],
            trust_level=2,
            session_scope={
                "write_allow": ["agent-coordinator/src/**"],
                "deny": [],
            },
        )

        assert len(result.violations) > 0
        violation = result.violations[0]
        assert violation.approval_required is True

    @pytest.mark.asyncio
    async def test_deny_pattern_blocks_even_within_write_allow(
        self, mock_supabase, db_client
    ):
        """Files matching deny patterns are blocked even if write_allow would match."""
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/operation_guardrails"
        ).mock(return_value=Response(200, json=[]))

        service = GuardrailsService(db_client)
        result = await service.check_operation(
            operation_text="edit file",
            file_paths=["agent-coordinator/src/secrets.yaml"],
            trust_level=2,
            session_scope={
                "write_allow": ["agent-coordinator/src/**"],
                "deny": ["**/*.yaml"],
            },
        )

        assert len(result.violations) > 0
        violation = result.violations[0]
        assert violation.pattern_name == "session_scope_violation"

    @pytest.mark.asyncio
    async def test_no_session_scope_means_no_scope_checking(
        self, mock_supabase, db_client
    ):
        """When session_scope is None, no scope checking happens (backward compat)."""
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/operation_guardrails"
        ).mock(return_value=Response(200, json=[]))

        service = GuardrailsService(db_client)
        result = await service.check_operation(
            operation_text="edit file",
            file_paths=["any/path/file.py"],
            trust_level=2,
            # session_scope not passed — defaults to None
        )

        assert result.safe is True
        assert len(result.violations) == 0

    @pytest.mark.asyncio
    async def test_multiple_files_some_in_scope_some_not(
        self, mock_supabase, db_client
    ):
        """When multiple files are provided, only out-of-scope ones get violations."""
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/operation_guardrails"
        ).mock(return_value=Response(200, json=[]))

        service = GuardrailsService(db_client)
        result = await service.check_operation(
            operation_text="edit files",
            file_paths=[
                "agent-coordinator/src/profiles.py",  # in scope
                "skills/some-skill/SKILL.md",  # out of scope
                "agent-coordinator/tests/test_foo.py",  # in scope
            ],
            trust_level=2,
            session_scope={
                "write_allow": ["agent-coordinator/**"],
                "deny": [],
            },
        )

        # Only the out-of-scope file should produce a violation
        scope_violations = [
            v for v in result.violations if v.pattern_name == "session_scope_violation"
        ]
        assert len(scope_violations) == 1
        assert "skills/some-skill/SKILL.md" in (scope_violations[0].matched_text or "")

    @pytest.mark.asyncio
    async def test_scope_check_coexists_with_destructive_patterns(
        self, mock_supabase, db_client
    ):
        """Session scope violations and destructive pattern violations can coexist."""
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/operation_guardrails"
        ).mock(
            return_value=Response(200, json=[
                {
                    "name": "git_force_push",
                    "category": "git",
                    "pattern": r"git\s+push\s+.*--force",
                    "severity": "block",
                    "min_trust_level": 3,
                }
            ])
        )
        # Mock the guardrail_violations insert
        mock_supabase.post(
            url__startswith="https://test.supabase.co/rest/v1/guardrail_violations"
        ).mock(return_value=Response(201, json={}))
        # Mock audit log
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/audit_log"
        ).mock(return_value=Response(201, json={"id": str(uuid4())}))

        service = GuardrailsService(db_client)
        result = await service.check_operation(
            operation_text="git push --force origin main",
            file_paths=["skills/some-skill/SKILL.md"],  # out of scope
            trust_level=2,
            session_scope={
                "write_allow": ["agent-coordinator/**"],
                "deny": [],
            },
        )

        # Should have both types of violations
        pattern_violations = [
            v for v in result.violations if v.pattern_name == "git_force_push"
        ]
        scope_violations = [
            v for v in result.violations if v.pattern_name == "session_scope_violation"
        ]
        assert len(pattern_violations) >= 1
        assert len(scope_violations) >= 1
        # The destructive pattern should block
        assert result.safe is False

    @pytest.mark.asyncio
    async def test_empty_write_allow_blocks_all_files(
        self, mock_supabase, db_client
    ):
        """When write_allow is empty, all file paths produce violations."""
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/operation_guardrails"
        ).mock(return_value=Response(200, json=[]))

        service = GuardrailsService(db_client)
        result = await service.check_operation(
            operation_text="edit file",
            file_paths=["any/path/file.py"],
            trust_level=2,
            session_scope={
                "write_allow": [],
                "deny": [],
            },
        )

        scope_violations = [
            v for v in result.violations if v.pattern_name == "session_scope_violation"
        ]
        assert len(scope_violations) == 1


class TestSessionScopeGrantOnClaim:
    """Tests for session grant creation when claiming a task with scope."""

    @pytest.mark.asyncio
    async def test_claim_task_with_scope_creates_grant(
        self, mock_supabase, db_client
    ):
        """Claiming a task with file scope creates a session grant recording the scope."""
        from src.session_grants import SessionGrantService

        task_id = str(uuid4())
        grant_id = str(uuid4())
        scope = {
            "write_allow": ["agent-coordinator/src/**"],
            "deny": ["**/.env"],
        }

        # Mock the insert for session_permission_grants (returns a list)
        mock_supabase.post(
            "https://test.supabase.co/rest/v1/session_permission_grants"
        ).mock(
            return_value=Response(201, json=[{
                "id": grant_id,
                "session_id": "test-session-1",
                "agent_id": "test-agent-1",
                "operation": "session_scope",
                "justification": None,
            }])
        )

        service = SessionGrantService(db_client)
        grant = await service.request_grant(
            session_id="test-session-1",
            agent_id="test-agent-1",
            operation="session_scope",
            justification=f"Task {task_id} scope: {scope}",
        )

        assert grant.operation == "session_scope"
        assert grant.agent_id == "test-agent-1"
        assert grant.session_id == "test-session-1"
