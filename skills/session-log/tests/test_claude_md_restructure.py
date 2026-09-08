"""Tests for the guidelines TOC — links resolve and topic docs exist.

Validates:
- the guidelines file's line count <= 120
- all docs/guides/ links in it resolve to actual files
- each expected topic doc exists with a descriptive filename
- CLAUDE.md still reaches those guides

Since 2026-09-08 the guidelines live in `AGENTS.md`, and `CLAUDE.md` is a thin
Claude-Code-specific file that pulls them in with an `@AGENTS.md` import. Before
that, `AGENTS.md` was a *symlink to* `CLAUDE.md`, so anything Claude-specific
written in CLAUDE.md was also served as project-wide guidance to every other
agent, and there was nowhere to put Claude-only notes.

These assertions therefore target `AGENTS.md` — the file that now carries the
table of contents — plus one assertion that the CLAUDE.md -> AGENTS.md link is
intact, so the reader's chain is checked end to end rather than at one hop.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
#: The file that carries the project guidelines and their TOC.
GUIDELINES_MD = REPO_ROOT / "AGENTS.md"
#: The Claude Code entry point, which imports the above rather than restating it.
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


class TestGuidelinesLineCount:
    def test_guidelines_exist(self) -> None:
        assert GUIDELINES_MD.exists(), "AGENTS.md must exist at repo root"

    def test_claude_md_exists(self) -> None:
        assert CLAUDE_MD.exists(), "CLAUDE.md must exist at repo root"

    def test_line_count_at_most_120(self) -> None:
        lines = GUIDELINES_MD.read_text(encoding="utf-8").splitlines()
        assert len(lines) <= 120, (
            f"AGENTS.md has {len(lines)} lines, expected <= 120. "
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
        """Every docs/guides/*.md link in AGENTS.md must point to an existing file."""
        content = GUIDELINES_MD.read_text(encoding="utf-8")
        import re

        # Match markdown links like [text](docs/guides/foo.md) or (docs/guides/foo.md)
        link_pattern = re.compile(r"\(docs/guides/([^)]+\.md)\)")
        links_found = link_pattern.findall(content)
        assert len(links_found) > 0, "AGENTS.md must contain links to docs/guides/*.md files"

        missing = []
        for filename in links_found:
            target = REPO_ROOT / "docs" / "guides" / filename
            if not target.exists():
                missing.append(filename)
        assert missing == [], f"Broken links in AGENTS.md: {missing}"

    def test_claude_md_imports_the_guidelines(self) -> None:
        """The guides must stay reachable from the Claude Code entry point.

        CLAUDE.md no longer restates the TOC, so "is the link in CLAUDE.md" is
        the wrong question; the right one is whether it still pulls in the file
        that has it. Without this, CLAUDE.md could silently stop importing
        AGENTS.md and every assertion above would keep passing.
        """
        content = CLAUDE_MD.read_text(encoding="utf-8")
        assert "@AGENTS.md" in content, (
            "CLAUDE.md must import the guidelines with `@AGENTS.md`; without it "
            "the docs/guides/ tree is unreachable from the Claude entry point."
        )
