"""Every skill must carry the frontmatter the harness skill loader needs.

This is deliberately the loader minimum, not the full content invariant in
`skill_invariants.REQUIRED_FRONTMATTER_KEYS`: several skills (explain-code,
the vendored upstream skills) legitimately omit `triggers`, `category` or
`tags`, and per-skill `test_skill_md.py` files own those stricter checks.

What no skill may omit is a parseable frontmatter block with a `name` equal to
its directory and a non-empty `description`. Without them the loader cannot
index the skill, so it silently disappears from the available-skills list.
`cite-requirements` shipped that way; this guard fails on that commit.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skill_invariants import assert_frontmatter_parses

SKILLS_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIRS = sorted(p.parent for p in SKILLS_ROOT.glob("*/SKILL.md"))


def test_skills_were_discovered():
    assert len(SKILL_DIRS) > 10, f"glob under {SKILLS_ROOT} found too few skills"


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_loader_frontmatter(skill_dir: Path):
    fm = assert_frontmatter_parses(skill_dir)
    assert fm.get("name") == skill_dir.name, (
        f"{skill_dir.name}/SKILL.md: frontmatter name {fm.get('name')!r} "
        f"must equal the directory name"
    )
    description = fm.get("description")
    assert isinstance(description, str) and description.strip(), (
        f"{skill_dir.name}/SKILL.md: frontmatter needs a non-empty description"
    )
