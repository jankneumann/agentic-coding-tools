"""Content invariants for the cleanup-feature skill."""
import re
from pathlib import Path

from skill_invariants import (
    assert_frontmatter_parses,
    assert_references_resolve,
    assert_related_resolve,
    assert_required_keys_present,
    assert_tail_block_present,
)

SKILL_DIR = Path(__file__).resolve().parents[2] / "cleanup-feature"

_HEADING = re.compile(r"^(#{2,4})\s+(.*)$", re.MULTILINE)


def _skill_text() -> str:
    return (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")


def _section(needle: str) -> str:
    """Return the text of the first heading whose title contains ``needle``.

    The section runs from its own heading to the next heading at the same or a
    shallower level, so an assertion scoped to a section cannot be satisfied by
    prose that lives somewhere else in the file.
    """
    text = _skill_text()
    headings = list(_HEADING.finditer(text))
    for index, match in enumerate(headings):
        if needle.lower() not in match.group(2).lower():
            continue
        level = len(match.group(1))
        for following in headings[index + 1 :]:
            if len(following.group(1)) <= level:
                return text[match.start() : following.start()]
        return text[match.start() :]
    raise AssertionError(
        f"{SKILL_DIR / 'SKILL.md'}: no heading found containing {needle!r}"
    )


def _defer_commit_section() -> str:
    return _section("Deferred-Commit")


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


def test_cleanup_feature_has_staged_rollout():
    text = (SKILL_DIR / "SKILL.md").read_text()
    assert "Staged Rollout" in text or "staged rollout" in text.lower()
    for marker in ("5%", "25%", "50%", "100%"):
        assert marker in text, f"Staged rollout sequence missing {marker}"


# --- ri-11 D3: merge-driven deferred-commit mode ---------------------------


def test_defer_commit_flag_is_documented_as_an_argument():
    """`--defer-commit` is a real invocation flag, listed where flags are listed."""
    arguments = _section("Arguments")
    assert "--defer-commit" in arguments, (
        "Arguments section does not document `--defer-commit`; the merge-driven "
        "cleanup mode has no documented way to be requested."
    )


def test_defer_commit_defaults_off():
    """Rule 4 (safe defaults): without the flag, `--post-merge` is unchanged."""
    section = _defer_commit_section()
    assert re.search(r"off by default|defaults? to off|default(s|ed)?\s*:?\s*off", section, re.I), (
        "The deferred-commit section does not state that `--defer-commit` is off "
        "by default. A mode that changes behaviour unless explicitly disabled is a "
        "silent breaking change."
    )
    assert re.search(r"without .*--defer-commit|absent|not (passed|present|set)", section, re.I), (
        "The deferred-commit section does not say what `--post-merge` does when "
        "the flag is absent (commit and push itself, exactly as today)."
    )


def test_defer_commit_names_the_sync_point_as_the_committer():
    """D3: cleanup stages; the sync point owns the single convergence commit."""
    section = _defer_commit_section()
    assert re.search(r"sync[- ]point", section, re.I), (
        "The deferred-commit section never names the sync point, so nothing says "
        "who makes the commit cleanup no longer makes."
    )
    assert re.search(r"(single|one|exactly one) .{0,40}commit", section, re.I), (
        "The deferred-commit section does not state that the sync point produces "
        "a single convergence commit (D3)."
    )


def test_defer_commit_stages_and_returns_without_committing_or_pushing():
    section = _defer_commit_section()
    assert "git add" in section, (
        "The deferred-commit section does not say the output is staged with `git add`."
    )
    assert re.search(r"commits? nothing|do(es)? not commit|never commits?", section, re.I), (
        "The deferred-commit section does not state that cleanup commits nothing."
    )
    assert re.search(r"push(es)? nothing|do(es)? not push|never pushes?", section, re.I), (
        "The deferred-commit section does not state that cleanup pushes nothing."
    )


def test_defer_commit_retains_cleanup_ownership_of_archive_and_spec_merge():
    """ri-11 rationale: `--defer-commit` changes who commits, not who archives."""
    section = _defer_commit_section()
    for marker in ("archive", "spec"):
        assert re.search(marker, section, re.I), (
            f"The deferred-commit section does not mention {marker!r}; cleanup must "
            "still own task migration, archival, and the spec-delta merge."
        )


def test_defer_commit_does_not_defer_the_decision_index_regeneration():
    """The 2026-05-12 failure mode: deferring the commit must not defer the regen.

    `make decisions` regenerates `docs/decisions/` from `openspec/changes/archive/`,
    and the archive move stales the index the instant it lands. The regen has to be
    staged alongside the archive so both land in the one convergence commit.
    """
    section = _defer_commit_section()
    assert "make decisions" in section, (
        "The deferred-commit section does not require `make decisions`; a deferred "
        "commit would then carry an archive move with a stale decision index."
    )
    assert "git add docs/decisions/" in section, (
        "The deferred-commit section does not stage `docs/decisions/`; the regen "
        "must be staged with the archive, not left for the sync point to remember."
    )
    assert "validate-decision-index" in section, (
        "The deferred-commit section does not name the `validate-decision-index` CI "
        "job that a stale index breaks on main for every unrelated PR."
    )


def test_decision_index_anti_pattern_row_survives():
    """The 2026-05-12 incident row is the reason the assertion above exists."""
    rationalizations = _section("Common Rationalizations")
    assert "make decisions" in rationalizations
    assert "validate-decision-index" in rationalizations


def test_defer_commit_partial_failure_never_discards_staged_output():
    section = _defer_commit_section()
    assert re.search(r"partial|fails? partway|mid-?sequence", section, re.I), (
        "The deferred-commit section does not describe the partial-failure case."
    )
    assert re.search(r"never discard|not discarded|rather than discard", section, re.I), (
        "The deferred-commit section does not state that staged output from changes "
        "that already succeeded is committed, never discarded (D3)."
    )


# --- ri-11 D10: the architecture target that writes provenance -------------


def test_post_merge_uses_the_staged_architecture_target():
    text = _skill_text()
    assert "make architecture-refresh" in text, (
        "cleanup-feature does not run `make architecture-refresh`; provenance is "
        "written only by the staged target (`run_staged`)."
    )
    assert not re.search(r"^\s*make architecture\s*$", text, re.MULTILINE), (
        "cleanup-feature still invokes the bare `make architecture` target, which "
        "never writes provenance, leaving ri-10's architecture producer in drift."
    )


def test_staged_architecture_target_states_why():
    section = _section("Update Local Repository")
    assert "make architecture-refresh" in section
    assert re.search(r"provenance", section, re.I), (
        "The architecture step does not say why the staged target is required "
        "(provenance is written only by the staged target, D10)."
    )
