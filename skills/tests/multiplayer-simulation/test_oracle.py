"""Ground-truth collision oracle tests (C.1, C.2; design D4)."""

from __future__ import annotations

from pathlib import Path

from mpsim.oracle import collision_present, delta_requirements


def _delta(root: Path, capability: str, *headings: str) -> Path:
    spec = root / "specs" / capability / "spec.md"
    spec.parent.mkdir(parents=True)
    body = "## MODIFIED Requirements\n\n" + "".join(
        f"### Requirement: {h}\n\nThe system SHALL do {h}.\n\n" for h in headings
    )
    spec.write_text(body)
    return root


def test_same_heading_in_same_capability_is_a_collision(tmp_path):
    a = _delta(tmp_path / "a", "sim-notes", "Note Titles")
    b = _delta(tmp_path / "b", "sim-notes", "Note Titles", "Other")
    assert collision_present(a, b) is True


def test_different_headings_in_same_capability_are_not_a_collision(tmp_path):
    a = _delta(tmp_path / "a", "sim-notes", "Note Titles")
    b = _delta(tmp_path / "b", "sim-notes", "Note Bodies")
    assert collision_present(a, b) is False


def test_same_heading_in_different_capabilities_is_not_a_collision(tmp_path):
    a = _delta(tmp_path / "a", "sim-notes", "Note Titles")
    b = _delta(tmp_path / "b", "sim-tags", "Note Titles")
    assert collision_present(a, b) is False


def test_delta_requirements_returns_capability_heading_pairs(tmp_path):
    root = _delta(tmp_path / "a", "sim-notes", "One", "Two")
    assert delta_requirements(root) == {("sim-notes", "One"), ("sim-notes", "Two")}


def test_a_delta_without_specs_has_no_requirements(tmp_path):
    (tmp_path / "empty").mkdir()
    assert delta_requirements(tmp_path / "empty") == set()
    assert collision_present(tmp_path / "empty", tmp_path / "empty") is False
