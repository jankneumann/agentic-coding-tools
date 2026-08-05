"""Tests for handbook synthesis (R1/R3, design D2/D4).

Synthesis merges a structuring backend's naming and narrative onto the fixed
seed skeleton. The backend may never widen membership, every narrative must
carry a resolvable locator, and a failed run must leave the previously
committed handbook untouched.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from synthesize_behaviors import (
    OfflineBackend,
    StructuringError,
    synthesize,
    write_handbook,
)

API_SRC = """def claim_task(agent_id):
    lock = acquire(agent_id)
    return lock
"""

SVC_SRC = """def acquire(agent_id):
    try:
        return db_write(agent_id)
    except LockTimeout:
        return None
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "api.py").write_text(API_SRC, encoding="utf-8")
    (src / "svc.py").write_text(SVC_SRC, encoding="utf-8")
    return tmp_path


def _graph() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "py:api.claim_task", "kind": "function", "name": "claim_task",
             "file": "src/api.py", "span": {"start": 1, "end": 3}},
            {"id": "py:svc.acquire", "kind": "function", "name": "acquire",
             "file": "src/svc.py", "span": {"start": 1, "end": 5}},
        ],
        "edges": [
            {"from": "py:api.claim_task", "to": "py:svc.acquire", "type": "call",
             "confidence": "high", "evidence": "ast"},
        ],
        "entrypoints": [{"node_id": "py:api.claim_task", "kind": "route",
                         "method": "POST", "path": "/tasks/claim"}],
    }


class _FakeBackend:
    """Structuring backend stub returning caller-supplied content."""

    name = "fake"
    model_id = "fake-model-1"

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.prompt_hash = "sha256:fakeprompt"

    def structure(self, seeds: dict[str, Any]) -> dict[str, Any]:
        return self._payload


def _good_payload() -> dict[str, Any]:
    return {
        "seed:api-claim-task": {
            "title": "Task claiming",
            "responsibility": "Atomically assign a queued task to one agent.",
            "inputs": ["agent id"],
            "outputs": ["lock"],
            "triggers": ["POST /tasks/claim"],
            "state_changes": ["task queued -> claimed"],
            "execution_paths": [
                {"summary": "claim succeeds", "evidence_nodes": ["py:api.claim_task"]}
            ],
            "exception_paths": [
                {"summary": "lock timeout returns None",
                 "evidence_nodes": ["py:svc.acquire"]}
            ],
        }
    }


# --------------------------------------------------------------------------- #
# R1 — synthesis produces a valid handbook
# --------------------------------------------------------------------------- #
def test_synthesis_produces_schema_valid_handbook(repo: Path) -> None:
    from handbook_schema import validate_handbook

    hb = synthesize(_graph(), repo, backend=_FakeBackend(_good_payload()))

    dc = validate_handbook(hb, _graph())
    assert dc.exit_code == 0, [d.to_dict() for d in dc.errors]


def test_offline_backend_produces_valid_handbook(repo: Path) -> None:
    from handbook_schema import validate_handbook

    hb = synthesize(_graph(), repo, backend=OfflineBackend())

    dc = validate_handbook(hb, _graph())
    assert dc.exit_code == 0, [d.to_dict() for d in dc.errors]
    assert hb["behavior_units"], "offline backend should still emit units"


def test_locators_are_stamped_and_verify(repo: Path) -> None:
    from verify_locators import VERIFIED, verify_handbook

    hb = synthesize(_graph(), repo, backend=_FakeBackend(_good_payload()))

    report = verify_handbook(hb, repo)
    assert report.counts[VERIFIED] > 0
    assert report.exit_code == 0


def test_snapshot_records_backend_identity(repo: Path) -> None:
    hb = synthesize(_graph(), repo, backend=_FakeBackend(_good_payload()))

    snap = hb["snapshot"]
    assert snap["backend"] == "fake"
    assert snap["model_id"] == "fake-model-1"
    assert snap["prompt_hash"] == "sha256:fakeprompt"
    assert "handbook_version" in snap
    assert "generated_at" in snap


def test_budget_estimate_recorded(repo: Path) -> None:
    hb = synthesize(_graph(), repo, backend=_FakeBackend(_good_payload()))
    assert hb["budget_estimate"]["l2_cards"] == len(hb["behavior_units"])


# --------------------------------------------------------------------------- #
# D4 — the backend may not widen the skeleton
# --------------------------------------------------------------------------- #
def test_backend_cannot_add_member_nodes(repo: Path) -> None:
    payload = _good_payload()
    payload["seed:api-claim-task"]["member_nodes"] = ["py:invented.node"]

    hb = synthesize(_graph(), repo, backend=_FakeBackend(payload))

    members = hb["behavior_units"][0]["member_nodes"]
    assert "py:invented.node" not in members
    assert set(members) == {"py:api.claim_task", "py:svc.acquire"}


def test_backend_evidence_outside_cluster_is_dropped(repo: Path) -> None:
    payload = _good_payload()
    payload["seed:api-claim-task"]["execution_paths"][0]["evidence_nodes"] = [
        "py:api.claim_task", "py:not.a.member",
    ]

    hb = synthesize(_graph(), repo, backend=_FakeBackend(payload))

    detail = hb["unit_details"][hb["behavior_units"][0]["id"]]
    node_ids = {e["node_id"] for e in detail["execution_paths"][0]["evidence"]}
    assert node_ids == {"py:api.claim_task"}


def test_narrative_without_any_resolvable_locator_is_rejected(repo: Path) -> None:
    payload = _good_payload()
    payload["seed:api-claim-task"]["execution_paths"] = [
        {"summary": "ungrounded claim", "evidence_nodes": ["py:ghost"]}
    ]

    hb = synthesize(_graph(), repo, backend=_FakeBackend(payload))

    detail = hb["unit_details"][hb["behavior_units"][0]["id"]]
    summaries = [p["summary"] for p in detail["execution_paths"]]
    assert "ungrounded claim" not in summaries


def test_backend_returning_unknown_cluster_is_ignored(repo: Path) -> None:
    payload = _good_payload()
    payload["seed:does-not-exist"] = {"title": "Ghost", "responsibility": "none"}

    hb = synthesize(_graph(), repo, backend=_FakeBackend(payload))

    titles = {u["title"] for u in hb["behavior_units"]}
    assert "Ghost" not in titles


# --------------------------------------------------------------------------- #
# R6 — uncovered entrypoints carried through
# --------------------------------------------------------------------------- #
def test_uncovered_entrypoints_are_carried_into_the_handbook(repo: Path) -> None:
    graph = _graph()
    graph["nodes"].append(
        {"id": "py:api.health", "kind": "function", "name": "health",
         "file": "src/api.py", "span": {"start": 1, "end": 1}}
    )
    graph["entrypoints"].append({"node_id": "py:api.health", "kind": "route"})

    hb = synthesize(graph, repo, backend=OfflineBackend())

    uncovered = {u["node_id"] for u in hb["uncovered"]}
    assert "py:api.health" in uncovered


def test_exception_patterns_become_exception_paths(repo: Path) -> None:
    enrichment = {
        "exception_patterns": [
            {"node_id": "py:svc.acquire", "file": "src/svc.py", "line": 4,
             "exception_type": "LockTimeout"}
        ]
    }

    hb = synthesize(_graph(), repo, backend=OfflineBackend(), enrichment=enrichment)

    detail = hb["unit_details"][hb["behavior_units"][0]["id"]]
    assert detail["exception_paths"], "exception patterns should surface as L3 paths"
    assert any("LockTimeout" in p["summary"] for p in detail["exception_paths"])


# --------------------------------------------------------------------------- #
# R3 / D2 — staged write preserves last known-good
# --------------------------------------------------------------------------- #
def test_failed_validation_preserves_existing_artifact(repo: Path) -> None:
    out = repo / "architecture.behaviors.json"
    out.write_text(json.dumps({"committed": "previous"}), encoding="utf-8")

    broken = {"behavior_units": [{"id": "bad-id"}], "system_flows": [],
              "unit_details": {}, "uncovered": []}

    rc = write_handbook(broken, _graph(), out)

    assert rc == 1
    assert json.loads(out.read_text()) == {"committed": "previous"}


def test_successful_write_replaces_artifact(repo: Path) -> None:
    out = repo / "architecture.behaviors.json"
    out.write_text(json.dumps({"committed": "previous"}), encoding="utf-8")

    hb = synthesize(_graph(), repo, backend=_FakeBackend(_good_payload()))
    rc = write_handbook(hb, _graph(), out)

    assert rc == 0
    assert json.loads(out.read_text())["behavior_units"]


def test_backend_error_surfaces_as_structuring_error(repo: Path) -> None:
    class _Boom:
        name = "boom"
        model_id = "none"
        prompt_hash = "sha256:x"

        def structure(self, seeds: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("backend exploded")

    with pytest.raises(StructuringError):
        synthesize(_graph(), repo, backend=_Boom())


# --------------------------------------------------------------------------- #
# D2 — determinism of the offline path
# --------------------------------------------------------------------------- #
def test_offline_synthesis_is_byte_stable(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")

    first = synthesize(_graph(), repo, backend=OfflineBackend())
    second = synthesize(_graph(), repo, backend=OfflineBackend())

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
