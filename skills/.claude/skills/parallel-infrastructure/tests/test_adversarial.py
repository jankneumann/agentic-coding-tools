"""Tests for adversarial review prompt wrapping."""

from __future__ import annotations

import sys
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from adversarial_prompt import ADVERSARIAL_PROMPT_PREFIX, wrap_adversarial


class TestAdversarialPromptPrefix:
    def test_prefix_is_nonempty(self):
        assert len(ADVERSARIAL_PROMPT_PREFIX) > 0

    def test_prefix_contains_adversarial_instructions(self):
        assert "ADVERSARIAL" in ADVERSARIAL_PROMPT_PREFIX
        assert "devil's advocate" in ADVERSARIAL_PROMPT_PREFIX

    def test_prefix_instructs_challenge(self):
        assert "Challenge design decisions" in ADVERSARIAL_PROMPT_PREFIX

    def test_prefix_instructs_edge_cases(self):
        assert "edge cases" in ADVERSARIAL_PROMPT_PREFIX

    def test_prefix_instructs_alternatives(self):
        assert "alternative" in ADVERSARIAL_PROMPT_PREFIX.lower()

    def test_prefix_requires_standard_schema(self):
        """Adversarial findings must use standard schema (D1: no new finding types)."""
        assert "review-findings.schema.json" in ADVERSARIAL_PROMPT_PREFIX

    def test_prefix_ends_with_separator(self):
        assert "END ADVERSARIAL INSTRUCTIONS" in ADVERSARIAL_PROMPT_PREFIX


class TestWrapAdversarial:
    def test_wraps_prompt_with_prefix(self):
        original = "Review this plan for feature X."
        wrapped = wrap_adversarial(original)
        assert wrapped.startswith(ADVERSARIAL_PROMPT_PREFIX)
        assert wrapped.endswith(original)

    def test_preserves_original_prompt(self):
        original = "Review the implementation of wp-backend."
        wrapped = wrap_adversarial(original)
        assert original in wrapped

    def test_prefix_comes_before_original(self):
        original = "Check this code."
        wrapped = wrap_adversarial(original)
        prefix_idx = wrapped.index("ADVERSARIAL")
        original_idx = wrapped.index(original)
        assert prefix_idx < original_idx
