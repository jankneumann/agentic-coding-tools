"""Compatibility tests for pull-request vendor review dispatch."""

from __future__ import annotations

import sys
from pathlib import Path

from review_dispatcher import ReviewResult

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vendor_review import dispatch_vendor_reviews


class _SdkOnlyOrchestrator:
    adapters: dict[str, object] = {}
    sdk_adapters: dict[str, object] = {"codex-remote": object()}

    def discover_reviewers(self, **_kwargs: object) -> list[object]:
        return [type("Reviewer", (), {"available": True})()]

    def dispatch_and_wait(self, **_kwargs: object) -> list[ReviewResult]:
        return [ReviewResult(
            vendor="codex",
            success=True,
            model_used="gpt-test",
            findings={"findings": []},
        )]


def test_pr_review_accepts_sdk_only_orchestrator(monkeypatch) -> None:
    """A caller must not discard an SDK-capable dispatcher as unconfigured."""
    import review_dispatcher

    orchestrator = _SdkOnlyOrchestrator()
    monkeypatch.setattr(
        review_dispatcher.ReviewOrchestrator,
        "from_coordinator",
        classmethod(lambda _cls: orchestrator),
    )
    monkeypatch.setattr(
        review_dispatcher.ReviewOrchestrator,
        "from_agents_yaml",
        classmethod(lambda _cls: (_ for _ in ()).throw(AssertionError("unexpected fallback"))),
    )

    result = dispatch_vendor_reviews(
        pr_number=7,
        pr_size={"additions": 60, "deletions": 1, "changed_files": 4, "files": []},
    )

    assert result["dispatched"] is True
    assert result["vendors"] == [{
        "vendor": "codex", "success": True, "model_used": "gpt-test",
        "elapsed_seconds": 0.0, "error": None, "findings_count": 0,
    }]
