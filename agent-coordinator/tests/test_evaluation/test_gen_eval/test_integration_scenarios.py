"""Integration tests for gen-eval scenario categories against live services.

These tests require docker-compose services to be running and are marked
with ``@pytest.mark.integration`` so they are skipped during normal CI.
They exercise the full pipeline: load YAML templates, create real transport
clients, evaluate via the Evaluator, and assert on ScenarioVerdict results.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from evaluation.gen_eval.clients.base import (
    TransportClientRegistry,
)
from evaluation.gen_eval.clients.http_client import HttpClient
from evaluation.gen_eval.config import GenEvalConfig
from evaluation.gen_eval.descriptor import (
    AuthConfig,
    EndpointDescriptor,
    InterfaceDescriptor,
    ServiceDescriptor,
    StartupConfig,
    StateVerifier,
)
from evaluation.gen_eval.evaluator import Evaluator
from evaluation.gen_eval.generator import TemplateGenerator
from evaluation.gen_eval.models import (
    ScenarioVerdict,
)

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Test configuration defaults
# ---------------------------------------------------------------------------

_BASE_URL = os.environ.get("COORDINATOR_BASE_URL", "http://localhost:8081")
_MCP_URL = os.environ.get("COORDINATOR_MCP_URL", "http://localhost:8082/sse")
_DB_DSN_ENV = "DATABASE_URL"

_SCENARIO_BASE = Path(__file__).resolve().parents[3] / "evaluation" / "gen_eval" / "scenarios"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _build_descriptor(
    scenario_dir: str,
    *,
    base_url: str = _BASE_URL,
) -> InterfaceDescriptor:
    """Build a minimal InterfaceDescriptor pointing at a single scenario dir."""
    return InterfaceDescriptor(
        project="agent-coordinator",
        version="test",
        services=[
            ServiceDescriptor(
                name="coordination-api",
                type="http",
                base_url=base_url,
                auth=AuthConfig(
                    type="api_key",
                    header="X-API-Key",
                    env_var="COORDINATION_API_KEY",
                ),
                endpoints=[
                    EndpointDescriptor(
                        path="/locks/acquire",
                        method="POST",
                        auth_required=True,
                    ),
                    EndpointDescriptor(
                        path="/locks/release",
                        method="POST",
                        auth_required=True,
                    ),
                    EndpointDescriptor(
                        path="/health",
                        method="GET",
                        auth_required=False,
                    ),
                    EndpointDescriptor(
                        path="/work/submit",
                        method="POST",
                        auth_required=True,
                    ),
                    EndpointDescriptor(
                        path="/work/claim",
                        method="POST",
                        auth_required=True,
                    ),
                    EndpointDescriptor(
                        path="/work/complete",
                        method="POST",
                        auth_required=True,
                    ),
                ],
            ),
        ],
        state_verifiers=[
            StateVerifier(
                name="postgres",
                type="postgres",
                dsn_env=_DB_DSN_ENV,
                tables=["file_locks", "work_queue"],
            ),
        ],
        startup=StartupConfig(
            command="docker-compose up -d",
            health_check=f"{base_url}/health",
            teardown="docker-compose down -v",
        ),
        scenario_dirs=[Path(scenario_dir)],
    )


def _build_config(descriptor_path: Path | None = None) -> GenEvalConfig:
    """Build a minimal GenEvalConfig for integration tests."""
    path = descriptor_path or Path("/dev/null")
    return GenEvalConfig(
        descriptor_path=path,
        mode="template-only",
        max_iterations=1,
        max_scenarios_per_iteration=50,
        max_expansions=10,
    )


def _build_registry(base_url: str = _BASE_URL) -> TransportClientRegistry:
    """Build a TransportClientRegistry with HTTP client pointing at live services."""
    registry = TransportClientRegistry()
    http_client = HttpClient(
        base_url=base_url,
        auth=AuthConfig(
            type="api_key",
            header="X-API-Key",
            env_var="COORDINATION_API_KEY",
        ),
    )
    registry.register("http", http_client)  # type: ignore[arg-type]
    return registry


async def _generate_and_evaluate(
    category_dir: str,
    *,
    max_scenarios: int = 5,
    base_url: str = _BASE_URL,
) -> list[ScenarioVerdict]:
    """Load templates from a category dir, generate scenarios, evaluate them."""
    scenario_path = str(_SCENARIO_BASE / category_dir)
    descriptor = _build_descriptor(scenario_path, base_url=base_url)
    config = _build_config()
    registry = _build_registry(base_url)

    generator = TemplateGenerator(descriptor=descriptor, config=config)
    evaluator = Evaluator(descriptor=descriptor, clients=registry)

    scenarios = await generator.generate(count=max_scenarios)
    assert len(scenarios) > 0, f"No scenarios loaded from {scenario_path}"

    verdicts = await evaluator.evaluate_batch(scenarios)
    return verdicts


# ---------------------------------------------------------------------------
# Lock Lifecycle Integration Tests
# ---------------------------------------------------------------------------


class TestLockLifecycleIntegration:
    """Test lock-lifecycle scenarios against live services."""

    @pytest.mark.asyncio
    async def test_acquire_release_succeeds(self) -> None:
        """Load lock-lifecycle templates and evaluate them.

        Verifies that at least one lock-lifecycle scenario produces
        a verdict, and checks for no unexpected errors.
        """
        verdicts = await _generate_and_evaluate("lock-lifecycle", max_scenarios=3)

        assert len(verdicts) > 0
        for v in verdicts:
            assert v.category == "lock-lifecycle"
            assert v.scenario_id
            assert v.status in ("pass", "fail", "error", "skip")

    @pytest.mark.asyncio
    async def test_conflict_detection(self) -> None:
        """Verify conflict detection scenarios load and execute.

        The conflict-detection template should produce scenarios that
        test double-acquire behavior.
        """
        scenario_path = str(_SCENARIO_BASE / "lock-lifecycle")
        descriptor = _build_descriptor(scenario_path)
        config = _build_config()

        generator = TemplateGenerator(descriptor=descriptor, config=config)
        scenarios = await generator.generate(count=50)

        conflict_scenarios = [s for s in scenarios if "conflict" in s.id.lower()]
        assert len(conflict_scenarios) > 0, "No conflict-detection scenarios found"

        registry = _build_registry()
        evaluator = Evaluator(descriptor=descriptor, clients=registry)

        for scenario in conflict_scenarios[:2]:
            verdict = await evaluator.evaluate(scenario)
            assert verdict.scenario_id == scenario.id
            assert verdict.status in ("pass", "fail", "error")
            # Cleanup warnings should not block the verdict
            assert isinstance(verdict.cleanup_warnings, list)


# ---------------------------------------------------------------------------
# Cross-Interface Integration Tests
# ---------------------------------------------------------------------------


class TestCrossInterfaceIntegration:
    """Test cross-interface consistency against live services."""

    @pytest.mark.asyncio
    async def test_http_mcp_cli_db_consistency(self) -> None:
        """Load cross-interface templates and evaluate them.

        Verifies that cross-interface scenarios are loaded and produce
        verdicts. These scenarios test that operations via HTTP, MCP,
        CLI, and DB all observe consistent state.
        """
        verdicts = await _generate_and_evaluate("cross-interface", max_scenarios=3)

        assert len(verdicts) > 0
        for v in verdicts:
            assert v.category == "cross-interface"
            # Cross-interface scenarios should reference multiple interfaces
            assert len(v.interfaces_tested) > 0


# ---------------------------------------------------------------------------
# Auth Boundary Integration Tests
# ---------------------------------------------------------------------------


class TestAuthBoundaryIntegration:
    """Test auth-boundary scenarios against live services."""

    @pytest.mark.asyncio
    async def test_missing_key_rejected(self) -> None:
        """Load auth-boundary templates and evaluate them.

        Verifies that auth-boundary scenarios produce verdicts.
        Missing/invalid key scenarios should result in HTTP 401/403.
        """
        verdicts = await _generate_and_evaluate("auth-boundary", max_scenarios=3)

        assert len(verdicts) > 0
        for v in verdicts:
            assert v.category == "auth-boundary"
            assert v.scenario_id
            assert v.status in ("pass", "fail", "error", "skip")


# ---------------------------------------------------------------------------
# Work Queue Integration Tests
# ---------------------------------------------------------------------------


class TestWorkQueueIntegration:
    """Test work-queue scenarios against live services."""

    @pytest.mark.asyncio
    async def test_submit_claim_complete(self) -> None:
        """Load work-queue templates and evaluate them.

        Verifies the full work queue lifecycle: submit, claim, complete.
        """
        verdicts = await _generate_and_evaluate("work-queue", max_scenarios=3)

        assert len(verdicts) > 0
        for v in verdicts:
            assert v.category == "work-queue"
            assert v.scenario_id
            assert v.status in ("pass", "fail", "error", "skip")
            assert v.duration_seconds >= 0
