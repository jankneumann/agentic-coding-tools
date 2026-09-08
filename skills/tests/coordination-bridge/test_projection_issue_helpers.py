"""Coordinator-only label helpers never route through the GitHub backend."""

from __future__ import annotations

from typing import Any

import coordination_bridge as bridge


def test_projection_label_helpers_bypass_github_and_bound_listing(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        bridge,
        "_github_issue_dispatch",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("GitHub routing used")),
    )
    monkeypatch.setattr(
        bridge,
        "_execute_single_endpoint_operation",
        lambda **kw: calls.append(kw) or {"status": "ok"},
    )

    bridge.try_projection_issue_list(
        labels=["change:demo", "projection:autopilot-phase"],
        limit=1000,
        http_url="https://coordinator.invalid",
    )
    bridge.try_projection_issue_update(
        issue_id="row", labels=[], http_url="https://coordinator.invalid"
    )

    assert calls[0]["path"] == "/issues/list"
    assert calls[0]["payload"]["limit"] == 100
    assert calls[1]["path"] == "/issues/update"
    assert calls[1]["payload"] == {"issue_id": "row", "labels": []}



def test_projection_issue_update_rejects_http_200_business_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        bridge,
        "_execute_single_endpoint_operation",
        lambda **_kw: {
            "status": "ok",
            "operation": "try_projection_issue_update",
            "response": {"success": False, "reason": "issue_not_found"},
        },
    )

    result = bridge.try_projection_issue_update(
        issue_id="missing", labels=[], http_url="https://coordinator.invalid"
    )

    assert result["status"] == "failed"
    assert result["reason"] == "issue_not_found"
