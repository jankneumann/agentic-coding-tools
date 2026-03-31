"""Integration and unit tests for AdaptiveBackend fallback behavior.

Integration tests (marked ``@pytest.mark.integration``) test against live
services. Unit tests verify the fallback logic with mocked backends and
can run without any external services.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from evaluation.gen_eval.cli_generator import CLIBackend, CLIBackendError
from evaluation.gen_eval.coordinator import CoordinatorIntegration, _build_findings_summary
from evaluation.gen_eval.hybrid_generator import AdaptiveBackend
from evaluation.gen_eval.models import EvalFeedback, Scenario
from evaluation.gen_eval.reports import GenEvalReport

# ===========================================================================
# Unit tests (no external services needed)
# ===========================================================================


class TestAdaptiveBackendFallback:
    """Unit tests for AdaptiveBackend rate-limit detection and SDK fallback."""

    @pytest.mark.asyncio
    async def test_cli_success_does_not_fallback(self) -> None:
        """When CLI succeeds, SDK is never called."""
        cli = AsyncMock(spec=CLIBackend)
        cli.name = "cli"
        cli.is_subscription_covered = True
        cli.run = AsyncMock(return_value="generated scenario yaml")
        cli.is_available = AsyncMock(return_value=True)

        sdk = AsyncMock()
        sdk.name = "sdk"
        sdk.is_available = AsyncMock(return_value=True)

        backend = AdaptiveBackend(cli=cli, sdk=sdk)
        result = await backend.run("test prompt")

        assert result == "generated scenario yaml"
        cli.run.assert_awaited_once_with("test prompt", system=None)
        sdk.run.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cli_rate_limit_triggers_sdk_fallback(self) -> None:
        """When CLI returns a rate-limit error, backend falls back to SDK."""
        cli = AsyncMock(spec=CLIBackend)
        cli.name = "cli"
        cli.is_subscription_covered = True
        cli.run = AsyncMock(
            side_effect=CLIBackendError(
                "Rate limited",
                exit_code=1,
                stderr="Error: rate limit exceeded, try again later",
            )
        )
        cli.is_available = AsyncMock(return_value=True)

        sdk = AsyncMock()
        sdk.name = "sdk"
        sdk.is_available = AsyncMock(return_value=True)
        sdk.run = AsyncMock(return_value="sdk generated output")

        backend = AdaptiveBackend(cli=cli, sdk=sdk)
        result = await backend.run("test prompt")

        assert result == "sdk generated output"
        cli.run.assert_awaited_once()
        sdk.run.assert_awaited_once_with("test prompt", system=None)
        # CLI should be marked unavailable after rate limit
        assert not backend._cli_available

    @pytest.mark.asyncio
    async def test_cli_non_rate_limit_error_raises(self) -> None:
        """When CLI fails with a non-rate-limit error, it should raise."""
        cli = AsyncMock(spec=CLIBackend)
        cli.name = "cli"
        cli.is_subscription_covered = True
        cli.run = AsyncMock(
            side_effect=CLIBackendError(
                "Some other error",
                exit_code=1,
                stderr="Permission denied",
            )
        )
        cli.is_available = AsyncMock(return_value=True)

        sdk = AsyncMock()
        sdk.name = "sdk"

        backend = AdaptiveBackend(cli=cli, sdk=sdk)

        with pytest.raises(CLIBackendError):
            await backend.run("test prompt")

        # SDK should NOT have been called
        sdk.run.assert_not_awaited()
        # CLI should still be marked available (not a rate limit)
        assert backend._cli_available

    @pytest.mark.asyncio
    async def test_cli_rate_limit_no_sdk_raises(self) -> None:
        """When CLI is rate limited and no SDK is configured, raises."""
        cli = AsyncMock(spec=CLIBackend)
        cli.name = "cli"
        cli.is_subscription_covered = True
        cli.run = AsyncMock(
            side_effect=CLIBackendError(
                "Rate limited",
                exit_code=1,
                stderr="too many requests",
            )
        )
        cli.is_available = AsyncMock(return_value=True)

        backend = AdaptiveBackend(cli=cli, sdk=None)

        with pytest.raises(CLIBackendError, match="no SDK backend"):
            await backend.run("test prompt")

    @pytest.mark.asyncio
    async def test_reset_restores_cli_availability(self) -> None:
        """After reset(), CLI becomes available again."""
        cli = AsyncMock(spec=CLIBackend)
        cli.name = "cli"
        cli.is_subscription_covered = True
        cli.run = AsyncMock(
            side_effect=CLIBackendError(
                "Rate limited",
                exit_code=1,
                stderr="rate limit",
            )
        )
        cli.is_available = AsyncMock(return_value=True)

        sdk = AsyncMock()
        sdk.name = "sdk"
        sdk.run = AsyncMock(return_value="sdk output")

        backend = AdaptiveBackend(cli=cli, sdk=sdk)
        await backend.run("prompt")
        assert not backend._cli_available

        backend.reset()
        assert backend._cli_available

    @pytest.mark.asyncio
    async def test_second_call_after_rate_limit_uses_sdk(self) -> None:
        """After a rate limit, subsequent calls go directly to SDK."""
        cli = AsyncMock(spec=CLIBackend)
        cli.name = "cli"
        cli.is_subscription_covered = True
        cli.run = AsyncMock(
            side_effect=CLIBackendError(
                "Rate limited",
                exit_code=1,
                stderr="rate limit exceeded",
            )
        )
        cli.is_available = AsyncMock(return_value=True)

        sdk = AsyncMock()
        sdk.name = "sdk"
        sdk.run = AsyncMock(return_value="sdk output")

        backend = AdaptiveBackend(cli=cli, sdk=sdk)

        # First call: CLI fails, falls back to SDK
        result1 = await backend.run("prompt 1")
        assert result1 == "sdk output"

        # Reset CLI mock to succeed (to verify it's NOT called)
        cli.run.reset_mock()
        cli.run.return_value = "cli output"
        cli.run.side_effect = None

        # Second call: should go directly to SDK
        result2 = await backend.run("prompt 2")
        assert result2 == "sdk output"
        cli.run.assert_not_awaited()

    def test_rate_limit_patterns_matching(self) -> None:
        """Test that various rate limit patterns are detected correctly."""
        cli = MagicMock(spec=CLIBackend)
        cli.name = "cli"
        backend = AdaptiveBackend(cli=cli, sdk=None)

        # Should match
        for stderr in [
            "Error: rate limit exceeded",
            "Too Many Requests",
            "quota exceeded for today",
            "HTTP 429 response",
        ]:
            err = CLIBackendError("fail", exit_code=1, stderr=stderr)
            assert backend._is_rate_limited(err), f"Should match: {stderr}"

        # Should NOT match
        for stderr in [
            "Permission denied",
            "File not found",
            "Connection refused",
        ]:
            err = CLIBackendError("fail", exit_code=1, stderr=stderr)
            assert not backend._is_rate_limited(err), f"Should not match: {stderr}"

        # Exit code 0 should never match
        err_ok = CLIBackendError("ok", exit_code=0, stderr="rate limit")
        assert not backend._is_rate_limited(err_ok)

    @pytest.mark.asyncio
    async def test_name_reflects_active_backend(self) -> None:
        """The name property should reflect which backend is active."""
        cli = AsyncMock(spec=CLIBackend)
        cli.name = "claude-cli"
        cli.is_subscription_covered = True

        sdk = AsyncMock()
        sdk.name = "anthropic-sdk"

        backend = AdaptiveBackend(cli=cli, sdk=sdk)
        assert backend.name == "claude-cli"

        # Force CLI unavailable
        backend._cli_available = False
        assert backend.name == "anthropic-sdk"

    @pytest.mark.asyncio
    async def test_is_subscription_covered(self) -> None:
        """is_subscription_covered reflects CLI availability."""
        cli = AsyncMock(spec=CLIBackend)
        cli.name = "cli"
        cli.is_subscription_covered = True

        backend = AdaptiveBackend(cli=cli, sdk=None)
        assert backend.is_subscription_covered is True

        backend._cli_available = False
        assert backend.is_subscription_covered is False


# ===========================================================================
# CoordinatorIntegration unit tests (mocked httpx)
# ===========================================================================


class TestCoordinatorIntegrationUnit:
    """Unit tests for CoordinatorIntegration with mocked HTTP client."""

    @pytest.mark.asyncio
    async def test_is_available_returns_false_on_connection_error(self) -> None:
        """When coordinator is unreachable, is_available returns False."""
        coord = CoordinatorIntegration(coordinator_url="http://localhost:99999")

        # Mock the client to raise a connection error
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))
        coord._client = mock_client

        result = await coord.is_available()
        assert result is False

    @pytest.mark.asyncio
    async def test_is_available_caches_result(self) -> None:
        """After first check, result is cached."""
        coord = CoordinatorIntegration()
        coord._available = True

        result = await coord.is_available()
        assert result is True

    @pytest.mark.asyncio
    async def test_distribute_scenarios_when_unavailable(self) -> None:
        """When coordinator is unavailable, distribute returns empty list."""
        coord = CoordinatorIntegration()
        coord._available = False

        scenarios = [
            Scenario(
                id="test-1",
                name="Test",
                description="Test scenario",
                category="test",
                interfaces=["http"],
                steps=[],
            )
        ]
        result = await coord.distribute_scenarios(scenarios)
        assert result == []

    @pytest.mark.asyncio
    async def test_store_findings_when_unavailable(self) -> None:
        """When coordinator is unavailable, store_findings does nothing."""
        coord = CoordinatorIntegration()
        coord._available = False

        # Should not raise
        await coord.store_findings(MagicMock())

    @pytest.mark.asyncio
    async def test_recall_previous_findings_when_unavailable(self) -> None:
        """When coordinator is unavailable, recall returns empty list."""
        coord = CoordinatorIntegration()
        coord._available = False

        result = await coord.recall_previous_findings("test-project")
        assert result == []

    @pytest.mark.asyncio
    async def test_distribute_scenarios_success(self) -> None:
        """When coordinator is available, scenarios are submitted."""
        coord = CoordinatorIntegration()
        coord._available = True

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.is_success = True
        mock_response.json.return_value = {"task_id": "task-123"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        coord._client = mock_client

        scenarios = [
            Scenario(
                id="test-1",
                name="Test Scenario",
                description="A test",
                category="lock-lifecycle",
                interfaces=["http"],
                steps=[],
            )
        ]

        result = await coord.distribute_scenarios(scenarios)
        assert result == ["task-123"]
        mock_client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_recall_findings_parses_memories(self) -> None:
        """Recall converts coordinator memories to EvalFeedback objects."""
        coord = CoordinatorIntegration()
        coord._available = True

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "memories": [
                {
                    "summary": "Gen-eval run: 10 scenarios",
                    "metadata": {
                        "failing_interfaces": ["POST /locks/acquire"],
                        "under_tested_categories": ["work-queue"],
                        "coverage_summary": {"http": 80.0},
                    },
                }
            ]
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        coord._client = mock_client

        result = await coord.recall_previous_findings("agent-coordinator")
        assert len(result) == 1
        assert isinstance(result[0], EvalFeedback)
        assert result[0].failing_interfaces == ["POST /locks/acquire"]
        assert result[0].under_tested_categories == ["work-queue"]

    def test_reset_clears_availability_cache(self) -> None:
        """reset() clears the cached availability state."""
        coord = CoordinatorIntegration()
        coord._available = True
        coord.reset()
        assert coord._available is None

    @pytest.mark.asyncio
    async def test_async_context_manager(self) -> None:
        """CoordinatorIntegration can be used as an async context manager."""
        async with CoordinatorIntegration() as coord:
            assert isinstance(coord, CoordinatorIntegration)
            # Should not have a client yet (lazy init)
            assert coord._client is None

    @pytest.mark.asyncio
    async def test_async_context_manager_closes_client(self) -> None:
        """Exiting async context manager closes the HTTP client."""
        coord = CoordinatorIntegration()
        mock_client = AsyncMock()
        coord._client = mock_client

        async with coord:
            pass

        mock_client.aclose.assert_awaited_once()
        assert coord._client is None

    @pytest.mark.asyncio
    async def test_distribute_scenarios_accepts_non_200_success(self) -> None:
        """distribute_scenarios accepts any 2xx status via is_success."""
        coord = CoordinatorIntegration()
        coord._available = True

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.is_success = True
        mock_response.json.return_value = {"task_id": "task-201"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        coord._client = mock_client

        scenarios = [
            Scenario(
                id="test-1",
                name="Test",
                description="A test",
                category="test",
                interfaces=["http"],
                steps=[],
            )
        ]

        result = await coord.distribute_scenarios(scenarios)
        assert result == ["task-201"]

    @pytest.mark.asyncio
    async def test_distribute_scenarios_rejects_failure_status(self) -> None:
        """distribute_scenarios skips scenarios with 4xx/5xx responses."""
        coord = CoordinatorIntegration()
        coord._available = True

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.is_success = False

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        coord._client = mock_client

        scenarios = [
            Scenario(
                id="test-1",
                name="Test",
                description="A test",
                category="test",
                interfaces=["http"],
                steps=[],
            )
        ]

        result = await coord.distribute_scenarios(scenarios)
        assert result == []

    def test_build_findings_summary(self) -> None:
        """_build_findings_summary produces a readable string."""
        report = GenEvalReport(
            total_scenarios=10,
            passed=8,
            failed=1,
            errors=1,
            skipped=0,
            pass_rate=0.8,
            coverage_pct=75.0,
            duration_seconds=120.0,
            budget_exhausted=False,
            verdicts=[],
            per_interface={},
            per_category={},
            unevaluated_interfaces=[],
            cost_summary={},
            iterations_completed=1,
        )
        summary = _build_findings_summary(report)
        assert "10 scenarios" in summary
        assert "8 passed" in summary
        assert "80.0%" in summary
        assert "75.0%" in summary


# ===========================================================================
# Integration tests (require live services)
# ===========================================================================


class TestAdaptiveBackendIntegration:
    """Integration tests for AdaptiveBackend with live services."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_cli_rate_limit_triggers_sdk_fallback_e2e(self) -> None:
        """End-to-end: mock CLI to return rate limit, verify SDK fallback.

        This test creates a real AdaptiveBackend but mocks the CLI backend
        to simulate a rate limit, then verifies the SDK path is taken.
        The SDK backend is also mocked since we don't want to make real
        API calls in integration tests.
        """
        cli = AsyncMock(spec=CLIBackend)
        cli.name = "cli"
        cli.is_subscription_covered = True
        cli.run = AsyncMock(
            side_effect=CLIBackendError(
                "Rate limited",
                exit_code=1,
                stderr="Error: rate limit exceeded",
            )
        )
        cli.is_available = AsyncMock(return_value=True)

        sdk = AsyncMock()
        sdk.name = "sdk"
        sdk.is_available = AsyncMock(return_value=True)
        sdk.run = AsyncMock(return_value='id: "generated-1"\nname: "Generated"\n')

        backend = AdaptiveBackend(cli=cli, sdk=sdk)

        # First call triggers fallback
        result = await backend.run("Generate a lock-lifecycle scenario")
        assert "generated-1" in result
        assert not backend._cli_available

        # Second call goes directly to SDK
        result2 = await backend.run("Generate another scenario")
        assert result2 is not None
        assert cli.run.await_count == 1  # CLI only called once (first time)
        assert sdk.run.await_count == 2  # SDK called both times
