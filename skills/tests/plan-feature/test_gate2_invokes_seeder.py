"""Content-assertion tests for /plan-feature Gate 2 seeder invocation.

These tests verify the SKILL.md text mentions the seeder by name and documents
its idempotency caveat. The actual orchestration is exercised by the
wp-integration end-to-end test (5.1).

Covers tasks 3.1, 3.2.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2].parent
_PLAN_FEATURE_SKILL = _REPO_ROOT / "skills" / "plan-feature" / "SKILL.md"


def _read_skill() -> str:
    return _PLAN_FEATURE_SKILL.read_text(encoding="utf-8")


def test_step_12_mentions_seed_tasks_from_md_on_approve():
    """SKILL.md Step 12 (Gate 2 Plan Approval) must reference the seeder script
    on the Approve outcome."""
    text = _read_skill()
    # Find Step 12 section.
    idx = text.find("### 12. Gate 2: Plan Approval")
    assert idx != -1, "Step 12 heading missing from plan-feature SKILL.md"
    # Limit scope to Step 12 region.
    next_section_idx = text.find("### 13.", idx)
    if next_section_idx == -1:
        next_section_idx = text.find("## Output", idx)
    assert next_section_idx != -1
    section = text[idx:next_section_idx]
    # The seeder filename SHALL appear in the Approve block.
    assert "seed_tasks_from_md.py" in section, (
        "Step 12 must reference seed_tasks_from_md.py — Gate 2 Approve invokes "
        "the seeder per change add-coordinator-task-status-renderer"
    )


def test_step_12_documents_idempotency_caveat():
    """SKILL.md Step 12 must document idempotency on the (change:<id>, task:<key>)
    label pair, OR cite D3/D7."""
    text = _read_skill()
    idx = text.find("### 12. Gate 2: Plan Approval")
    assert idx != -1
    next_section_idx = text.find("### 13.", idx)
    if next_section_idx == -1:
        next_section_idx = text.find("## Output", idx)
    section = text[idx:next_section_idx]
    has_idempotency = (
        "idempot" in section.lower()
        or "task:<key>" in section
        or "(change:<id>, task:<key>)" in section
        or "D3" in section
        or "D7" in section
    )
    assert has_idempotency, (
        "Step 12 must document the seeder's idempotency guarantee "
        "(mention idempotency OR the (change:<id>, task:<key>) label pair OR cite D3/D7)"
    )
