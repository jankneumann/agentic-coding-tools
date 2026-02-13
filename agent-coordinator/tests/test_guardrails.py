"""Tests for the guardrails engine."""

import pytest
from httpx import Response

from src.guardrails import (
    FALLBACK_PATTERNS,
    GuardrailPattern,
    GuardrailResult,
    GuardrailsService,
    GuardrailViolation,
)


class TestGuardrailsService:
    """Tests for GuardrailsService."""

    @pytest.mark.asyncio
    async def test_block_force_push(self, mock_supabase, db_client):
        """Test that force push is blocked for low-trust agents."""
        # Return patterns from DB
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/operation_guardrails"
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "name": "git_force_push",
                        "category": "git",
                        "pattern": r"git\s+push\s+.*--force",
                        "severity": "block",
                        "min_trust_level": 3,
                    }
                ],
            )
        )

        service = GuardrailsService(db_client)
        result = await service.check_operation(
            operation_text="git push --force origin main",
            trust_level=2,
        )

        assert result.safe is False
        assert len(result.violations) == 1
        assert result.violations[0].pattern_name == "git_force_push"
        assert result.violations[0].blocked is True

    @pytest.mark.asyncio
    async def test_allow_force_push_high_trust(self, mock_supabase, db_client):
        """Test that force push is allowed for high-trust agents."""
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/operation_guardrails"
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "name": "git_force_push",
                        "category": "git",
                        "pattern": r"git\s+push\s+.*--force",
                        "severity": "block",
                        "min_trust_level": 3,
                    }
                ],
            )
        )

        service = GuardrailsService(db_client)
        result = await service.check_operation(
            operation_text="git push --force origin main",
            trust_level=3,
        )

        assert result.safe is True
        assert len(result.violations) == 0

    @pytest.mark.asyncio
    async def test_block_rm_rf(self, mock_supabase, db_client):
        """Test that rm -rf is blocked."""
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/operation_guardrails"
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "name": "rm_rf",
                        "category": "file",
                        "pattern": r"rm\s+-rf\s+",
                        "severity": "block",
                        "min_trust_level": 3,
                    }
                ],
            )
        )

        service = GuardrailsService(db_client)
        result = await service.check_operation(
            operation_text="rm -rf /tmp/build",
            trust_level=2,
        )

        assert result.safe is False
        assert result.violations[0].pattern_name == "rm_rf"

    @pytest.mark.asyncio
    async def test_safe_operation(self, mock_supabase, db_client):
        """Test that safe operations pass."""
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/operation_guardrails"
        ).mock(return_value=Response(200, json=FALLBACK_PATTERNS))

        service = GuardrailsService(db_client)
        result = await service.check_operation(
            operation_text="git commit -m 'fix: update readme'",
            trust_level=2,
        )

        assert result.safe is True
        assert len(result.violations) == 0

    @pytest.mark.asyncio
    async def test_fallback_patterns_on_db_error(self, mock_supabase, db_client):
        """Test fallback to code patterns when DB is unavailable."""
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/operation_guardrails"
        ).mock(return_value=Response(500, json={"error": "Internal Server Error"}))

        service = GuardrailsService(db_client)
        result = await service.check_operation(
            operation_text="git push --force origin main",
            trust_level=2,
        )

        assert result.safe is False
        assert result.violations[0].pattern_name == "git_force_push"

    @pytest.mark.asyncio
    async def test_warn_severity_doesnt_block(self, mock_supabase, db_client):
        """Test that warn-severity patterns don't mark as unsafe."""
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/operation_guardrails"
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "name": "env_file_modify",
                        "category": "credential",
                        "pattern": r"\.(env|env\.local)",
                        "severity": "warn",
                        "min_trust_level": 2,
                    }
                ],
            )
        )

        service = GuardrailsService(db_client)
        result = await service.check_operation(
            operation_text="editing .env file",
            trust_level=1,
        )

        assert result.safe is True  # warn doesn't block
        assert len(result.violations) == 1
        assert result.violations[0].severity == "warn"
        assert result.violations[0].blocked is False

    @pytest.mark.asyncio
    async def test_file_path_matching(self, mock_supabase, db_client):
        """Test matching against file paths."""
        mock_supabase.get(
            url__startswith="https://test.supabase.co/rest/v1/operation_guardrails"
        ).mock(
            return_value=Response(
                200,
                json=[
                    {
                        "name": "credentials_file",
                        "category": "credential",
                        "pattern": r"(credentials|secrets)\.(json|yaml)",
                        "severity": "warn",
                        "min_trust_level": 2,
                    }
                ],
            )
        )

        service = GuardrailsService(db_client)
        result = await service.check_operation(
            operation_text="modifying configuration",
            file_paths=["config/credentials.json"],
            trust_level=1,
        )

        assert len(result.violations) == 1
        assert result.violations[0].pattern_name == "credentials_file"


class TestGuardrailDataClasses:
    """Tests for guardrail dataclasses."""

    def test_pattern_from_dict(self):
        """Test creating GuardrailPattern from dict."""
        pattern = GuardrailPattern.from_dict(FALLBACK_PATTERNS[0])
        assert pattern.name == "git_force_push"
        assert pattern.category == "git"
        assert pattern.severity == "block"

    def test_violation_from_dict(self):
        """Test creating GuardrailViolation from dict."""
        violation = GuardrailViolation.from_dict({
            "pattern_name": "rm_rf",
            "category": "file",
            "severity": "block",
            "blocked": True,
        })
        assert violation.pattern_name == "rm_rf"
        assert violation.blocked is True

    def test_result_from_dict(self):
        """Test creating GuardrailResult from dict."""
        result = GuardrailResult.from_dict({
            "safe": False,
            "violations": [
                {"pattern_name": "test", "category": "git", "severity": "block", "blocked": True}
            ],
        })
        assert result.safe is False
        assert len(result.violations) == 1
