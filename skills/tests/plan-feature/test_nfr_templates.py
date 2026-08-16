"""NFR capture contract for the feature-workflow templates and plan-feature rubric.

Fitness-function-driven development needs an *objective, measurable* quality
target recorded at planning time -- otherwise there is nothing to write a
fitness function against. These tests pin the three places that capture it:
the proposal template (declares the NFR), the design template (maps it to the
check that verifies it), and the plan-feature discovery rubric (elicits it).
"""
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATES = _REPO_ROOT / "openspec" / "schemas" / "feature-workflow" / "templates"
_PROPOSAL_TEMPLATE = _TEMPLATES / "proposal.md"
_DESIGN_TEMPLATE = _TEMPLATES / "design.md"
_SKILL_MD = _REPO_ROOT / "skills" / "plan-feature" / "SKILL.md"


def _section(text: str, heading: str) -> str:
    """Return the body of `heading` up to the next heading of the same level."""
    level = len(heading) - len(heading.lstrip("#"))
    start = text.index(heading)
    rest = text[start + len(heading):]
    nxt = re.search(rf"^#{{1,{level}}} ", rest, re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def test_proposal_template_has_nfr_section():
    text = _PROPOSAL_TEMPLATE.read_text()
    assert "## Non-Functional Requirements" in text, (
        "proposal.md template must declare a '## Non-Functional Requirements' section "
        "so measurable quality targets are captured at planning time"
    )

    body = _section(text, "## Non-Functional Requirements")
    for prompt in ("Attribute", "Metric", "Target", "Verified by"):
        assert prompt in body, (
            f"NFR section must prompt for {prompt!r} "
            "(attribute / metric / target / verifying phase)"
        )
    assert "|" in body, "NFR section must carry a table for the declared targets"
    assert "phase" in body.lower(), (
        "NFR section must name the phase that verifies each target"
    )

    # Placement: after What Changes, before Approaches Considered.
    assert (
        text.index("## What Changes")
        < text.index("## Non-Functional Requirements")
        < text.index("## Approaches Considered")
    ), "NFR section must sit between '## What Changes' and '## Approaches Considered'"


def test_design_template_has_fitness_mapping():
    text = _DESIGN_TEMPLATE.read_text()
    assert "### Fitness Functions" in text, (
        "design.md template must carry a '### Fitness Functions' subsection mapping "
        "each declared NFR to the check that verifies it"
    )

    body = _section(text, "### Fitness Functions")
    assert "proposal.md" in body, (
        "Fitness Functions subsection must reference the NFRs declared in proposal.md"
    )
    lowered = body.lower()
    assert "check" in lowered, (
        "Fitness Functions subsection must name the check that verifies each NFR"
    )
    assert "defer" in lowered, (
        "Fitness Functions subsection must allow an NFR to be explicitly deferred "
        "rather than silently unmapped"
    )


def test_rubric_has_nfr_category():
    text = _SKILL_MD.read_text()
    section = _section(text, "#### 3b. Discovery Questions")

    assert "six categories" not in section, (
        "Discovery category count must be updated once the NFR category is added"
    )
    assert re.search(r"^7\. \*\*", section, re.MULTILINE), (
        "Discovery questions must include a 7th category for NFR elicitation, "
        "formatted like categories 1-6"
    )

    category7 = section[section.index("\n7. **") :]
    assert "AskUserQuestion" in category7, (
        "NFR category must use the AskUserQuestion tool like categories 1-6"
    )
    assert "Examples:" in category7, (
        "NFR category must carry an Examples line like categories 1-6"
    )
    assert "Non-Functional Requirements" in category7, (
        "NFR category must state that answers populate the proposal's "
        "Non-Functional Requirements table"
    )
    lowered = category7.lower()
    for quality in (
        "observability",
        "resilience",
        "performance",
        "compatibility",
        "operability",
    ):
        assert quality in lowered, (
            f"NFR category must prompt for the {quality!r} architectural quality"
        )
