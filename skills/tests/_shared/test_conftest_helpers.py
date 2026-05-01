"""Tests for the 5 invariant assertion helpers in conftest.py.

Each helper is exercised against a known-good fixture (must pass) and a
known-broken fixture (must fail with a clear message). Together these tests
verify the content-invariant test framework requirement.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from skill_invariants import (
    assert_frontmatter_parses,
    assert_references_resolve,
    assert_related_resolve,
    assert_required_keys_present,
    assert_tail_block_present,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_frontmatter_parses_on_good_skill():
    fm = assert_frontmatter_parses(FIXTURES / "good_skill")
    assert fm["name"] == "good-skill"
    assert fm["user_invocable"] is True


def test_frontmatter_parses_fails_on_broken_yaml():
    with pytest.raises(Exception) as exc:
        assert_frontmatter_parses(FIXTURES / "broken_yaml")
    assert "frontmatter" in str(exc.value).lower() or "yaml" in str(exc.value).lower()


def test_required_keys_present_on_good_skill():
    assert_required_keys_present(FIXTURES / "good_skill")


def test_required_keys_present_fails_on_missing_keys():
    with pytest.raises(Exception) as exc:
        assert_required_keys_present(FIXTURES / "missing_keys")
    assert "missing or empty required" in str(exc.value)


def test_tail_block_present_on_good_skill():
    assert_tail_block_present(FIXTURES / "good_skill")


def test_tail_block_present_fails_on_missing_block():
    with pytest.raises(Exception) as exc:
        assert_tail_block_present(FIXTURES / "missing_tail_block")
    assert "tail-block section missing" in str(exc.value)


def test_tail_block_present_exempts_infra_skill():
    """user_invocable: false skills are exempt from tail-block requirement."""
    assert_tail_block_present(FIXTURES / "exempt_infra_skill")


def test_references_resolve_on_good_skill():
    """Good skill cites no references; assertion passes vacuously."""
    assert_references_resolve(FIXTURES / "good_skill")


def test_references_resolve_fails_on_bad_reference():
    with pytest.raises(Exception) as exc:
        assert_references_resolve(FIXTURES / "bad_reference")
    assert "does-not-exist.md" in str(exc.value)


def test_related_resolve_on_good_skill():
    """Good skill has no related: key; assertion passes vacuously."""
    assert_related_resolve(FIXTURES / "good_skill")


def test_related_resolve_fails_on_unknown_target():
    with pytest.raises(Exception) as exc:
        assert_related_resolve(FIXTURES / "bad_related")
    assert "this-skill-does-not-exist" in str(exc.value)
