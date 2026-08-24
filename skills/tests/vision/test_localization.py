"""Guards on the three ways `vision` diverges from its upstream source.

The skill is adapted from https://github.com/kunchenguid/vision. A future
upstream sync is a file-overwrite operation, so each localization gets a test
that fails loudly if the adaptation is reverted rather than re-applied.

Assertions pin mechanisms, not spellings: prose checks run against a
whitespace-collapsed, emphasis-stripped view so copy edits survive, and
numeric constraints are extracted rather than matched as literals.
"""
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
    """Collapse whitespace and strip emphasis markers so prose assertions
    survive line wrapping and bold/italic copy edits."""
    return re.sub(r"\s+", " ", text.replace("*", ""))


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def skill_prose(skill_text: str) -> str:
    """SKILL.md with wrapping and emphasis collapsed, for phrase assertions."""
    return _unwrap(skill_text)


@pytest.fixture(scope="module")
def skill_instructions(skill_text: str) -> str:
    """SKILL.md minus the Provenance section.

    Provenance names the upstream tooling it replaced, so a bare substring ban on
    that tooling would fire on the very note explaining the replacement. Every
    other section is instruction the agent executes, and must stay clean.
    """
    start = skill_text.find("## Provenance")
    end = skill_text.find("## Hard rules")
    assert start != -1 and end > start, "Provenance section must precede Hard rules"
    return skill_text[:start] + skill_text[end:]


@pytest.fixture(scope="module")
def template_text() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


# --- Packaging ------------------------------------------------------------
# Manifest registration is not asserted here: the shared validator
# (skills/shared/validate_install_manifest.py, run by install.sh --check and
# skills/tests/install_sh/) already errors on an unclassified skill and derives
# cross-skill dependencies from the <skill-base-dir>/../ references in SKILL.md.


def test_not_a_vendor_fetch_destination():
    """fetch-vendor-skills.sh overwrites its local destinations in place; the
    adapted skill must never be one. The governing registry is the VENDORS
    array's third pipe-field (the local skill name), not vendor-manifest.json,
    whose paths are upstream-repo source paths."""
    fetcher = (SKILLS_ROOT / "fetch-vendor-skills.sh").read_text(encoding="utf-8")
    block = re.search(r"VENDORS=\((.*?)\)", fetcher, re.DOTALL)
    assert block, "VENDORS registry not found in fetch-vendor-skills.sh"
    locals_ = [
        entry.split("|")[2].strip().split("/")[0]
        for entry in re.findall(r'"([^"]+)"', block.group(1))
        if entry.count("|") == 2
    ]
    assert locals_, "VENDORS registry parsed to zero entries — parser out of date"
    assert "vision" not in locals_, (
        "a VENDORS entry targets local skill 'vision'; the next fetch would "
        "overwrite the adaptation — vision is a first-class repo skill"
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


def test_refuses_rather_than_inventing_evidence(skill_prose: str):
    prose = skill_prose.lower()
    assert "never fabricate" in prose
    assert "stop and say so" in prose, (
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


def test_verdict_batches_fit_the_question_tool(skill_prose: str):
    """AskUserQuestion takes at most 4 questions per call; a batch must leave
    room for the reasoning question in the same call. Extract the stated bound
    rather than pinning a phrase, so any over-cap rewording fails too."""
    m = re.search(r"batches of (\d+)-(\d+) hypotheticals", skill_prose)
    assert m, "6c must state a numeric verdict-batch bound"
    assert int(m.group(2)) + 1 <= 4, (
        f"a {m.group(2)}-card batch plus the reasoning question exceeds the "
        "tool's 4-question cap"
    )


def test_remote_sessions_get_a_reachable_board(skill_prose: str):
    """A container-local path means nothing to the author's browser; remote
    sessions must be told to deliver the board, not hand over a bare path."""
    assert "Remote session" in skill_prose
    assert "Deliver the file" in skill_prose, (
        "the remote-session bullet must name a delivery action for the board"
    )


def test_external_targets_never_write_into_this_repo(skill_prose: str):
    """Step 0 allows an external owner/repo target; its VISION.md must land in a
    clone of the target, never in this repo's checkout or worktree."""
    assert "clone of the target" in skill_prose
    assert "they govern this repo only" in skill_prose


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
# The ban on repo-root `skills/vision/...` runtime paths is not repeated here:
# validate_install_manifest.py's portability scan (exercised by install.sh
# --check and skills/tests/install_sh/) owns that rule for all portable skills.


def test_uses_skill_base_dir_path_convention(skill_text: str):
    assert "<skill-base-dir>" in skill_text, (
        "owned assets and sibling skills must be addressed via <skill-base-dir>; "
        "see skills/references/skill-path-resolution.md"
    )


def test_claims_a_worktree_before_writing(skill_text: str):
    """Pin the mechanism tokens, matching sibling suites (explore-feature,
    quick-task, iterate-on-plan), not one exact quoting of the invocation."""
    assert "worktree.py" in skill_text, "a mutating skill must claim a managed worktree"
    assert "checkout_policy.py" in skill_text and "require-mutation" in skill_text, (
        "the mutation guard must run before the first write"
    )
    assert "WORKTREE_PATH" in skill_text, (
        "setup only prints shell assignments; without eval + cd \"$WORKTREE_PATH\" "
        "the guard runs in the shared checkout and aborts every local run (PR #404 P1)"
    )


# --- Template integrity ---------------------------------------------------

TEMPLATE_SLOTS = ["{{PROJECT}}", "{{RUN_NOTE}}", "{{DRAFT_MARKDOWN}}", "CARDS"]


@pytest.mark.parametrize("slot", TEMPLATE_SLOTS)
def test_template_keeps_its_fill_slots(slot: str, template_text: str):
    assert slot in template_text, f"board template lost its {slot} slot"


def test_template_ships_and_links_the_stylesheet(template_text: str):
    assert STYLESHEET.exists(), f"missing stylesheet at {STYLESHEET}"
    assert 'href="review.css"' in template_text, (
        "the board must load the house stylesheet from beside it"
    )


def test_board_has_no_external_resource_loads(template_text: str):
    """The board opens from disk; a remote asset would make it fail offline."""
    remote = re.findall(r'(?:src|href)="(https?:)?//[^"]+"', template_text)
    assert not remote, f"board template loads external resources: {remote}"


def test_draft_slot_is_not_a_template_literal(template_text: str):
    """The vision's own output format mandates backticks (`{project}`), so a
    backtick-delimited DRAFT literal breaks on every conforming draft (PR #404 P1).
    The slot must be filled as a JSON string literal instead."""
    assert "`{{DRAFT_MARKDOWN}}`" not in template_text, (
        "DRAFT is a backtick template literal again; a conforming draft's inline "
        "code closes it and blanks the board"
    )
    assert "JSON" in template_text, "the DRAFT slot must document its JSON encoding"


def test_card_fields_are_escaped_before_innerhtml(template_text: str):
    """Card fields quote repo history (untrusted text) and land in innerHTML;
    every ${c.<field>} interpolation must pass through esc() (PR #404 P2)."""
    bare = re.findall(r"\$\{c\.\w+\}", template_text)
    assert not bare, f"unescaped card-field interpolations: {bare}"
