"""Content invariants for the cite-requirements skill.

The skill shipped without any frontmatter, so the harness skill loader could
not index it: it never appeared in the available-skills list and could only be
reached by reading the file directly.
"""

from __future__ import annotations

from pathlib import Path

from skill_invariants import (
    assert_frontmatter_parses,
    assert_related_resolve,
    assert_required_keys_present,
)

SKILL_DIR = Path(__file__).resolve().parents[2] / "cite-requirements"


def test_frontmatter_parses():
    assert_frontmatter_parses(SKILL_DIR)


def test_required_keys_present():
    assert_required_keys_present(SKILL_DIR)


def test_name_matches_directory():
    assert assert_frontmatter_parses(SKILL_DIR)["name"] == "cite-requirements"


def test_related_resolve():
    assert_related_resolve(SKILL_DIR)
