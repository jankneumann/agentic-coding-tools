"""Integration test for the full GenEvalOrchestrator run.

Marked with ``@pytest.mark.integration`` — requires docker-compose services.
Tests template-only mode end-to-end: startup, generation, evaluation, report.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from evaluation.gen_eval.clients.base import TransportClientRegistry
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
from evaluation.gen_eval.orchestrator import GenEvalOrchestrator
from evaluation.gen_eval.reports import GenEvalReport

pytestmark = pytest.mark.integration

_BASE_URL = os.environ.get("COORDINATOR_BASE_URL", "http://localhost:8081")
_SCENARIO_BASE = Path(__file__).resolve().parents[3] / "evaluation" / "gen_eval" / "scenarios"


def _build_full_descriptor() -> InterfaceDescriptor:
    """Build a descriptor covering all scenario categories."""
    scenario_dirs = [
        _SCENARIO_BASE / cat
        for cat in ["lock-lifecycle", "auth-boundary", "work-queue", "cross-interface"]
        if (_SCENARIO_BASE / cat).is_dir()
    ]

    return InterfaceDescriptor(
        project="agent-coordinator",
        version="test",
        services=[
            ServiceDescriptor(
                name="coordination-api",
                type="http",
                base_url=_BASE_URL,
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
                ],
            ),
        ],
        state_verifiers=[
            StateVerifier(
                name="postgres",
                type="postgres",
                dsn_env="DATABASE_URL",
                tables=["file_locks", "work_queue"],
            ),
        ],
        startup=StartupConfig(
            command="docker-compose up -d",
            health_check=f"{_BASE_URL}/health",
            teardown="docker-compose down -v",
        ),
        scenario_dirs=scenario_dirs,
    )


class TestOrchestratorIntegration:
    """Integration tests for the full orchestrator pipeline."""

    @pytest.mark.asyncio
    async def test_full_template_only_run(self) -> None:
        """Run the orchestrator in template-only mode with mocked lifecycle.

        Mocks out docker-compose startup/teardown and health checks so we
        can test the orchestrator flow against live HTTP services without
        requiring docker-compose management by the test itself.
        """
        descriptor = _build_full_descriptor()
        config = GenEvalConfig(
            descriptor_path=Path("/dev/null"),
            mode="template-only",
            max_iterations=1,
            max_scenarios_per_iteration=10,
            max_expansions=5,
            parallel_scenarios=2,
            health_check_retries=1,
            health_check_interval_seconds=0.1,
        )

        registry = TransportClientRegistry()
        http_client = HttpClient(
            base_url=_BASE_URL,
            auth=AuthConfig(
                type="api_key",
                header="X-API-Key",
                env_var="COORDINATION_API_KEY",
            ),
        )
        registry.register("http", http_client)  # type: ignore[arg-type]

        generator = TemplateGenerator(descriptor=descriptor, config=config)
        evaluator = Evaluator(descriptor=descriptor, clients=registry)

        orchestrator = GenEvalOrchestrator(
            config=config,
            descriptor=descriptor,
            generator=generator,
            evaluator=evaluator,
        )

        # Mock service lifecycle (we assume services are already running)
        with (
            patch.object(orchestrator, "_run_startup"),
            patch.object(orchestrator, "_health_check"),
            patch.object(orchestrator, "_seed_data"),
            patch.object(orchestrator, "_run_teardown"),
        ):
            report = await orchestrator.run()

        # Verify report structure
        assert isinstance(report, GenEvalReport)
        assert report.total_scenarios > 0
        assert report.iterations_completed == 1
        assert report.passed >= 0
        assert report.failed >= 0
        assert report.errors >= 0
        assert report.pass_rate >= 0.0
        assert report.duration_seconds > 0.0
        assert isinstance(report.per_category, dict)
        assert isinstance(report.per_interface, dict)
        assert isinstance(report.cost_summary, dict)

    @pytest.mark.asyncio
    async def test_report_contains_category_breakdown(self) -> None:
        """Verify the report includes per-category breakdown for evaluated scenarios."""
        descriptor = _build_full_descriptor()
        config = GenEvalConfig(
            descriptor_path=Path("/dev/null"),
            mode="template-only",
            max_iterations=1,
            max_scenarios_per_iteration=5,
            max_expansions=3,
            parallel_scenarios=1,
        )

        registry = TransportClientRegistry()
        http_client = HttpClient(
            base_url=_BASE_URL,
            auth=AuthConfig(
                type="api_key",
                header="X-API-Key",
                env_var="COORDINATION_API_KEY",
            ),
        )
        registry.register("http", http_client)  # type: ignore[arg-type]

        generator = TemplateGenerator(descriptor=descriptor, config=config)
        evaluator = Evaluator(descriptor=descriptor, clients=registry)

        orchestrator = GenEvalOrchestrator(
            config=config,
            descriptor=descriptor,
            generator=generator,
            evaluator=evaluator,
        )

        with (
            patch.object(orchestrator, "_run_startup"),
            patch.object(orchestrator, "_health_check"),
            patch.object(orchestrator, "_seed_data"),
            patch.object(orchestrator, "_run_teardown"),
        ):
            report = await orchestrator.run()

        # At least one category should have been evaluated
        assert len(report.per_category) > 0
        for cat, counts in report.per_category.items():
            assert "total" in counts
            assert counts["total"] > 0
