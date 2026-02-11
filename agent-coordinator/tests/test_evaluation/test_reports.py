"""Tests for report generation."""

import json

import pytest

from evaluation.metrics import (
    AggregatedMetrics,
    TaskMetrics,
    TokenUsage,
    TrialMetrics,
)
from evaluation.reports.generator import ReportGenerator


@pytest.fixture
def sample_task_metrics():
    """Create sample task metrics for report testing."""
    metrics = []
    for trial in range(3):
        m = TaskMetrics(
            task_id="test-task-1",
            trial_num=trial + 1,
            backend_name="claude_code",
            ablation_label="all-on",
            wall_clock_seconds=10.0 + trial,
            success=True,
        )
        m.token_usage = TokenUsage(
            input_tokens=500,
            output_tokens=200,
            total_tokens=700,
            estimated_cost_usd=0.01,
        )
        m.correctness.test_pass_rate = 0.9
        metrics.append(m)
    return metrics


@pytest.fixture
def sample_trial_metrics():
    """Create sample trial metrics for report testing."""
    return [
        TrialMetrics(
            task_id="test-task-1",
            backend_name="claude_code",
            ablation_label="all-on",
            num_trials=3,
            wall_clock=AggregatedMetrics.from_values([10.0, 11.0, 12.0]),
            total_tokens=AggregatedMetrics.from_values([700.0, 700.0, 700.0]),
            cost_usd=AggregatedMetrics.from_values([0.01, 0.01, 0.01]),
            test_pass_rate=AggregatedMetrics.from_values([0.9, 0.9, 0.9]),
            coordination_overhead=AggregatedMetrics.from_values([5.0, 6.0, 5.5]),
            speedup_factor=AggregatedMetrics.from_values([1.0, 1.0, 1.0]),
            success_rate=1.0,
        ),
    ]


class TestReportGenerator:
    def test_generate_creates_files(self, tmp_path, sample_task_metrics, sample_trial_metrics):
        generator = ReportGenerator(tmp_path)
        md_path, json_path = generator.generate(
            task_metrics=sample_task_metrics,
            trial_metrics=sample_trial_metrics,
            run_id="test-run-001",
        )

        assert md_path.exists()
        assert json_path.exists()
        assert md_path.name == "test-run-001.md"
        assert json_path.name == "test-run-001.json"

    def test_markdown_content(self, tmp_path, sample_task_metrics, sample_trial_metrics):
        generator = ReportGenerator(tmp_path)
        md_path, _ = generator.generate(
            task_metrics=sample_task_metrics,
            trial_metrics=sample_trial_metrics,
            run_id="test-run-002",
        )

        content = md_path.read_text()
        assert "# Evaluation Report: test-run-002" in content
        assert "test-task-1" in content
        assert "claude_code" in content
        assert "100%" in content  # success rate

    def test_json_content(self, tmp_path, sample_task_metrics, sample_trial_metrics):
        generator = ReportGenerator(tmp_path)
        _, json_path = generator.generate(
            task_metrics=sample_task_metrics,
            trial_metrics=sample_trial_metrics,
            run_id="test-run-003",
        )

        data = json.loads(json_path.read_text())
        assert data["metadata"]["run_id"] == "test-run-003"
        assert len(data["raw_metrics"]) == 3
        assert len(data["trial_summaries"]) == 1

    def test_config_summary(self, tmp_path, sample_task_metrics, sample_trial_metrics):
        generator = ReportGenerator(tmp_path)
        md_path, json_path = generator.generate(
            task_metrics=sample_task_metrics,
            trial_metrics=sample_trial_metrics,
            run_id="test-run-004",
            config_summary={"num_tasks": 5, "backends": ["claude_code"]},
        )

        md_content = md_path.read_text()
        assert "Configuration" in md_content

        json_data = json.loads(json_path.read_text())
        assert json_data["metadata"]["config"]["num_tasks"] == 5

    def test_consensus_results(self, tmp_path, sample_task_metrics, sample_trial_metrics):
        generator = ReportGenerator(tmp_path)
        consensus = [
            {
                "task_id": "test-task-1",
                "scores": {"claude-sonnet": 0.85, "gpt-4o": 0.80},
                "agreement_rate": 0.9,
                "disagreement": None,
            }
        ]

        md_path, json_path = generator.generate(
            task_metrics=sample_task_metrics,
            trial_metrics=sample_trial_metrics,
            run_id="test-run-005",
            consensus_results=consensus,
        )

        md_content = md_path.read_text()
        assert "Consensus Evaluation" in md_content

    def test_output_dir_created(self, tmp_path, sample_task_metrics, sample_trial_metrics):
        nested = tmp_path / "deep" / "nested" / "dir"
        generator = ReportGenerator(nested)
        md_path, _ = generator.generate(
            task_metrics=sample_task_metrics,
            trial_metrics=sample_trial_metrics,
            run_id="test-run-006",
        )
        assert md_path.exists()
