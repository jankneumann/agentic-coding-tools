"""Structural guard for docs/guides/multiplayer-collaboration.md.

Enforces only what is mechanical (headings, links, resolvable change-ids).
Content accuracy of the solo/team cells is a review check.
"""

import re
from pathlib import Path

from openspec_paths import change_dir, repo_root_from

ROOT = repo_root_from(__file__, 3)
GUIDE = ROOT / "docs/guides/multiplayer-collaboration.md"
GUIDE_REL = "docs/guides/multiplayer-collaboration.md"
INBOUND = (ROOT / "AGENTS.md", ROOT / "docs/guides/documentation.md")
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
TICKS = re.compile(r"`([^`]+)`")
GUARANTEE = "Solo mode adds no new prompts, gates, or PR checkpoints."
SKILL_ROWS = (
    "plan-feature",
    "implement-feature",
    "validate-feature",
    "autopilot",
    "autopilot-roadmap",
    "supervise",
    "cleanup-feature",
    "reconcile",
    "install.sh",
)
ASSUMPTION_COLUMNS = ("Assumption", "Where it lives", "Team failure mode", "Addressed by")
SKILL_COLUMNS = ("Skill", "Solo mode", "Team mode", "Delivered by")


def change_id_resolves(root: Path, change_id: str) -> bool:
    return change_dir(root, change_id).is_dir()


def read_guide() -> str:
    assert GUIDE.exists(), f"{GUIDE_REL} is missing"
    return GUIDE.read_text()


def section(text: str, heading: str) -> str:
    """Body of the `## heading` section, up to the next `## ` heading."""
    match = re.search(
        rf"^## {re.escape(heading)}[ \t]*$(.*?)(?=^## |\Z)", text, re.M | re.S
    )
    assert match, f"missing required section '## {heading}'"
    return match.group(1)


def table_rows(body: str, columns: tuple) -> list:
    lines = [ln.strip() for ln in body.splitlines() if ln.strip().startswith("|")]
    assert lines, "no markdown table found"
    header = [c.strip() for c in lines[0].strip("|").split("|")]
    assert tuple(header) == columns, f"table columns {header} != {list(columns)}"
    rows = []
    for ln in lines[2:]:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        assert len(cells) == len(columns), f"row has wrong cell count: {ln}"
        rows.append(cells)
    return rows


def check_change_ids(cell: str, where: str) -> None:
    ids = TICKS.findall(cell)
    assert ids, f"{where}: no backticked change-id"
    for cid in ids:
        assert change_id_resolves(ROOT, cid), f"{where}: change-id '{cid}' does not resolve"


def principal_sections(text: str) -> list:
    body = section(text, "Principles")
    parts = re.split(r"^### ", body, flags=re.M)[1:]
    return ["### " + p for p in parts]


def test_guide_is_linked_from_entry_points():
    assert GUIDE.exists(), f"{GUIDE_REL} is missing"
    for src in INBOUND:
        targets = [t.split("#")[0] for t in LINK.findall(src.read_text())]
        resolved = [(src.parent / t).resolve() for t in targets if t]
        assert GUIDE.resolve() in resolved, (
            f"{src.relative_to(ROOT)} has no link resolving to {GUIDE_REL}"
        )


def test_guide_has_no_links_into_archivable_openspec_paths():
    text = read_guide()
    archivable = (ROOT / "openspec/changes").resolve(), (ROOT / "openspec/roadmaps").resolve()
    for target in LINK.findall(text):
        if re.match(r"[a-z]+:", target) or target.startswith("#"):
            continue
        resolved = (GUIDE.parent / target.split("#")[0]).resolve()
        for base in archivable:
            assert base not in (resolved, *resolved.parents), (
                f"link '{target}' points into archivable path {base.relative_to(ROOT)}"
            )


def test_principles_p1_to_p10_in_order_with_resolvable_implementers():
    sections = principal_sections(read_guide())
    headings = [s.splitlines()[0] for s in sections]
    assert len(headings) == 10, f"expected 10 principle headings, found {len(headings)}"
    for n, head in enumerate(headings, start=1):
        assert head.startswith(f"### P{n}. "), f"principle {n}: heading '{head}' is out of order"
    for sec in sections:
        name = sec.splitlines()[0]
        lines = sec.splitlines()
        existing = next((ln for ln in lines if ln.startswith("**Existing:**")), None)
        planned = next((ln for ln in lines if ln.startswith("**Planned:**")), None)
        assert existing, f"{name}: missing **Existing:** line"
        assert planned, f"{name}: missing **Planned:** line"
        links = LINK.findall(existing)
        for target in links:
            path = (GUIDE.parent / target.split("#")[0]).resolve()
            assert path.exists(), f"{name}: existing link '{target}' does not resolve"
        ids = TICKS.findall(planned)
        for cid in ids:
            assert change_id_resolves(ROOT, cid), (
                f"{name}: planned change-id '{cid}' does not resolve"
            )
        assert links or ids, f"{name}: names no implementer (Existing and Planned both empty)"


def test_assumption_table():
    body = section(read_guide(), "Single-principal assumptions")
    rows = table_rows(body, ASSUMPTION_COLUMNS)
    assert len(rows) == 8, f"expected 8 assumption rows, found {len(rows)}"
    for cells in rows:
        check_change_ids(cells[3], f"assumption '{cells[0]}'")


def test_modes_section():
    body = section(read_guide(), "Modes")
    for term in ("**Principal**", "**Solo mode**", "**Team mode**"):
        assert term in body, f"## Modes lacks bold term {term}"
    assert GUARANTEE in body, f"## Modes lacks exact sentence: {GUARANTEE!r}"
    assert "`ownership-map`" in body, "## Modes does not name `ownership-map`"
    assert "passive output" in body, "## Modes lacks the 'passive output' clause"


def test_per_skill_table():
    body = section(read_guide(), "Skills in solo and team mode")
    rows = table_rows(body, SKILL_COLUMNS)
    by_skill = {r[0].strip("`"): r for r in rows}
    for skill in SKILL_ROWS:
        assert skill in by_skill, f"per-skill table is missing row for '{skill}'"
    for skill, cells in by_skill.items():
        assert cells[1], f"skill '{skill}': empty Solo mode cell"
        assert cells[2], f"skill '{skill}': empty Team mode cell"
        check_change_ids(cells[3], f"skill '{skill}'")


def test_authority_and_maintenance_section():
    body = section(read_guide(), "Authority and maintenance")
    for phrase in ("specs are normative", "archived", "same pull request"):
        assert phrase in body, f"## Authority and maintenance lacks phrase '{phrase}'"


def test_change_id_resolution_accepts_archived_only_change(tmp_path):
    archived = tmp_path / "openspec/changes/archive/2026-01-01-some-change"
    archived.mkdir(parents=True)
    assert change_id_resolves(tmp_path, "some-change")
    assert not change_id_resolves(tmp_path, "absent-change")
