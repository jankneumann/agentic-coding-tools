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
#: Since `5fe437b1 feat(context): restructure CLAUDE.md into TOC + topic docs`,
#: CLAUDE.md is a table of contents and the workflow diagram it used to inline
#: lives here. The invariant these tests hold is unchanged -- an operator who
#: starts at CLAUDE.md can reach /prototype-feature -- but it is now satisfied
#: by a link plus a diagram in two files rather than by one file.
WORKFLOW_GUIDE = REPO_ROOT / "docs" / "guides" / "workflow.md"


@pytest.fixture(scope="module")
def workflow_doc() -> str:
    return SKILLS_WORKFLOW_DOC.read_text()


@pytest.fixture(scope="module")
def claude_md() -> str:
    return CLAUDE_MD.read_text()


@pytest.fixture(scope="module")
def workflow_guide() -> str:
    return WORKFLOW_GUIDE.read_text()


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
    """The CLAUDE.md -> workflow-diagram chain must still reach the prototype stage.

    CLAUDE.md no longer inlines the diagram, so "is it in CLAUDE.md" is the
    wrong question; asking it let these tests pass vacuously right up until
    they were first run. The reader's path is what matters: CLAUDE.md must
    link to the guide, and the guide must carry the references in order.
    """

    def test_claude_md_links_to_the_workflow_guide(self, claude_md: str) -> None:
        # Without this link the guide is unreachable from the entry point and
        # the two tests below would be checking an orphaned file.
        assert "docs/guides/workflow.md" in claude_md, (
            "CLAUDE.md must link to docs/guides/workflow.md -- it is the "
            "pointer that replaced the inlined workflow diagram"
        )

    def test_prototype_feature_in_workflow_diagram(
        self, workflow_guide: str
    ) -> None:
        assert "/prototype-feature" in workflow_guide, (
            "the workflow diagram must reference /prototype-feature"
        )

    def test_iterate_on_plan_prototype_context_in_workflow_diagram(
        self, workflow_guide: str
    ) -> None:
        assert "--prototype-context" in workflow_guide, (
            "the workflow diagram must reference "
            "/iterate-on-plan --prototype-context as the convergence mechanism"
        )

    def test_prototype_step_appears_after_plan_before_implement(
        self, workflow_guide: str
    ) -> None:
        # Ordering matters -- the prototype step is between plan and implement.
        # If someone accidentally inserts it after implement, it breaks the
        # mental model of "diverge before commit".
        plan_pos = workflow_guide.find("/plan-feature")
        prototype_pos = workflow_guide.find("/prototype-feature")
        implement_pos = workflow_guide.find("/implement-feature")
        assert plan_pos != -1 and prototype_pos != -1 and implement_pos != -1
        assert plan_pos < prototype_pos < implement_pos, (
            "in the workflow diagram, /prototype-feature must appear "
            "between /plan-feature and /implement-feature"
        )
