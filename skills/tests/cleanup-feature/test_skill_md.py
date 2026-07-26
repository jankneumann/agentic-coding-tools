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
