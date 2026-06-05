"""Tests for CLAUDE.md restructuring — TOC links resolve and topic docs exist.

Validates:
- CLAUDE.md line count <= 120
- All docs/guides/ links in CLAUDE.md resolve to actual files
- Each expected topic doc exists with a descriptive filename
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
GUIDES_DIR = REPO_ROOT / "docs" / "guides"

EXPECTED_TOPIC_DOCS = [
    "workflow.md",
    "python-environment.md",
    "git-conventions.md",
    "skills.md",
    "worktree-management.md",
    "documentation.md",
    "session-completion.md",
]


class TestClaudeMdLineCount:
    def test_claude_md_exists(self) -> None:
        assert CLAUDE_MD.exists(), "CLAUDE.md must exist at repo root"

    def test_line_count_at_most_120(self) -> None:
        lines = CLAUDE_MD.read_text(encoding="utf-8").splitlines()
        assert len(lines) <= 120, (
            f"CLAUDE.md has {len(lines)} lines, expected <= 120. "
            "Restructure content into docs/guides/ topic docs."
        )


class TestTopicDocsExist:
    def test_guides_directory_exists(self) -> None:
        assert GUIDES_DIR.is_dir(), "docs/guides/ directory must exist"

    @pytest.mark.parametrize("filename", EXPECTED_TOPIC_DOCS)
    def test_topic_doc_exists(self, filename: str) -> None:
        path = GUIDES_DIR / filename
        assert path.exists(), f"Expected topic doc {path.relative_to(REPO_ROOT)} not found"

    @pytest.mark.parametrize("filename", EXPECTED_TOPIC_DOCS)
    def test_topic_doc_is_nonempty(self, filename: str) -> None:
        path = GUIDES_DIR / filename
        if path.exists():
            content = path.read_text(encoding="utf-8").strip()
            assert len(content) > 50, (
                f"{filename} is too short ({len(content)} chars). "
                "Topic docs must contain complete, actionable guidance."
            )


class TestTocLinksResolve:
    def test_all_guide_links_resolve(self) -> None:
        """Every docs/guides/*.md link in CLAUDE.md must point to an existing file."""
        content = CLAUDE_MD.read_text(encoding="utf-8")
        import re

        # Match markdown links like [text](docs/guides/foo.md) or (docs/guides/foo.md)
        link_pattern = re.compile(r"\(docs/guides/([^)]+\.md)\)")
        links_found = link_pattern.findall(content)
        assert len(links_found) > 0, "CLAUDE.md must contain links to docs/guides/*.md files"

        missing = []
        for filename in links_found:
            target = REPO_ROOT / "docs" / "guides" / filename
            if not target.exists():
                missing.append(filename)
        assert missing == [], f"Broken links in CLAUDE.md: {missing}"
