"""Content invariants for the codebase-atlas skill.

Follows the Architecture-category convention (as `refresh-architecture` does):
frontmatter and cross-reference invariants, without the methodology-skill tail
block (Common Rationalizations / Red Flags / Verification), which is scoped to
the engineering-methodology skills.
"""

from pathlib import Path

from skill_invariants import (
    assert_frontmatter_parses,
    assert_related_resolve,
    assert_required_keys_present,
)

SKILL_DIR = Path(__file__).resolve().parents[2] / "codebase-atlas"


def test_frontmatter_parses():
    assert_frontmatter_parses(SKILL_DIR)


def test_required_keys_present():
    assert_required_keys_present(SKILL_DIR)


def test_related_resolve():
    assert_related_resolve(SKILL_DIR)


def test_declared_flags_exist_in_the_cli():
    """Every flag the SKILL.md advertises must be accepted by build_atlas.py.

    Documentation drift in the other direction is the whole problem this session
    is about, so the skill's own flag table is held to the implementation.
    """
    import build_atlas

    parser = build_atlas.parse_args([])
    body = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    for flag in ("--check", "--output", "--json-only", "--no-coverage", "--graph"):
        assert flag in body, f"{flag} is implemented but undocumented"
        assert hasattr(parser, flag.lstrip("-").replace("-", "_"))


def test_documented_make_targets_exist():
    """`make atlas` / `make atlas-check` must be real targets, not aspirational."""
    makefile = (SKILL_DIR.parents[1] / "Makefile").read_text(encoding="utf-8")
    assert "\natlas:" in makefile
    assert "\natlas-check:" in makefile


def test_runtime_invocation_is_documented():
    """A `portable` skill must be usable from an installed runtime copy.

    `install.sh` copies the skill directory but not this repo's root Makefile, so
    a SKILL.md that documents only `make atlas` breaks in consumer repositories.
    The `<skill-base-dir>` script form must be present, and the Make targets must
    be marked as source-checkout conveniences.
    """
    body = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert '"<skill-base-dir>/scripts/build_atlas.py"' in body
    assert "source-checkout convenience" in body
