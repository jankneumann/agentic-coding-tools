"""Assurance helpers and mutation-surface inventory.

This module defines the canonical mutation operation surface used by
assurance tests to verify boundary enforcement and audit coverage.
"""

from __future__ import annotations

# Canonical mutation operations exposed via MCP tools.
MCP_MUTATION_OPERATIONS: tuple[str, ...] = (
    "acquire_lock",
    "release_lock",
    "complete_work",
    "submit_work",
    "write_handoff",
    "remember",
    "check_guardrails",
)

# Canonical mutation operations exposed via HTTP API endpoints.
HTTP_MUTATION_OPERATIONS: tuple[str, ...] = (
    "acquire_lock",
    "release_lock",
    "complete_work",
    "submit_work",
    "remember",
    "check_guardrails",
)

MUTATION_OPERATIONS: tuple[str, ...] = tuple(
    sorted(set(MCP_MUTATION_OPERATIONS) | set(HTTP_MUTATION_OPERATIONS))
)
