"""Tests for the LLM structuring backend and grouping normalizer (deferred #1).

The offline backend renames 1:1 seed clusters; an LLM backend's value is that it
can *merge and split* clusters into human-meaningful behavior units. These tests
pin two things: (1) the grouping normalizer that lets the assembler accept a
merge/split payload while the legacy 1:1 dict shape stays byte-identical, and
(2) the Claude backend, exercised through an injected completion function so it
runs without network or credentials.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from synthesize_behaviors import (
    ClaudeStructuringBackend,
    StructuringError,
    _extract_json,
    _normalize_structuring,
    synthesize,
)

API_SRC = "def a():\n    return b()\n"
SVC_SRC = "def b():\n    return c()\n"
REP_SRC = "def render():\n    return html\n"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "api.py").write_text(API_SRC, encoding="utf-8")
    (src / "svc.py").write_text(SVC_SRC, encoding="utf-8")
    (src / "report.py").write_text(REP_SRC, encoding="utf-8")
    return tmp_path


def _graph() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "py:api.a", "kind": "function", "name": "a", "file": "src/api.py",
             "span": {"start": 1, "end": 2}},
            {"id": "py:svc.b", "kind": "function", "name": "b", "file": "src/svc.py",
             "span": {"start": 1, "end": 2}},
            {"id": "py:report.render", "kind": "function", "name": "render",
             "file": "src/report.py", "span": {"start": 1, "end": 2}},
        ],
        "edges": [
            {"from": "py:api.a", "to": "py:svc.b", "type": "call",
             "confidence": "high", "evidence": "ast"},
        ],
        "entrypoints": [
            {"node_id": "py:api.a", "kind": "route"},
            {"node_id": "py:report.render", "kind": "route"},
        ],
    }


def _seeds() -> dict[str, Any]:
    """A two-cluster seed skeleton for normalizer unit tests."""
    return {
        "clusters": [
            {"id": "seed:api-a", "root": "py:api.a", "roots": ["py:api.a"],
             "member_nodes": ["py:api.a", "py:svc.b"], "member_files": ["src/api.py"],
             "hubs": [], "exception_patterns": []},
            {"id": "seed:report-render", "root": "py:report.render",
             "roots": ["py:report.render"], "member_nodes": ["py:report.render"],
             "member_files": ["src/report.py"], "hubs": [], "exception_patterns": []},
        ],
        "uncovered": [],
        "summary": {"clusters": 2, "uncovered_entrypoints": 0},
    }


# --------------------------------------------------------------------------- #
# _extract_json — tolerate the ways a model wraps JSON
# --------------------------------------------------------------------------- #
def test_extract_plain_json() -> None:
    assert _extract_json('{"units": []}') == {"units": []}


def test_extract_fenced_json() -> None:
    text = 'Here you go:\n```json\n{"units": [{"seed_ids": ["seed:x"]}]}\n```\n'
    assert _extract_json(text)["units"][0]["seed_ids"] == ["seed:x"]


def test_extract_json_with_prose_around_object() -> None:
    text = 'Sure. {"units": []} Hope that helps.'
    assert _extract_json(text) == {"units": []}


def test_extract_json_raises_on_garbage() -> None:
    with pytest.raises(ValueError):
        _extract_json("no json here at all")


# --------------------------------------------------------------------------- #
# Normalizer — legacy dict shape is unchanged (byte-identical guarantee)
# --------------------------------------------------------------------------- #
def test_legacy_dict_shape_yields_one_spec_per_cluster() -> None:
    structured = {"seed:api-a": {"title": "Alpha"}, "seed:report-render": {}}

    specs = _normalize_structuring(structured, _seeds())

    ids = [s["unit_id"] for s in specs]
    assert ids == ["bh:api-a", "bh:report-render"]  # sorted, 1:1
    alpha = next(s for s in specs if s["unit_id"] == "bh:api-a")
    assert alpha["member_nodes"] == ["py:api.a", "py:svc.b"]
    assert alpha["content"]["title"] == "Alpha"
    assert alpha["cluster_ids"] == ["seed:api-a"]


def test_empty_structuring_still_covers_every_cluster() -> None:
    specs = _normalize_structuring({}, _seeds())
    assert {s["unit_id"] for s in specs} == {"bh:api-a", "bh:report-render"}


# --------------------------------------------------------------------------- #
# Normalizer — grouping shape (merge / split)
# --------------------------------------------------------------------------- #
def test_grouping_merges_clusters_into_one_unit() -> None:
    structured = {"units": [
        {"seed_ids": ["seed:api-a", "seed:report-render"], "title": "Everything"},
    ]}

    specs = _normalize_structuring(structured, _seeds())

    assert len(specs) == 1
    spec = specs[0]
    assert set(spec["cluster_ids"]) == {"seed:api-a", "seed:report-render"}
    assert spec["member_nodes"] == ["py:api.a", "py:report.render", "py:svc.b"]
    assert spec["content"]["title"] == "Everything"


def test_grouping_first_wins_on_duplicate_seed() -> None:
    structured = {"units": [
        {"seed_ids": ["seed:api-a"], "title": "First"},
        {"seed_ids": ["seed:api-a", "seed:report-render"], "title": "Second"},
    ]}

    specs = _normalize_structuring(structured, _seeds())

    by_id = {s["unit_id"]: s for s in specs}
    # seed:api-a claimed by First; Second keeps only report-render
    assert by_id["bh:api-a"]["cluster_ids"] == ["seed:api-a"]
    second = next(s for s in specs if "seed:report-render" in s["cluster_ids"])
    assert second["cluster_ids"] == ["seed:report-render"]


def test_grouping_drops_invented_seed_ids() -> None:
    structured = {"units": [
        {"seed_ids": ["seed:api-a", "seed:ghost"], "title": "Real plus ghost"},
    ]}

    specs = _normalize_structuring(structured, _seeds())

    covered = {c for s in specs for c in s["cluster_ids"]}
    assert "seed:ghost" not in covered
    assert "seed:api-a" in covered


def test_grouping_unclaimed_seed_becomes_its_own_unit() -> None:
    structured = {"units": [{"seed_ids": ["seed:api-a"], "title": "Only A"}]}

    specs = _normalize_structuring(structured, _seeds())

    # report-render referenced by nobody — must still get a unit
    assert any(s["cluster_ids"] == ["seed:report-render"] for s in specs)


def test_grouping_unit_with_no_valid_seeds_is_dropped() -> None:
    structured = {"units": [
        {"seed_ids": ["seed:ghost"], "title": "Phantom"},
        {"seed_ids": ["seed:api-a"], "title": "Real"},
    ]}

    specs = _normalize_structuring(structured, _seeds())

    titles = {s["content"].get("title") for s in specs}
    assert "Phantom" not in titles


def test_normalizer_output_is_deterministic() -> None:
    structured = {"units": [
        {"seed_ids": ["seed:report-render"], "title": "R"},
        {"seed_ids": ["seed:api-a"], "title": "A"},
    ]}
    first = _normalize_structuring(structured, _seeds())
    second = _normalize_structuring(structured, _seeds())
    assert [s["unit_id"] for s in first] == [s["unit_id"] for s in second]


# --------------------------------------------------------------------------- #
# ClaudeStructuringBackend — injected completion, no network
# --------------------------------------------------------------------------- #
class _Recorder:
    """Injectable completion fn that records prompts and returns canned JSON."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._responses.pop(0)


def test_backend_identity_fields() -> None:
    backend = ClaudeStructuringBackend(model="claude-opus-5", complete=lambda p: "{}")
    assert backend.name == "claude"
    assert backend.model_id == "claude-opus-5"
    assert backend.prompt_hash.startswith("sha256:")


def test_backend_returns_grouping_payload() -> None:
    payload = json.dumps({"units": [{"seed_ids": ["seed:api-a"], "title": "A"}]})
    backend = ClaudeStructuringBackend(complete=_Recorder([payload]))

    out = backend.structure(_seeds())

    assert out["units"][0]["seed_ids"] == ["seed:api-a"]


def test_backend_chunks_large_seed_sets() -> None:
    seeds = _seeds()
    rec = _Recorder(['{"units": [{"seed_ids": ["seed:api-a"]}]}',
                     '{"units": [{"seed_ids": ["seed:report-render"]}]}'])
    backend = ClaudeStructuringBackend(complete=rec, chunk_size=1)

    out = backend.structure(seeds)

    assert len(rec.prompts) == 2  # one call per cluster at chunk_size=1
    covered = {s for u in out["units"] for s in u["seed_ids"]}
    assert covered == {"seed:api-a", "seed:report-render"}


def test_backend_prompt_contains_seed_context() -> None:
    rec = _Recorder(['{"units": []}'])
    ClaudeStructuringBackend(complete=rec).structure(_seeds())

    prompt = rec.prompts[0]
    assert "seed:api-a" in prompt
    assert "py:api.a" in prompt  # member nodes are offered to the model


def test_backend_raises_on_unparseable_response() -> None:
    backend = ClaudeStructuringBackend(complete=lambda p: "I refuse to answer.")
    with pytest.raises(ValueError):
        backend.structure(_seeds())


def test_backend_raises_when_units_missing() -> None:
    backend = ClaudeStructuringBackend(complete=lambda p: '{"notunits": []}')
    with pytest.raises(ValueError):
        backend.structure(_seeds())


# --------------------------------------------------------------------------- #
# End-to-end: synthesize with a grouping backend
# --------------------------------------------------------------------------- #
def test_synthesize_with_grouping_backend_merges_members(repo: Path) -> None:
    from handbook_schema import validate_handbook

    payload = json.dumps({"units": [
        {"seed_ids": ["seed:api-a"], "title": "Request handling",
         "responsibility": "Handle the inbound request.",
         "execution_paths": [{"summary": "a calls b", "evidence_nodes": ["py:api.a"]}]},
    ]})
    backend = ClaudeStructuringBackend(complete=lambda p: payload)

    hb = synthesize(_graph(), repo, backend=backend, source_roots={"python": "src"})

    dc = validate_handbook(hb, _graph())
    assert dc.exit_code == 0, [d.to_dict() for d in dc.errors]
    unit = next(u for u in hb["behavior_units"] if u["id"] == "bh:api-a")
    assert set(unit["member_nodes"]) == {"py:api.a", "py:svc.b"}
    assert hb["snapshot"]["backend"] == "claude"


def test_synthesize_grouping_cannot_add_member_nodes(repo: Path) -> None:
    payload = json.dumps({"units": [
        {"seed_ids": ["seed:api-a"], "title": "X", "member_nodes": ["py:invented"],
         "execution_paths": [{"summary": "s", "evidence_nodes": ["py:invented"]}]},
    ]})
    backend = ClaudeStructuringBackend(complete=lambda p: payload)

    hb = synthesize(_graph(), repo, backend=backend, source_roots={"python": "src"})

    unit = next(u for u in hb["behavior_units"] if u["id"] == "bh:api-a")
    assert "py:invented" not in unit["member_nodes"]
    detail = hb["unit_details"]["bh:api-a"]
    # ungrounded path (evidence outside the skeleton) is dropped
    assert all("py:invented" not in json.dumps(p) for p in detail["execution_paths"])


def test_synthesize_wraps_backend_failure(repo: Path) -> None:
    def _boom(prompt: str) -> str:
        raise RuntimeError("api exploded")

    backend = ClaudeStructuringBackend(complete=_boom)
    with pytest.raises(StructuringError):
        synthesize(_graph(), repo, backend=backend, source_roots={"python": "src"})
