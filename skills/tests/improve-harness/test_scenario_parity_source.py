"""/improve-harness reads scenario-parity capability gaps through the live memory API shape.

Drives ``analyze_failures.query_memory`` against a local ``http.server`` stub that enforces the
real ``MemoryQueryRequest`` (``agent_id`` required, ``Authorization: Bearer`` checked when a key
is configured), filters rows on ``agent_id`` exactly as ``get_relevant_memories`` does, and
answers with the real ``memories`` list envelope, then feeds the entries
through ``normalize_memory_entries`` / ``rank_findings``.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import threading
import types
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

SKILLS_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = SKILLS_ROOT / "improve-harness" / "scripts" / "analyze_failures.py"
EXAMPLE = Path(__file__).resolve().parent / "fixtures" / "capability-gap-entry.example.json"
API_KEY = "test-key"


@pytest.fixture()
def af() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("analyze_failures_scenario_parity", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


NIGHTLY_AGENT = "agent-scenarios-nightly"  # agent_scenarios.gap_emitter.DEFAULT_AGENT_ID


def _entry(
    vendor: str, run_id: str, created_at: datetime, agent_id: str = NIGHTLY_AGENT
) -> dict[str, Any]:
    """The example payload re-targeted at another vendor / run, as the coordinator returns it."""
    entry = copy.deepcopy(json.loads(EXAMPLE.read_text(encoding="utf-8")))
    entry["details"]["vendor"] = vendor
    entry["details"]["run_id"] = run_id
    entry["session_id"] = run_id
    entry["tags"] = [f"vendor:{vendor}" if t.startswith("vendor:") else t for t in entry["tags"]]
    return {
        "id": f"mem-{vendor}-{run_id}",
        "event_type": entry["event_type"],
        "summary": entry["summary"],
        "details": entry["details"],
        "outcome": None,
        "lessons": [],
        "tags": entry["tags"],
        "relevance_score": 1.0,
        "created_at": created_at.isoformat(),
        "_agent_id": agent_id,  # stored writer; the live API filters on it but never returns it
    }


class _Coordinator:
    def __init__(
        self,
        memories: list[dict[str, Any]],
        *,
        require_key: bool = True,
        forbidden_agents: frozenset[str] = frozenset(),
    ) -> None:
        self.memories = memories
        self.requests: list[dict[str, Any]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:  # silence
                pass

            def _reply(self, status: int, body: dict[str, Any]) -> None:
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self) -> None:  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append({"path": self.path, "body": body,
                                      "auth": self.headers.get("Authorization")})
                if require_key and self.headers.get("Authorization") != f"Bearer {API_KEY}":
                    self._reply(401, {"detail": "unauthorized"})
                    return
                if self.path != "/memory/query":
                    self._reply(404, {"detail": "not found"})
                    return
                if not isinstance(body.get("agent_id"), str):  # MemoryQueryRequest.agent_id
                    self._reply(422, {"detail": "agent_id required"})
                    return
                if body["agent_id"] in forbidden_agents:  # key bound to another agent
                    self._reply(403, {"detail": "API key is not permitted to act as agent_id"})
                    return
                tags = body.get("tags") or []
                limit = int(body.get("limit", 10))
                rows = [
                    {k: v for k, v in m.items() if k != "_agent_id"}
                    for m in outer.memories
                    # get_relevant_memories: WHERE agent_id = p_agent_id (exact)
                    if m["_agent_id"] == body["agent_id"]
                    and (not tags or set(tags) & set(m["tags"]))
                ]
                self._reply(200, {"memories": rows[:limit], "limit": limit, "truncated": False})

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> _Coordinator:
        self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()


NOW = datetime.now(UTC)


def _memories() -> list[dict[str, Any]]:
    return [
        _entry("codex", "nightly-A", NOW - timedelta(days=1)),
        _entry("claude", "nightly-A", NOW - timedelta(days=1)),  # same run, other vendor
        _entry("codex", "nightly-B", NOW - timedelta(hours=2)),  # a later run
        _entry("codex", "nightly-OLD", NOW - timedelta(days=90)),  # outside the 30-day window
    ]


def test_query_memory_returns_scenario_parity_entries(
    af: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _Coordinator(_memories()) as coord:
        monkeypatch.setattr(af, "COORDINATOR_URL", coord.url)
        monkeypatch.setenv("COORDINATION_API_KEY", API_KEY)
        entries = af.query_memory(time_window_days=30, limit=100)
    assert {e["session_id"] if "session_id" in e else e["details"]["run_id"] for e in entries} == {
        "nightly-A", "nightly-B"}
    assert len(entries) == 3  # the 90-day-old entry is dropped client-side
    sent = coord.requests[0]
    assert sent["path"] == "/memory/query"
    assert sent["body"]["agent_id"] == "improve-harness"
    assert sent["body"]["tags"] == ["capability_gap"]
    assert "time_window_days" not in sent["body"]
    assert sent["auth"] == f"Bearer {API_KEY}"


def test_query_memory_without_key_is_rejected_by_a_secured_coordinator(
    af: types.ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with _Coordinator(_memories()) as coord:
        monkeypatch.setattr(af, "COORDINATOR_URL", coord.url)
        monkeypatch.delenv("COORDINATION_API_KEY", raising=False)
        assert af.query_memory() == []
    assert "WARNING" in capsys.readouterr().err


def test_agent_id_override_reaches_the_request(
    af: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _Coordinator(_memories(), require_key=False) as coord:
        monkeypatch.setattr(af, "COORDINATOR_URL", coord.url)
        monkeypatch.setenv("IMPROVE_HARNESS_AGENT_ID", "custom-agent")
        af.query_memory()
    assert coord.requests[0]["body"]["agent_id"] == "custom-agent"


def test_scenario_parity_is_attributed_and_frequency_counts_run_vendor_pairs(
    af: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _Coordinator(_memories()) as coord:
        monkeypatch.setattr(af, "COORDINATOR_URL", coord.url)
        monkeypatch.setenv("COORDINATION_API_KEY", API_KEY)
        entries = af.query_memory(time_window_days=30)
    ranked = af.rank_findings(entries)
    assert len(ranked) == 1
    finding = ranked[0]
    assert finding["capability_gap"] == (
        "scenario-parity/validate-feature-clean-pass/report-has-status")
    assert "scenario-parity" in finding["sources"]
    assert finding["affected_skills"] == ["validate-feature"]
    assert finding["max_severity"] == "high"
    # two vendors in run A (2) + a later run B (1)
    assert finding["frequency"] == 3
    normalized = af.normalize_memory_entries(entries)
    assert {n["source"] for n in normalized} == {"scenario-parity"}


def test_default_query_reaches_the_scenario_parity_writer(
    af: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The coordinator filters agent_id exactly, so the default query must ask for the
    nightly emitter's agent_id too -- querying only ``improve-harness`` finds nothing."""
    with _Coordinator(_memories(), require_key=False) as coord:
        monkeypatch.setattr(af, "COORDINATOR_URL", coord.url)
        monkeypatch.delenv("IMPROVE_HARNESS_AGENT_ID", raising=False)
        assert af.query_memory(agent_id="improve-harness") == []
        coord.requests.clear()
        entries = af.query_memory()
    assert [r["body"]["agent_id"] for r in coord.requests] == ["improve-harness", NIGHTLY_AGENT]
    assert len(entries) == 3


def test_rows_from_several_agents_are_merged_and_deduplicated(
    af: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    own = _entry("codex", "manual-1", NOW - timedelta(days=2), agent_id="improve-harness")
    memories = _memories() + [own, copy.deepcopy(own)]  # a duplicate row id is returned once
    with _Coordinator(memories, require_key=False) as coord:
        monkeypatch.setattr(af, "COORDINATOR_URL", coord.url)
        monkeypatch.setenv(
            "IMPROVE_HARNESS_AGENT_ID", f"improve-harness, {NIGHTLY_AGENT},improve-harness"
        )
        entries = af.query_memory()
    assert [r["body"]["agent_id"] for r in coord.requests] == ["improve-harness", NIGHTLY_AGENT]
    assert sorted(e["id"] for e in entries) == sorted(
        ["mem-codex-manual-1", "mem-codex-nightly-A", "mem-claude-nightly-A", "mem-codex-nightly-B"]
    )


def test_a_forbidden_agent_id_is_skipped_not_fatal(
    af: types.ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with _Coordinator(
        _memories(), require_key=False, forbidden_agents=frozenset({"improve-harness"})
    ) as coord:
        monkeypatch.setattr(af, "COORDINATOR_URL", coord.url)
        monkeypatch.delenv("IMPROVE_HARNESS_AGENT_ID", raising=False)
        entries = af.query_memory()
    assert len(entries) == 3
    assert "WARNING" in capsys.readouterr().err
