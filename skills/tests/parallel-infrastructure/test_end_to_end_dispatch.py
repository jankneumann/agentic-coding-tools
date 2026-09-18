"""End-to-end dispatch health test.

Exercises the real multi-vendor dispatch path (CLI + SDK) with a trivial prompt
and asserts that every configured vendor either succeeds or fails gracefully
with a classified error (auth, capacity, unavailable — not a crash or
unclassified UNKNOWN).

This closes the gap left by static health checks: it tests the full
dispatch→subprocess/HTTP→parse→validate pipeline, not just config readability.

Live and opt-in: the tests call real vendors, which costs money and needs
credentials, so they skip unless ``RUN_LIVE_DISPATCH_E2E=1``. The module still
lives in a collected suite, so CI imports it on every run and an import or API
break fails there even though nothing is dispatched.

Run it::

    RUN_LIVE_DISPATCH_E2E=1 skills/.venv/bin/python -m pytest \
        skills/tests/parallel-infrastructure/test_end_to_end_dispatch.py -v -s
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# Imported from the committed canonical scripts directory (put on sys.path by
# this directory's conftest.py), never from a generated runtime copy such as
# .agents/skills/, which does not exist in a clean checkout.
from review_dispatcher import ErrorClass, ReviewOrchestrator

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_DISPATCH_E2E") != "1",
    reason="live vendor dispatch; set RUN_LIVE_DISPATCH_E2E=1 to run",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PING_PROMPT = """\
You are a JSON-only review bot. Emit ONLY a single JSON object with one key: "findings".
No markdown, no prose, no code fences.

The "findings" value must be an array containing exactly one object with these keys:
- "id": 1
- "type": "correctness"
- "criticality": "low"
- "description": "pong"
- "disposition": "accept"
- "axis": "correctness"
- "severity": "fyi"

Example: {"findings":[{"id":1,"type":"correctness","criticality":"low","description":"pong","disposition":"accept","axis":"correctness","severity":"fyi"}]}
"""

MIN_REVIEW_VENDORS = 2  # mirrored from review_dispatcher


def _is_classified(error_class: ErrorClass | None) -> bool:
    """A classified error is any non-UNKNOWN, non-None class."""
    return error_class is not None and error_class != ErrorClass.UNKNOWN


def _orchestrator() -> ReviewOrchestrator:
    """Build orchestrator using the same discovery order as production."""
    # In harness / cloud environments COORDINATION_API_URL is set and
    # points to the live coordinator.  This exercises Tier 1/2 selection.
    return ReviewOrchestrator.from_coordinator()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_orchestrator_can_discover_vendors() -> None:
    """At least MIN_REVIEW_VENDORS vendors must be dispatchable."""
    orch = _orchestrator()
    reviewers = orch.discover_reviewers(dispatch_mode="review")
    available = [r for r in reviewers if r.available]
    vendor_names = sorted({r.vendor for r in available})

    assert len(vendor_names) >= MIN_REVIEW_VENDORS, (
        f"Only {len(vendor_names)} vendor(s) dispatchable "
        f"({', '.join(vendor_names)}); need {MIN_REVIEW_VENDORS}"
    )


def test_end_to_end_dispatch_round_trip() -> None:
    """Dispatch a trivial prompt to all available vendors.

    Every result must either:
      - succeed (success=True, findings present), or
      - fail with a classified error_class (auth, capacity, unavailable, transient)

    Any result with error_class=UNKNOWN or an unexpected exception is a
    regression in our error-surfacing pipeline.
    """
    orch = _orchestrator()
    reviewers = orch.discover_reviewers(dispatch_mode="review")
    available = [r for r in reviewers if r.available]

    if not available:
        pytest.skip("No vendors available for dispatch in this environment")

    results = orch.dispatch_and_wait(
        review_type="e2e-health",
        dispatch_mode="review",
        prompt=PING_PROMPT,
        cwd=Path.cwd(),
    )

    violations: list[str] = []
    aggregate: list[dict] = []

    for r in results:
        info = {
            "vendor": r.vendor,
            "success": r.success,
            "model_used": r.model_used,
            "models_attempted": r.models_attempted,
            "elapsed_seconds": round(r.elapsed_seconds, 2),
            "error": r.error,
            "error_class": r.error_class.value if r.error_class else None,
        }
        aggregate.append(info)

        if r.success:
            assert r.findings is not None, (
                f"{r.vendor} claimed success but returned no findings"
            )
            # Vendors emit only the {"findings": [...]} shape; the review_type
            # /target envelope is added by the caller before consensus.
            findings_arr = r.findings.get("findings") or []
            assert isinstance(findings_arr, list), (
                f"{r.vendor} 'findings' is not an array"
            )
            for i, fnd in enumerate(findings_arr):
                for key in ("id", "type", "criticality", "description",
                            "disposition", "axis", "severity"):
                    assert key in fnd, (
                        f"{r.vendor} finding[{i}] missing required key '{key}'"
                    )
            continue

        # Every failure must be classified. None and UNKNOWN both mean the
        # pipeline failed to surface the cause, so each is a violation on its
        # own, regardless of how the other vendors fared.
        if not _is_classified(r.error_class):
            violations.append(
                f"{r.vendor}: unclassified failure "
                f"(error_class={info['error_class']}, error={r.error!r})"
            )

        # A missing error string on failure usually means an exception path
        # swallowed the real cause.
        if not r.error:
            violations.append(f"{r.vendor}: failure with no error message")

    # Print a human-readable summary even when the test passes
    print("\n=== E2E Dispatch Results ===")
    print(json.dumps(aggregate, indent=2))
    print("============================\n")

    assert results, "dispatch returned no results for available vendors"
    assert not violations, (
        "Vendor failures not surfaced as classified errors:\n  "
        + "\n  ".join(violations)
    )
