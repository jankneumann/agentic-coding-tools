"""The oracle-source vocabulary (design D2).

Answers: where do this test's expected values come from?
"""

from __future__ import annotations

ORACLE_SOURCES: tuple[str, ...] = (
    "spec",
    "property",
    "reference_impl",
    "external_contract",
    "characterization",
    "current_impl_output",
    "none",
)

# Binary partition used throughout the analysis.
INTENT_DERIVED: frozenset[str] = frozenset({"spec", "property", "reference_impl", "external_contract"})
NOT_INTENT_DERIVED: frozenset[str] = frozenset({"characterization", "current_impl_output", "none"})

# Expected values copied from the implementation, declared or not.
IMPL_DERIVED: frozenset[str] = frozenset({"characterization", "current_impl_output"})

DESCRIPTIONS: dict[str, str] = {
    "spec": "A stated requirement, scenario or documented contract of the unit under test",
    "property": "An invariant or relation that must hold for all inputs",
    "reference_impl": "An independent computation of the same answer",
    "external_contract": "A schema, protocol or third-party format the code must conform to",
    "characterization": "Today's behaviour, deliberately frozen to guard a refactor",
    "current_impl_output": "Today's output copied into the assertion without a stated reason",
    "none": "The test asserts nothing about outputs",
}


def validate_label(label: str) -> str:
    """Return ``label`` if it is in the vocabulary, else raise ``ValueError``."""
    if label not in ORACLE_SOURCES:
        raise ValueError(f"unknown oracle source {label!r}; allowed values: {', '.join(ORACLE_SOURCES)}")
    return label


def is_intent_derived(label: str) -> bool:
    return validate_label(label) in INTENT_DERIVED
