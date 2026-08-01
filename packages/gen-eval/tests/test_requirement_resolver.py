"""Requirement identifiers are stable and fail closed (tasks 1.1-1.3).

Spec scenarios:
  - Requirement Identifiers Are Stable And Fail Closed
      · an identifier is derived from the heading
      · two headings deriving the same identifier fail the resolver

Design decisions: D2.

Task 1.1's note drives the REAL specs — every ``openspec/specs/*/spec.md`` —
because a fixture authored alongside the resolver agrees with whatever the
resolver does; only the repository's own headings (632 of them, some
starting with backticks or containing em-dashes) can disagree with it. The
collision test is the one exception: no real collision exists across the 29
capability specs today, so it is constructed under ``tmp_path``.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from gen_eval.traceability import (
    RequirementCollisionError,
    RequirementResolver,
    parse_requirement_headings,
    requirement_id,
    slugify,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SPECS_ROOT = REPO_ROOT / "openspec" / "specs"
CHANGES_ROOT = REPO_ROOT / "openspec" / "changes"

# Same pattern as contracts/traceability.schema.json's `requirements[]` items.
_CITATION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*\.[a-z0-9][a-z0-9-]*$")


def _real_spec_files() -> list[Path]:
    return sorted(SPECS_ROOT.glob("*/spec.md"))


# ---------------------------------------------------------------------------
# 1.1 — identifier derivation from the repository's real specs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("spec_path", _real_spec_files(), ids=lambda p: p.parent.name)
def test_every_derived_id_matches_the_citation_pattern(spec_path: Path) -> None:
    capability = spec_path.parent.name
    headings = parse_requirement_headings(spec_path.read_text(encoding="utf-8"))
    assert headings, (
        f"{spec_path} has no ### Requirement: headings — a broken fixture, not a real spec"
    )
    for heading in headings:
        derived = requirement_id(capability, heading)
        assert _CITATION_PATTERN.match(derived), (
            f"{capability!r} heading {heading!r} derives {derived!r}, which does not "
            f"match the traceability.schema.json citation pattern"
        )


def test_no_real_spec_has_a_slug_collision() -> None:
    """Every one of the 632 current headings derives a distinct id per capability."""
    resolver = RequirementResolver(SPECS_ROOT, CHANGES_ROOT)
    for spec_path in _real_spec_files():
        capability = spec_path.parent.name
        # Raises RequirementCollisionError on a collision — the assertion is
        # that this does not raise for any real capability today.
        by_slug = resolver.effective_headings(capability)
        assert len(by_slug) == len(
            parse_requirement_headings(spec_path.read_text(encoding="utf-8"))
        )


def test_identifier_is_capability_dot_slug() -> None:
    assert requirement_id("agent-coordinator", "File Locking") == (
        "agent-coordinator.file-locking"
    )


def test_slugify_handles_backticks_and_em_dashes() -> None:
    # Real headings from this repository (see openspec/specs/*/spec.md).
    assert slugify("`OPENSPEC_BRANCH_OVERRIDE` SHALL remain orthogonal to the new signal") == (
        "openspec-branch-override-shall-remain-orthogonal-to-the-new-signal"
    )
    assert slugify(
        "New Coordinator Endpoint — Sync-Point Status"
    ) == "new-coordinator-endpoint-sync-point-status"


# ---------------------------------------------------------------------------
# collision — constructed, since no real instance exists (task 1.1 note)
# ---------------------------------------------------------------------------


def test_two_headings_deriving_the_same_slug_fail_the_resolver(tmp_path: Path) -> None:
    specs_root = tmp_path / "specs"
    (specs_root / "widget").mkdir(parents=True)
    (specs_root / "widget" / "spec.md").write_text(
        "## Requirements\n"
        "### Requirement: Foo Bar\n"
        "The system SHALL do a thing.\n\n"
        "### Requirement: Foo, Bar!\n"
        "The system SHALL do a related thing.\n",
        encoding="utf-8",
    )
    resolver = RequirementResolver(specs_root, tmp_path / "changes")
    with pytest.raises(RequirementCollisionError) as excinfo:
        resolver.effective_headings("widget")
    message = str(excinfo.value)
    assert "Foo Bar" in message
    assert "Foo, Bar!" in message
    assert "widget.foo-bar" in message


def test_collision_error_names_the_slug_and_capability(tmp_path: Path) -> None:
    specs_root = tmp_path / "specs"
    (specs_root / "widget").mkdir(parents=True)
    (specs_root / "widget" / "spec.md").write_text(
        "## Requirements\n### Requirement: A\nx\n\n### Requirement: A!\ny\n",
        encoding="utf-8",
    )
    resolver = RequirementResolver(specs_root, tmp_path / "changes")
    with pytest.raises(RequirementCollisionError) as excinfo:
        resolver.effective_headings("widget")
    assert excinfo.value.capability == "widget"
    assert excinfo.value.slug == "a"
    assert set(excinfo.value.headings) == {"A", "A!"}


# ---------------------------------------------------------------------------
# 1.3 — cross-check against OpenSpec's own parse
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("openspec") is None, reason="openspec CLI not on PATH")
@pytest.mark.parametrize("spec_path", _real_spec_files(), ids=lambda p: p.parent.name)
def test_resolver_agrees_with_openspecs_own_parse(spec_path: Path) -> None:
    """The only guard against the resolver and the CLI diverging on what a
    requirement is (task 1.3 note). ``openspec show --json`` enumerates
    requirement TEXT, not headings, so the cross-check is: the count agrees,
    and each requirement's ``openspec``-reported text is contained in the
    resolver's block for the requirement at the same ordinal position — the
    two parses walked the same file in the same order.
    """
    capability = spec_path.parent.name
    result = subprocess.run(
        [
            shutil.which("openspec"),
            "show",
            capability,
            "--json",
            "--type",
            "spec",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    cli_requirements = data["requirements"]

    from gen_eval.traceability import _split_blocks  # noqa: PLC0415 test-only import

    blocks = _split_blocks(spec_path.read_text(encoding="utf-8"))

    assert len(blocks) == len(cli_requirements) == data["requirementCount"], (
        f"{capability}: resolver found {len(blocks)} requirements, openspec show "
        f"reports {len(cli_requirements)} ({data['requirementCount']} declared)"
    )
    for (_, block_text), cli_req in zip(blocks, cli_requirements, strict=True):
        first_line = cli_req["text"].strip().splitlines()[0]
        assert first_line in block_text, (
            f"{capability}: block text does not contain openspec's reported "
            f"requirement text {first_line!r}"
        )
