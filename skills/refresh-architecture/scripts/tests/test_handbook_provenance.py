"""Handbook coverage in the provenance/freshness system (R3, design D2/D3).

The handbook joins the existing content-based freshness gate rather than
growing a second staleness story. Two properties matter most: a repo without a
committed handbook is fresh-by-absence (so the feature can land before any map
exists), and a committed handbook's bytes are covered by the same digest check
as every other owned artifact.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from arch_utils import provenance as prov


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    arch = tmp_path / prov.ARCH_DIR_DEFAULT
    arch.mkdir(parents=True)
    (arch / "architecture.graph.json").write_text('{"nodes":[],"edges":[]}', encoding="utf-8")
    (arch / "architecture.summary.json").write_text("{}", encoding="utf-8")
    return tmp_path


def _handbook_doc() -> dict[str, Any]:
    return {
        "snapshot": {"generated_at": "2026-08-05T00:00:00+00:00", "git_sha": "abc",
                     "handbook_version": "1.0.0"},
        "system_flows": [],
        "behavior_units": [],
        "unit_details": {},
        "uncovered": [],
    }


def _arch(repo: Path) -> Path:
    return repo / prov.ARCH_DIR_DEFAULT


# --------------------------------------------------------------------------- #
# R3 — the handbook is an owned artifact
# --------------------------------------------------------------------------- #
def test_handbook_is_registered_as_an_owned_artifact() -> None:
    names = [name for name, _required in prov._OWNED_TOP_LEVEL]
    assert "architecture.behaviors.json" in names


def test_handbook_is_optional_not_required() -> None:
    required = {
        name: req for name, req in prov._OWNED_TOP_LEVEL
    }["architecture.behaviors.json"]
    assert required is False, "absence of a handbook must not make a refresh stale"


def test_committed_handbook_digest_is_recorded(repo: Path) -> None:
    (_arch(repo) / "architecture.behaviors.json").write_text(
        json.dumps(_handbook_doc()), encoding="utf-8"
    )

    artifacts = prov.owned_artifacts(repo)
    paths = {a["path"] for a in artifacts}

    assert f"{prov.ARCH_DIR_DEFAULT}/architecture.behaviors.json" in paths
    entry = next(a for a in artifacts if a["path"].endswith("architecture.behaviors.json"))
    assert entry["sha256"]
    assert entry["size_bytes"] > 0


def test_absent_handbook_is_not_recorded(repo: Path) -> None:
    artifacts = prov.owned_artifacts(repo)
    paths = {a["path"] for a in artifacts}
    assert not any(p.endswith("architecture.behaviors.json") for p in paths)


def test_handbook_html_view_is_covered_by_views_walk(repo: Path) -> None:
    views = _arch(repo) / "views"
    views.mkdir()
    (views / "handbook.html").write_text("<h1>hi</h1>", encoding="utf-8")

    paths = {a["path"] for a in prov.owned_artifacts(repo)}

    assert f"{prov.ARCH_DIR_DEFAULT}/views/handbook.html" in paths


# --------------------------------------------------------------------------- #
# Digest drift is detected like any other owned artifact
# --------------------------------------------------------------------------- #
def test_edited_handbook_changes_its_recorded_digest(repo: Path) -> None:
    hb = _arch(repo) / "architecture.behaviors.json"
    hb.write_text(json.dumps(_handbook_doc()), encoding="utf-8")
    before = next(
        a for a in prov.owned_artifacts(repo) if a["path"].endswith("behaviors.json")
    )["sha256"]

    doc = _handbook_doc()
    doc["uncovered"] = [{"node_id": "py:x", "reason": "no_traced_flow"}]
    hb.write_text(json.dumps(doc), encoding="utf-8")
    after = next(
        a for a in prov.owned_artifacts(repo) if a["path"].endswith("behaviors.json")
    )["sha256"]

    assert before != after


# --------------------------------------------------------------------------- #
# D2 — verification is the refresh-time step, and it is deterministic
# --------------------------------------------------------------------------- #
def test_verify_step_is_a_noop_without_a_handbook(repo: Path) -> None:
    from verify_locators import main as verify_main

    rc = verify_main([
        "--handbook", str(_arch(repo) / "architecture.behaviors.json"),
        "--repo-root", str(repo),
    ])

    assert rc == 0


def test_verify_step_records_reason_code_on_drift(tmp_path: Path) -> None:
    from verify_locators import STALE_REASON_LOCATOR_DRIFT, verify_handbook

    src = tmp_path / "src"
    src.mkdir()
    target = src / "a.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")

    doc = _handbook_doc()
    doc["behavior_units"] = [{
        "id": "bh:u", "title": "U", "responsibility": "r", "inputs": [], "outputs": [],
        "depends_on": [], "member_nodes": ["py:a.f"],
    }]
    doc["unit_details"] = {"bh:u": {
        "triggers": [], "state_changes": [], "execution_paths": [],
        "exception_paths": [],
        "evidence": [{"node_id": "py:a.f", "file": "src/a.py",
                      "span": {"start": 1, "end": 2},
                      "content_digest": "sha256:stale", "role": "member"}],
    }}

    report = verify_handbook(doc, tmp_path)

    assert STALE_REASON_LOCATOR_DRIFT in report.stale_reasons


def test_repeat_synthesis_at_same_revision_is_byte_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from synthesize_behaviors import OfflineBackend, synthesize

    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("def f():\n    return g()\n", encoding="utf-8")
    (src / "b.py").write_text("def g():\n    return 1\n", encoding="utf-8")

    graph = {
        "nodes": [
            {"id": "py:a.f", "kind": "function", "name": "f", "file": "src/a.py",
             "span": {"start": 1, "end": 2}},
            {"id": "py:b.g", "kind": "function", "name": "g", "file": "src/b.py",
             "span": {"start": 1, "end": 2}},
        ],
        "edges": [{"from": "py:a.f", "to": "py:b.g", "type": "call",
                   "confidence": "high", "evidence": "ast"}],
        "entrypoints": [{"node_id": "py:a.f", "kind": "route"}],
    }

    first = synthesize(graph, tmp_path, backend=OfflineBackend(), git_sha="fixed")
    second = synthesize(graph, tmp_path, backend=OfflineBackend(), git_sha="fixed")

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
