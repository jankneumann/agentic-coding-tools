"""Tests for the canonical router-to-dispatch isolation contract."""

from __future__ import annotations

import pytest

from src.isolation_contract import (
    ISOLATION_MODES,
    IsolationContractError,
    configured_isolation_value,
    resolve_isolation,
    validate_isolation,
)


def test_canonical_vocabulary_is_pinned_without_container() -> None:
    assert ISOLATION_MODES == ("none", "worktree", "sandbox")
    with pytest.raises(IsolationContractError, match="routing_policy.*container"):
        validate_isolation("container", rung="routing_policy")


def test_router_value_wins_and_records_router_source() -> None:
    result = resolve_isolation(
        router_reachable=True,
        router_value="sandbox",
        configured_value="worktree",
    )
    assert result.value == "sandbox"
    assert result.source == "router"


def test_silent_or_unreachable_router_falls_back_to_config_then_default() -> None:
    configured = resolve_isolation(
        router_reachable=True,
        router_value=None,
        configured_value="worktree",
    )
    default = resolve_isolation(router_reachable=False, router_value=None, configured_value=None)
    assert (configured.value, configured.source) == ("worktree", "agents_yaml")
    assert (default.value, default.source) == ("none", "default")


def test_invalid_present_value_names_its_rung() -> None:
    with pytest.raises(IsolationContractError, match="router.*container"):
        resolve_isolation(
            router_reachable=True,
            router_value="container",
            configured_value="worktree",
        )


def test_invalid_configured_value_names_agents_yaml_rung() -> None:
    with pytest.raises(IsolationContractError, match="agents_yaml.*container"):
        resolve_isolation(router_reachable=False, router_value=None, configured_value="container")


def test_empty_present_value_is_invalid_instead_of_defaulting() -> None:
    with pytest.raises(IsolationContractError, match="router"):
        resolve_isolation(router_reachable=True, router_value="", configured_value=None)


def test_mapping_helper_prefers_mode_override_then_entry_default() -> None:
    configured = {
        "isolation": "worktree",
        "cli": {
            "dispatch_modes": {
                "review": {"isolation": "sandbox"},
                "alternative": {},
            }
        },
    }

    assert configured_isolation_value(configured, "review") == "sandbox"
    assert configured_isolation_value(configured, "alternative") == "worktree"
    assert configured_isolation_value(configured, "quick") == "worktree"


def test_mapping_helper_preserves_invalid_presence_for_validation() -> None:
    configured = {
        "isolation": "worktree",
        "cli": {"dispatch_modes": {"review": {"isolation": "container"}}},
    }

    with pytest.raises(IsolationContractError, match="agents_yaml.*container"):
        resolve_isolation(
            router_reachable=False,
            router_value=None,
            configured_value=configured_isolation_value(configured, "review"),
        )
