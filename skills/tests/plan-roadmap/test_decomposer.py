"""Tests for the plan-roadmap validation-only decomposer module."""

from __future__ import annotations

import copy
import tempfile
from pathlib import Path

import pytest
from decomposer import (
    main,
    make_repo_relative,
    scan_archive_state,
    validate_proposal,
    validate_roadmap,
)

# Repo root: skills/tests/plan-roadmap/test_decomposer.py -> parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _valid_roadmap() -> dict:
    return {
        "schema_version": 1,
        "roadmap_id": "roadmap-example",
        "source_proposal": "openspec/roadmaps/example/proposal.md",
        "status": "planning",
        "policy": {"default_action": "wait_if_budget_exceeded"},
        "items": [
            {
                "item_id": "ri-01",
                "title": "Add structured logging",
                "description": "Emit JSON logs.",
                "rationale": "Foundation for metrics.",
                "status": "candidate",
                "priority": 1,
                "effort": "S",
                "depends_on": [],
                "acceptance_outcomes": ["Logs are JSON."],
            },
            {
                "item_id": "ri-02",
                "title": "Export metrics",
                "description": "Add /metrics endpoint.",
                "rationale": "Enables alerting.",
                "status": "candidate",
                "priority": 2,
                "effort": "M",
                "depends_on": ["ri-01"],
                "acceptance_outcomes": ["/metrics returns counters."],
            },
        ],
    }


PROSE_PROPOSAL_NO_KEYWORDS = """\
# Tidy Up the Onboarding Flow

## Background

New folks get lost in the first ten minutes. We want the first run to feel
calm and obvious, with sensible defaults and a clear next step.

## What we want

A welcome screen, a guided first task, and a way to skip ahead for power users.
"""


# ---------------------------------------------------------------------------
# validate_proposal — readiness gate, NOT a vocabulary gate
# ---------------------------------------------------------------------------
class TestValidateProposal:
    def test_empty_fails(self):
        errors = validate_proposal("")
        assert errors
        assert any("empty" in e.lower() for e in errors)

    def test_whitespace_only_fails(self):
        assert validate_proposal("   \n\t  ") != []

    def test_no_headings_fails(self):
        errors = validate_proposal("just a paragraph with no headings at all")
        assert errors
        assert any("heading" in e.lower() for e in errors)

    def test_heading_passes(self):
        assert validate_proposal("# Title\n\nSome body text.") == []

    def test_prose_without_capability_vocabulary_passes(self):
        # The old keyword gate would reject this; the new gate must not.
        assert validate_proposal(PROSE_PROPOSAL_NO_KEYWORDS) == []


# ---------------------------------------------------------------------------
# validate_roadmap — schema + semantic integrity
# ---------------------------------------------------------------------------
class TestValidateRoadmap:
    def test_valid_roadmap_passes(self):
        assert validate_roadmap(_valid_roadmap(), _REPO_ROOT) == []

    def test_non_mapping_rejected(self):
        errors = validate_roadmap([1, 2, 3], _REPO_ROOT)  # type: ignore[arg-type]
        assert errors
        assert any("mapping" in e.lower() for e in errors)

    def test_missing_required_field_is_schema_error(self):
        data = _valid_roadmap()
        del data["roadmap_id"]
        errors = validate_roadmap(data, _REPO_ROOT)
        assert errors
        assert all(e.startswith("Schema:") for e in errors)

    def test_bad_effort_enum_is_schema_error(self):
        data = _valid_roadmap()
        data["items"][0]["effort"] = "HUGE"
        errors = validate_roadmap(data, _REPO_ROOT)
        assert errors
        assert any(e.startswith("Schema:") for e in errors)

    def test_duplicate_item_id_rejected(self):
        data = _valid_roadmap()
        data["items"][1]["item_id"] = "ri-01"
        # fix the now-dangling dependency so we isolate the duplicate check
        data["items"][1]["depends_on"] = []
        errors = validate_roadmap(data, _REPO_ROOT)
        assert any("duplicate" in e.lower() and "ri-01" in e for e in errors)

    def test_dangling_dependency_rejected(self):
        data = _valid_roadmap()
        data["items"][1]["depends_on"] = ["ri-99"]
        errors = validate_roadmap(data, _REPO_ROOT)
        assert any("ri-99" in e and "not a declared" in e for e in errors)

    def test_self_dependency_rejected(self):
        data = _valid_roadmap()
        data["items"][0]["depends_on"] = ["ri-01"]
        errors = validate_roadmap(data, _REPO_ROOT)
        assert any("depends on itself" in e for e in errors)

    def test_cycle_rejected(self):
        data = _valid_roadmap()
        data["items"][0]["depends_on"] = ["ri-02"]  # ri-01 <-> ri-02
        errors = validate_roadmap(data, _REPO_ROOT)
        assert any("cycle" in e.lower() for e in errors)

    def test_dangling_dep_suppresses_cycle_noise(self):
        # A dangling reference should report the reference error, not a
        # confusing cycle error layered on top.
        data = _valid_roadmap()
        data["items"][1]["depends_on"] = ["ri-99"]
        errors = validate_roadmap(data, _REPO_ROOT)
        assert not any("cycle" in e.lower() for e in errors)

    def test_errors_are_independent_of_input_mutation(self):
        data = _valid_roadmap()
        snapshot = copy.deepcopy(data)
        validate_roadmap(data, _REPO_ROOT)
        assert data == snapshot  # validation must not mutate the input


# ---------------------------------------------------------------------------
# scan_archive_state
# ---------------------------------------------------------------------------
class TestScanArchiveState:
    def test_archived_and_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "openspec" / "changes" / "archive" / "2026-01-15-old-feature"
            archive.mkdir(parents=True)
            active = root / "openspec" / "changes" / "new-feature"
            active.mkdir(parents=True)

            state = scan_archive_state(root)
            assert state["old-feature"] == "completed"
            assert state["new-feature"] == "in_progress"

    def test_archive_takes_precedence_over_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "openspec" / "changes" / "archive" / "2026-01-15-dup").mkdir(parents=True)
            (root / "openspec" / "changes" / "dup").mkdir(parents=True)
            state = scan_archive_state(root)
            assert state["dup"] == "completed"

    def test_empty_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            assert scan_archive_state(Path(tmp)) == {}


# ---------------------------------------------------------------------------
# make_repo_relative
# ---------------------------------------------------------------------------
class TestMakeRepoRelative:
    def test_absolute_inside_root(self):
        root = Path("/repo")
        assert make_repo_relative("/repo/openspec/x.md", root) == "openspec/x.md"

    def test_already_relative_unchanged(self):
        assert make_repo_relative("openspec/x.md", Path("/repo")) == "openspec/x.md"

    def test_absolute_outside_root_unchanged(self):
        assert make_repo_relative("/elsewhere/x.md", Path("/repo")) == "/elsewhere/x.md"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
class TestCli:
    def _write(self, tmp: str, data: dict) -> Path:
        import yaml

        path = Path(tmp) / "roadmap.yaml"
        path.write_text(yaml.dump(data, sort_keys=False))
        return path

    def test_validate_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, _valid_roadmap())
            rc = main(["validate", str(path), "--repo-root", str(_REPO_ROOT)])
            assert rc == 0

    def test_validate_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = _valid_roadmap()
            data["items"][1]["depends_on"] = ["ri-99"]
            path = self._write(tmp, data)
            rc = main(["validate", str(path), "--repo-root", str(_REPO_ROOT)])
            assert rc == 1

    def test_validate_missing_file(self):
        rc = main(["validate", "/nonexistent/roadmap.yaml", "--repo-root", str(_REPO_ROOT)])
        assert rc == 2
