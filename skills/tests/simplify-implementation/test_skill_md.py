"""Content invariants for the simplify-implementation skill."""
from pathlib import Path

from skill_invariants import (
    assert_frontmatter_parses,
    assert_references_resolve,
    assert_related_resolve,
    assert_required_keys_present,
    assert_tail_block_present,
)

SKILL_DIR = Path(__file__).resolve().parents[2] / "simplify-implementation"


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
    assert "manual only" in lower or "invocation mode:** **manual" in lower
    assert "not" in lower and "default" in lower and "autopilot" in lower, (
        "simplify must state it is not default-on in autopilot"
    )


def test_simplify_has_redundant_intermediate_pattern():
    text = (SKILL_DIR / "SKILL.md").read_text().lower()
    assert "redundant intermediate" in text


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


# --- Test-pruning phase -------------------------------------------------
#
# These guard the *ordering* and *two-sidedness* of the prune doctrine — the two
# properties whose loss would make the skill unsafe. They deliberately do not
# keyword-check the prose; a prune sweep on this file should be able to reword
# every catalog row without touching these tests.


def test_prune_phase_is_ordered_after_characterization():
    """Pruning before pins exist drops the surface to zero coverage."""
    text = (SKILL_DIR / "SKILL.md").read_text()
    coverage_gate = text.index("## Coverage Gate")
    prune_section = text.index("## Test Pruning")
    assert coverage_gate < prune_section, (
        "Test Pruning must be documented after the Coverage Gate — characterize first"
    )
    characterize_step = text.index("### 2. Coverage gate")
    prune_step = text.index("### 3. Test prune")
    candidate_step = text.index("### 4. Candidate list")
    assert characterize_step < prune_step < candidate_step, (
        "workflow order must be characterize -> prune -> simplify"
    )


def test_prune_catalog_is_two_sided():
    """A delete catalog with no keep catalog licenses unbounded test deletion."""
    text = (SKILL_DIR / "SKILL.md").read_text()
    assert "### Delete catalog" in text
    keep = next(
        (line for line in text.splitlines() if line.startswith("### Keep catalog")),
        None,
    )
    assert keep is not None, (
        "Delete catalog must be paired with a Keep catalog (Chesterton's Fence for tests)"
    )


def test_prune_gate_is_wired_into_verification():
    """A documented phase with no gate in the checklist is unenforced."""
    text = (SKILL_DIR / "SKILL.md").read_text()
    assert (SKILL_DIR / "scripts" / "check_test_prune.py").exists()
    verification = text[text.index("## Verification"):]
    assert "check_test_prune.py" in verification, (
        "the prune gate must appear in the Verification checklist, not only in prose"
    )
