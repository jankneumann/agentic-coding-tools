"""Tests for changelog.py — version parsing, bump logic, and commit parsing."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

# Import from the scripts directory
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from changelog import (
    BumpLevel,
    ParsedCommit,
    bump_version,
    format_changelog_section,
    parse_version,
    AnalysisResult,
    CONVENTIONAL_RE,
    COMMIT_TYPE_MAP,
)


# ---------------------------------------------------------------------------
# Version parsing
# ---------------------------------------------------------------------------


class TestParseVersion:
    def test_valid_version(self):
        assert parse_version("1.2.3") == (1, 2, 3)

    def test_zero_version(self):
        assert parse_version("0.0.0") == (0, 0, 0)

    def test_large_numbers(self):
        assert parse_version("10.200.3000") == (10, 200, 3000)

    def test_whitespace_stripped(self):
        assert parse_version("  1.2.3  ") == (1, 2, 3)

    def test_invalid_format_two_parts(self):
        with pytest.raises(ValueError, match="Invalid version format"):
            parse_version("1.2")

    def test_invalid_format_four_parts(self):
        with pytest.raises(ValueError, match="Invalid version format"):
            parse_version("1.2.3.4")

    def test_invalid_format_empty(self):
        with pytest.raises(ValueError):
            parse_version("")


# ---------------------------------------------------------------------------
# Version bumping
# ---------------------------------------------------------------------------


class TestBumpVersion:
    def test_patch_bump(self):
        assert bump_version("1.2.3", BumpLevel.PATCH) == "1.2.4"

    def test_minor_bump(self):
        assert bump_version("1.2.3", BumpLevel.MINOR) == "1.3.0"

    def test_major_bump(self):
        assert bump_version("1.2.3", BumpLevel.MAJOR) == "2.0.0"

    def test_patch_from_zero(self):
        assert bump_version("0.0.0", BumpLevel.PATCH) == "0.0.1"

    def test_minor_from_zero(self):
        assert bump_version("0.0.0", BumpLevel.MINOR) == "0.1.0"

    def test_major_from_zero(self):
        assert bump_version("0.0.0", BumpLevel.MAJOR) == "1.0.0"

    def test_minor_resets_patch(self):
        assert bump_version("2.5.9", BumpLevel.MINOR) == "2.6.0"

    def test_major_resets_minor_and_patch(self):
        assert bump_version("3.7.12", BumpLevel.MAJOR) == "4.0.0"


# ---------------------------------------------------------------------------
# Commit regex parsing
# ---------------------------------------------------------------------------


class TestConventionalRegex:
    def test_feat_with_scope(self):
        m = CONVENTIONAL_RE.match("abc1234 feat(coordinator): add notification system")
        assert m is not None
        assert m.group("hash") == "abc1234"
        assert m.group("type") == "feat"
        assert m.group("scope") == "coordinator"
        assert m.group("desc") == "add notification system"
        assert m.group("breaking") is None

    def test_fix_without_scope(self):
        m = CONVENTIONAL_RE.match("def5678 fix: resolve crash on startup")
        assert m is not None
        assert m.group("type") == "fix"
        assert m.group("scope") is None
        assert m.group("desc") == "resolve crash on startup"

    def test_breaking_with_bang(self):
        m = CONVENTIONAL_RE.match("aaa1111 feat(api)!: remove deprecated endpoint")
        assert m is not None
        assert m.group("breaking") == "!"
        assert m.group("type") == "feat"
        assert m.group("scope") == "api"

    def test_chore_with_scope(self):
        m = CONVENTIONAL_RE.match("bbb2222 chore(deps): update dependencies")
        assert m is not None
        assert m.group("type") == "chore"

    def test_non_conventional_no_match(self):
        m = CONVENTIONAL_RE.match("ccc3333 Merge pull request #42")
        assert m is None

    def test_non_conventional_no_colon(self):
        m = CONVENTIONAL_RE.match("ddd4444 just a message")
        assert m is None


# ---------------------------------------------------------------------------
# Commit type mapping
# ---------------------------------------------------------------------------


class TestCommitTypeMap:
    def test_feat_is_minor(self):
        section, bump = COMMIT_TYPE_MAP["feat"]
        assert section == "Added"
        assert bump == BumpLevel.MINOR

    def test_fix_is_patch(self):
        section, bump = COMMIT_TYPE_MAP["fix"]
        assert section == "Fixed"
        assert bump == BumpLevel.PATCH

    def test_all_types_have_valid_sections(self):
        valid_sections = {"Added", "Changed", "Deprecated", "Removed", "Fixed", "Security", "Documentation"}
        for commit_type, (section, _) in COMMIT_TYPE_MAP.items():
            assert section in valid_sections, f"{commit_type} maps to unknown section {section}"


# ---------------------------------------------------------------------------
# BumpLevel ordering
# ---------------------------------------------------------------------------


class TestBumpLevel:
    def test_ordering(self):
        assert BumpLevel.PATCH < BumpLevel.MINOR < BumpLevel.MAJOR

    def test_max_selects_highest(self):
        levels = [BumpLevel.PATCH, BumpLevel.MINOR, BumpLevel.PATCH]
        assert max(levels) == BumpLevel.MINOR

    def test_str(self):
        assert str(BumpLevel.MAJOR) == "MAJOR"
        assert str(BumpLevel.MINOR) == "MINOR"
        assert str(BumpLevel.PATCH) == "PATCH"


# ---------------------------------------------------------------------------
# Changelog section formatting
# ---------------------------------------------------------------------------


class TestFormatChangelogSection:
    def test_basic_section(self):
        result = AnalysisResult(
            current_version="1.0.0",
            suggested_bump=BumpLevel.MINOR,
            next_version="1.1.0",
            sections={
                "Added": ["- **api**: new endpoint (`abc1234`)"],
                "Fixed": ["- resolve crash (`def5678`)"],
            },
        )
        output = format_changelog_section(result, "1.1.0", "2026-04-01")
        assert "## [1.1.0] - 2026-04-01" in output
        assert "### Added" in output
        assert "### Fixed" in output
        assert "new endpoint" in output
        assert "resolve crash" in output

    def test_empty_sections_omitted(self):
        result = AnalysisResult(
            current_version="1.0.0",
            suggested_bump=BumpLevel.PATCH,
            next_version="1.0.1",
            sections={"Fixed": ["- a fix (`aaa`)"]},
        )
        output = format_changelog_section(result, "1.0.1", "2026-04-01")
        assert "### Added" not in output
        assert "### Fixed" in output

    def test_section_ordering(self):
        result = AnalysisResult(
            current_version="0.1.0",
            suggested_bump=BumpLevel.MINOR,
            next_version="0.2.0",
            sections={
                "Fixed": ["- fix (`a`)"],
                "Added": ["- feature (`b`)"],
                "Changed": ["- refactor (`c`)"],
            },
        )
        output = format_changelog_section(result, "0.2.0", "2026-04-01")
        # Added should come before Changed, which comes before Fixed
        added_pos = output.index("### Added")
        changed_pos = output.index("### Changed")
        fixed_pos = output.index("### Fixed")
        assert added_pos < changed_pos < fixed_pos
