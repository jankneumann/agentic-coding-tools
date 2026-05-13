"""Shared pytest helpers — re-exports from skill_invariants.py.

Per-skill `test_skill_md.py` files should import from `skill_invariants`
(stable module path) rather than from `conftest` (which pytest auto-discovers
specially and is not safe to import via the normal mechanism).

This conftest.py exposes a `skill_invariants` fixture for ergonomic use.
"""
from __future__ import annotations

import pytest

from skill_invariants import (
    assert_frontmatter_parses,
    assert_references_resolve,
    assert_related_resolve,
    assert_required_keys_present,
    assert_tail_block_present,
)


@pytest.fixture
def skill_invariants():
    """Bundle of all five invariant helpers as a fixture for ergonomic test code."""
    return {
        "frontmatter": assert_frontmatter_parses,
        "required_keys": assert_required_keys_present,
        "references": assert_references_resolve,
        "related": assert_related_resolve,
        "tail_block": assert_tail_block_present,
    }
