import pytest
from openspec_paths import change_dir, repo_root_from


ROOT = repo_root_from(__file__, 3)
CHANGE_ID = "write-durable-state-artifacts-guide"
DESIGN = change_dir(ROOT, CHANGE_ID) / "design.md"
GUIDE = ROOT / "docs/guides/state-artifacts.md"
DOCUMENTATION_INDEX = ROOT / "docs/guides/documentation.md"
SKILL_NAMES = (
    "autopilot",
    "autopilot-roadmap",
    "session-log",
    "supervise",
    "implement-feature",
    "validate-feature",
)
GUIDE_REFERENCE = "docs/guides/state-artifacts.md"


def test_guide_documents_all_five_artifact_classes_and_ownership_fields():
    assert GUIDE.exists(), "canonical durable state-artifacts guide is missing"
    text = GUIDE.read_text()
    for artifact in (
        "Per-change loop state",
        "Roadmap checkpoint",
        "Roadmap learning entry",
        "Phase record",
        "Handoff document",
    ):
        assert artifact in text
    for field in (
        "Path / holder",
        "Canonical writer",
        "Authority",
        "Consumers",
        "Missing or stale behavior",
    ):
        assert field in text


def test_guide_pins_rehydration_order_and_conflict_rules():
    text = GUIDE.read_text()
    text_lower = text.lower()
    ordered = (
        "1. Bootstrap locator",
        "2. Roadmap definition",
        "3. Roadmap execution state",
        "4. Change execution state",
        "5. Learning context",
        "6. Phase history",
        "7. Handoff context",
        "8. Rebuild projections",
    )
    positions = [text.index(marker) for marker in ordered]
    assert positions == sorted(positions)
    assert "newer advisory timestamp never overrides canonical state" in text_lower
    assert "never-started roadmap" in text_lower
    assert "claimed prior progress" in text_lower


@pytest.mark.parametrize("skill_name", SKILL_NAMES)
def test_canonical_skill_references_state_artifacts_guide(skill_name: str):
    text = (ROOT / f"skills/{skill_name}/SKILL.md").read_text()
    assert GUIDE_REFERENCE in text


def test_documentation_index_references_state_artifacts_guide():
    assert "(state-artifacts.md)" in DOCUMENTATION_INDEX.read_text()


def test_supervise_rehydration_matches_canonical_order():
    text = (ROOT / "skills/supervise/SKILL.md").read_text()
    markers = (
        "Bootstrap locator",
        "Roadmap definition",
        "Roadmap execution state",
        "Change execution state",
        "Learning context",
        "Phase history",
        "Handoff context",
        "Rebuild projections",
    )
    positions = [text.index(marker) for marker in markers]
    assert positions == sorted(positions)


def test_design_rehydration_matches_canonical_order():
    text = DESIGN.read_text()
    markers = (
        "1. Bootstrap locator",
        "2. Roadmap definition",
        "3. Roadmap execution state",
        "4. Change execution state",
        "5. Learning context",
        "6. Phase history",
        "7. Handoff context",
        "8. Rebuild projections",
    )
    positions = [text.index(marker) for marker in markers]
    assert positions == sorted(positions)


@pytest.mark.parametrize("skill_name", SKILL_NAMES)
def test_changed_skill_mirrors_are_byte_identical(skill_name: str):
    canonical = (ROOT / f"skills/{skill_name}/SKILL.md").read_bytes()
    agents = ROOT / f".agents/skills/{skill_name}/SKILL.md"
    claude = ROOT / f".claude/skills/{skill_name}/SKILL.md"
    if not agents.exists() or not claude.exists():
        pytest.skip("runtime mirrors are installed artifacts, not tracked checkout inputs")
    assert agents.read_bytes() == canonical
    assert claude.read_bytes() == canonical


def _ownership_row() -> str:
    rows = [
        line
        for line in GUIDE.read_text().splitlines()
        if line.startswith("|") and "`openspec/owners.yaml`" in line
    ]
    assert len(rows) == 1, "inventory must carry exactly one openspec/owners.yaml row"
    return rows[0]


def test_inventory_row_for_ownership_map_covers_every_cell():
    row = _ownership_row()
    cells = [c.strip() for c in row.strip().strip("|").split("|")]
    header = [
        c.strip()
        for c in next(
            line for line in GUIDE.read_text().splitlines() if line.startswith("| Artifact class")
        )
        .strip()
        .strip("|")
        .split("|")
    ]
    assert len(cells) == len(header)
    assert all(cells), "no empty cell in the ownership-map row"
    assert "Ownership map" in cells[0]
    # writer: humans by reviewed PR, no skill writes it
    assert "reviewed PR" in cells[2] and "No skill writes it" in cells[2]
    # authority names the fail-closed default owner
    assert "default owner" in cells[3].lower()
    # missing/stale cell: absence is solo mode, invalid fails closed
    assert "solo mode" in cells[5].lower()
    assert "fails closed" in cells[5].lower()


def test_ownership_row_names_codeowners_as_derived_projection():
    row = _ownership_row()
    assert "CODEOWNERS" in row
    assert "derived projection" in row
