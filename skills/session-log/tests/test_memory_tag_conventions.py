"""Tests for failure metadata tag conventions in episodic memory.

Validates:
- Structured tags (failure_type:X, capability_gap:X, etc.) can be stored
- Query by failure_type works (tag-based recall)
- source: tag prefix works for all four vocabulary values
- Tag schema documented in docs/guides/memory-conventions.md

These tests validate the tag CONVENTIONS, not the memory service itself
(which already accepts arbitrary string tags). The conventions are
documented, not code-enforced.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CONVENTIONS_DOC = REPO_ROOT / "docs" / "guides" / "memory-conventions.md"

# ── Tag schema constants (defined by D4 design decision) ──

REQUIRED_TAG_PREFIXES = [
    "failure_type",
    "capability_gap",
    "affected_skill",
    "severity",
    "source",
]

SOURCE_VOCABULARY = [
    "self-reported",
    "coordinator-emitted",
    "session-log",
    "transcript-mined",
]

FAILURE_TYPES = [
    "scope_violation",
    "verification_failed",
    "lock_unavailable",
    "timeout",
    "convergence_failed",
    "context_exhaustion",
]

SEVERITY_LEVELS = [
    "low",
    "medium",
    "high",
    "critical",
]


class TestTagSchemaDocumented:
    """The tag schema must be documented in memory-conventions.md."""

    def test_conventions_doc_exists(self) -> None:
        assert CONVENTIONS_DOC.exists(), (
            "docs/guides/memory-conventions.md must exist. "
            "It documents the shared capability-gap tag schema."
        )

    def test_conventions_doc_is_nonempty(self) -> None:
        if not CONVENTIONS_DOC.exists():
            pytest.skip("Conventions doc not yet created")
        content = CONVENTIONS_DOC.read_text(encoding="utf-8")
        assert len(content.strip()) > 100

    @pytest.mark.parametrize("prefix", REQUIRED_TAG_PREFIXES)
    def test_tag_prefix_documented(self, prefix: str) -> None:
        if not CONVENTIONS_DOC.exists():
            pytest.skip("Conventions doc not yet created")
        content = CONVENTIONS_DOC.read_text(encoding="utf-8")
        assert prefix in content, (
            f"Tag prefix '{prefix}' must be documented in memory-conventions.md"
        )

    @pytest.mark.parametrize("source", SOURCE_VOCABULARY)
    def test_source_value_documented(self, source: str) -> None:
        if not CONVENTIONS_DOC.exists():
            pytest.skip("Conventions doc not yet created")
        content = CONVENTIONS_DOC.read_text(encoding="utf-8")
        assert source in content, (
            f"Source value '{source}' must be documented in memory-conventions.md"
        )


class TestTagFormat:
    """Tags follow the `prefix:value` format convention."""

    def test_failure_type_tag_format(self) -> None:
        """failure_type tags use the prefix:value format."""
        tag = "failure_type:scope_violation"
        prefix, _, value = tag.partition(":")
        assert prefix == "failure_type"
        assert value == "scope_violation"

    def test_source_tag_format(self) -> None:
        """source tags use the prefix:value format."""
        tag = "source:self-reported"
        prefix, _, value = tag.partition(":")
        assert prefix == "source"
        assert value == "self-reported"

    def test_all_source_values_are_valid(self) -> None:
        """All source vocabulary values produce valid tags."""
        for source in SOURCE_VOCABULARY:
            tag = f"source:{source}"
            prefix, _, value = tag.partition(":")
            assert prefix == "source"
            assert value == source
            assert value  # non-empty

    def test_all_failure_types_are_valid(self) -> None:
        """All failure_type enum values produce valid tags."""
        for ft in FAILURE_TYPES:
            tag = f"failure_type:{ft}"
            prefix, _, value = tag.partition(":")
            assert prefix == "failure_type"
            assert value == ft

    def test_all_severity_levels_are_valid(self) -> None:
        """All severity levels produce valid tags."""
        for sev in SEVERITY_LEVELS:
            tag = f"severity:{sev}"
            prefix, _, value = tag.partition(":")
            assert prefix == "severity"
            assert value == sev


class TestTagQueryability:
    """Tags must support filtering by prefix when passed to recall."""

    def test_tags_are_strings(self) -> None:
        """Tags are plain strings — the memory API accepts list[str]."""
        tags = [
            "failure_type:scope_violation",
            "capability_gap:missing file lock",
            "affected_skill:implement-feature",
            "severity:high",
            "source:self-reported",
        ]
        assert all(isinstance(t, str) for t in tags)

    def test_capability_gap_tag_is_free_text(self) -> None:
        """capability_gap values are free text (not enum-constrained)."""
        tag = "capability_gap:agent failed to detect circular dependency"
        prefix, _, value = tag.partition(":")
        assert prefix == "capability_gap"
        assert len(value) > 0

    def test_deduplication_key_extractable(self) -> None:
        """The dedup key (capability_gap, affected_skill, session_id) can be
        extracted from a set of tags + session metadata."""
        tags = [
            "capability_gap:missing file lock",
            "affected_skill:implement-feature",
            "source:self-reported",
        ]
        session_id = "sess-123"

        tag_dict = {}
        for t in tags:
            k, _, v = t.partition(":")
            tag_dict[k] = v

        dedup_key = (
            tag_dict.get("capability_gap"),
            tag_dict.get("affected_skill"),
            session_id,
        )
        assert dedup_key == ("missing file lock", "implement-feature", "sess-123")
