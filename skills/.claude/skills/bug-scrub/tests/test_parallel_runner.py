"""Tests for parallel_runner — ThreadPoolExecutor-based collector execution."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# sys.path insertion so we can import modules from scripts/
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from models import Finding, SourceResult
from parallel_runner import run_collectors_parallel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ok_collector(source: str, findings: list[Finding] | None = None):
    """Return a collector function that succeeds."""

    def _collect(project_dir: str) -> SourceResult:
        return SourceResult(
            source=source,
            status="ok",
            findings=findings or [],
            duration_ms=1,
        )

    return _collect


def _slow_collector(source: str, delay: float):
    """Return a collector that sleeps for *delay* seconds."""

    def _collect(project_dir: str) -> SourceResult:
        time.sleep(delay)
        return SourceResult(source=source, status="ok", duration_ms=1)

    return _collect


def _failing_collector(source: str, exc: Exception):
    """Return a collector that raises *exc*."""

    def _collect(project_dir: str) -> SourceResult:
        raise exc

    return _collect


# ========================================================================
# Test cases
# ========================================================================


class TestParallelRunnerBasic:
    """Core functionality tests."""

    def test_empty_collectors(self) -> None:
        """No collectors produces empty result list."""
        results = run_collectors_parallel({}, "/tmp/proj")
        assert results == []

    def test_single_collector_success(self) -> None:
        """Single collector returns its result."""
        collectors = {"pytest": _ok_collector("pytest")}
        results = run_collectors_parallel(collectors, "/tmp/proj")
        assert len(results) == 1
        assert results[0].source == "pytest"
        assert results[0].status == "ok"

    def test_multiple_collectors_success(self) -> None:
        """Multiple collectors all succeed."""
        finding = Finding(
            id="ruff-1",
            source="ruff",
            severity="low",
            category="lint",
            title="Unused import",
        )
        collectors = {
            "pytest": _ok_collector("pytest"),
            "ruff": _ok_collector("ruff", [finding]),
            "mypy": _ok_collector("mypy"),
        }
        results = run_collectors_parallel(collectors, "/tmp/proj")
        assert len(results) == 3
        assert [r.source for r in results] == ["pytest", "ruff", "mypy"]
        assert results[1].findings == [finding]


class TestParallelRunnerFailure:
    """Error handling tests."""

    def test_failed_collector_returns_error_sourceresult(self) -> None:
        """A collector that raises returns an error SourceResult; others continue."""
        collectors = {
            "pytest": _ok_collector("pytest"),
            "ruff": _failing_collector("ruff", RuntimeError("ruff crashed")),
            "mypy": _ok_collector("mypy"),
        }
        results = run_collectors_parallel(collectors, "/tmp/proj")
        assert len(results) == 3
        assert results[0].status == "ok"
        assert results[1].status == "error"
        assert "ruff crashed" in results[1].messages[0]
        assert results[2].status == "ok"

    def test_timeout_returns_error_sourceresult(self) -> None:
        """A collector that exceeds timeout returns error SourceResult."""
        collectors = {
            "fast": _ok_collector("fast"),
            "slow": _slow_collector("slow", delay=5.0),
        }
        results = run_collectors_parallel(
            collectors, "/tmp/proj", timeout_per_collector=1
        )
        assert len(results) == 2
        assert results[0].status == "ok"
        assert results[1].status == "error"
        assert "timed out" in results[1].messages[0]


class TestParallelRunnerOrdering:
    """Submission order preservation tests."""

    def test_results_in_submission_order(self) -> None:
        """Results match dict key insertion order regardless of completion time."""
        collectors = {
            "slow": _slow_collector("slow", delay=0.2),
            "fast": _ok_collector("fast"),
            "medium": _slow_collector("medium", delay=0.1),
        }
        results = run_collectors_parallel(collectors, "/tmp/proj")
        assert [r.source for r in results] == ["slow", "fast", "medium"]

    def test_mixed_success_and_failure_order(self) -> None:
        """Order is preserved even when some collectors fail."""
        collectors = {
            "a": _ok_collector("a"),
            "b": _failing_collector("b", ValueError("boom")),
            "c": _ok_collector("c"),
            "d": _failing_collector("d", TypeError("type error")),
        }
        results = run_collectors_parallel(collectors, "/tmp/proj")
        assert [r.source for r in results] == ["a", "b", "c", "d"]
        assert [r.status for r in results] == ["ok", "error", "ok", "error"]


class TestParallelRunnerMaxWorkers:
    """Thread pool configuration tests."""

    def test_max_workers_parameter_is_respected(self) -> None:
        """max_workers is forwarded to ThreadPoolExecutor."""
        collectors = {"a": _ok_collector("a")}
        with patch(
            "parallel_runner.ThreadPoolExecutor", wraps=__import__(
                "concurrent.futures", fromlist=["ThreadPoolExecutor"]
            ).ThreadPoolExecutor
        ) as mock_pool:
            run_collectors_parallel(
                collectors, "/tmp/proj", max_workers=3
            )
            mock_pool.assert_called_once_with(max_workers=3)


class TestParallelRunnerEquivalence:
    """Verify parallel results match sequential execution."""

    def test_sequential_equivalence(self) -> None:
        """Parallel and sequential runs produce the same SourceResult lists.

        Compares source, status, findings, and messages — excludes duration_ms.
        """
        finding_a = Finding(
            id="f-1",
            source="a",
            severity="high",
            category="test-failure",
            title="Failure A",
        )
        finding_b = Finding(
            id="f-2",
            source="b",
            severity="low",
            category="lint",
            title="Lint B",
        )

        collectors = {
            "a": _ok_collector("a", [finding_a]),
            "b": _ok_collector("b", [finding_b]),
            "c": _ok_collector("c"),
        }

        # Sequential execution
        sequential_results: list[SourceResult] = []
        for name, func in collectors.items():
            sequential_results.append(func("/tmp/proj"))

        # Parallel execution
        parallel_results = run_collectors_parallel(
            collectors, "/tmp/proj"
        )

        assert len(sequential_results) == len(parallel_results)
        for seq, par in zip(sequential_results, parallel_results):
            assert seq.source == par.source
            assert seq.status == par.status
            assert seq.findings == par.findings
            assert seq.messages == par.messages
