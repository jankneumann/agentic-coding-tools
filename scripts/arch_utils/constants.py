"""Canonical constants for the architecture analysis pipeline.

Single source of truth for edge types, node kinds, and confidence levels.
New analyzers should use these rather than inventing ad-hoc strings.
"""

from __future__ import annotations

from enum import Enum


# ---------------------------------------------------------------------------
# Edge types
# ---------------------------------------------------------------------------


class EdgeType(str, Enum):
    """All recognised relationship types between architecture nodes."""

    CALL = "call"
    IMPORT = "import"
    API_CALL = "api_call"
    DB_ACCESS = "db_access"
    FK_REFERENCE = "fk_reference"
    HOOK_USAGE = "hook_usage"
    COMPONENT_CHILD = "component_child"
    CIRCULAR_DEPENDENCY = "circular_dependency"
    LAYER_VIOLATION = "layer_violation"

    def __str__(self) -> str:  # pragma: no cover
        return self.value


# Edges that represent structural dependency (used for cycle detection,
# parallel-zone computation, and impact analysis).
DEPENDENCY_EDGE_TYPES: frozenset[str] = frozenset({
    EdgeType.CALL.value,
    EdgeType.IMPORT.value,
    EdgeType.FK_REFERENCE.value,
    EdgeType.HOOK_USAGE.value,
    EdgeType.COMPONENT_CHILD.value,
})

# Edges that represent side-effect relationships (DB writes, API calls).
SIDE_EFFECT_EDGE_TYPES: frozenset[str] = frozenset({
    EdgeType.DB_ACCESS.value,
    EdgeType.API_CALL.value,
})


# ---------------------------------------------------------------------------
# Node kinds
# ---------------------------------------------------------------------------


class NodeKind(str, Enum):
    """All recognised node kinds in the canonical graph."""

    FUNCTION = "function"
    CLASS = "class"
    MODULE = "module"
    TABLE = "table"
    COLUMN = "column"
    INDEX = "index"
    COMPONENT = "component"
    HOOK = "hook"
    STORED_FUNCTION = "stored_function"
    TRIGGER = "trigger"
    MIGRATION = "migration"

    def __str__(self) -> str:  # pragma: no cover
        return self.value


# ---------------------------------------------------------------------------
# Confidence levels
# ---------------------------------------------------------------------------


class Confidence(str, Enum):
    """Ordered confidence levels for edges and flows."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    def __str__(self) -> str:  # pragma: no cover
        return self.value

    @property
    def numeric(self) -> float:
        """Return a 0.0–1.0 score for aggregation / sorting."""
        return {
            Confidence.HIGH: 1.0,
            Confidence.MEDIUM: 0.6,
            Confidence.LOW: 0.3,
        }[self]

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Confidence):
            return NotImplemented
        return self.numeric >= other.numeric

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Confidence):
            return NotImplemented
        return self.numeric > other.numeric

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Confidence):
            return NotImplemented
        return self.numeric <= other.numeric

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Confidence):
            return NotImplemented
        return self.numeric < other.numeric
