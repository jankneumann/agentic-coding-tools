"""Merge backend abstraction for transport-agnostic merge orchestration.

Three implementations selected automatically via detect_merge_backend():
  1. CoordinatorTrainBackend — coordinator merge train with speculative testing
  2. GitHubQueueBackend — GitHub's native merge queue
  3. DirectMergeBackend — direct gh pr merge (solo-dev fallback)

Design decisions: D1 (MergeBackend protocol)
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from merge_pr import _try_merge_queue, merge_pr


@dataclass
class MergeResult:
    success: bool
    pr_number: int
    backend: str
    strategy: str | None = None
    status: str | None = None
    error: str | None = None
    train_id: str | None = None
    partition_count: int | None = None
    raw: dict = field(default_factory=dict)


@runtime_checkable
class MergeBackend(Protocol):
    @property
    def name(self) -> str: ...
    def merge(self, *, pr_number: int, strategy: str, **kwargs: Any) -> MergeResult: ...
    def get_queue_status(self) -> list[dict]: ...
    def supports_train(self) -> bool: ...


class DirectMergeBackend:
    @property
    def name(self) -> str:
        return "direct"

    def merge(self, *, pr_number: int, strategy: str, **kwargs: Any) -> MergeResult:
        raw = merge_pr(pr_number, strategy)
        return MergeResult(
            success=raw.get("success", False),
            pr_number=pr_number,
            backend="direct",
            strategy=raw.get("strategy", strategy),
            status=raw.get("status"),
            error=raw.get("error"),
            raw=raw,
        )

    def get_queue_status(self) -> list[dict]:
        return []

    def supports_train(self) -> bool:
        return False


class GitHubQueueBackend:
    @property
    def name(self) -> str:
        return "github_queue"

    def merge(self, *, pr_number: int, strategy: str, **kwargs: Any) -> MergeResult:
        is_fork = kwargs.get("is_fork", False)
        branch = kwargs.get("branch", "")
        raw = _try_merge_queue(pr_number, strategy, is_fork, branch=branch)
        return MergeResult(
            success=raw.get("success", False),
            pr_number=pr_number,
            backend="github_queue",
            strategy=raw.get("strategy", strategy),
            status=raw.get("status"),
            error=raw.get("error"),
            raw=raw,
        )

    def get_queue_status(self) -> list[dict]:
        return []

    def supports_train(self) -> bool:
        return False


class CoordinatorTrainBackend:
    def __init__(self, *, api_url: str, api_key: str | None = None) -> None:
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "coordinator_train"

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        return headers

    def merge(self, *, pr_number: int, strategy: str, **kwargs: Any) -> MergeResult:
        try:
            import requests
        except ImportError:
            return MergeResult(
                success=False,
                pr_number=pr_number,
                backend="coordinator_train",
                error="requests library not available for coordinator communication",
            )

        feature_id = kwargs.get("feature_id", f"pr-{pr_number}")

        try:
            compose_resp = requests.post(
                f"{self._api_url}/merge-train/compose",
                headers=self._headers(),
                timeout=30,
            )
            if compose_resp.status_code != 200:
                return MergeResult(
                    success=False,
                    pr_number=pr_number,
                    backend="coordinator_train",
                    error=f"compose_train failed: HTTP {compose_resp.status_code}",
                )
            compose_data = compose_resp.json()
            train_id = compose_data.get("train_id", "")

            status_resp = requests.get(
                f"{self._api_url}/merge-train/status/{train_id}",
                headers=self._headers(),
                timeout=30,
            )
            if status_resp.status_code == 200:
                status_data = status_resp.json()
                entries = status_data.get("entries", [])
                entry = next(
                    (e for e in entries if e.get("feature_id") == feature_id),
                    None,
                )
                if entry and entry.get("status") == "spec_passed":
                    return MergeResult(
                        success=True,
                        pr_number=pr_number,
                        backend="coordinator_train",
                        strategy=strategy,
                        status="merged",
                        train_id=train_id,
                        partition_count=compose_data.get("partition_count"),
                        raw=compose_data,
                    )

            return MergeResult(
                success=True,
                pr_number=pr_number,
                backend="coordinator_train",
                strategy=strategy,
                status="speculating",
                train_id=train_id,
                partition_count=compose_data.get("partition_count"),
                raw=compose_data,
            )

        except Exception as exc:
            return MergeResult(
                success=False,
                pr_number=pr_number,
                backend="coordinator_train",
                error=str(exc),
            )

    def get_queue_status(self) -> list[dict]:
        try:
            import requests
            resp = requests.get(
                f"{self._api_url}/work/queue",
                headers=self._headers(),
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json().get("entries", [])
        except Exception:
            pass
        return []

    def supports_train(self) -> bool:
        return True


def _get_coordinator_status() -> dict:
    try:
        result = subprocess.run(
            [
                "python3",
                str(
                    Path(__file__).resolve().parent.parent.parent
                    / "coordination-bridge/scripts/check_coordinator.py"
                ),
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        pass
    return {"COORDINATOR_AVAILABLE": False, "CAN_QUEUE_WORK": False}


def _has_github_merge_queue() -> bool:
    try:
        result = subprocess.run(
            [
                "gh", "api", "repos/:owner/:repo",
                "--jq", ".allow_merge_commit",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def detect_merge_backend() -> MergeBackend:
    status = _get_coordinator_status()

    if status.get("COORDINATOR_AVAILABLE") and status.get("CAN_QUEUE_WORK"):
        import os
        api_url = status.get(
            "coordinator_url",
            os.environ.get("COORDINATION_API_URL", "http://localhost:8081"),
        )
        api_key = os.environ.get("COORDINATION_API_KEY")
        return CoordinatorTrainBackend(api_url=api_url, api_key=api_key)

    if _has_github_merge_queue():
        return GitHubQueueBackend()

    return DirectMergeBackend()
