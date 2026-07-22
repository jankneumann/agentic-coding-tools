"""Regression coverage for review_dispatcher's script-friendly vendor probe."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from review_dispatcher import (  # type: ignore[import-untyped]
    ReviewOrchestrator,
    ReviewerInfo,
    main,
)


def _orchestrator_with(reviewers: list[ReviewerInfo]) -> MagicMock:
    orchestrator = MagicMock()
    # Keep the coordinator result from falling through to agents.yaml.
    orchestrator.adapters = {"configured": MagicMock()}
    orchestrator.sdk_adapters = {}
    orchestrator.discover_reviewers.return_value = reviewers
    return orchestrator


def test_check_vendors_returns_zero_when_a_reviewer_is_dispatchable() -> None:
    orchestrator = _orchestrator_with(
        [
            ReviewerInfo(
                vendor="codex",
                agent_id="codex-local",
                available=True,
                dispatch_tier="cli",
            ),
        ]
    )

    with (
        patch.object(
            ReviewOrchestrator,
            "from_coordinator",
            return_value=orchestrator,
        ),
        patch.object(sys, "argv", ["review_dispatcher.py", "--check-vendors"]),
    ):
        assert main() == 0

    orchestrator.discover_reviewers.assert_called_once_with(dispatch_mode="review")


def test_check_vendors_returns_nonzero_when_no_reviewer_is_dispatchable() -> None:
    orchestrator = _orchestrator_with([])

    with (
        patch.object(
            ReviewOrchestrator,
            "from_coordinator",
            return_value=orchestrator,
        ),
        patch.object(sys, "argv", ["review_dispatcher.py", "--check-vendors"]),
    ):
        assert main() == 1
