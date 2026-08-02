"""Content invariants for the simplify skill."""
from pathlib import Path

from skill_invariants import (
    assert_frontmatter_parses,
    assert_references_resolve,
    assert_related_resolve,
    assert_required_keys_present,
    assert_tail_block_present,
)

SKILL_DIR = Path(__file__).resolve().parents[2] / "simplify"


def test_frontmatter_parses():
    assert_frontmatter_parses(SKILL_DIR)


def test_required_keys_present():
    assert_required_keys_present(SKILL_DIR)


def test_references_resolve():
    assert_references_resolve(SKILL_DIR)


def test_related_resolve():
    assert_related_resolve(SKILL_DIR)


def test_tail_block_present():
    assert_tail_block_present(SKILL_DIR)


def test_simplify_has_chestertons_fence_and_rule_of_500():
    text = (SKILL_DIR / "SKILL.md").read_text()
    assert "Chesterton" in text, "simplify must reference Chesterton's Fence"
    assert "Rule of 500" in text, "simplify must reference Rule of 500"


def test_simplify_has_coverage_gate_and_characterization():
    text = (SKILL_DIR / "SKILL.md").read_text()
    assert "Coverage Gate" in text or "coverage gate" in text.lower()
    assert "characterization" in text.lower(), (
        "simplify must require characterization tests when the surface is unpinned"
    )


def test_simplify_has_dual_run_verification():
    text = (SKILL_DIR / "SKILL.md").read_text()
    lower = text.lower()
    assert "dual-run" in lower or "dual run" in lower, (
        "simplify must require dual-run verification (baseline + HEAD)"
    )
    assert "baseline" in lower


def test_simplify_mentions_state_based_or_beyonce():
    text = (SKILL_DIR / "SKILL.md").read_text()
    lower = text.lower()
    assert "state-based" in lower or "beyoncé" in lower or "beyonce" in lower, (
        "simplify must prefer state-based tests / Beyoncé Rule composition with TDD"
    )


def test_simplify_has_isomorphic_extract_pattern():
    text = (SKILL_DIR / "SKILL.md").read_text()
    lower = text.lower()
    assert "isomorphic extract" in lower or "isomorphic" in lower
    assert "dead code" in lower


def test_simplify_manual_invocation_only():
    text = (SKILL_DIR / "SKILL.md").read_text()
    lower = text.lower()
    assert "manual" in lower
    assert "autopilot" in lower and (
        "not" in lower or "default" in lower
    ), "simplify must state it is not default-on in autopilot"


def test_simplify_documents_scripts():
    text = (SKILL_DIR / "SKILL.md").read_text()
    assert "check_scope.py" in text
    assert "check_test_contract.py" in text
    assert "verify_behavior_preservation.py" in text


def test_related_includes_tdd_and_tech_debt():
    text = (SKILL_DIR / "SKILL.md").read_text()
    # frontmatter related list
    assert "test-driven-development" in text
    assert "tech-debt-analysis" in text
