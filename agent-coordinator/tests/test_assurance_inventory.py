"""Tests for assurance mutation-surface inventory."""

from src.assurance import (
    HTTP_MUTATION_OPERATIONS,
    MCP_MUTATION_OPERATIONS,
    MUTATION_OPERATIONS,
)


def test_mcp_mutation_inventory_contains_required_operations():
    required = {
        "acquire_lock",
        "release_lock",
        "complete_work",
        "submit_work",
        "write_handoff",
        "remember",
        "check_guardrails",
    }
    assert required.issubset(set(MCP_MUTATION_OPERATIONS))


def test_http_mutation_inventory_contains_required_operations():
    required = {
        "acquire_lock",
        "release_lock",
        "complete_work",
        "submit_work",
        "remember",
        "check_guardrails",
    }
    assert required.issubset(set(HTTP_MUTATION_OPERATIONS))


def test_unified_mutation_inventory_is_deduplicated():
    assert len(MUTATION_OPERATIONS) == len(set(MUTATION_OPERATIONS))
