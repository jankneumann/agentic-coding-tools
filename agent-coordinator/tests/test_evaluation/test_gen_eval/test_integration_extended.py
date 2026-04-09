"""Integration test: extended assertions + side effects + semantic eval + manifests (Phase 7).

Validates that all new features work together in a realistic scenario
that combines multiple extended assertion types, side-effect verification,
and semantic evaluation in a single multi-step scenario.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from evaluation.gen_eval.clients.base import StepResult, TransportClientRegistry
from evaluation.gen_eval.descriptor import InterfaceDescriptor
from evaluation.gen_eval.evaluator import Evaluator
from evaluation.gen_eval.feedback import FeedbackSynthesizer
from evaluation.gen_eval.manifest import (
    ScenarioManifestEntry,
    ScenarioPackManifest,
    Source,
    Visibility,
    filter_by_visibility,
)
from evaluation.gen_eval.models import (
    ActionStep,
    ExpectBlock,
    Scenario,
    SemanticBlock,
    SideEffectsBlock,
    SideEffectStep,
)
from evaluation.gen_eval.reports import GenEvalReport, generate_markdown_report


def _mock_registry(*results: StepResult) -> TransportClientRegistry:
    registry = MagicMock(spec=TransportClientRegistry)
    registry.execute = AsyncMock(side_effect=list(results))
    return registry


def _mock_descriptor() -> InterfaceDescriptor:
    desc = MagicMock(spec=InterfaceDescriptor)
    desc.total_interface_count.return_value = 5
    desc.all_interfaces.return_value = [
        "POST /memory/store",
        "POST /memory/query",
        "GET /health",
        "mcp:remember",
        "cli:memory",
    ]
    return desc


class TestIntegrationExtended:
    """Full integration: extended assertions + side effects + semantic + manifests."""

    @pytest.mark.asyncio
    async def test_memory_lifecycle_with_all_features(self) -> None:
        """Simulate a full memory lifecycle scenario using all new features."""
        # Step 1: Store memory → success
        store_result = StepResult(
            status_code=200,
            body={"success": True, "memory_id": "mem-001"},
        )
        # Step 2: Query memory → returns results with stored entry
        query_result = StepResult(
            status_code=200,
            body={
                "memories": [
                    {
                        "id": "mem-001",
                        "summary": "Project deadline approaching",
                        "tags": ["deadlines"],
                    },
                    {"id": "mem-002", "summary": "Sprint planning notes", "tags": ["planning"]},
                ],
                "total": 2,
            },
        )
        # Side-effect verify: audit has the store entry
        audit_result = StepResult(
            status_code=200,
            body={"rows": 1, "row": {"action": "store", "agent_id": "agent-1"}},
        )
        # Side-effect prohibit: no working memory entries (only episodic)
        prohibit_result = StepResult(
            status_code=200,
            body={"rows": 0},
        )

        registry = _mock_registry(store_result, query_result, audit_result, prohibit_result)
        evaluator = Evaluator(_mock_descriptor(), registry)

        # Build scenario with all new features
        scenario = Scenario(
            id="memory-lifecycle-integration",
            name="Memory Lifecycle Integration",
            description="Full memory lifecycle with extended assertions and side effects",
            category="memory-crud",
            priority=1,
            interfaces=["http", "db"],
            steps=[
                # Step 1: Store
                ActionStep(
                    id="store",
                    transport="http",
                    method="POST",
                    endpoint="/memory/store",
                    body={"summary": "Project deadline approaching", "tags": ["deadlines"]},
                    expect=ExpectBlock(status=200, body={"success": True}),
                    capture={"memory_id": "$.memory_id"},
                ),
                # Step 2: Query with extended assertions + side effects + semantic
                ActionStep(
                    id="query",
                    transport="http",
                    method="POST",
                    endpoint="/memory/query",
                    body={"tags": ["deadlines"]},
                    expect=ExpectBlock(
                        status=200,
                        body_contains={"memories": [{"tags": ["deadlines"]}]},
                        array_contains={
                            "path": "$.memories",
                            "match": {"id": "mem-001"},
                        },
                    ),
                    side_effects=SideEffectsBlock(
                        verify=[
                            SideEffectStep(
                                id="audit_logged",
                                transport="db",
                                sql="SELECT * FROM audit_log WHERE action='store'",
                                expect=ExpectBlock(rows=1),
                            ),
                        ],
                        prohibit=[
                            SideEffectStep(
                                id="no_working_memory",
                                transport="db",
                                sql="SELECT * FROM memory_working",
                                expect=ExpectBlock(rows_gte=1),
                            ),
                        ],
                    ),
                    semantic=SemanticBlock(
                        judge=True,
                        criteria="Results should be relevant to project deadlines",
                        min_confidence=0.7,
                        fields=["$.memories[*].summary"],
                    ),
                ),
            ],
        )

        mock_judgment = {
            "verdict": "pass",
            "confidence": 0.88,
            "reasoning": "Results contain deadline-related memories",
        }

        with patch(
            "evaluation.gen_eval.evaluator.semantic_judge_evaluate",
            new_callable=AsyncMock,
            return_value=mock_judgment,
        ):
            verdict = await evaluator.evaluate(scenario)

        # Overall verdict should pass
        assert verdict.status == "pass"
        assert len(verdict.steps) == 2

        # Step 1: basic pass
        assert verdict.steps[0].status == "pass"
        assert verdict.steps[0].captured_vars == {"memory_id": "mem-001"}

        # Step 2: extended assertions + side effects + semantic
        step2 = verdict.steps[1]
        assert step2.status == "pass"

        # Side-effect verdicts present
        assert len(step2.side_effect_verdicts) == 2
        assert step2.side_effect_verdicts[0].mode == "verify"
        assert step2.side_effect_verdicts[0].status == "pass"
        assert step2.side_effect_verdicts[1].mode == "prohibit"
        assert step2.side_effect_verdicts[1].status == "pass"

        # Semantic verdict present
        assert step2.semantic_verdict is not None
        assert step2.semantic_verdict.status == "pass"
        assert step2.semantic_verdict.confidence == 0.88

    @pytest.mark.asyncio
    async def test_feedback_includes_all_signal_types(self) -> None:
        """Feedback synthesizer incorporates side-effect and semantic signals."""
        from evaluation.gen_eval.models import (
            ScenarioVerdict,
            SemanticVerdict,
            SideEffectVerdict,
            StepVerdict,
        )

        verdicts = [
            ScenarioVerdict(
                scenario_id="lifecycle-1",
                scenario_name="Lifecycle 1",
                status="fail",
                steps=[
                    StepVerdict(
                        step_id="store",
                        transport="http",
                        status="pass",
                        side_effect_verdicts=[
                            SideEffectVerdict(
                                step_id="audit_check",
                                mode="verify",
                                status="fail",
                                diff={"rows": {"expected": 1, "actual": 0}},
                            ),
                        ],
                        semantic_verdict=SemanticVerdict(
                            status="skip",
                            reasoning="LLM unavailable",
                        ),
                    ),
                ],
                category="memory-crud",
                interfaces_tested=["POST /memory/store"],
            ),
        ]

        synthesizer = FeedbackSynthesizer()
        feedback = synthesizer.synthesize(verdicts, _mock_descriptor())

        # Should include both side-effect and semantic focus items
        focus_str = " ".join(feedback.suggested_focus)
        assert "side-effect-failure:lifecycle-1" in focus_str
        assert "semantic-gap:lifecycle-1" in focus_str

    def test_manifest_visibility_filtering(self) -> None:
        """Manifests correctly filter public vs holdout scenarios."""
        manifests = {
            "memory-crud": ScenarioPackManifest(
                pack="memory-crud",
                scenarios=[
                    ScenarioManifestEntry(
                        id="store-recall",
                        visibility=Visibility.public,
                        source=Source.spec,
                    ),
                    ScenarioManifestEntry(
                        id="edge-case-holdout",
                        visibility=Visibility.holdout,
                        source=Source.manual,
                    ),
                ],
            ),
        }

        all_ids = ["store-recall", "edge-case-holdout", "unclassified"]

        # Public filter
        public = filter_by_visibility(manifests, all_ids, "public")
        assert "store-recall" in public
        assert "unclassified" in public  # Unknown treated as public
        assert "edge-case-holdout" not in public

        # All filter
        all_visible = filter_by_visibility(manifests, all_ids, "all")
        assert len(all_visible) == 3

    @pytest.mark.asyncio
    async def test_report_generation_with_all_features(self) -> None:
        """Report includes side-effect details, semantic confidence, and visibility."""
        from evaluation.gen_eval.models import (
            ScenarioVerdict,
            SemanticVerdict,
            SideEffectVerdict,
            StepVerdict,
        )

        verdict = ScenarioVerdict(
            scenario_id="integration-test",
            scenario_name="Integration Test",
            status="fail",
            steps=[
                StepVerdict(
                    step_id="main",
                    transport="http",
                    status="fail",
                    side_effect_verdicts=[
                        SideEffectVerdict(
                            step_id="audit",
                            mode="verify",
                            status="fail",
                            error_message="Expected 1 row, got 0",
                        ),
                    ],
                    semantic_verdict=SemanticVerdict(
                        status="fail",
                        confidence=0.35,
                        reasoning="Results not relevant",
                    ),
                ),
            ],
            failure_summary="Step main failed",
            category="test",
            interfaces_tested=["POST /test"],
        )

        report = GenEvalReport(
            total_scenarios=1,
            passed=0,
            failed=1,
            errors=0,
            skipped=0,
            pass_rate=0.0,
            coverage_pct=20.0,
            duration_seconds=0.1,
            budget_exhausted=False,
            verdicts=[verdict],
            per_interface={"POST /test": {"pass": 0, "fail": 1, "error": 0}},
            per_category={"test": {"total": 1, "pass": 0, "fail": 1, "error": 0}},
            unevaluated_interfaces=[],
            cost_summary={"cli_calls": 0, "time_minutes": 0.1, "sdk_cost_usd": 0.0},
            iterations_completed=1,
            visibility_summary={
                "public": {"total": 1, "passed": 0, "failed": 1},
            },
        )

        md = generate_markdown_report(report)

        # Should include all three new report sections
        assert "audit" in md  # side-effect step ID
        assert "0.35" in md  # semantic confidence
        assert "public" in md.lower()  # visibility
