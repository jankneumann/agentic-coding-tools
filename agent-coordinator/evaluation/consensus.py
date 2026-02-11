"""Multi-LLM consensus evaluator.

Submits task outputs to multiple LLMs for independent qualitative
assessment. Reports per-judge scores, agreement rate, and flags
significant disagreements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class JudgeScore:
    """Score from a single LLM judge."""

    judge_model: str
    quality_score: float  # 0.0 - 1.0
    reasoning: str = ""
    categories: dict[str, float] = field(default_factory=dict)


@dataclass
class ConsensusResult:
    """Aggregated result from multiple LLM judges."""

    task_id: str
    task_output: str
    judge_scores: list[JudgeScore] = field(default_factory=list)
    agreement_rate: float = 0.0
    consensus_score: float = 0.0
    disagreement: str | None = None  # Flagged if judges diverge significantly

    def compute_consensus(self, threshold: float = 0.3) -> None:
        """Compute agreement rate and flag disagreements.

        Args:
            threshold: Maximum score difference before flagging disagreement.
        """
        if not self.judge_scores:
            return

        scores = [js.quality_score for js in self.judge_scores]
        self.consensus_score = sum(scores) / len(scores)

        if len(scores) < 2:
            self.agreement_rate = 1.0
            return

        # Pairwise agreement: fraction of pairs within threshold
        pairs = 0
        agreements = 0
        for i in range(len(scores)):
            for j in range(i + 1, len(scores)):
                pairs += 1
                if abs(scores[i] - scores[j]) <= threshold:
                    agreements += 1

        self.agreement_rate = agreements / pairs if pairs > 0 else 1.0

        max_diff = max(scores) - min(scores)
        if max_diff > threshold:
            high_judge = max(self.judge_scores, key=lambda js: js.quality_score)
            low_judge = min(self.judge_scores, key=lambda js: js.quality_score)
            self.disagreement = (
                f"{high_judge.judge_model} scored {high_judge.quality_score:.2f} vs "
                f"{low_judge.judge_model} scored {low_judge.quality_score:.2f} "
                f"(diff: {max_diff:.2f})"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "scores": {
                js.judge_model: js.quality_score for js in self.judge_scores
            },
            "agreement_rate": self.agreement_rate,
            "consensus_score": self.consensus_score,
            "disagreement": self.disagreement,
        }


class ConsensusEvaluator:
    """Evaluates task outputs using multiple LLM judges.

    This is a framework class. Actual LLM API calls should be
    implemented by subclasses or injected via a callback.
    """

    def __init__(
        self,
        judge_models: list[str] | None = None,
        score_threshold: float = 0.3,
    ) -> None:
        self._judge_models = judge_models or [
            "claude-sonnet-4-5-20250929",
            "gpt-4o",
        ]
        self._threshold = score_threshold

    async def evaluate(
        self,
        task_id: str,
        task_description: str,
        task_output: str,
        golden_patch: str | None = None,
    ) -> ConsensusResult:
        """Evaluate a task output using all configured judges.

        Subclasses should override _query_judge to implement
        actual LLM API calls.
        """
        result = ConsensusResult(task_id=task_id, task_output=task_output)

        for model in self._judge_models:
            score = await self._query_judge(
                model=model,
                task_description=task_description,
                task_output=task_output,
                golden_patch=golden_patch,
            )
            result.judge_scores.append(score)

        result.compute_consensus(self._threshold)
        return result

    async def _query_judge(
        self,
        model: str,
        task_description: str,
        task_output: str,
        golden_patch: str | None = None,
    ) -> JudgeScore:
        """Query a single LLM judge for a quality assessment.

        Override this method to implement actual API calls.
        Default implementation returns a placeholder score.
        """
        return JudgeScore(
            judge_model=model,
            quality_score=0.0,
            reasoning="Not implemented — override _query_judge with actual LLM API call",
        )
