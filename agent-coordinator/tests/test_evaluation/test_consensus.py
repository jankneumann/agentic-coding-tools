"""Tests for consensus evaluator."""

import pytest

from evaluation.consensus import ConsensusEvaluator, ConsensusResult, JudgeScore


class TestConsensusResult:
    def test_compute_consensus_agreement(self):
        result = ConsensusResult(
            task_id="t1",
            task_output="output",
            judge_scores=[
                JudgeScore(judge_model="model-a", quality_score=0.8),
                JudgeScore(judge_model="model-b", quality_score=0.85),
            ],
        )
        result.compute_consensus(threshold=0.3)

        assert result.consensus_score == pytest.approx(0.825)
        assert result.agreement_rate == 1.0  # Within threshold
        assert result.disagreement is None

    def test_compute_consensus_disagreement(self):
        result = ConsensusResult(
            task_id="t1",
            task_output="output",
            judge_scores=[
                JudgeScore(judge_model="model-a", quality_score=0.9),
                JudgeScore(judge_model="model-b", quality_score=0.3),
            ],
        )
        result.compute_consensus(threshold=0.3)

        assert result.agreement_rate == 0.0
        assert result.disagreement is not None
        assert "model-a" in result.disagreement
        assert "model-b" in result.disagreement

    def test_single_judge(self):
        result = ConsensusResult(
            task_id="t1",
            task_output="output",
            judge_scores=[
                JudgeScore(judge_model="model-a", quality_score=0.8),
            ],
        )
        result.compute_consensus()

        assert result.agreement_rate == 1.0
        assert result.consensus_score == 0.8

    def test_empty_judges(self):
        result = ConsensusResult(task_id="t1", task_output="output")
        result.compute_consensus()
        assert result.agreement_rate == 0.0
        assert result.consensus_score == 0.0

    def test_to_dict(self):
        result = ConsensusResult(
            task_id="t1",
            task_output="output",
            judge_scores=[
                JudgeScore(judge_model="model-a", quality_score=0.8),
            ],
        )
        result.compute_consensus()

        d = result.to_dict()
        assert d["task_id"] == "t1"
        assert "model-a" in d["scores"]


class TestConsensusEvaluator:
    @pytest.mark.asyncio
    async def test_evaluate_default(self):
        evaluator = ConsensusEvaluator(judge_models=["model-a", "model-b"])
        result = await evaluator.evaluate(
            task_id="t1",
            task_description="Fix a bug",
            task_output="patched code",
        )

        assert result.task_id == "t1"
        assert len(result.judge_scores) == 2
        # Default implementation returns 0.0 scores
        assert all(js.quality_score == 0.0 for js in result.judge_scores)
