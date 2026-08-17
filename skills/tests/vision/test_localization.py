"""Guards on the three ways `vision` diverges from its upstream source.

The skill is adapted from https://github.com/kunchenguid/vision. A future
upstream sync is a file-overwrite operation, so each localization gets a test
that fails loudly if the adaptation is reverted rather than re-applied.
"""
import json
import re
from pathlib import Path

import pytest

SKILLS_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = SKILLS_ROOT.parent
SKILL_DIR = SKILLS_ROOT / "vision"
SKILL_MD = SKILL_DIR / "SKILL.md"
TEMPLATE = SKILL_DIR / "assets" / "review-template.html"
STYLESHEET = SKILL_DIR / "assets" / "review.css"


def _unwrap(text: str) -> str:
    """Collapse whitespace so prose assertions survive line wrapping."""
    return re.sub(r"\s+", " ", text)


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def skill_prose(skill_text: str) -> str:
    """SKILL.md with wrapping collapsed, for phrase assertions."""
    return _unwrap(skill_text)


@pytest.fixture(scope="module")
def skill_instructions(skill_text: str) -> str:
    """SKILL.md minus the Provenance section.

    Provenance names the upstream tooling it replaced, so a bare substring ban on
    that tooling would fire on the very note explaining the replacement. Every
    other section is instruction the agent executes, and must stay clean.
    """
    start = skill_text.find("## Provenance")
    end = skill_text.find("## Host requirement")
    assert start != -1 and end > start, "Provenance section must precede Host requirement"
    return skill_text[:start] + skill_text[end:]


@pytest.fixture(scope="module")
def template_text() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


# --- Packaging ------------------------------------------------------------


def test_board_assets_ship_with_the_skill():
    """install.sh rsyncs whole skill dirs, so assets/ ships; both files must exist."""
    assert TEMPLATE.exists(), f"missing board template at {TEMPLATE}"
    assert STYLESHEET.exists(), f"missing stylesheet at {STYLESHEET}"


def test_registered_in_install_manifest():
    manifest = json.loads((SKILLS_ROOT / "install-manifest.json").read_text(encoding="utf-8"))
    assert "vision" in manifest["skills"], "vision missing from install-manifest.json skills"
    assert manifest["cross_skill_dependencies"].get("vision") == ["shared", "worktree"], (
        "vision declares a worktree/shared dependency; keep cross_skill_dependencies in sync"
    )


def test_not_registered_as_a_vendor_skill():
    """fetch-vendor-skills.sh overwrites files in place and would clobber the adaptation."""
    vendors = json.loads((SKILLS_ROOT / "vendor-manifest.json").read_text(encoding="utf-8"))
    for name, entry in vendors["vendors"].items():
        for path in entry.get("paths", []):
            assert not path.endswith("skills/vision"), (
                f"vendor entry {name} would overwrite the adapted skill at {path}; "
                "vision is a first-class repo skill, not a vendored copy"
            )


def test_upstream_attribution_is_recorded(skill_text: str):
    assert "kunchenguid/vision" in skill_text, "upstream attribution (MIT) must be preserved"


# --- Localization 1: evidence ladder --------------------------------------

# Paths the Step 3 evidence ladder tells the agent to mine. Each must actually
# exist, or the ladder sends the agent looking for artifacts this repo lacks.
EVIDENCE_PATHS = [
    "openspec/project.md",
    "openspec/specs",
    "openspec/changes/archive",
    "docs/decisions",
    "docs/guides",
    "docs/merge-logs",
    "CLAUDE.md",
]


@pytest.mark.parametrize("rel", EVIDENCE_PATHS)
def test_evidence_ladder_cites_paths_that_exist(rel: str, skill_text: str):
    assert rel in skill_text, f"evidence ladder no longer cites {rel}"
    assert (REPO_ROOT / rel).exists(), f"evidence ladder cites {rel}, which does not exist"


def test_decision_artifacts_outrank_pr_titles(skill_text: str):
    """Tier A (proposals, ADRs) must be introduced before Tier B (merged PRs)."""
    tier_a = skill_text.find("Tier A - Decision artifacts")
    tier_b = skill_text.find("Tier B - Merged pull requests")
    tier_c = skill_text.find("Tier C - Commit history")
    assert -1 not in (tier_a, tier_b, tier_c), "the three evidence tiers must all be present"
    assert tier_a < tier_b < tier_c, "evidence tiers must be ordered A -> B -> C"


def test_refuses_rather_than_inventing_evidence(skill_text: str):
    assert "Never fabricate" in skill_text
    assert re.search(r"\*\*stop\*\*", skill_text), (
        "the skill must stop when no evidence tier is readable"
    )


# --- Localization 2: verdict channel --------------------------------------


def test_verdicts_return_through_the_repo_question_tool(skill_text: str):
    assert "AskUserQuestion" in skill_text, (
        "verdicts must return through AskUserQuestion, this repo's human-gate tool"
    )
    assert "numbered list" in skill_text, (
        "a runtime without AskUserQuestion needs the documented inline fallback"
    )


def test_external_review_service_is_not_reintroduced(
    skill_instructions: str, template_text: str
):
    """The upstream loop shells out to `npx -y lavish-axi`; the adapted one does not."""
    for name, text in (
        ("SKILL.md", skill_instructions),
        ("review-template.html", template_text),
    ):
        assert "npx -y lavish-axi" not in text, (
            f"{name} reintroduces the external lavish-axi launch; the adapted review "
            "loop runs from a local file with verdicts via AskUserQuestion"
        )
        assert "npx skills add" not in text, (
            f"{name} reintroduces the upstream npx install path; this repo installs "
            "skills through skills/install.sh"
        )


def test_in_page_ledger_is_not_the_channel_of_record(skill_prose: str, template_text: str):
    assert "never as the channel of record" in skill_prose
    assert "channel of record" in template_text, (
        "the template header must warn that its ledger is a convenience, not the record"
    )


# --- Localization 3: repo conventions -------------------------------------


def test_uses_skill_base_dir_path_convention(skill_text: str):
    assert "<skill-base-dir>" in skill_text, (
        "owned assets and sibling skills must be addressed via <skill-base-dir>; "
        "see skills/references/skill-path-resolution.md"
    )
    assert not re.search(r"(?<!\.)\bskills/vision/assets\b", skill_text), (
        "repo-root paths are not valid installed runtime paths"
    )


def test_claims_a_worktree_before_writing(skill_text: str):
    assert "worktree.py" in skill_text, "a mutating skill must claim a managed worktree"
    assert (
        'python3 "<skill-base-dir>/../shared/checkout_policy.py" require-mutation'
        in skill_text
    ), "the mutation guard must run, in the canonical form, before the first write"


# --- Template integrity ---------------------------------------------------

TEMPLATE_SLOTS = ["{{PROJECT}}", "{{RUN_NOTE}}", "{{DRAFT_MARKDOWN}}", "CARDS"]


@pytest.mark.parametrize("slot", TEMPLATE_SLOTS)
def test_template_keeps_its_fill_slots(slot: str, template_text: str):
    assert slot in template_text, f"board template lost its {slot} slot"


def test_template_references_the_shipped_stylesheet(template_text: str):
    assert 'href="review.css"' in template_text, (
        "the board must load the house stylesheet from beside it"
    )


def test_board_has_no_external_resource_loads(template_text: str):
    """The board opens from disk; a remote asset would make it fail offline."""
    remote = re.findall(r'(?:src|href)="(https?:)?//[^"]+"', template_text)
    assert not remote, f"board template loads external resources: {remote}"
