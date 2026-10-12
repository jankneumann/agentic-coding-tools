"""SKILL.md contract (design D1, D6): it must document the module it ships with."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

import evidence_ledger  # on sys.path via conftest.py

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_MD = REPO_ROOT / "skills" / "evidence-ledger" / "SKILL.md"


def _split() -> tuple[dict, str]:
    text = SKILL_MD.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    assert match, "SKILL.md must start with a YAML frontmatter block"
    return yaml.safe_load(match.group(1)), match.group(2)


def test_frontmatter_names_the_skill() -> None:
    front, _ = _split()
    assert front["name"] == "evidence-ledger"
    assert front["category"]
    assert front["description"]


def test_skill_is_not_user_invocable() -> None:
    front, _ = _split()
    assert front["user_invocable"] is False


def test_every_violation_code_is_documented() -> None:
    _, body = _split()
    missing = sorted(c for c in evidence_ledger.VIOLATION_CODES if f"`{c}`" not in body)
    assert missing == []


def test_reserved_source_unavailable_kind_is_documented() -> None:
    _, body = _split()
    assert "`source_unavailable`" in body


def test_paths_are_relative_to_the_skill_base_dir() -> None:
    _, body = _split()
    assert "<skill-base-dir>/scripts/evidence_ledger.py" in body
    assert "skills/evidence-ledger/" not in body
