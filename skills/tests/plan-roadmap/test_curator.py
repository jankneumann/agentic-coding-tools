"""Tests for the plan-roadmap host-assisted curator (Mode A)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from curator import (
    _compute_heuristic_flags,
    apply_curation,
    build_curation_request,
)
from decomposer import decompose
from jsonschema import Draft202012Validator
from models import Effort, ItemStatus, Roadmap, RoadmapItem, RoadmapStatus, load_roadmap

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
_FIXTURE_PROPOSAL = """\
# Example Proposal

## Context and Goals

This is narrative framing that should not become a deliverable.
The project provides a system for managing widgets.

## Phase 1 — Foundations

### Capability: Database Schema Migration

Introduce widgets table with proper indexing.

- Schema migration must succeed on an empty database.
- Rollback must work.

### Capability: Widgets REST API

CRUD endpoints for widget resources.

- All endpoints must return JSON.
- Authentication must be enforced.

## Phase 2 — Ergonomics

### Capability: CLI for Widget Management

Command-line tool that talks to the REST API.

- CLI must support create, list, and delete.
- Output must be both human-readable and JSON.

## Constraints

- The system must remain MIT-licensed.
"""


@pytest.fixture
def draft_roadmap() -> Roadmap:
    return decompose(_FIXTURE_PROPOSAL, "docs/fixtures/example.md")


@pytest.fixture
def schema_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "plan-roadmap" / "contracts"


# ---------------------------------------------------------------------------
# Heuristic flags
# ---------------------------------------------------------------------------
class TestHeuristicFlags:
    def _mk(self, **over) -> RoadmapItem:
        base = dict(
            item_id="ri-x",
            title="X",
            status=ItemStatus.CANDIDATE,
            priority=1,
            effort=Effort.M,
            depends_on=[],
            acceptance_outcomes=[],
        )
        base.update(over)
        return RoadmapItem(**base)

    def test_narrative_title(self):
        item = self._mk(title="Context and Goals")
        flags = _compute_heuristic_flags(item)
        assert "likely-narrative" in flags

    def test_constraint_title(self):
        item = self._mk(title="Constraints")
        assert "likely-constraint" in _compute_heuristic_flags(item)

    def test_phase_header(self):
        item = self._mk(title="Phase 1 — Foundations")
        assert "phase-header" in _compute_heuristic_flags(item)

    def test_capability_keyword(self):
        item = self._mk(title="Capability: Auth Service")
        flags = _compute_heuristic_flags(item)
        assert "has-capability-keyword" in flags

    def test_generic_acceptance(self):
        item = self._mk(
            title="Foo",
            acceptance_outcomes=["Foo is implemented and tested"],
        )
        assert "generic-acceptance" in _compute_heuristic_flags(item)

    def test_real_acceptance_not_flagged(self):
        item = self._mk(
            title="Foo",
            acceptance_outcomes=["Endpoint must return 200 on success."],
        )
        assert "generic-acceptance" not in _compute_heuristic_flags(item)

    def test_small_effort_and_no_deps(self):
        item = self._mk(effort=Effort.XS, depends_on=[])
        flags = _compute_heuristic_flags(item)
        assert "small-effort-estimate" in flags
        assert "no-dependencies-inferred" in flags


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------
class TestSchemaValidation:
    def test_request_conforms_to_schema(self, draft_roadmap: Roadmap, schema_dir: Path):
        schema = json.loads((schema_dir / "curation-request.schema.json").read_text())
        request = build_curation_request(
            draft_roadmap,
            draft_roadmap_ref="/tmp/draft.yaml",
            response_path_hint="/tmp/response.json",
        )
        Draft202012Validator(schema).validate(request)

    def test_empty_response_validates(self, schema_dir: Path):
        schema = json.loads((schema_dir / "curation-response.schema.json").read_text())
        Draft202012Validator(schema).validate({"schema_version": 1, "decisions": []})

    def test_keep_and_drop_validate(self, schema_dir: Path):
        schema = json.loads((schema_dir / "curation-response.schema.json").read_text())
        Draft202012Validator(schema).validate({
            "schema_version": 1,
            "decisions": [
                {"original_id": "ri-a", "action": "keep", "new_id": "ri-01-a",
                 "effort": "S", "priority": 1, "depends_on": [], "rationale": "r"},
                {"original_id": "ri-b", "action": "drop", "rationale": "noise"},
                {"original_id": "ri-c", "action": "merge", "merge_into": "ri-01-a",
                 "rationale": "duplicate"},
            ],
        })

    def test_merge_without_target_rejected(self, schema_dir: Path):
        schema = json.loads((schema_dir / "curation-response.schema.json").read_text())
        with pytest.raises(Exception):
            Draft202012Validator(schema).validate({
                "schema_version": 1,
                "decisions": [{"original_id": "ri-a", "action": "merge", "rationale": "r"}],
            })


# ---------------------------------------------------------------------------
# apply_curation
# ---------------------------------------------------------------------------
class TestApplyCuration:
    def test_no_decisions_preserves_items(self, draft_roadmap: Roadmap):
        response = {"schema_version": 1, "decisions": []}
        curated = apply_curation(draft_roadmap, response)
        assert len(curated.items) == len(draft_roadmap.items)

    def test_drop_removes_item(self, draft_roadmap: Roadmap):
        target = draft_roadmap.items[0].item_id
        response = {"schema_version": 1, "decisions": [
            {"original_id": target, "action": "drop", "rationale": "not a deliverable"},
        ]}
        curated = apply_curation(draft_roadmap, response)
        assert target not in {it.item_id for it in curated.items}
        assert len(curated.items) == len(draft_roadmap.items) - 1

    def test_keep_applies_overrides(self, draft_roadmap: Roadmap):
        target = draft_roadmap.items[0].item_id
        response = {"schema_version": 1, "decisions": [
            {"original_id": target, "action": "keep", "new_id": "ri-99-renamed",
             "title": "New Title", "effort": "XL", "priority": 7,
             "depends_on": [], "rationale": "renamed"},
        ]}
        curated = apply_curation(draft_roadmap, response)
        renamed = [it for it in curated.items if it.item_id == "ri-99-renamed"]
        assert len(renamed) == 1
        assert renamed[0].title == "New Title"
        assert renamed[0].effort == Effort.XL
        assert renamed[0].priority == 7

    def test_merge_removes_source_and_rewrites_deps(self, draft_roadmap: Roadmap):
        # Set up: give item[1] a dep on item[0], then merge item[0] into item[2].
        draft_roadmap.items[1].depends_on = [draft_roadmap.items[0].item_id]
        src = draft_roadmap.items[0].item_id
        tgt = draft_roadmap.items[2].item_id
        response = {"schema_version": 1, "decisions": [
            {"original_id": src, "action": "merge", "merge_into": tgt,
             "rationale": "overlap"},
        ]}
        curated = apply_curation(draft_roadmap, response)
        ids = {it.item_id for it in curated.items}
        assert src not in ids
        assert tgt in ids
        # item[1]'s dep on src should now point to tgt
        item1 = next(it for it in curated.items if it.item_id == draft_roadmap.items[1].item_id)
        assert tgt in item1.depends_on

    def test_merge_chain_resolves(self, draft_roadmap: Roadmap):
        # a -> b -> c, expect a rewritten to c and both a and b removed.
        a = draft_roadmap.items[0].item_id
        b = draft_roadmap.items[1].item_id
        c = draft_roadmap.items[2].item_id
        response = {"schema_version": 1, "decisions": [
            {"original_id": a, "action": "merge", "merge_into": b, "rationale": "x"},
            {"original_id": b, "action": "merge", "merge_into": c, "rationale": "y"},
        ]}
        curated = apply_curation(draft_roadmap, response)
        ids = {it.item_id for it in curated.items}
        assert a not in ids
        assert b not in ids
        assert c in ids

    def test_unknown_original_id_rejected(self, draft_roadmap: Roadmap):
        response = {"schema_version": 1, "decisions": [
            {"original_id": "ri-does-not-exist", "action": "drop", "rationale": "x"},
        ]}
        with pytest.raises(ValueError, match="unknown original_id"):
            apply_curation(draft_roadmap, response)

    def test_merge_cycle_rejected(self, draft_roadmap: Roadmap):
        a = draft_roadmap.items[0].item_id
        b = draft_roadmap.items[1].item_id
        response = {"schema_version": 1, "decisions": [
            {"original_id": a, "action": "merge", "merge_into": b, "rationale": "x"},
            {"original_id": b, "action": "merge", "merge_into": a, "rationale": "y"},
        ]}
        with pytest.raises(ValueError, match="cycle"):
            apply_curation(draft_roadmap, response)

    def test_merge_into_unknown_id_rejected(self, draft_roadmap: Roadmap):
        # Regression for Codex P1 (line 268): a typo'd merge target was
        # silently accepted, with the source item deleted and its
        # rewritten deps filtered as unknown later in the pipeline.
        a = draft_roadmap.items[0].item_id
        response = {"schema_version": 1, "decisions": [
            {"original_id": a, "action": "merge",
             "merge_into": "ri-typo-not-a-real-id", "rationale": "x"},
        ]}
        with pytest.raises(ValueError, match="Merge target .* does not match"):
            apply_curation(draft_roadmap, response)

    def test_merge_into_dropped_item_rejected(self, draft_roadmap: Roadmap):
        # Regression for Codex P1 (line 268): merge target was a real id
        # but was itself dropped in the same decision batch. The source
        # item would be silently deleted via the drop chain.
        a = draft_roadmap.items[0].item_id
        b = draft_roadmap.items[1].item_id
        response = {"schema_version": 1, "decisions": [
            {"original_id": a, "action": "merge", "merge_into": b, "rationale": "x"},
            {"original_id": b, "action": "drop", "rationale": "obsolete"},
        ]}
        with pytest.raises(ValueError, match="was itself dropped"):
            apply_curation(draft_roadmap, response)

    def test_colliding_new_ids_rejected(self, draft_roadmap: Roadmap):
        # Regression for Codex P1 (line 303): two keep decisions that
        # rename to the same new_id used to silently drop one item.
        a = draft_roadmap.items[0].item_id
        b = draft_roadmap.items[1].item_id
        response = {"schema_version": 1, "decisions": [
            {"original_id": a, "action": "keep", "new_id": "ri-shared",
             "rationale": "rename a"},
            {"original_id": b, "action": "keep", "new_id": "ri-shared",
             "rationale": "rename b"},
        ]}
        with pytest.raises(ValueError, match="Multiple items resolve to final_id"):
            apply_curation(draft_roadmap, response)

    def test_depends_on_accepts_new_ids(self, draft_roadmap: Roadmap):
        # Rename item[0] to ri-aa; item[1] declares a dep on the new name.
        a = draft_roadmap.items[0].item_id
        b = draft_roadmap.items[1].item_id
        response = {"schema_version": 1, "decisions": [
            {"original_id": a, "action": "keep", "new_id": "ri-aa", "rationale": "rename"},
            {"original_id": b, "action": "keep", "depends_on": ["ri-aa"], "rationale": "dep"},
        ]}
        curated = apply_curation(draft_roadmap, response)
        item_b = next(it for it in curated.items if it.item_id == b)
        assert "ri-aa" in item_b.depends_on

    def test_output_has_no_cycles(self, draft_roadmap: Roadmap):
        # Seed a cycle in deps; apply_curation must break it before returning.
        draft_roadmap.items[0].depends_on = [draft_roadmap.items[1].item_id]
        draft_roadmap.items[1].depends_on = [draft_roadmap.items[0].item_id]
        response = {"schema_version": 1, "decisions": []}
        curated = apply_curation(draft_roadmap, response)
        assert not curated.has_cycle()


# ---------------------------------------------------------------------------
# End-to-end CLI round-trip
# ---------------------------------------------------------------------------
class TestCliRoundTrip:
    def test_structural_then_finalize(self, tmp_path: Path):
        proposal_path = tmp_path / "proposal.md"
        proposal_path.write_text(_FIXTURE_PROPOSAL)
        out_dir = tmp_path / "out"

        curator_script = (
            Path(__file__).resolve().parents[2]
            / "plan-roadmap" / "scripts" / "curator.py"
        )

        # Structural pass
        result = subprocess.run(
            [sys.executable, str(curator_script), "structural",
             "--proposal", str(proposal_path),
             "--out-dir", str(out_dir)],
            capture_output=True, text=True, check=True,
        )
        assert "wrote" in result.stdout

        draft_path = out_dir / "roadmap.draft.yaml"
        request_path = out_dir / "curation-request.json"
        assert draft_path.exists()
        assert request_path.exists()

        request = json.loads(request_path.read_text())
        assert request["schema_version"] == 1
        assert len(request["candidates"]) >= 3  # at least the 3 Capability: sections

        # Simulate an agent turn: keep the three Capability items, drop others,
        # add deps: API depends on DB migration, CLI depends on API.
        originals = {c["original_id"]: c for c in request["candidates"]}
        decisions = []
        db_id = api_id = cli_id = None
        for oid, cand in originals.items():
            title = cand["title"].lower()
            if "database schema" in title:
                db_id = "ri-01-db-migration"
                decisions.append({"original_id": oid, "action": "keep",
                                  "new_id": db_id, "effort": "S", "priority": 1,
                                  "depends_on": [], "rationale": "foundation"})
            elif "rest api" in title:
                api_id = "ri-02-rest-api"
                decisions.append({"original_id": oid, "action": "keep",
                                  "new_id": api_id, "effort": "M", "priority": 2,
                                  "depends_on": ["ri-01-db-migration"],
                                  "rationale": "depends on schema"})
            elif "cli for widget" in title:
                cli_id = "ri-03-cli"
                decisions.append({"original_id": oid, "action": "keep",
                                  "new_id": cli_id, "effort": "S", "priority": 3,
                                  "depends_on": ["ri-02-rest-api"],
                                  "rationale": "wraps api"})
            else:
                decisions.append({"original_id": oid, "action": "drop",
                                  "rationale": "narrative or phase header"})
        assert db_id and api_id and cli_id, "fixture should yield 3 capabilities"

        response_path = out_dir / "curation-response.json"
        response_path.write_text(json.dumps({"schema_version": 1, "decisions": decisions}))

        # Finalize
        final_out = tmp_path / "roadmap.yaml"
        result = subprocess.run(
            [sys.executable, str(curator_script), "finalize",
             "--draft", str(draft_path),
             "--decisions", str(response_path),
             "--out", str(final_out)],
            capture_output=True, text=True, check=True,
        )

        roadmap = load_roadmap(final_out)
        ids = [it.item_id for it in roadmap.items]
        assert ids == ["ri-01-db-migration", "ri-02-rest-api", "ri-03-cli"]

        api = next(it for it in roadmap.items if it.item_id == "ri-02-rest-api")
        assert api.depends_on == ["ri-01-db-migration"]
        cli = next(it for it in roadmap.items if it.item_id == "ri-03-cli")
        assert cli.depends_on == ["ri-02-rest-api"]

        assert not roadmap.has_cycle()

        # Validate final roadmap against the roadmap schema
        from jsonschema import validate as js_validate
        repo_root = Path(__file__).resolve().parents[3]
        schema = json.loads(
            (repo_root / "openspec" / "schemas" / "roadmap.schema.json").read_text()
        )
        data = yaml.safe_load(final_out.read_text())
        js_validate(data, schema)
