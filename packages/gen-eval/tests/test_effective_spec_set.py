"""The effective requirement set: archive shadowed by the active change (tasks 1.4-1.5).

Spec scenarios:
  - The Active Change's Spec Delta Shadows The Archived Spec
      · a citation to the change's own new requirement resolves
      · removing a requirement breaks operations that still cite it
      · renaming a requirement moves its identifier, fail-closed
      · another change's unarchived requirement cannot be referenced

Design decisions: D11.

The ADDED case drives this change's own real delta
(``openspec/changes/trace-requirements-to-contracts/specs/gen-eval-framework/spec.md``)
and the other-change-invisible case drives a real change directory
(``add-coordinator-llm-gateway``, which adds a capability with no archived
spec at all). REMOVED and RENAMED have no instance in the repository today,
so they are constructed under ``tmp_path`` via the resolver's injectable
roots.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from gen_eval.traceability import (
    MalformedDeltaError,
    RequirementResolver,
    UnresolvedRequirementError,
    requirement_id,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SPECS_ROOT = REPO_ROOT / "openspec" / "specs"
CHANGES_ROOT = REPO_ROOT / "openspec" / "changes"

THIS_CHANGE = "trace-requirements-to-contracts"


# ---------------------------------------------------------------------------
# ADDED — driven by this change's own real delta
# ---------------------------------------------------------------------------


def test_a_citation_to_this_changes_own_new_requirement_resolves() -> None:
    resolver = RequirementResolver(SPECS_ROOT, CHANGES_ROOT)
    req_id = requirement_id(
        "gen-eval-framework", "Contracted operations cite the requirements they serve"
    )
    heading = resolver.resolve(req_id, change_id=THIS_CHANGE)
    assert heading == "Contracted operations cite the requirements they serve"


def test_this_changes_new_requirement_does_not_resolve_without_the_change_id() -> None:
    """The archive alone (no shadow) does not yet know about an unlanded requirement."""
    resolver = RequirementResolver(SPECS_ROOT, CHANGES_ROOT)
    req_id = requirement_id(
        "gen-eval-framework", "Contracted operations cite the requirements they serve"
    )
    with pytest.raises(UnresolvedRequirementError):
        resolver.resolve(req_id, change_id=None)


def test_all_added_requirements_resolve_under_this_change() -> None:
    """Every ADDED heading in this change's own delta resolves.

    The count check is a deliberate trip-wire, not incidental: a parser
    regression that silently drops or duplicates headings would make the
    loop below pass on whatever subset survived. Rather than pin a literal
    (this test originally hardcoded 14; task 4.1 added a 15th ADDED
    requirement, "Pass-rate gating governs exit status", in 89365ffe
    without updating this number — exactly the staleness this rewrite
    removes), count `### Requirement:` headings in the raw delta text
    independently of the resolver's own parser and assert the two agree.
    A future ADDED requirement changes both sides of that comparison
    together, so this test cannot go stale the way the count literal did.
    """
    resolver = RequirementResolver(SPECS_ROOT, CHANGES_ROOT)
    delta_path = CHANGES_ROOT / THIS_CHANGE / "specs" / "gen-eval-framework" / "spec.md"
    from gen_eval.traceability import parse_requirement_headings  # noqa: PLC0415

    delta_text = delta_path.read_text(encoding="utf-8")
    added_headings = parse_requirement_headings(delta_text)
    raw_heading_count = len(re.findall(r"^### Requirement:", delta_text, flags=re.MULTILINE))
    assert raw_heading_count >= 1, "fixture assumption: the ADDED section is non-empty"
    assert len(added_headings) == raw_heading_count, (
        "parse_requirement_headings found a different number of headings than a raw "
        "count of the delta text — the parser dropped, merged, or duplicated one"
    )
    assert len(set(added_headings)) == len(added_headings), "no duplicate ADDED heading"
    for heading in added_headings:
        req_id = requirement_id("gen-eval-framework", heading)
        assert resolver.resolve(req_id, change_id=THIS_CHANGE) == heading


# ---------------------------------------------------------------------------
# other-change invisibility — driven by a real, different change directory
# ---------------------------------------------------------------------------


def test_another_changes_unarchived_requirement_cannot_be_referenced() -> None:
    """``llm-gateway`` is added by add-coordinator-llm-gateway, not archived,
    and not this change. It must be invisible regardless of which change_id
    (or none) this resolver was handed.
    """
    other_change = "add-coordinator-llm-gateway"
    delta_path = CHANGES_ROOT / other_change / "specs" / "llm-gateway" / "spec.md"
    assert delta_path.is_file(), "fixture assumption: this real change dir still exists"
    assert not (SPECS_ROOT / "llm-gateway").is_dir(), (
        "fixture assumption: llm-gateway has not been archived yet"
    )

    resolver = RequirementResolver(SPECS_ROOT, CHANGES_ROOT)
    req_id = requirement_id("llm-gateway", "Data Plane Is a Separate Deployable")

    for change_id in (None, THIS_CHANGE):
        with pytest.raises(UnresolvedRequirementError) as excinfo:
            resolver.resolve(req_id, change_id=change_id)
        # Must say "not in the effective set", not merely "not found" — the
        # two are different problems (task 1.4 note).
        assert "effective requirement set" in str(excinfo.value)


# ---------------------------------------------------------------------------
# REMOVED — constructed (no real instance today)
# ---------------------------------------------------------------------------


def _write_spec(specs_root: Path, capability: str, headings: list[str]) -> None:
    body = "## Requirements\n\n" + "\n\n".join(
        f"### Requirement: {h}\n\nThe system SHALL do the {h} thing.\n\n"
        f"#### Scenario: it happens\n\n- WHEN x\n- THEN y\n"
        for h in headings
    )
    target = specs_root / capability / "spec.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")


def _write_delta(
    changes_root: Path,
    change_id: str,
    capability: str,
    *,
    added: list[str] | None = None,
    removed: list[str] | None = None,
    renamed: list[tuple[str, str]] | None = None,
) -> None:
    parts: list[str] = []
    if added:
        parts.append(
            "## ADDED Requirements\n\n"
            + "\n\n".join(
                f"### Requirement: {h}\n\nThe system SHALL do the {h} thing.\n" for h in added
            )
        )
    if removed:
        parts.append(
            "## REMOVED Requirements\n\n"
            + "\n\n".join(f"### Requirement: {h}\n" for h in removed)
        )
    if renamed:
        lines = ["## RENAMED Requirements\n"]
        for old, new in renamed:
            lines.append(f"- FROM: `### Requirement: {old}`")
            lines.append(f"- TO: `### Requirement: {new}`")
        parts.append("\n".join(lines))
    target = changes_root / change_id / "specs" / capability / "spec.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n\n".join(parts) + "\n", encoding="utf-8")


def test_removing_a_requirement_breaks_operations_that_still_cite_it(tmp_path: Path) -> None:
    specs_root = tmp_path / "specs"
    changes_root = tmp_path / "changes"
    _write_spec(specs_root, "widget", ["Alpha Feature", "Beta Feature"])
    _write_delta(changes_root, "remove-alpha", "widget", removed=["Alpha Feature"])

    resolver = RequirementResolver(specs_root, changes_root)
    req_id = requirement_id("widget", "Alpha Feature")

    # Still resolves against the archive alone.
    assert resolver.resolve(req_id, change_id=None) == "Alpha Feature"
    # Removed by the change: an operation still citing it now fails.
    with pytest.raises(UnresolvedRequirementError):
        resolver.resolve(req_id, change_id="remove-alpha")
    # Beta is untouched and still resolves under the same change.
    assert resolver.resolve(requirement_id("widget", "Beta Feature"), change_id="remove-alpha") == (
        "Beta Feature"
    )


def test_removing_an_absent_requirement_fails_closed(tmp_path: Path) -> None:
    specs_root = tmp_path / "specs"
    changes_root = tmp_path / "changes"
    _write_spec(specs_root, "widget", ["Alpha Feature"])
    _write_delta(changes_root, "bad-remove", "widget", removed=["Nonexistent Feature"])

    resolver = RequirementResolver(specs_root, changes_root)
    with pytest.raises(MalformedDeltaError):
        resolver.effective_headings("widget", change_id="bad-remove")


# ---------------------------------------------------------------------------
# RENAMED — constructed (no real instance today)
# ---------------------------------------------------------------------------


def test_renaming_a_requirement_moves_its_identifier_fail_closed(tmp_path: Path) -> None:
    specs_root = tmp_path / "specs"
    changes_root = tmp_path / "changes"
    _write_spec(specs_root, "widget", ["Old Name"])
    _write_delta(
        changes_root, "rename-it", "widget", renamed=[("Old Name", "New Name")]
    )

    resolver = RequirementResolver(specs_root, changes_root)
    old_id = requirement_id("widget", "Old Name")
    new_id = requirement_id("widget", "New Name")

    # Old id resolves against the archive alone...
    assert resolver.resolve(old_id, change_id=None) == "Old Name"
    # ...but stops resolving once the rename lands (fail closed, both directions).
    with pytest.raises(UnresolvedRequirementError):
        resolver.resolve(old_id, change_id="rename-it")
    # The new id starts resolving under the same change.
    assert resolver.resolve(new_id, change_id="rename-it") == "New Name"
    # And the new id does NOT resolve without the change (D11 shadowing).
    with pytest.raises(UnresolvedRequirementError):
        resolver.resolve(new_id, change_id=None)


def test_rename_from_an_absent_source_fails_closed(tmp_path: Path) -> None:
    specs_root = tmp_path / "specs"
    changes_root = tmp_path / "changes"
    _write_spec(specs_root, "widget", ["Alpha Feature"])
    _write_delta(
        changes_root, "bad-rename", "widget", renamed=[("Nonexistent", "New Name")]
    )
    resolver = RequirementResolver(specs_root, changes_root)
    with pytest.raises(MalformedDeltaError):
        resolver.effective_headings("widget", change_id="bad-rename")


def test_rename_to_an_existing_target_fails_closed(tmp_path: Path) -> None:
    specs_root = tmp_path / "specs"
    changes_root = tmp_path / "changes"
    _write_spec(specs_root, "widget", ["Alpha Feature", "Beta Feature"])
    _write_delta(
        changes_root, "bad-rename2", "widget", renamed=[("Alpha Feature", "Beta Feature")]
    )
    resolver = RequirementResolver(specs_root, changes_root)
    with pytest.raises(MalformedDeltaError):
        resolver.effective_headings("widget", change_id="bad-rename2")
