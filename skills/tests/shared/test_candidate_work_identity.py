"""Immutable source identity and suggested change-ID contracts."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SHARED = REPO_ROOT / "skills" / "shared"
sys.path.insert(0, str(SHARED))

from candidate_work import (  # noqa: E402
    derive_suggested_change_id,
    normalize_source_identity,
    normalize_suggested_change_id,
)


def test_improve_harness_normalizes_its_capability_gap_identity() -> None:
    assert (
        normalize_source_identity(
            "improve-harness", "  Retry\tControl \n  GAP  "
        )
        == "retry control gap"
    )


@pytest.mark.parametrize("generator", ["bug-scrub", "explore-feature"])
def test_bug_and_explore_preserve_the_exact_source_identity(generator: str) -> None:
    source_id = "  Fïnding/Δ  "

    assert normalize_source_identity(generator, source_id) == source_id


@pytest.mark.parametrize(
    ("suggested_id", "expected"),
    [
        ("add-Retry_Policy", "add-retry-policy"),
        ("update-Retry_Policy", "update-retry-policy"),
        ("remove-Retry_Policy", "remove-retry-policy"),
        ("refactor-Retry_Policy", "refactor-retry-policy"),
        ("fix-Retry_Policy", "update-retry-policy"),
        ("Retry_Policy", "update-retry-policy"),
        ("Über Δ", "update-ber"),
        ("!!!", "update-item"),
    ],
)
def test_suggested_change_id_uses_ascii_slugs_and_canonical_prefixes(
    suggested_id: str, expected: str
) -> None:
    assert normalize_suggested_change_id(suggested_id) == expected


@pytest.mark.parametrize(
    ("generator", "source_id", "expected"),
    [
        ("bug-scrub", "BUG:42", "update-bug-42-0bcf2adc"),
        (
            "improve-harness",
            "  Retry\tControl \n  GAP  ",
            "update-retry-control-gap-d07e9584",
        ),
        ("explore-feature", " Δ ", "update-item-0d5998cb"),
    ],
)
def test_derived_ids_use_only_canonical_immutable_identity(
    generator: str, source_id: str, expected: str
) -> None:
    assert derive_suggested_change_id(generator, source_id) == expected


def test_explicit_hint_is_normalized_without_an_identity_suffix() -> None:
    assert (
        derive_suggested_change_id(
            "bug-scrub", "BUG:42", explicit_hint="fix-Retry_Policy"
        )
        == "update-retry-policy"
    )


@pytest.mark.parametrize("generator", ["bug-scrub", "improve-harness", "explore-feature"])
def test_blank_source_identity_is_rejected(generator: str) -> None:
    with pytest.raises(ValueError, match="source_id must not be blank"):
        derive_suggested_change_id(generator, "  \t\n")


def test_unknown_generator_cannot_invent_a_source_identity_rule() -> None:
    with pytest.raises(ValueError, match="unsupported candidate-work generator"):
        normalize_source_identity("new-generator", "source-1")
