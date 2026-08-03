"""Scaffolded roadmap changes must be valid OpenSpec changes.

The scaffolder used to create ``specs/`` and write nothing into it. Git does not
track empty directories, so the directory vanished on commit and the change failed
``openspec validate --strict`` with "Change must have at least one delta."

These tests pin the three properties that failure violated: a delta file is
written, it survives a commit, and OpenSpec itself accepts it.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from models import Effort, ItemStatus, Roadmap, RoadmapItem, RoadmapStatus
from scaffolder import scaffold_changes


def _item(
    item_id: str = "dg-01",
    title: str = "Pin the isolation contract",
    **kwargs,
) -> RoadmapItem:
    defaults = {
        "status": ItemStatus.APPROVED,
        "priority": 1,
        "effort": Effort.S,
        "depends_on": [],
        "description": "Specify the isolation vocabulary in one place.",
        "rationale": "Producer and consumer must agree on the vocabulary.",
        "acceptance_outcomes": [
            "The isolation vocabulary is specified once and referenced by both sides",
            "A coordinator-unreachable path yields a defined decision rather than an error",
        ],
    }
    defaults.update(kwargs)
    return RoadmapItem(item_id=item_id, title=title, **defaults)


def _roadmap(items: list[RoadmapItem] | None = None) -> Roadmap:
    return Roadmap(
        schema_version=1,
        roadmap_id="dispatch-governance",
        source_proposal="proposals/dispatch-governance.md",
        items=items if items is not None else [_item()],
        status=RoadmapStatus.APPROVED,
    )


# ---------------------------------------------------------------------------
# A delta is written at all
# ---------------------------------------------------------------------------
def test_scaffold_writes_a_spec_delta(tmp_path: Path) -> None:
    (created,) = scaffold_changes(_roadmap(), tmp_path)

    deltas = list((created / "specs").rglob("spec.md"))
    assert deltas, "scaffold produced no spec delta — specs/ would vanish on commit"

    body = deltas[0].read_text()
    assert "## ADDED Requirements" in body
    assert "### Requirement:" in body
    assert "#### Scenario:" in body


def test_every_acceptance_outcome_becomes_a_requirement(tmp_path: Path) -> None:
    item = _item(
        acceptance_outcomes=["Alpha holds", "Beta holds", "Gamma holds"]
    )
    (created,) = scaffold_changes(_roadmap([item]), tmp_path)

    body = next((created / "specs").rglob("spec.md")).read_text()
    assert body.count("### Requirement:") == 3
    assert body.count("#### Scenario:") == 3
    for outcome in ("Alpha holds", "Beta holds", "Gamma holds"):
        assert outcome in body


def test_requirement_body_leads_with_the_modal_verb(tmp_path: Path) -> None:
    """OpenSpec --strict inspects only a requirement's FIRST line for SHALL/MUST."""
    (created,) = scaffold_changes(_roadmap(), tmp_path)
    body = next((created / "specs").rglob("spec.md")).read_text()

    for block in body.split("### Requirement:")[1:]:
        lines = [ln for ln in block.splitlines()[1:] if ln.strip()]
        assert lines, "requirement has an empty body"
        assert "SHALL" in lines[0] or "MUST" in lines[0], (
            f"first body line lacks a modal verb: {lines[0]!r}"
        )


def test_outcome_that_already_states_shall_is_not_double_wrapped(tmp_path: Path) -> None:
    item = _item(acceptance_outcomes=["The router SHALL emit an isolation value"])
    (created,) = scaffold_changes(_roadmap([item]), tmp_path)
    body = next((created / "specs").rglob("spec.md")).read_text()

    assert "The system SHALL ensure that the router SHALL" not in body
    assert "The router SHALL emit an isolation value." in body


def test_item_without_outcomes_still_produces_a_valid_delta(tmp_path: Path) -> None:
    """An item with nothing recorded must still scaffold something that validates."""
    item = _item(acceptance_outcomes=[])
    (created,) = scaffold_changes(_roadmap([item]), tmp_path)

    body = next((created / "specs").rglob("spec.md")).read_text()
    assert "### Requirement:" in body
    assert "#### Scenario:" in body
    assert "SHALL" in body


# ---------------------------------------------------------------------------
# Capability placement
# ---------------------------------------------------------------------------
def test_capability_defaults_to_the_roadmap_id(tmp_path: Path) -> None:
    (created,) = scaffold_changes(_roadmap(), tmp_path)
    assert (created / "specs" / "dispatch-governance" / "spec.md").exists()


def test_explicit_capability_overrides_the_default(tmp_path: Path) -> None:
    item = _item(capability="vendor-dispatch")
    (created,) = scaffold_changes(_roadmap([item]), tmp_path)
    assert (created / "specs" / "vendor-dispatch" / "spec.md").exists()


def test_scaffold_is_marked_as_preliminary(tmp_path: Path) -> None:
    """A sketch that does not announce itself gets mistaken for a considered spec."""
    (created,) = scaffold_changes(_roadmap(), tmp_path)
    body = next((created / "specs").rglob("spec.md")).read_text()
    assert "SCAFFOLD" in body
    assert "refinement" in body.lower()


# ---------------------------------------------------------------------------
# design.md is emitted only when it carries something
# ---------------------------------------------------------------------------
def test_design_is_written_when_the_item_has_rationale(tmp_path: Path) -> None:
    (created,) = scaffold_changes(_roadmap(), tmp_path)
    assert (created / "design.md").exists()


def test_design_is_skipped_when_there_is_nothing_to_say(tmp_path: Path) -> None:
    item = _item(rationale=None, depends_on=[])
    (created,) = scaffold_changes(_roadmap([item]), tmp_path)
    assert not (created / "design.md").exists()


# ---------------------------------------------------------------------------
# The properties that actually bit
# ---------------------------------------------------------------------------
def test_specs_survive_a_commit(tmp_path: Path) -> None:
    """The original defect: an empty specs/ is silently dropped by git."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    scaffold_changes(_roadmap(), tmp_path)
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e",
        "PATH": __import__("os").environ["PATH"],
    }
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "scaffold"], cwd=tmp_path, check=True, env=env)

    tracked = subprocess.run(
        ["git", "ls-files"], cwd=tmp_path, check=True,
        capture_output=True, text=True, env=env,
    ).stdout
    assert "specs/" in tracked and "spec.md" in tracked, (
        "spec delta was not committed — specs/ was empty and git dropped it"
    )


@pytest.mark.skipif(shutil.which("openspec") is None, reason="openspec CLI not installed")
def test_scaffolded_change_passes_openspec_strict(tmp_path: Path) -> None:
    """The end-to-end property: OpenSpec itself accepts the scaffold."""
    (tmp_path / "openspec").mkdir()
    (tmp_path / "openspec" / "project.md").write_text("# Test project\n")
    (tmp_path / "openspec" / "specs").mkdir()

    scaffold_changes(_roadmap(), tmp_path)

    result = subprocess.run(
        ["openspec", "validate", "pin-the-isolation-contract", "--type", "change", "--strict"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"scaffolded change failed openspec --strict:\n"
        f"{result.stdout}\n{result.stderr}"
    )
