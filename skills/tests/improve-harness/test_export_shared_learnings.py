"""export_shared_learnings.py: opt-in gate, allowlist, privacy filters, determinism."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest

SKILLS_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = SKILLS_ROOT / "improve-harness" / "scripts" / "export_shared_learnings.py"


def _load_exporter() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("export_shared_learnings_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def exporter() -> types.ModuleType:
    return _load_exporter()


def _stub_memory(monkeypatch: pytest.MonkeyPatch, entries: list[dict[str, Any]]) -> list[dict]:
    calls: list[dict] = []
    stub = types.ModuleType("analyze_failures")

    def query_memory(time_window_days: int = 30, limit: int = 500) -> list[dict[str, Any]]:
        calls.append({"time_window_days": time_window_days, "limit": limit})
        return entries

    stub.query_memory = query_memory  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "analyze_failures", stub)
    return calls


def _enable(root: Path, enabled: object = True) -> None:
    cfg = root / ".agentic-toolkit"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "config.json").write_text(
        json.dumps({"schema_version": 1, "shared_learnings": {"enabled": enabled}})
    )


def _entry(**overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "event_type": "discovery",
        "summary": "Agent could not detect circular dependency",
        "outcome": "failed",
        "lessons": ["check imports first"],
        "details": {"transcript": "private"},
        "agent_id": "agent-123",
        "session_id": "sess-9",
        "created_at": "2026-01-02T00:00:00Z",
        "tags": [
            "failure_type:scope_violation",
            "capability_gap:missing circular dependency detection",
            "affected_skill:implement-feature",
            "severity:high",
            "source:self-reported",
            "agent:agent-123",
            "session:sess-9",
            "change:secret-change",
            "vendor:acme",
            "model:big",
        ],
    }
    entry.update(overrides)
    return entry


def _read(root: Path) -> list[dict[str, Any]]:
    text = (root / ".agentic-toolkit" / "learnings.jsonl").read_text()
    return [json.loads(line) for line in text.splitlines()]


@pytest.mark.parametrize(
    "state", ["absent", "disabled", "string-true", "bad-json", "not-object", "wrong-schema"]
)
def test_export_refused_without_opt_in(
    tmp_path: Path, exporter: types.ModuleType, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    calls = _stub_memory(monkeypatch, [_entry()])
    cfg = tmp_path / ".agentic-toolkit"
    if state == "disabled":
        _enable(tmp_path, False)
    elif state == "string-true":
        _enable(tmp_path, "true")
    elif state == "bad-json":
        cfg.mkdir()
        (cfg / "config.json").write_text("{nope")
    elif state == "not-object":
        cfg.mkdir()
        (cfg / "config.json").write_text("[]")
    elif state == "wrong-schema":
        # An unknown schema is not an opt-in, exactly as the stamp reader treats it.
        cfg.mkdir()
        (cfg / "config.json").write_text(
            json.dumps({"schema_version": 2, "shared_learnings": {"enabled": True}})
        )
    before = {p: p.read_bytes() for p in cfg.rglob("*") if p.is_file()} if cfg.exists() else {}

    assert exporter.export(tmp_path) == 2
    assert not (cfg / "learnings.jsonl").exists()
    assert calls == []  # memory is not even queried
    after = {p: p.read_bytes() for p in cfg.rglob("*") if p.is_file()} if cfg.exists() else {}
    assert before == after


def test_refusal_does_not_overwrite_existing_learnings(
    tmp_path: Path, exporter: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_memory(monkeypatch, [_entry()])
    _enable(tmp_path, False)
    learnings = tmp_path / ".agentic-toolkit" / "learnings.jsonl"
    learnings.write_text("keep\n")
    assert exporter.export(tmp_path) == 2
    assert learnings.read_text() == "keep\n"


def test_export_with_opt_in_writes_one_object_per_line(
    tmp_path: Path, exporter: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _stub_memory(monkeypatch, [_entry(), _entry(summary="Second gap")])
    _enable(tmp_path)
    assert exporter.export(tmp_path, time_window_days=7, limit=50) == 0
    assert calls == [{"time_window_days": 7, "limit": 50}]
    records = _read(tmp_path)
    assert len(records) == 2
    assert all(isinstance(r, dict) for r in records)


def test_private_fields_are_dropped(
    tmp_path: Path, exporter: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_memory(monkeypatch, [_entry()])
    _enable(tmp_path)
    exporter.export(tmp_path)
    (record,) = _read(tmp_path)
    assert set(record) <= {"event_type", "summary", "outcome", "lessons", "tags", "created_at"}
    for banned in ("details", "agent_id", "session_id"):
        assert banned not in record
    assert "agent-123" not in json.dumps(record)


def test_identity_bearing_tags_are_dropped(
    tmp_path: Path, exporter: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_memory(monkeypatch, [_entry()])
    _enable(tmp_path)
    exporter.export(tmp_path)
    (record,) = _read(tmp_path)
    assert "capability_gap:missing circular dependency detection" in record["tags"]
    assert set(record["tags"]) == {
        "failure_type:scope_violation",
        "capability_gap:missing circular dependency detection",
        "affected_skill:implement-feature",
        "severity:high",
        "source:self-reported",
    }
    for prefix in ("agent:", "session:", "change:", "vendor:", "model:"):
        assert not any(t.startswith(prefix) for t in record["tags"])


def test_transcript_mined_entries_are_excluded(
    tmp_path: Path, exporter: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    mined = _entry(
        summary="mined only",
        tags=["capability_gap:x", "source:transcript-mined", "affected_skill:s"],
    )
    _stub_memory(monkeypatch, [mined, _entry()])
    _enable(tmp_path)
    exporter.export(tmp_path)
    records = _read(tmp_path)
    assert [r["summary"] for r in records] == ["Agent could not detect circular dependency"]
    assert "mined only" not in (tmp_path / ".agentic-toolkit" / "learnings.jsonl").read_text()


@pytest.mark.parametrize(
    "variant", ["Source:Transcript-Mined", " source:transcript-mined", "source:transcript-mined:v2"]
)
def test_transcript_mined_variants_fail_closed(
    tmp_path: Path, exporter: types.ModuleType, monkeypatch: pytest.MonkeyPatch, variant: str
) -> None:
    mined = _entry(summary="mined variant", tags=["capability_gap:x", variant])
    _stub_memory(monkeypatch, [mined, _entry()])
    _enable(tmp_path)
    exporter.export(tmp_path)
    assert "mined variant" not in (tmp_path / ".agentic-toolkit" / "learnings.jsonl").read_text()


def test_producer_transcript_tag_is_excluded(
    tmp_path: Path, exporter: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exclusion matches the tag collect-transcripts actually writes, not a hand-typed copy."""
    scripts = SKILLS_ROOT / "collect-transcripts" / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "deep_analyze_under_test", scripts / "deep_analyze.py"
    )
    assert spec and spec.loader
    deep_analyze = importlib.util.module_from_spec(spec)
    # dataclasses resolves sys.modules[cls.__module__] while building the class.
    monkeypatch.setitem(sys.modules, "deep_analyze_under_test", deep_analyze)
    spec.loader.exec_module(deep_analyze)
    finding = deep_analyze.TranscriptFinding(
        failure_type="tool_error", capability_gap="x", affected_skill="s", severity="low",
    )
    producer_tags = finding.to_memory_tags()
    assert any(t.startswith("source:") for t in producer_tags)

    mined = _entry(summary="mined by producer", tags=producer_tags)
    _stub_memory(monkeypatch, [mined, _entry()])
    _enable(tmp_path)
    assert exporter.export(tmp_path) == 0
    assert "mined by producer" not in (tmp_path / ".agentic-toolkit" / "learnings.jsonl").read_text()
    assert [r["summary"] for r in _read(tmp_path)] == ["Agent could not detect circular dependency"]


def test_export_calls_the_real_query_memory_signature(
    tmp_path: Path, exporter: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Load the real analyze_failures (coordinator HTTP stubbed) so the exporter's
    keyword call is checked against the real ``query_memory`` signature."""
    af_path = SKILLS_ROOT / "improve-harness" / "scripts" / "analyze_failures.py"
    spec = importlib.util.spec_from_file_location("analyze_failures", af_path)
    assert spec and spec.loader
    af = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(af)
    monkeypatch.setitem(sys.modules, "analyze_failures", af)
    requests: list[str] = []

    class _Resp:
        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps([_entry()]).encode()

    def fake_urlopen(req: Any, timeout: int = 0) -> _Resp:
        requests.append(req.full_url)
        return _Resp()

    monkeypatch.setattr(af, "urlopen", fake_urlopen)
    _enable(tmp_path)
    assert exporter.export(tmp_path, time_window_days=7, limit=50) == 0
    assert len(requests) == 1 and requests[0].endswith("/memory/query")
    assert len(_read(tmp_path)) == 1


def test_secrets_are_redacted(
    tmp_path: Path, exporter: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "AKIAABCDEFGHIJKLMNOP"
    _stub_memory(
        monkeypatch,
        [_entry(summary=f"leaked {secret} in logs", lessons=[f"rotate {secret}", "ok"])],
    )
    _enable(tmp_path)
    exporter.export(tmp_path)
    text = (tmp_path / ".agentic-toolkit" / "learnings.jsonl").read_text()
    assert secret not in text
    assert "REDACTED" in text


def test_output_is_deterministic_sorted_and_deduplicated(
    tmp_path: Path, exporter: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = _entry(summary="b summary", created_at="2026-01-02T00:00:00Z")
    b = _entry(summary="a summary", created_at="2026-01-02T00:00:00Z")
    c = _entry(summary="early", created_at="2026-01-01T00:00:00Z")
    dup = _entry(summary="b summary", created_at="2026-02-01T00:00:00Z")  # same dedupe key as a
    _stub_memory(monkeypatch, [a, b, c, dup])
    _enable(tmp_path)

    exporter.export(tmp_path)
    first = (tmp_path / ".agentic-toolkit" / "learnings.jsonl").read_bytes()
    _stub_memory(monkeypatch, [dup, c, b, a])  # different input order
    exporter.export(tmp_path)
    second = (tmp_path / ".agentic-toolkit" / "learnings.jsonl").read_bytes()

    assert first == second
    summaries = [json.loads(line)["summary"] for line in first.decode().splitlines()]
    assert summaries == ["early", "a summary", "b summary"]


def test_missing_tags_dedupe_on_unknown(
    tmp_path: Path, exporter: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    one = _entry(summary="same", tags=["severity:low"])
    two = _entry(summary="same", tags=["severity:high"], created_at="2026-03-01T00:00:00Z")
    _stub_memory(monkeypatch, [one, two])
    _enable(tmp_path)
    exporter.export(tmp_path)
    assert len(_read(tmp_path)) == 1


def test_empty_memory_leaves_existing_file_unchanged(
    tmp_path: Path, exporter: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_memory(monkeypatch, [])
    _enable(tmp_path)
    learnings = tmp_path / ".agentic-toolkit" / "learnings.jsonl"
    learnings.write_text("previous\n")
    assert exporter.export(tmp_path) == 3
    assert learnings.read_text() == "previous\n"


def test_cli_help_runs_standalone() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "learnings.jsonl" in result.stdout


def test_cli_refuses_without_config(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert "refusing" in result.stderr
    assert not (tmp_path / ".agentic-toolkit").exists()
