"""Content invariants for skills/skill-audit/SKILL.md (design D7, D9).

Keys are asserted explicitly rather than through ``assert_required_keys_present``
(whose tuple still lists ``triggers``), so the test passes both with the
``triggers:`` key present and with it stripped. Pattern: add-visual-code-explainer D6.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
import yaml

from skill_invariants import (
    assert_frontmatter_parses,
    assert_references_resolve,
    assert_related_resolve,
    assert_tail_block_present,
)

SKILL_DIR = Path(__file__).resolve().parents[2] / "skill-audit"
_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _strip_triggers(skill_md: Path) -> None:
    text = skill_md.read_text(encoding="utf-8")
    match = _FRONTMATTER.match(text)
    assert match
    fm = yaml.safe_load(match.group(1))
    fm.pop("triggers", None)
    skill_md.write_text("---\n" + yaml.safe_dump(fm, sort_keys=False).rstrip() + "\n---\n" + text[match.end():], encoding="utf-8")


@pytest.fixture(params=["with-triggers", "without-triggers"])
def skill_dir(request, tmp_path) -> Path:
    if request.param == "with-triggers":
        return SKILL_DIR
    copy = tmp_path / "skill-audit"
    shutil.copytree(SKILL_DIR, copy)
    _strip_triggers(copy / "SKILL.md")
    fm = assert_frontmatter_parses(copy)
    assert "triggers" not in fm
    return copy


def test_frontmatter_parses(skill_dir):
    assert_frontmatter_parses(skill_dir)


def test_explicit_required_keys(skill_dir):
    fm = assert_frontmatter_parses(skill_dir)
    assert fm["name"] == "skill-audit"
    assert fm["description"] and "SKILL.md" in fm["description"] and "model-tier fit" in fm["description"]
    assert fm["category"]
    assert isinstance(fm["tags"], list) and fm["tags"]
    assert fm["user_invocable"] is True
    assert fm["related"] == ["improve-harness", "agent-ergonomics", "prioritize-proposals"]


def test_related_excludes_audit_choices_and_resolves(skill_dir):
    fm = assert_frontmatter_parses(skill_dir)
    assert "audit-choices" not in fm["related"]
    assert_related_resolve(SKILL_DIR)


def test_description_disambiguates_from_other_audits():
    fm = assert_frontmatter_parses(SKILL_DIR)
    assert "audit-choices" in fm["description"]
    assert "coordinator" in fm["description"]


def test_references_resolve_and_are_one_level_deep(skill_dir):
    assert_references_resolve(SKILL_DIR)
    cited = set(re.findall(r"references/([A-Za-z0-9._/-]+\.md)", (skill_dir / "SKILL.md").read_text()))
    assert cited == {"layers.md", "dispatch-map.md", "usage.md"}
    for name in cited:
        assert "/" not in name
        assert (skill_dir / "references" / name).is_file()
    assert all(p.parent == skill_dir / "references" for p in (skill_dir / "references").rglob("*.md"))


def test_tail_block_present(skill_dir):
    assert_tail_block_present(skill_dir)


def test_line_budget(skill_dir):
    assert len((skill_dir / "SKILL.md").read_text().splitlines()) <= 150


def test_skill_states_read_only_contract():
    text = (SKILL_DIR / "SKILL.md").read_text()
    assert "never edits the audited skill" in text
    assert "--check-freshness" in text and "--propose" in text and "--convention" in text
    assert '"<skill-base-dir>/scripts/skill_audit.py"' in text
