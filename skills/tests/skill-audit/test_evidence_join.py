"""Evidence join tests (harness-engineering delta; skill-workflow "Coordinator down").

The bridge is stubbed (design D10). Attribution precedence, the unknown
bucket, the 60 % / 3-session concentration rule, source preservation, and
graceful degradation are each pinned to a spec scenario.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from archetype_roster import clear_archetypes_raw_cache, resolve_tier_for_provider
from evidence_join import (
    collect_evidence,
    entries_for_skill,
    fetch_memory_entries,
    load_loop_states,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ROSTER = FIXTURES / "archetypes.yaml"
EVIDENCE = FIXTURES / "evidence"
NOW = datetime(2026, 9, 16, tzinfo=timezone.utc)
MEMORIES = json.loads((EVIDENCE / "memory_response.json").read_text())["memories"]
SESSIONS = json.loads((EVIDENCE / "discovery.json").read_text())["agents"]


def setup_module(module):
    clear_archetypes_raw_cache()


class StubBridge:
    """Records calls; ``recall`` is the full try_recall envelope to return."""

    def __init__(self, recall, sessions=None):
        self.recall = recall
        self.sessions = sessions or []
        self.calls = 0

    def try_recall(self, **kwargs):
        self.calls += 1
        if isinstance(self.recall, Exception):
            raise self.recall
        return self.recall

    def detect_coordination(self, **kwargs):
        return {"COORDINATOR_AVAILABLE": True, "http_url": "http://stub"}

    def _resolve_api_key(self, key):
        return None

    def _http_request(self, **kwargs):
        return {"status_code": 200, "data": {"agents": self.sessions}}


def ok_bridge(sessions=None) -> StubBridge:
    return StubBridge({"status": "ok", "response": {"memories": MEMORIES}}, sessions)


def repo_with_loop_state(tmp_path: Path, *, archived: bool = False) -> Path:
    base = tmp_path / "openspec" / "changes"
    target = base / ("archive/2026-09-15-fixture-change" if archived else "fixture-change")
    target.mkdir(parents=True)
    shutil.copy(EVIDENCE / "loop_state.json", target / "loop-state.json")
    return tmp_path


def _rows(result):
    return {(r["archetype"], r["provider"], r["model"], r["thinking"]): r for r in result.tier_rows}


# --- attribution ------------------------------------------------------------


def test_failure_attributed_through_loop_state(tmp_path):
    repo = repo_with_loop_state(tmp_path)
    result = collect_evidence(
        "implement-feature", window_days=30, bridge=ok_bridge(SESSIONS), repo_root=repo, roster_path=ROSTER, now=NOW
    )
    assert result.status == "available"
    rows = _rows(result)
    model, thinking = resolve_tier_for_provider("claude_code", "standard", path=ROSTER)
    row = rows[("implementer", "claude_code", model, thinking)]
    assert row["attributed_by"] == "loop-state"
    assert row["count"] == 1 and row["max_severity"] == "high"
    assert row["sources"] == ["self-reported"]


def test_loop_state_scan_includes_archive(tmp_path):
    repo = repo_with_loop_state(tmp_path, archived=True)
    states = load_loop_states(repo)
    assert "fixture-change" in states
    result = collect_evidence(
        "implement-feature", window_days=30, bridge=ok_bridge(), repo_root=repo, roster_path=ROSTER, now=NOW
    )
    assert any(r["attributed_by"] == "loop-state" for r in result.tier_rows)


def test_failure_attributed_through_discovery_heartbeat(tmp_path):
    result = collect_evidence(
        "implement-feature", window_days=30, bridge=ok_bridge(SESSIONS), repo_root=tmp_path, roster_path=ROSTER, now=NOW
    )
    rows = _rows(result)
    model, thinking = resolve_tier_for_provider("codex", "premium", path=ROSTER)
    row = rows[("reviewer", "codex", model, thinking)]
    assert row["attributed_by"] == "discovery"
    assert row["count"] == 1
    # The reviewer's earlier implementer session is outside the heartbeat window.
    assert not any(k[0] == "implementer" and k[1] == "codex" for k in rows)


def test_unattributable_failure_is_kept(tmp_path):
    result = collect_evidence(
        "implement-feature", window_days=30, bridge=ok_bridge(), repo_root=tmp_path, roster_path=ROSTER, now=NOW
    )
    rows = _rows(result)
    unknown = rows[("unknown", "unknown", "unknown", None)]
    assert unknown["attributed_by"] == "unknown"
    # m-loop (no loop-state on disk here), m-disc (no sessions), m-unknown, shared-gap: 4 deduped entries
    assert result.total == 4
    assert sum(r["count"] for r in result.tier_rows) == result.total


def test_window_and_skill_filters_apply():
    deduped = entries_for_skill(MEMORIES, "implement-feature", window_days=30, now=NOW)
    ids = {e["id"] for e in deduped}
    assert "m-too-old" not in ids and "m-other-skill" not in ids
    assert len(deduped) == 4  # m-dup-a and m-dup-b merge


# --- sources ---------------------------------------------------------------


def test_sources_are_preserved_through_the_join(tmp_path):
    result = collect_evidence(
        "implement-feature", window_days=30, bridge=ok_bridge(), repo_root=tmp_path, roster_path=ROSTER, now=NOW
    )
    unknown = _rows(result)[("unknown", "unknown", "unknown", None)]
    assert "session-log" in unknown["sources"] and "transcript-mined" in unknown["sources"]
    assert result.multi_source_count == 1  # the shared gap counts once
    assert result.multi_source_fraction == 1 / result.total


# --- concentration -----------------------------------------------------------


def _entry(i: int, session: str, agent_id: str, agent_type: str = "claude_code", created="2026-09-13T10:00:00+00:00"):
    return {
        "id": f"c-{i}",
        "summary": "x",
        "details": {},
        "tags": ["capability_gap", f"capability_gap:gap-{i}", "affected_skill:validate-feature", "severity:medium", "source:self-reported"],
        "created_at": created,
        "session_id": session,
        "agent_id": agent_id,
        "agent_type": agent_type,
    }


def test_concentrated_failure_produces_a_finding(tmp_path):
    runner_sessions = [
        {"agent_id": f"agent-{n}", "started_at": "2026-09-13T09:00:00+00:00", "last_heartbeat": "2026-09-13T11:00:00+00:00", "phase_archetype": "runner"}
        for n in range(4)
    ]
    entries = [
        _entry(0, "s1", "agent-0"),
        _entry(1, "s2", "agent-1"),
        _entry(2, "s3", "agent-2"),
        _entry(3, "s4", "agent-3"),
        _entry(4, "s4", "agent-3"),
        _entry(5, "s5", "nobody"),
        _entry(6, "s6", "nobody"),
    ]
    result = collect_evidence(
        "validate-feature", window_days=30, entries=entries, sessions=runner_sessions, loop_states={}, roster_path=ROSTER, now=NOW
    )
    assert result.total == 7
    haiku = next(r for r in result.tier_rows if r["model"] == "haiku")
    assert haiku["count"] == 5 and haiku["sessions"] == 4
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.kind == "tier_concentrated_failure"
    assert finding.evidence["count"] == "5/7"
    assert "claude_code" in finding.evidence["tier"] and "haiku" in finding.evidence["tier"]
    assert finding.remediation != "delete"


def test_concentration_requires_three_sessions():
    sessions = [
        {"agent_id": "agent-0", "started_at": "2026-09-13T09:00:00+00:00", "last_heartbeat": "2026-09-13T11:00:00+00:00", "phase_archetype": "runner"}
    ]
    entries = [_entry(i, "same-session", "agent-0") for i in range(5)]
    result = collect_evidence(
        "validate-feature", window_days=30, entries=entries, sessions=sessions, loop_states={}, roster_path=ROSTER, now=NOW
    )
    assert result.tier_rows[0]["count"] == 5 and result.tier_rows[0]["sessions"] == 1
    assert result.findings == []


# --- degradation ---------------------------------------------------------------


def test_coordinator_down(tmp_path):
    down = StubBridge({"status": "skipped", "operation": "try_recall", "reason": "coordinator_unreachable", "COORDINATOR_AVAILABLE": False})
    result = collect_evidence("plan-feature", window_days=30, bridge=down, repo_root=tmp_path, roster_path=ROSTER, now=NOW)
    assert result.status == "unavailable"
    assert result.reason == "coordinator_unreachable"
    assert result.tier_rows == []
    assert result.to_ledger() == {"status": "unavailable", "tier_rows": [], "reason": "coordinator_unreachable"}


def test_recall_unauthorized_is_unavailable_not_an_error(tmp_path):
    live_shape = {"status": "skipped", "operation": "try_recall", "reason": "unauthorized", "COORDINATOR_AVAILABLE": True, "COORDINATION_TRANSPORT": "http"}
    result = collect_evidence("plan-feature", window_days=30, bridge=StubBridge(live_shape), repo_root=tmp_path, roster_path=ROSTER, now=NOW)
    assert result.status == "unavailable" and result.reason == "unauthorized"


def test_bridge_exception_and_missing_bridge_degrade():
    boom = StubBridge(RuntimeError("socket closed"))
    result = collect_evidence("plan-feature", window_days=30, bridge=boom, repo_root=None, roster_path=ROSTER, now=NOW)
    assert result.status == "unavailable" and result.reason.startswith("bridge_error")
    entries, reason = fetch_memory_entries(None, window_days=30)
    assert entries is None and reason == "bridge_unavailable"


def test_available_with_no_entries_has_empty_table():
    result = collect_evidence("plan-feature", window_days=30, bridge=ok_bridge(), repo_root=None, roster_path=ROSTER, now=NOW)
    assert result.status == "available" and result.tier_rows == []
    assert result.to_ledger()["multi_source_fraction"] == 0.0


# --- Codex review PR #552 thread 1: memory rows carry no identity fields ------


def test_no_concentration_finding_when_entries_carry_no_session_id():
    """A tier cannot look "concentrated" on the strength of missing identities.

    `POST /memory/query` serializes no `session_id` (and no `agent_id` or
    `agent_type`), so every production row collapses to the single literal
    "unknown" session. The concentration rule needs >= 3 *distinct* sessions, so
    it must not fire here no matter how many entries pile onto one tier —
    otherwise absent data would read as evidence.
    """
    # Distinct gaps, so the (capability_gap, affected_skill, session_id) dedup
    # key does not collapse them first — without session_id it otherwise folds
    # every identical gap into a single row, which is its own consequence of
    # the missing identity fields.
    entries = [
        {
            "tags": [
                f"capability_gap:gap-{i}",
                "affected_skill:demo",
                "severity:high",
                "source:self-reported",
            ],
            "created_at": "2026-09-01T00:00:00+00:00",
            "change_id": "no-such-change",
        }
        for i in range(9)
    ]
    result = collect_evidence(
        "demo",
        window_days=3650,
        entries=entries,
        sessions=[],
        loop_states={},
        roster_path=ROSTER,
        now=NOW,
    )
    assert result.total == 9
    assert [f for f in result.findings if f.kind == "tier_concentrated_failure"] == []
    assert result.tier_rows, "entries are still reported, never dropped"
    assert all(r["sessions"] == 1 for r in result.tier_rows)
    assert all(r["attributed_by"] == "unknown" for r in result.tier_rows)
