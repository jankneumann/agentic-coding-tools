"""Capability-gap emission, sinks and spool (tasks 4.1-4.3)."""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from agent_scenarios.gap_emitter import (
    CoordinatorMemorySink,
    SpoolMemorySink,
    add_parser,
    build_gap_entries,
    emit_gaps,
    flush_spool,
)
from agent_scenarios.models import (
    GateVerdict,
    ParityMatrix,
    TrajectoryFinding,
    TrajectoryVerdict,
    VendorRunVerdict,
)
from tests.test_schemas import load_schema

SCHEMA = load_schema("capability-gap-entry.schema.json")
EXAMPLE = load_schema("capability-gap-entry.example.json")


def gate(gid: str, status: str = "fail", detail: str = "d") -> GateVerdict:
    return GateVerdict(gate_id=gid, check="file", mode="verify", status=status, detail=detail)  # type: ignore[arg-type]


def verdict(vendor: str, status: str, gates: list[GateVerdict], **kw: Any) -> VendorRunVerdict:
    return VendorRunVerdict(
        scenario_id="validate-feature-clean-pass", vendor=vendor, gate_verdicts=gates,
        trajectory=kw.pop("trajectory", TrajectoryVerdict(status="skip")),
        deterministic_status=status, **kw,  # type: ignore[arg-type]
    )


def matrix(*verdicts: VendorRunVerdict) -> ParityMatrix:
    return ParityMatrix(scenario_id="validate-feature-clean-pass", scenario_name="n",
                        results=list(verdicts))


SKILL_OF = {"validate-feature-clean-pass": "validate-feature"}


def build(*verdicts: VendorRunVerdict) -> list[dict[str, Any]]:
    return build_gap_entries("nightly-1", [matrix(*verdicts)], skill_of=SKILL_OF,
                             repo_sha="r", skills_sha="s")


# --- construction ---------------------------------------------------------------------


def test_fail_produces_tagged_entry_matching_schema_and_example() -> None:
    entries = build(verdict("codex", "fail", [gate("ok", "pass"), gate("report-has-status")]))
    assert len(entries) == 1
    e = entries[0]
    jsonschema.validate(e, SCHEMA)
    assert e["session_id"] == "nightly-1" and e["details"]["run_id"] == "nightly-1"
    assert e["summary"] == "[codex] scenario validate-feature-clean-pass failed gates: report-has-status"
    assert set(e["tags"]) == set(EXAMPLE["tags"])
    assert e["event_type"] == "capability_gap" and e["agent_id"] == "agent-scenarios-nightly"
    assert e["details"]["skills_sha"] == "s" and e["details"]["repo_sha"] == "r"


def test_gap_key_uses_first_failed_gate_in_declaration_order() -> None:
    e = build(verdict("claude", "fail", [gate("z-first"), gate("a-second")]))[0]
    assert "capability_gap:scenario-parity/validate-feature-clean-pass/z-first" in e["tags"]
    assert [g["gate_id"] for g in e["details"]["failed_gates"]] == ["z-first", "a-second"]


def test_detail_truncated_to_500_chars() -> None:
    e = build(verdict("claude", "fail", [gate("g", detail="x" * 2000)]))[0]
    assert len(e["details"]["failed_gates"][0]["detail"]) == 500
    jsonschema.validate(e, SCHEMA)


def test_errors_and_judge_findings_emit_nothing() -> None:
    judged = TrajectoryVerdict(
        status="fail", findings=[TrajectoryFinding(kind="other", description="meh")]
    )
    entries = build(
        verdict("a", "error", [], error="CLI missing"),
        verdict("c", "pass", [gate("g", "pass")], trajectory=judged),
    )
    assert entries == []


# --- coordinator sink against a local stub --------------------------------------------


class _Stub:
    def __init__(self, status: int = 200, body: bytes = b'{"success": true}') -> None:
        self.status, self.body = status, body
        self.requests: list[dict[str, Any]] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a: Any) -> None:
                pass

            def do_POST(self) -> None:  # noqa: N802
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                outer.requests.append({"path": self.path, "auth": self.headers.get("Authorization"),
                                       "ctype": self.headers.get("Content-Type"),
                                       "body": json.loads(raw)})
                self.send_response(outer.status)
                self.send_header("Content-Length", str(len(outer.body)))
                self.end_headers()
                self.wfile.write(outer.body)

        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def stub() -> Any:
    s = _Stub()
    yield s
    s.close()


ENTRY = {"agent_id": "a", "session_id": "r", "event_type": "capability_gap", "summary": "s",
         "details": {}, "tags": ["capability_gap"]}


def test_coordinator_sink_headers_body_and_url(stub: _Stub) -> None:
    sink = CoordinatorMemorySink.from_env(
        "MY_URL", "MY_KEY", environ={"MY_URL": stub.url + "/", "MY_KEY": "k1"}
    )
    assert sink.send(ENTRY) is True
    req = stub.requests[0]
    assert req["path"] == "/memory/store" and req["auth"] == "Bearer k1"
    assert req["ctype"] == "application/json" and req["body"] == ENTRY


@pytest.mark.parametrize(
    ("status", "body"),
    [(200, b'{"success": false}'), (200, b"not json"), (200, b"[]"), (500, b'{"success": true}'),
     (401, b"{}")],
)
def test_only_2xx_with_success_true_is_a_delivery(status: int, body: bytes) -> None:
    s = _Stub(status, body)
    try:
        assert CoordinatorMemorySink(s.url, "k").send(ENTRY) is False
    finally:
        s.close()


def test_unset_url_spools_without_any_http_request(tmp_path: Path, stub: _Stub) -> None:
    sink = CoordinatorMemorySink.from_env("UNSET_URL_VAR", environ={})
    spool = SpoolMemorySink(tmp_path / "spool.jsonl")
    res = emit_gaps([ENTRY, ENTRY], sink, spool)
    assert (res.delivered, res.spooled) == (0, 2)
    assert stub.requests == []
    assert len(spool.pending()) == 2


def _closed_port_url() -> str:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{s.getsockname()[1]}"


def test_unreachable_coordinator_spools_every_entry(tmp_path: Path) -> None:
    spool = SpoolMemorySink(tmp_path / "spool.jsonl")
    res = emit_gaps([ENTRY] * 3, CoordinatorMemorySink(_closed_port_url(), timeout=1), spool)
    assert (res.delivered, res.spooled) == (0, 3)
    assert spool.pending() == [ENTRY] * 3


def test_emit_delivers_when_acknowledged(tmp_path: Path, stub: _Stub) -> None:
    spool = SpoolMemorySink(tmp_path / "spool.jsonl")
    res = emit_gaps([ENTRY], CoordinatorMemorySink(stub.url), spool)
    assert (res.delivered, res.spooled) == (1, 0)
    assert not spool.path.exists()


# --- spool replay ---------------------------------------------------------------------


class _FlakySink:
    """Acknowledges entries whose summary is in ``ok``."""

    def __init__(self, ok: set[str]) -> None:
        self.ok = ok

    def send(self, entry: dict[str, Any]) -> bool:
        return entry["summary"] in self.ok


def _entry(n: int) -> dict[str, Any]:
    return ENTRY | {"summary": f"e{n}"}


def test_flush_delivers_and_keeps_still_failing(tmp_path: Path) -> None:
    spool = SpoolMemorySink(tmp_path / "spool.jsonl")
    for i in range(4):
        spool.send(_entry(i))
    res = flush_spool(spool, _FlakySink({"e0", "e2"}))
    assert (res.delivered, res.remaining) == (2, 2)
    assert [e["summary"] for e in spool.pending()] == ["e1", "e3"]
    res2 = flush_spool(spool, _FlakySink({"e1", "e3"}))
    assert (res2.delivered, res2.remaining) == (2, 0)
    assert spool.pending() == []


def test_flush_of_missing_spool_is_a_noop(tmp_path: Path) -> None:
    res = flush_spool(SpoolMemorySink(tmp_path / "none.jsonl"), _FlakySink(set()))
    assert (res.delivered, res.remaining) == (0, 0)


def test_concurrent_flush_and_emit_lose_and_duplicate_nothing(tmp_path: Path) -> None:
    spool = SpoolMemorySink(tmp_path / "spool.jsonl")
    for i in range(20):
        spool.send(_entry(i))
    delivered: list[str] = []
    gate_open = threading.Event()

    class Slow:
        def send(self, entry: dict[str, Any]) -> bool:
            gate_open.set()
            # Deliver the even ones; odd ones stay undelivered.
            if int(entry["summary"][1:]) % 2 == 0:
                delivered.append(entry["summary"])
                return True
            return False

    def emitter() -> None:
        gate_open.wait(5)
        emit_gaps([_entry(100 + i) for i in range(10)], _FlakySink(set()), spool)

    t = threading.Thread(target=emitter)
    t.start()
    flush_spool(spool, Slow())
    t.join()
    remaining = [e["summary"] for e in spool.pending()]
    assert len(remaining) == len(set(remaining))
    expected = {f"e{i}" for i in range(20) if i % 2} | {f"e{100 + i}" for i in range(10)}
    assert set(remaining) == expected
    assert set(delivered) == {f"e{i}" for i in range(20) if i % 2 == 0}


def test_gaps_flush_cli(tmp_path: Path, stub: _Stub, monkeypatch: pytest.MonkeyPatch,
                        capsys: pytest.CaptureFixture[str]) -> None:
    import argparse

    spool_path = tmp_path / "spool.jsonl"
    SpoolMemorySink(spool_path).send(ENTRY)
    monkeypatch.setenv("COORDINATION_API_URL", stub.url)
    parser = argparse.ArgumentParser()
    add_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["gaps", "flush", "--spool", str(spool_path)])
    assert args.func(args) == 0
    assert json.loads(capsys.readouterr().out) == {"delivered": 1, "remaining": 0}
    assert SpoolMemorySink(spool_path).pending() == []
