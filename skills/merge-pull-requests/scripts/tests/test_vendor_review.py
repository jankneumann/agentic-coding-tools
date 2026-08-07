"""Compatibility tests for pull-request vendor review dispatch."""

from __future__ import annotations

import sys
from pathlib import Path

TEST_PATH = Path(__file__).resolve()
sys.path.insert(0, str(TEST_PATH.parents[3] / "parallel-infrastructure" / "scripts"))
sys.path.insert(0, str(TEST_PATH.parents[1]))

from review_dispatcher import ReviewResult  # noqa: E402
from review_attempts import run_vendor_recovery  # noqa: E402

from vendor_review import build_review_prompt, dispatch_vendor_reviews  # noqa: E402


class _SdkOnlyOrchestrator:
    adapters: dict[str, object] = {}
    sdk_adapters: dict[str, object] = {"codex-remote": object()}

    def __init__(self) -> None:
        self.dispatch_kwargs: dict[str, object] = {}

    def discover_reviewers(self, **_kwargs: object) -> list[object]:
        return [type("Reviewer", (), {"available": True})()]

    def dispatch_and_wait(self, **kwargs: object) -> list[ReviewResult]:
        self.dispatch_kwargs = kwargs
        return [ReviewResult(
            vendor="codex",
            success=True,
            model_used="gpt-test",
            findings={"findings": []},
        )]


def _eligible_review_result() -> ReviewResult:
    chain = run_vendor_recovery(
        logical_request_id="pr-review-codex",
        vendor="codex",
        primary_model="gpt-test",
        fallback_models=[],
        timeout_seconds=10,
        requested_routing={
            "archetype": "reviewer",
            "tier": "premium",
            "phase": "IMPL_REVIEW",
            "source": "test",
            "fallback_reason": None,
        },
        invoke=lambda *_args: {"validation_status": "schema_valid", "findings": []},
    )
    return ReviewResult(
        vendor="codex",
        success=True,
        model_used="gpt-test",
        findings={"findings": []},
        logical_request_id=str(chain["logical_request_id"]),
        requested_vendor=str(chain["requested_vendor"]),
        requested_routing=dict(chain["requested_routing"]),
        deadline_at=str(chain["deadline_at"]),
        budget=dict(chain["budget"]),
        attempts=list(chain["attempts"]),
        terminal_outcome=str(chain["terminal_outcome"]),
        terminal_vendor=str(chain["terminal_vendor"]),
        quorum_eligible=bool(chain["quorum_eligible"]),
    )


class _EligibleOrchestrator(_SdkOnlyOrchestrator):
    def dispatch_and_wait(self, **kwargs: object) -> list[ReviewResult]:
        self.dispatch_kwargs = kwargs
        return [_eligible_review_result()]


def test_review_prompt_uses_canonical_schema_fields() -> None:
    prompt = build_review_prompt(
        8,
        {"additions": 10, "deletions": 1, "changed_files": 1, "files": []},
    )

    assert '"review_type": "implementation"' in prompt
    assert '"axis":' in prompt
    assert '"severity":' in prompt


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
    assert result["vendors"][0] == {
        "vendor": "codex", "success": False, "model_used": "gpt-test",
        "elapsed_seconds": 0.0, "error": None, "findings_count": 0,
        "logical_request_id": None,
        "requested_vendor": None,
        "requested_routing": {},
        "attempts": [],
        "terminal_outcome": None,
        "terminal_vendor": None,
        "quorum_eligible": False,
    }
    assert result["consensus"] is None


def test_pr_review_uses_validated_attempts_and_canonical_review_type(monkeypatch) -> None:
    import review_dispatcher

    orchestrator = _EligibleOrchestrator()
    monkeypatch.setattr(
        review_dispatcher.ReviewOrchestrator,
        "from_coordinator",
        classmethod(lambda _cls: orchestrator),
    )

    result = dispatch_vendor_reviews(
        pr_number=8,
        pr_size={"additions": 10, "deletions": 1, "changed_files": 1, "files": []},
    )

    assert result["vendors"][0]["success"] is True
    assert result["vendors"][0]["attempts"][-1]["terminal"] is True
    assert result["vendors"][0]["terminal_vendor"] == "codex"
    assert result["consensus"]["review_type"] == "implementation"
    assert orchestrator.dispatch_kwargs["review_type"] == "implementation"


def test_pr_review_rejects_success_only_findings(monkeypatch) -> None:
    import review_dispatcher

    class LegacyWithFinding(_SdkOnlyOrchestrator):
        def dispatch_and_wait(self, **_kwargs: object) -> list[ReviewResult]:
            return [ReviewResult(
                vendor="codex",
                success=True,
                model_used="gpt-test",
                findings={"findings": [{
                    "id": 1,
                    "type": "correctness",
                    "criticality": "critical",
                    "description": "legacy success must not vote",
                    "disposition": "fix",
                }]},
            )]

    monkeypatch.setattr(
        review_dispatcher.ReviewOrchestrator,
        "from_coordinator",
        classmethod(lambda _cls: LegacyWithFinding()),
    )

    result = dispatch_vendor_reviews(
        pr_number=9,
        pr_size={"additions": 10, "deletions": 1, "changed_files": 1, "files": []},
    )

    assert result["vendors"][0]["success"] is False
    assert result["consensus"] is None


def test_pr_review_redacts_error_and_discards_invalid_attempt_audit(monkeypatch) -> None:
    import review_dispatcher

    class InvalidAuditOrchestrator(_SdkOnlyOrchestrator):
        def dispatch_and_wait(self, **kwargs: object) -> list[ReviewResult]:
            self.dispatch_kwargs = kwargs
            return [ReviewResult(
                vendor="codex",
                success=False,
                model_used="gpt-test",
                error="token=sk-super-secret " + ("x" * 5000),
                attempts=[{"error_detail": "password=hunter2"}],
            )]

    monkeypatch.setattr(
        review_dispatcher.ReviewOrchestrator,
        "from_coordinator",
        classmethod(lambda _cls: InvalidAuditOrchestrator()),
    )

    result = dispatch_vendor_reviews(
        pr_number=10,
        pr_size={"additions": 10, "deletions": 1, "changed_files": 1, "files": []},
    )

    summary = result["vendors"][0]
    assert "super-secret" not in summary["error"]
    assert len(summary["error"]) <= 4096
    assert summary["attempts"] == []
