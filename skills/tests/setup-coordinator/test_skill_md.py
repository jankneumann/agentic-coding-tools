"""Content invariants for the setup-coordinator skill.

Imported from ``skill_invariants``, never from ``conftest``: the shared conftest
warns it is not safe to import normally, and several sibling suites ship one.

``assert_tail_block_present`` applies here because the frontmatter does not set
``user_invocable: false``. The file carried none of the three tail-block
sections before this change, so that assertion introduces a requirement rather
than merely restating one.
"""

from __future__ import annotations

import re
from pathlib import Path

from skill_invariants import (
    assert_frontmatter_parses,
    assert_references_resolve,
    assert_related_resolve,
    assert_required_keys_present,
    assert_tail_block_present,
)

SKILL_DIR = Path(__file__).resolve().parents[2] / "setup-coordinator"
SKILL_MD = SKILL_DIR / "SKILL.md"

LINE_BUDGET = (120, 150)
SUBCOMMANDS = ("detect-harnesses", "check", "configure", "report")


def _text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def test_frontmatter_parses_and_declares_the_required_keys():
    assert_frontmatter_parses(SKILL_DIR)
    assert_required_keys_present(SKILL_DIR)


def test_references_and_related_targets_resolve():
    assert_references_resolve(SKILL_DIR)
    assert_related_resolve(SKILL_DIR)


def test_tail_block_is_present():
    assert_tail_block_present(SKILL_DIR)


def test_line_count_is_within_the_budget():
    lines = len(_text().splitlines())
    low, high = LINE_BUDGET
    assert low <= lines <= high, f"SKILL.md is {lines} lines; budget is {low}-{high}"


def test_the_entrypoint_is_invoked_through_the_skill_base_placeholder():
    """A literal canonical path is rejected by the payload linter (D8)."""
    text = _text()
    assert "<skill-base-dir>/scripts/setup_coordinator.py" in text
    assert not re.search(r"skills/setup-coordinator/scripts/", text)


def test_every_subcommand_is_documented():
    text = _text()
    for name in SUBCOMMANDS:
        assert name in text, f"SKILL.md never mentions the `{name}` subcommand"


def test_knowledge_content_survived_the_rewrite():
    """The transport table, HTTP guidance, and troubleshooting list are the
    model-facing knowledge a script cannot carry, so they must stay."""
    text = _text()
    assert "## Transport Model" in text
    assert "| Scenario | Transport | Database |" in text
    assert "## When to use HTTP" in text
    assert "## Fallback and Troubleshooting" in text
    assert "COORDINATION_ALLOWED_HOSTS" in text


def test_the_improvised_settings_fragment_is_gone():
    """The inline JSON edit is the defect surface this change removes."""
    text = _text()
    assert "grep -q" not in text
    assert "settings.setdefault" not in text
    assert "json.dumps(settings" not in text


def test_operator_owned_steps_are_reported_not_performed():
    text = _text()
    assert 'make -C "$COORDINATOR_DIR" mcp-setup' in text
    assert 'make -C "$COORDINATOR_DIR" hooks-setup' in text
    assert "never performs them" in text or "it never performs them" in text


def test_presence_is_not_validity_is_stated():
    text = _text().lower()
    assert "presence only" in text
    assert "unexpired" in text or "expiry" in text
