"""Shared utilities for architecture analysis scripts.

Provides common abstractions so language analyzers, the graph compiler,
validators, and view generators can be developed independently without
duplicating graph I/O, traversal, or constant definitions.
"""

from arch_utils.constants import DEPENDENCY_EDGE_TYPES, Confidence, EdgeType, NodeKind
from arch_utils.diagnostics import Diagnostic, DiagnosticCollector
from arch_utils.graph_io import load_graph, save_json
from arch_utils.node_id import make_node_id, mermaid_id, parse_node_id
from arch_utils.traversal import (
    build_adjacency,
    find_cycles,
    reachable_from,
    transitive_dependents,
)

__all__ = [
    "DEPENDENCY_EDGE_TYPES",
    "Confidence",
    "Diagnostic",
    "DiagnosticCollector",
    "EdgeType",
    "NodeKind",
    "build_adjacency",
    "find_cycles",
    "load_graph",
    "make_node_id",
    "mermaid_id",
    "parse_node_id",
    "reachable_from",
    "save_json",
    "transitive_dependents",
]
