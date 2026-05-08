"""Tests for scripts/ai_dora_snapshot.py.

The script is at the repo's top-level scripts/ — outside skills/ pyproject
testpaths — so run these explicitly:

    pytest scripts/tests/test_ai_dora_snapshot.py -v

Tests use a SubclassedCoordinatorSource that overrides ``_get`` to return canned
JSON, so no live coordinator is required.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ai_dora_snapshot as ads  # noqa: E402


NOW = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)


def make_window(days: int = 7) -> ads.Window:
    return ads.Window(start=NOW - timedelta(days=days), end=NOW)


def audit_entry(
    *,
    operation: str,
    success: bool = True,
    created_at: datetime | None = None,
    result: dict | None = None,
    agent_id: str = "claude-1",
) -> dict:
    return {
        "id": f"e-{operation}-{int((created_at or NOW).timestamp())}",
        "agent_id": agent_id,
        "agent_type": "claude_code",
        "operation": operation,
        "parameters": {},
        "result": result or {},
        "duration_ms": 100,
        "success": success,
        "created_at": (created_at or NOW).isoformat(),
    }


class CannedCoordinator(ads.CoordinatorSource):
    """Coordinator source that returns a fixed audit payload — no network."""

    def __init__(self, entries: list[dict]) -> None:
        super().__init__(api_url="http://x", api_key="k")
        self._entries = entries

    def _get(self, path: str, params: dict[str, str] | None = None) -> dict:  # type: ignore[override]
        return {"entries": list(self._entries)}


# ---------------------------------------------------------------------------
# Window parsing
# ---------------------------------------------------------------------------


class TestWindow:
    def test_days(self) -> None:
        w = ads.parse_window("7d")
        assert w.days == 7

    def test_hours(self) -> None:
        w = ads.parse_window("24h")
        assert w.days == 1

    def test_weeks(self) -> None:
        w = ads.parse_window("2w")
        assert w.days == 14

    def test_invalid(self) -> None:
        with pytest.raises(ValueError):
            ads.parse_window("garbage")


# ---------------------------------------------------------------------------
# CoordinatorSource
# ---------------------------------------------------------------------------


class TestCoordinatorSource:
    def test_unavailable_without_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("COORD_API_URL", raising=False)
        monkeypatch.delenv("COORD_API_KEY", raising=False)
        ok, reason = ads.CoordinatorSource().available()
        assert ok is False
        assert "COORD_API_URL" in reason

    def test_unavailable_without_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COORD_API_URL", "http://x")
        monkeypatch.delenv("COORD_API_KEY", raising=False)
        ok, reason = ads.CoordinatorSource().available()
        assert ok is False
        assert "COORD_API_KEY" in reason

    def test_available_when_both_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COORD_API_URL", "http://x")
        monkeypatch.setenv("COORD_API_KEY", "k")
        ok, _ = ads.CoordinatorSource().available()
        assert ok is True

    def test_get_builds_url_and_headers(self) -> None:
        captured: dict[str, Any] = {}

        class CaptureSource(ads.CoordinatorSource):
            def _get(self, path: str, params: dict[str, str] | None = None) -> dict:
                captured["path"] = path
                captured["params"] = params
                return {"entries": []}

        src = CaptureSource(api_url="http://coord/", api_key="abc")
        src.fetch(make_window(7))
        assert captured["path"] == "/audit"
        assert captured["params"] == {"limit": str(src.fetch_limit)}

    def test_fetch_filters_by_window(self) -> None:
        entries = [
            audit_entry(operation="acquire_lock", created_at=NOW - timedelta(days=1)),
            audit_entry(operation="acquire_lock", created_at=NOW - timedelta(days=10)),
            audit_entry(operation="acquire_lock", created_at=NOW - timedelta(hours=1)),
        ]
        src = CannedCoordinator(entries)
        bundle = src.fetch(make_window(7))
        assert bundle["total_in_window"] == 2

    def test_fetch_buckets_by_operation(self) -> None:
        entries = [
            audit_entry(operation="acquire_lock"),
            audit_entry(operation="release_lock"),
            audit_entry(operation="acquire_lock", success=False),
        ]
        src = CannedCoordinator(entries)
        bundle = src.fetch(make_window(7))
        assert set(bundle["by_operation"].keys()) == {"acquire_lock", "release_lock"}
        assert len(bundle["by_operation"]["acquire_lock"]) == 2

    def test_fetch_skips_entries_with_bad_timestamp(self) -> None:
        entries = [
            audit_entry(operation="x"),
            {**audit_entry(operation="bad"), "created_at": "garbage"},
            {**audit_entry(operation="missing"), "created_at": None},
        ]
        src = CannedCoordinator(entries)
        bundle = src.fetch(make_window(7))
        assert bundle["total_in_window"] == 1

    def test_fetch_limit_hit_flag(self) -> None:
        # Set fetch_limit to 2 so any 2-entry response hits the limit.
        src = CannedCoordinator([
            audit_entry(operation="op1"),
            audit_entry(operation="op2"),
        ])
        src.fetch_limit = 2
        bundle = src.fetch(make_window(7))
        assert bundle["limit_hit"] is True


# ---------------------------------------------------------------------------
# Metric computers — the ones that actually changed with /audit wiring
# ---------------------------------------------------------------------------


class TestToolRetryRate:
    def test_unavailable_without_coordinator(self) -> None:
        m = ads.m_tool_retry_rate({})
        assert m.status == ads.Status.UNAVAILABLE

    def test_unavailable_with_empty_audit(self) -> None:
        m = ads.m_tool_retry_rate({"coordinator": {"entries": []}})
        assert m.status == ads.Status.UNAVAILABLE
        assert "no audit entries" in m.reason

    def test_failure_rate_from_audit(self) -> None:
        bundle = {"coordinator": {"entries": [
            audit_entry(operation="x", success=True),
            audit_entry(operation="x", success=True),
            audit_entry(operation="x", success=False),
            audit_entry(operation="x", success=False),
        ]}}
        m = ads.m_tool_retry_rate(bundle)
        assert m.status == ads.Status.OK
        assert m.value == 0.5

    def test_all_success_means_zero(self) -> None:
        bundle = {"coordinator": {"entries": [
            audit_entry(operation="x", success=True) for _ in range(5)
        ]}}
        m = ads.m_tool_retry_rate(bundle)
        assert m.value == 0.0


class TestVendorReviewDivergence:
    def test_reason_sharper_when_review_ops_present(self) -> None:
        bundle = {"coordinator": {"by_operation": {
            "review_dispatch": [audit_entry(operation="review_dispatch")],
        }}}
        m = ads.m_vendor_review_divergence(bundle)
        assert m.status == ads.Status.UNAVAILABLE
        assert "per-vendor verdict" in m.reason

    def test_reason_when_no_review_ops(self) -> None:
        bundle = {"coordinator": {"by_operation": {"acquire_lock": []}}}
        m = ads.m_vendor_review_divergence(bundle)
        assert "no review_dispatch" in m.reason


class TestCostPerMergedFeature:
    def test_unavailable_without_coordinator(self) -> None:
        m = ads.m_cost_per_merged_feature({})
        assert m.status == ads.Status.UNAVAILABLE

    def test_unavailable_without_token_ops(self) -> None:
        bundle = {"coordinator": {"by_operation": {}}}
        m = ads.m_cost_per_merged_feature(bundle)
        assert m.status == ads.Status.UNAVAILABLE
        assert "phase_token" in m.reason

    def test_token_total_without_repo_source(self) -> None:
        bundle = {"coordinator": {"by_operation": {
            "phase_token_post": [
                audit_entry(operation="phase_token_post", result={"tokens": 1000}),
                audit_entry(operation="phase_token_post", result={"tokens": 500}),
            ],
        }}}
        m = ads.m_cost_per_merged_feature(bundle)
        assert m.status == ads.Status.OK
        assert m.value == 1500
        assert "no merge denominator" in m.unit

    def test_average_when_both_sources_present(self) -> None:
        bundle = {
            "coordinator": {"by_operation": {
                "phase_token_post": [
                    audit_entry(operation="phase_token_post", result={"tokens": 600}),
                    audit_entry(operation="phase_token_post", result={"tokens": 400}),
                ],
            }},
            "repo": {"merges": [{"sha": "a"}, {"sha": "b"}]},
        }
        m = ads.m_cost_per_merged_feature(bundle)
        assert m.status == ads.Status.OK
        assert m.value == 500.0
        assert m.unit == "tokens/merge"

    def test_unavailable_when_no_merges_for_denominator(self) -> None:
        bundle = {
            "coordinator": {"by_operation": {
                "phase_token_post": [
                    audit_entry(operation="phase_token_post", result={"tokens": 100}),
                ],
            }},
            "repo": {"merges": []},
        }
        m = ads.m_cost_per_merged_feature(bundle)
        assert m.status == ads.Status.UNAVAILABLE
        assert "denominator is zero" in m.reason

    def test_falls_back_to_count_field(self) -> None:
        bundle = {"coordinator": {"by_operation": {
            "phase_token_post": [
                audit_entry(operation="phase_token_post", result={"count": 200}),
            ],
        }}}
        m = ads.m_cost_per_merged_feature(bundle)
        assert m.value == 200


class TestLeadTimeForChanges:
    def test_unavailable_with_only_coordinator(self) -> None:
        m = ads.m_lead_time_for_changes({"coordinator": {"entries": []}})
        assert m.status == ads.Status.UNAVAILABLE
        assert "repo=False" in m.reason

    def test_unavailable_with_only_repo(self) -> None:
        m = ads.m_lead_time_for_changes({"repo": {"merges": []}})
        assert m.status == ads.Status.UNAVAILABLE
        assert "coordinator=False" in m.reason


# ---------------------------------------------------------------------------
# End-to-end: render with canned coordinator + repo bundle
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_render_markdown_groups_by_loop(self, capsys: pytest.CaptureFixture[str]) -> None:
        bundle = {
            "coordinator": {
                "entries": [audit_entry(operation="x", success=False)],
                "by_operation": {"phase_token_post": [
                    audit_entry(operation="phase_token_post", result={"tokens": 1000}),
                ]},
            },
            "repo": {"merges": [{"sha": "a"}], "rework_actions": {}, "validation_phases": {}},
        }
        metrics = ads.collect(bundle, make_window(7))
        out = ads.render_markdown(metrics, make_window(7), {"coordinator": "ok", "repo": "ok"})
        assert "## Inner loop" in out
        assert "## Middle loop" in out
        assert "## Outer loop" in out
        # tool_retry_rate computes against canned audit
        assert "`tool_retry_rate`" in out

    def test_render_json_shape(self) -> None:
        out = ads.render_json([], make_window(7), {})
        payload = json.loads(out)
        assert "window" in payload
        assert "metrics" in payload
        assert "sources" in payload
