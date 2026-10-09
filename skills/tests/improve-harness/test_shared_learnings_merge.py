"""analyze_failures.py: one-way merge of the shared learnings projection."""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

SKILLS_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = SKILLS_ROOT / "improve-harness" / "scripts" / "analyze_failures.py"


@pytest.fixture()
def af() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("analyze_failures_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tags(gap: str, skill: str = "implement-feature", **extra: str) -> list[str]:
    tags = [
        f"capability_gap:{gap}",
        f"affected_skill:{skill}",
        "severity:high",
        "failure_type:scope_violation",
        "source:self-reported",
    ]
    tags.extend(f"{k}:{v}" for k, v in extra.items())
    return tags


def _local(gap: str, summary: str, session: str = "s1") -> dict[str, Any]:
    return {"summary": summary, "session_id": session, "tags": _tags(gap)}


def _shared(gap: str, summary: str) -> dict[str, Any]:
    return {"summary": summary, "event_type": "discovery", "tags": _tags(gap)}


def _write(root: Path, records: list[dict[str, Any]], *, enabled: object = True,
           config: bool = True, name: str = "learnings.jsonl") -> Path:
    cfg = root / ".agentic-toolkit"
    cfg.mkdir(parents=True, exist_ok=True)
    if config:
        (cfg / "config.json").write_text(
            json.dumps({"schema_version": 1, "shared_learnings": {"enabled": enabled}})
        )
    path = cfg / name
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


def test_shared_record_is_merged_and_attributed(af: types.ModuleType, tmp_path: Path) -> None:
    _write(tmp_path, [_shared("gap-b", "teammate learned this")])
    records = af.load_shared_learnings(tmp_path)
    merged = af.merge_shared_learnings([_local("gap-a", "mine")], records)
    ranked = af.rank_findings(merged)
    by_gap = {f["capability_gap"]: f for f in ranked}
    assert "origin:shared-repo" in by_gap["gap-b"]["sources"]
    assert "origin:shared-repo" not in by_gap["gap-a"]["sources"]


def test_duplicate_shared_record_appears_once_from_custom_path(
    af: types.ModuleType, tmp_path: Path
) -> None:
    custom = tmp_path / "elsewhere.jsonl"
    custom.write_text(json.dumps(_shared("gap-a", "same summary")) + "\n")
    _write(tmp_path, [], enabled=True)  # default path holds nothing; custom must be read
    records = af.load_shared_learnings(tmp_path, custom)
    assert len(records) == 1

    local = [_local("gap-a", "same summary", session="s7")]
    merged = af.merge_shared_learnings(local, records)
    assert len(merged) == 1
    (finding,) = af.rank_findings(merged)
    assert finding["frequency"] == 1
    assert "origin:shared-repo" in finding["sources"]
    assert "self-reported" in finding["sources"]


def test_duplicates_among_shared_records_collapse(af: types.ModuleType) -> None:
    shared = [_shared("g", "x"), _shared("g", "x"), _shared("g", "y")]
    merged = af.merge_shared_learnings([], shared)
    assert [e["summary"] for e in merged] == ["x", "y"]
    assert all("origin:shared-repo" in e["tags"] for e in merged)


@pytest.mark.parametrize("state", ["no-config", "disabled"])
def test_disabled_sharing_ignores_the_file(
    af: types.ModuleType, tmp_path: Path, state: str
) -> None:
    _write(tmp_path, [_shared("gap-b", "x")], enabled=False, config=(state == "disabled"))
    assert af.load_shared_learnings(tmp_path) == []
    merged = af.merge_shared_learnings([_local("gap-a", "mine")], af.load_shared_learnings(tmp_path))
    assert all(
        "origin:shared-repo" not in f["sources"] for f in af.rank_findings(merged)
    )


def test_missing_file_and_bad_lines_are_tolerated(
    af: types.ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, [])
    (tmp_path / ".agentic-toolkit" / "learnings.jsonl").write_text(
        "{broken\n\n" + json.dumps(_shared("g", "ok")) + "\n[1]\n"
    )
    records = af.load_shared_learnings(tmp_path)
    assert [r["summary"] for r in records] == ["ok"]
    assert "not valid JSON" in capsys.readouterr().err
    (tmp_path / ".agentic-toolkit" / "learnings.jsonl").unlink()
    assert af.load_shared_learnings(tmp_path) == []


def test_merge_does_not_mutate_inputs(af: types.ModuleType) -> None:
    local = [_local("g", "same")]
    shared = [_shared("g", "same"), _shared("h", "other")]
    local_before = json.dumps(local)
    shared_before = json.dumps(shared)
    af.merge_shared_learnings(local, shared)
    assert json.dumps(local) == local_before
    assert json.dumps(shared) == shared_before


def test_cli_merges_and_never_stores_to_memory(
    af: types.ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(tmp_path, [_shared("gap-shared", "from teammate")])
    requested: list[tuple[str, str | None]] = []

    class _Resp:
        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps([_local("gap-local", "mine")]).encode()

    def fake_urlopen(req: Any, timeout: int = 0) -> _Resp:
        requested.append((req.full_url, req.get_method()))
        return _Resp()

    monkeypatch.setattr(af, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        sys, "argv", ["analyze_failures.py", "--json", "--repo-root", str(tmp_path)]
    )
    af.main()

    out = json.loads(capsys.readouterr().out)
    gaps = {f["capability_gap"]: f for f in out}
    assert set(gaps) == {"gap-local", "gap-shared"}
    assert "origin:shared-repo" in gaps["gap-shared"]["sources"]
    assert requested, "memory was queried"
    assert all(url.endswith("/memory/query") for url, _ in requested)
    assert not any("memory/store" in url for url, _ in requested)


def test_cli_honours_shared_learnings_flag(
    af: types.ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(tmp_path, [_shared("default-gap", "d")])
    custom = _write(tmp_path, [_shared("custom-gap", "c")], name="custom.jsonl")
    monkeypatch.setattr(af, "query_memory", lambda **kw: [])
    monkeypatch.setattr(
        sys, "argv",
        ["analyze_failures.py", "--json", "--repo-root", str(tmp_path),
         "--shared-learnings", str(custom)],
    )
    af.main()
    gaps = {f["capability_gap"] for f in json.loads(capsys.readouterr().out)}
    assert gaps == {"custom-gap"}


def test_module_has_no_memory_write_path(af: types.ModuleType) -> None:
    source = SCRIPT.read_text()
    assert "/memory/store" not in source
    assert "remember" not in source.replace("remembered", "")
