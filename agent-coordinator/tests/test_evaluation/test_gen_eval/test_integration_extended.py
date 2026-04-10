"""Integration test combining extended assertions, side effects, semantic eval, and manifests.

Tests the full pipeline: model creation → evaluator execution → report generation
with all new feature types working together.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from evaluation.gen_eval.clients.base import StepResult, TransportClientRegistry
from evaluation.gen_eval.descriptor import InterfaceDescriptor
from evaluation.gen_eval.evaluator import Evaluator
from evaluation.gen_eval.feedback import FeedbackSynthesizer
from evaluation.gen_eval.manifest import ManifestEntry, ScenarioPackManifest
from evaluation.gen_eval.models import (
    ActionStep,
    ExpectBlock,
    Scenario,
    SemanticBlock,
    SideEffectsBlock,
    SideEffectStep,
)
from evaluation.gen_eval.semantic_judge import evaluate_semantic


def _make_result(
    status_code: int = 200,
    body: dict[str, Any] | None = None,
) -> StepResult:
    return StepResult(status_code=status_code, body=body or {})


class TestIntegrationExtended:
    """Full integration test combining all new features."""

    def test_scenario_with_all_features(self) -> None:
        """Scenario using extended assertions + side-effects + semantic block."""
        # Build a scenario with everything
        scenario = Scenario(
            id="full-integration-test",
            name="Integration: all features",
            description="Tests extended assertions, side-effects, and semantic eval together",
            category="integration",
            priority=1,
            interfaces=["http", "db"],
            tags=["integration", "e2e"],
            steps=[
                ActionStep(
                    id="create-resource",
                    transport="http",
                    method="POST",
                    endpoint="/resources/create",
                    body={"name": "test-resource", "type": "document"},
                    expect=ExpectBlock(
                        status_one_of=[200, 201],
                        body_contains={"success": True, "resource": {"name": "test-resource"}},
                    ),
                    capture={"resource_id": "$.resource_id"},
                    side_effects=SideEffectsBlock(
                        verify=[
                            SideEffectStep(
                                id="resource-in-db",
                                transport="db",
                                sql="SELECT count(*) as rows FROM resources WHERE name = 'test-resource'",
                                expect=ExpectBlock(rows_gte=1),
                            ),
                        ],
                        prohibit=[
                            SideEffectStep(
                                id="no-duplicate-resources",
                                transport="db",
                                mode="prohibit",
                                sql="SELECT count(*) as rows FROM resources WHERE name = 'test-resource' AND count > 1",
                                expect=ExpectBlock(rows_gte=1),
                            ),
                        ],
                    ),
                    semantic=SemanticBlock(
                        judge=True,
                        criteria="Response should contain a valid resource ID",
                        min_confidence=0.7,
                    ),
                ),
                ActionStep(
                    id="list-resources",
                    transport="http",
                    method="GET",
                    endpoint="/resources",
                    expect=ExpectBlock(
                        status=200,
                        body_excludes={"error": "not_found"},
                        array_contains=[
                            {"path": "$.items", "match": {"name": "test-resource"}},
                        ],
                    ),
                ),
            ],
        )

        # Mock transport results
        registry = TransportClientRegistry()
        client = AsyncMock()
        call_count = 0

        async def mock_execute(step: Any, context: Any) -> StepResult:
            nonlocal call_count
            call_count += 1
            if step.id == "create-resource":
                return _make_result(
                    status_code=201,
                    body={
                        "success": True,
                        "resource": {"name": "test-resource"},
                        "resource_id": "res-123",
                    },
                )
            if step.id == "resource-in-db":
                return _make_result(body={"rows": 1})
            if step.id == "no-duplicate-resources":
                return _make_result(body={"rows": 0})
            if step.id == "list-resources":
                return _make_result(
                    status_code=200,
                    body={"items": [{"name": "test-resource"}, {"name": "other"}]},
                )
            return _make_result()

        client.execute = mock_execute
        registry.register("http", client)
        registry.register("db", client)

        descriptor = MagicMock(spec=InterfaceDescriptor)
        descriptor.all_interfaces.return_value = ["POST /resources/create", "GET /resources"]
        descriptor.total_interface_count.return_value = 2
        evaluator = Evaluator(descriptor=descriptor, clients=registry)

        # Run evaluation
        verdict = asyncio.get_event_loop().run_until_complete(
            evaluator.evaluate(scenario)
        )

        # Verify overall status
        assert verdict.status == "pass"
        assert len(verdict.steps) == 2

        # Verify first step has side-effect verdicts
        step1 = verdict.steps[0]
        assert step1.side_effect_verdicts is not None
        assert len(step1.side_effect_verdicts) == 2
        assert all(v["status"] == "pass" for v in step1.side_effect_verdicts)

        # Verify transport was called for main steps + side-effect steps
        assert call_count >= 4  # 2 main + 2 side-effects

        # Semantic verdict should be skip (no LLM backend configured)
        assert step1.semantic_verdict is not None
        assert step1.semantic_verdict.status == "skip"

    def test_semantic_evaluation_via_evaluator(self) -> None:
        """Evaluator invokes semantic evaluation when LLM backend is provided."""
        scenario = Scenario(
            id="semantic-integration",
            name="Semantic eval via evaluator",
            description="Tests semantic eval wired through evaluator",
            category="test",
            priority=1,
            interfaces=["http"],
            steps=[
                ActionStep(
                    id="search",
                    transport="http",
                    method="GET",
                    endpoint="/search",
                    expect=ExpectBlock(status=200),
                    semantic=SemanticBlock(
                        judge=True,
                        criteria="Results should be relevant to the query",
                        min_confidence=0.7,
                    ),
                ),
            ],
        )

        registry = TransportClientRegistry()
        client = AsyncMock()
        client.execute = AsyncMock(
            return_value=_make_result(
                status_code=200,
                body={"results": [{"title": "relevant result"}]},
            )
        )
        registry.register("http", client)

        # Mock LLM backend
        llm_backend = AsyncMock()
        llm_backend.is_available = AsyncMock(return_value=True)
        llm_backend.run = AsyncMock(
            return_value='{"pass": true, "confidence": 0.9, "reasoning": "Relevant"}'
        )

        descriptor = MagicMock(spec=InterfaceDescriptor)
        descriptor.all_interfaces.return_value = []
        evaluator = Evaluator(
            descriptor=descriptor, clients=registry, llm_backend=llm_backend
        )

        verdict = asyncio.get_event_loop().run_until_complete(
            evaluator.evaluate(scenario)
        )

        assert verdict.status == "pass"
        assert verdict.steps[0].semantic_verdict is not None
        assert verdict.steps[0].semantic_verdict.status == "pass"
        assert verdict.steps[0].semantic_verdict.confidence == 0.9
        llm_backend.run.assert_called_once()

    def test_semantic_fail_causes_step_failure(self) -> None:
        """Semantic evaluation failure should cause step to fail."""
        scenario = Scenario(
            id="semantic-fail",
            name="Semantic fail",
            description="Tests semantic fail",
            category="test",
            priority=1,
            interfaces=["http"],
            steps=[
                ActionStep(
                    id="bad-search",
                    transport="http",
                    method="GET",
                    endpoint="/search",
                    expect=ExpectBlock(status=200),
                    semantic=SemanticBlock(judge=True, criteria="Must be relevant"),
                ),
            ],
        )

        registry = TransportClientRegistry()
        client = AsyncMock()
        client.execute = AsyncMock(
            return_value=_make_result(status_code=200, body={"results": []})
        )
        registry.register("http", client)

        llm_backend = AsyncMock()
        llm_backend.is_available = AsyncMock(return_value=True)
        llm_backend.run = AsyncMock(
            return_value='{"pass": false, "confidence": 0.85, "reasoning": "No results"}'
        )

        descriptor = MagicMock(spec=InterfaceDescriptor)
        descriptor.all_interfaces.return_value = []
        evaluator = Evaluator(
            descriptor=descriptor, clients=registry, llm_backend=llm_backend
        )

        verdict = asyncio.get_event_loop().run_until_complete(
            evaluator.evaluate(scenario)
        )

        assert verdict.status == "fail"
        assert verdict.steps[0].semantic_verdict is not None
        assert verdict.steps[0].semantic_verdict.status == "fail"

    def test_manifest_roundtrip_with_new_entries(self) -> None:
        """Manifest can include E2E scenario entries."""
        manifest = ScenarioPackManifest(
            entries=[
                ManifestEntry(
                    scenario_id="memory-lifecycle-e2e",
                    visibility="public",
                    source="spec",
                    determinism="deterministic",
                    owner="gen-eval",
                    promotion_status="candidate",
                ),
                ManifestEntry(
                    scenario_id="lock-task-workflow-e2e",
                    visibility="public",
                    source="spec",
                ),
            ]
        )
        assert "memory-lifecycle-e2e" in manifest.public_ids()
        assert len(manifest.entries) == 2

    def test_feedback_with_side_effect_and_semantic(self) -> None:
        """FeedbackSynthesizer processes verdicts with new fields."""
        from evaluation.gen_eval.models import ScenarioVerdict, SemanticVerdict, StepVerdict

        step = StepVerdict(
            step_id="s1",
            transport="http",
            status="fail",
            actual={},
            side_effect_verdicts=[
                {"step_id": "verify-1", "mode": "verify", "status": "fail"},
            ],
            semantic_verdict=SemanticVerdict(
                status="skip", reasoning="LLM unavailable"
            ),
        )
        verdict = ScenarioVerdict(
            scenario_id="integration-test",
            scenario_name="Integration",
            status="fail",
            steps=[step],
            interfaces_tested=["http"],
            category="test",
        )

        descriptor = MagicMock(spec=InterfaceDescriptor)
        descriptor.all_interfaces.return_value = ["http"]
        descriptor.total_interface_count.return_value = 1

        synth = FeedbackSynthesizer()
        feedback = synth.synthesize([verdict], descriptor)

        # Should have focus areas from failing interfaces + side-effects + semantic gaps
        assert len(feedback.suggested_focus) > 0
