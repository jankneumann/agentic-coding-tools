"""Tests for MergeBackend protocol and implementations.

Covers spec scenarios:
- merge-infrastructure.1: Backend detection with coordinator available
- merge-infrastructure.1: Backend detection with GitHub merge queue
- merge-infrastructure.1: Solo-dev fallback (DirectMergeBackend)

Design decisions:
- D1: MergeBackend protocol for transport-agnostic orchestration
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from merge_backend import (
    CoordinatorTrainBackend,
    DirectMergeBackend,
    GitHubQueueBackend,
    MergeBackend,
    MergeResult,
    detect_merge_backend,
)


class TestMergeBackendProtocol:
    """Verify the MergeBackend protocol contract."""

    def test_direct_merge_implements_protocol(self) -> None:
        backend = DirectMergeBackend()
        assert isinstance(backend, MergeBackend)

    def test_github_queue_implements_protocol(self) -> None:
        backend = GitHubQueueBackend()
        assert isinstance(backend, MergeBackend)

    def test_coordinator_train_implements_protocol(self) -> None:
        backend = CoordinatorTrainBackend(api_url="http://localhost:8081")
        assert isinstance(backend, MergeBackend)

    def test_merge_returns_merge_result(self) -> None:
        backend = DirectMergeBackend()
        with patch("merge_backend.merge_pr") as mock_merge:
            mock_merge.return_value = {
                "action": "merge",
                "success": True,
                "pr_number": 42,
                "strategy": "squash",
            }
            result = backend.merge(pr_number=42, strategy="squash")
        assert isinstance(result, MergeResult)
        assert result.success is True
        assert result.pr_number == 42

    def test_get_queue_status_returns_list(self) -> None:
        backend = DirectMergeBackend()
        status = backend.get_queue_status()
        assert isinstance(status, list)

    def test_supports_train_is_bool(self) -> None:
        assert DirectMergeBackend().supports_train() is False
        assert GitHubQueueBackend().supports_train() is False
        assert CoordinatorTrainBackend(
            api_url="http://localhost:8081",
        ).supports_train() is True

    def test_backend_name_property(self) -> None:
        assert DirectMergeBackend().name == "direct"
        assert GitHubQueueBackend().name == "github_queue"
        assert CoordinatorTrainBackend(
            api_url="http://localhost:8081",
        ).name == "coordinator_train"


class TestDirectMergeBackend:
    """Test the DirectMergeBackend — solo-dev path."""

    def test_merge_delegates_to_merge_pr(self) -> None:
        backend = DirectMergeBackend()
        with patch("merge_backend.merge_pr") as mock_merge:
            mock_merge.return_value = {
                "action": "merge",
                "success": True,
                "pr_number": 99,
                "strategy": "rebase",
            }
            result = backend.merge(pr_number=99, strategy="rebase")

        mock_merge.assert_called_once_with(99, "rebase")
        assert result.success is True
        assert result.strategy == "rebase"
        assert result.backend == "direct"

    def test_merge_failure_propagates(self) -> None:
        backend = DirectMergeBackend()
        with patch("merge_backend.merge_pr") as mock_merge:
            mock_merge.return_value = {
                "action": "merge",
                "success": False,
                "pr_number": 99,
                "error": "PR has merge conflicts",
            }
            result = backend.merge(pr_number=99, strategy="squash")

        assert result.success is False
        assert result.error == "PR has merge conflicts"

    def test_get_queue_status_returns_empty(self) -> None:
        assert DirectMergeBackend().get_queue_status() == []

    def test_supports_train_false(self) -> None:
        assert DirectMergeBackend().supports_train() is False


class TestGitHubQueueBackend:
    """Test the GitHubQueueBackend — GitHub merge queue path."""

    def test_merge_uses_merge_queue_flag(self) -> None:
        backend = GitHubQueueBackend()
        with patch("merge_backend._try_merge_queue") as mock_mq:
            mock_mq.return_value = {
                "action": "merge",
                "success": True,
                "status": "enqueued",
                "pr_number": 42,
                "strategy": "squash",
                "merge_queue": True,
            }
            result = backend.merge(pr_number=42, strategy="squash")

        assert result.success is True
        assert result.backend == "github_queue"
        assert result.status == "enqueued"

    def test_supports_train_false(self) -> None:
        assert GitHubQueueBackend().supports_train() is False


class TestCoordinatorTrainBackend:
    """Test the CoordinatorTrainBackend — coordinator train path."""

    def test_supports_train_true(self) -> None:
        backend = CoordinatorTrainBackend(api_url="http://localhost:8081")
        assert backend.supports_train() is True

    def test_merge_calls_compose_train(self) -> None:
        backend = CoordinatorTrainBackend(api_url="http://localhost:8081")

        mock_requests = MagicMock()
        mock_compose_resp = MagicMock()
        mock_compose_resp.status_code = 200
        mock_compose_resp.json.return_value = {
            "success": True,
            "train_id": "train-abc",
            "partition_count": 2,
        }
        mock_status_resp = MagicMock()
        mock_status_resp.status_code = 200
        mock_status_resp.json.return_value = {
            "entries": [
                {
                    "feature_id": "feat-42",
                    "status": "spec_passed",
                    "train_position": 0,
                },
            ],
        }
        mock_requests.post.return_value = mock_compose_resp
        mock_requests.get.return_value = mock_status_resp

        with patch.dict("sys.modules", {"requests": mock_requests}):
            result = backend.merge(
                pr_number=42, strategy="rebase", feature_id="feat-42",
            )

        assert result.backend == "coordinator_train"
        assert result.train_id == "train-abc"


class TestDetectMergeBackend:
    """Test detect_merge_backend() factory — D1 detection order."""

    def test_coordinator_available_returns_train_backend(self) -> None:
        coordinator_status = {
            "COORDINATOR_AVAILABLE": True,
            "CAN_QUEUE_WORK": True,
        }
        with patch(
            "merge_backend._get_coordinator_status",
            return_value=coordinator_status,
        ):
            backend = detect_merge_backend()
        assert isinstance(backend, CoordinatorTrainBackend)

    def test_coordinator_unavailable_github_queue_returns_queue_backend(
        self,
    ) -> None:
        coordinator_status = {
            "COORDINATOR_AVAILABLE": False,
            "CAN_QUEUE_WORK": False,
        }
        with patch(
            "merge_backend._get_coordinator_status",
            return_value=coordinator_status,
        ):
            with patch(
                "merge_backend._has_github_merge_queue",
                return_value=True,
            ):
                backend = detect_merge_backend()
        assert isinstance(backend, GitHubQueueBackend)

    def test_nothing_available_returns_direct_backend(self) -> None:
        coordinator_status = {
            "COORDINATOR_AVAILABLE": False,
            "CAN_QUEUE_WORK": False,
        }
        with patch(
            "merge_backend._get_coordinator_status",
            return_value=coordinator_status,
        ):
            with patch(
                "merge_backend._has_github_merge_queue",
                return_value=False,
            ):
                backend = detect_merge_backend()
        assert isinstance(backend, DirectMergeBackend)

    def test_coordinator_available_but_cant_queue_falls_through(self) -> None:
        coordinator_status = {
            "COORDINATOR_AVAILABLE": True,
            "CAN_QUEUE_WORK": False,
        }
        with patch(
            "merge_backend._get_coordinator_status",
            return_value=coordinator_status,
        ):
            with patch(
                "merge_backend._has_github_merge_queue",
                return_value=False,
            ):
                backend = detect_merge_backend()
        assert isinstance(backend, DirectMergeBackend)
