"""Doc-lint tests for the prototyping-stage updates.

Spec scenarios covered:
- skill-workflow.WorkflowDocumentationUpdates.workflow-doc-describes-prototype-stage
- skill-workflow.WorkflowDocumentationUpdates.claude-md-workflow-diagram-updated

These tests don't validate semantics — they verify that the *visible
references* a future reader needs are present. The CLAUDE.md and
docs/skills-workflow.md flow diagrams are the canonical "where to look
next" pointers; missing /prototype-feature here would mean the new
skill is invisible to operators even though it's installed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS_WORKFLOW_DOC = REPO_ROOT / "docs" / "skills-workflow.md"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"


@pytest.fixture(scope="module")
def workflow_doc() -> str:
    return SKILLS_WORKFLOW_DOC.read_text()


@pytest.fixture(scope="module")
def claude_md() -> str:
    return CLAUDE_MD.read_text()


class TestSkillsWorkflowDocReferencesPrototypeFeature:
    def test_prototype_feature_appears_in_overview_flow(
        self, workflow_doc: str
    ) -> None:
        assert "/prototype-feature" in workflow_doc, (
            "docs/skills-workflow.md must reference /prototype-feature "
            "so operators can find the new optional stage"
        )

    def test_prototype_feature_in_step_dependencies_table(
        self, workflow_doc: str
    ) -> None:
        # The step dependencies table is what operators consult when
        # they're confused about ordering. The prototype stage must
        # appear there to be discoverable.
        # We look for the row by markdown table-cell wrapper.
        assert "| `/prototype-feature`" in workflow_doc, (
            "Step Dependencies table must include a /prototype-feature row"
        )

    def test_iterate_on_plan_prototype_context_referenced(
        self, workflow_doc: str
    ) -> None:
        assert "--prototype-context" in workflow_doc, (
            "docs/skills-workflow.md must mention "
            "/iterate-on-plan --prototype-context as the convergence step"
        )


class TestSkillsWorkflowDocPrinciple:
    """Spec: workflow-doc-describes-prototype-stage requires the
    'Divergence is first-class' principle text to appear under Design Principles."""

    def test_divergence_is_first_class_section_exists(
        self, workflow_doc: str
    ) -> None:
        # Match the principle headline; the body can vary in wording but
        # the headline is the operator's pointer to the explanation.
        assert "Divergence is first-class" in workflow_doc, (
            "docs/skills-workflow.md must add a 'Divergence is first-class "
            "on both sides of the approval gate' section under Design Principles"
        )

    def test_principle_calls_out_both_sides_of_gate(
        self, workflow_doc: str
    ) -> None:
        # The full principle wording matters — "both sides" is the new
        # framing that justifies why /prototype-feature exists alongside
        # /parallel-review-* (review-side divergence).
        assert "both sides" in workflow_doc.lower() or (
            "generation" in workflow_doc.lower()
            and "review" in workflow_doc.lower()
        ), (
            "principle section must explain divergence on BOTH the "
            "generation side (prototype-feature) AND the review side "
            "(parallel-review-*)"
        )


class TestClaudeMdWorkflowDiagramUpdated:
    def test_prototype_feature_in_claude_md_workflow(
        self, claude_md: str
    ) -> None:
        assert "/prototype-feature" in claude_md, (
            "CLAUDE.md workflow diagram must reference /prototype-feature"
        )

    def test_iterate_on_plan_prototype_context_in_claude_md(
        self, claude_md: str
    ) -> None:
        assert "--prototype-context" in claude_md, (
            "CLAUDE.md must reference /iterate-on-plan --prototype-context "
            "as the convergence mechanism"
        )

    def test_prototype_step_appears_after_plan_before_implement(
        self, claude_md: str
    ) -> None:
        # Ordering matters — the prototype step is between plan and implement.
        # If someone accidentally inserts it after implement, it breaks the
        # mental model of "diverge before commit".
        plan_pos = claude_md.find("/plan-feature")
        prototype_pos = claude_md.find("/prototype-feature")
        implement_pos = claude_md.find("/implement-feature")
        assert plan_pos != -1 and prototype_pos != -1 and implement_pos != -1
        assert plan_pos < prototype_pos < implement_pos, (
            "in CLAUDE.md workflow diagram, /prototype-feature must appear "
            "between /plan-feature and /implement-feature"
        )
