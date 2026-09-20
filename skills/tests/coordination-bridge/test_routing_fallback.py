"""Tests for routing_fallback.local_static_route (dg-04 design D8).

Change: implement-the-task-router-vendor-x-location-x-model (dg-04), package
        "Local fallback and bridge".
Spec: openspec/changes/implement-the-task-router-vendor-x-location-x-model/
      specs/task-routing/spec.md -- Requirement: Honest local fallback.
Design decisions: D3 (rules ordered/typed/versioned), D8 (local fallback is
      configuration-derived and honest).

These tests build a minimal checkout (routing.yaml + agents.yaml +
archetypes.yaml) under tmp_path rather than depending on the real repo's
config staying in a particular shape, so a routing.yaml edit elsewhere
cannot silently break this suite's assumptions.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

_BRIDGE_DIR = Path(__file__).resolve().parents[2] / "coordination-bridge" / "scripts"
if str(_BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_DIR))

import routing_fallback  # noqa: E402

_ROUTING_YAML = {
    "schema_version": 1,
    "policy_version": "test-v1",
    "defaults": {
        "dispatch_mode": "quick",
        "phase_dispatch_modes": {"IMPL_REVIEW": "review"},
    },
    "rules": [
        {
            "id": "direct-secrets-local",
            "when": {"secret_need": "direct"},
            "constrain": {"location": "local"},
        },
        {
            "id": "read-only-review",
            "when": {"scope": "read-only"},
            "constrain": {"dispatch_mode": "review"},
        },
    ],
    "fallback": {
        "location_order": ["local", "cloud", "unknown"],
        "isolation_order": ["worktree", "sandbox", "none"],
        "dispatch_mode_order": ["review", "alternative", "quick", "sdk"],
    },
}

_AGENTS_YAML = {
    "agents": {
        "claude-local": {
            "type": "claude_code",
            "location": "local",
            "policy_vendor": "claude",
            "catalog_vendor": "claude_code",
            "endpoint_kind": "vendor-cli",
            "isolation": "worktree",
            "cli": {"dispatch_modes": {"review": {}, "alternative": {}, "quick": {}}},
        },
        "claude-remote": {
            "type": "claude_code",
            "location": "cloud",
            "policy_vendor": "claude",
            "catalog_vendor": "claude_code",
            "endpoint_kind": "vendor-sdk",
            "isolation": "none",
            "cli": {"dispatch_modes": {"review": {}, "alternative": {}, "quick": {}}},
            "sdk": {"model": "claude-sonnet-4-6", "model_fallbacks": ["claude-haiku-4-5"]},
        },
    }
}

_ARCHETYPES_YAML = {
    "model_aliases": {
        "claude_code": {
            "standard": "claude-sonnet-4-6",
            "premium": {"model": "claude-opus-5", "thinking": "high"},
        }
    }
}


@pytest.fixture()
def checkout(tmp_path: Path) -> Path:
    coordinator_dir = tmp_path / "agent-coordinator"
    coordinator_dir.mkdir()
    (coordinator_dir / "routing.yaml").write_text(yaml.safe_dump(_ROUTING_YAML))
    (coordinator_dir / "agents.yaml").write_text(yaml.safe_dump(_AGENTS_YAML))
    (coordinator_dir / "archetypes.yaml").write_text(yaml.safe_dump(_ARCHETYPES_YAML))
    return tmp_path


def _route(checkout: Path, **kwargs: Any) -> dict[str, Any]:
    task_signals = kwargs.pop("task_signals", {"archetype": "implementer", "phase": "IMPLEMENT"})
    routing_profile = kwargs.pop("routing_profile", None)
    return routing_fallback.local_static_route(
        task_signals,
        static_provider=kwargs.pop("static_provider", "claude_code"),
        static_model=kwargs.pop("static_model", "claude-sonnet-4-6"),
        routing_profile=routing_profile,
        repo_root=checkout,
        **kwargs,
    )


def test_selects_the_only_exact_lane_when_unconstrained(checkout: Path) -> None:
    # claude-sonnet-4-6 is in BOTH lanes' model sets (cli tier map for
    # claude-local, sdk model for claude-remote): local wins by fallback
    # location_order, worktree isolation wins over none.
    result = _route(checkout)

    assert result["fallback"] is True
    assert result["provenance"]["source"] == "local-static"
    assert result["provenance"]["persisted"] is False
    assert result["provenance"]["durable_audit"] is False
    assert result["provenance"]["catalog_key"] is None
    assert result["assignment"] == result["selected"]["assignment"]
    assert result["selected"]["assignment"]["agent_id"] == "claude-local"
    assert result["selected"]["assignment"]["location"] == "local"
    assert result["selected"]["assignment"]["isolation"] == "worktree"
    # The other exact lane is retained as an alternative, not dropped.
    assert [a["assignment"]["agent_id"] for a in result["alternatives"]] == ["claude-remote"]


def test_rule_derived_location_constrains_selection(checkout: Path) -> None:
    result = _route(checkout, routing_profile={"secret_need": "direct"})

    assert result["selected"]["assignment"]["location"] == "local"
    assert result["provenance"]["matched_rule_ids"] == ["direct-secrets-local"]
    assert "rule:direct-secrets-local:location=local" in result["provenance"]["rationale"]


def test_rule_derived_dispatch_mode_filters_out_unconfigured_lanes(checkout: Path) -> None:
    # read-only-review forces dispatch_mode=review; both lanes configure it here.
    result = _route(checkout, routing_profile={"scope": "read-only"})

    assert result["selected"]["assignment"]["dispatch_mode"] == "review"


def test_explicit_and_rule_constraint_conflict_yields_no_candidates(checkout: Path) -> None:
    with pytest.raises(routing_fallback.LocalRoutingFallbackError):
        _route(
            checkout,
            routing_profile={"secret_need": "direct", "required_location": "cloud"},
        )


def test_default_dispatch_mode_used_when_no_rule_matches(checkout: Path) -> None:
    result = _route(
        checkout,
        task_signals={"archetype": "implementer", "phase": "IMPL_REVIEW"},
    )

    assert result["selected"]["assignment"]["dispatch_mode"] == "review"
    assert "default:dispatch_mode=review" in result["provenance"]["rationale"]


def test_no_exact_model_match_raises_bounded_error(checkout: Path) -> None:
    with pytest.raises(routing_fallback.LocalRoutingFallbackError):
        _route(checkout, static_model="model-nobody-configured")


def test_no_matching_vendor_type_raises_bounded_error(checkout: Path) -> None:
    with pytest.raises(routing_fallback.LocalRoutingFallbackError):
        _route(checkout, static_provider="codex")


def test_sdk_only_lane_is_selectable_via_sdk_dispatch_mode(tmp_path: Path) -> None:
    coordinator_dir = tmp_path / "agent-coordinator"
    coordinator_dir.mkdir()
    (coordinator_dir / "routing.yaml").write_text(yaml.safe_dump(_ROUTING_YAML))
    agents = {
        "agents": {
            "grok-remote": {
                "type": "grok",
                "location": "cloud",
                "policy_vendor": "grok",
                "catalog_vendor": "grok",
                "endpoint_kind": "vendor-sdk",
                "isolation": "none",
                "sdk": {"model": "grok-5", "model_fallbacks": []},
            }
        }
    }
    (coordinator_dir / "agents.yaml").write_text(yaml.safe_dump(agents))
    (coordinator_dir / "archetypes.yaml").write_text(yaml.safe_dump({"model_aliases": {}}))

    result = routing_fallback.local_static_route(
        {"archetype": "implementer"},
        static_provider="grok",
        static_model="grok-5",
        routing_profile={"required_dispatch_mode": "sdk"},
        repo_root=tmp_path,
    )

    assert result["selected"]["assignment"]["dispatch_mode"] == "sdk"
    assert result["selected"]["assignment"]["agent_id"] == "grok-remote"


def test_malformed_routing_yaml_fails_loud(tmp_path: Path) -> None:
    coordinator_dir = tmp_path / "agent-coordinator"
    coordinator_dir.mkdir()
    (coordinator_dir / "routing.yaml").write_text(yaml.safe_dump({"schema_version": 2}))
    (coordinator_dir / "agents.yaml").write_text(yaml.safe_dump(_AGENTS_YAML))

    with pytest.raises(ValueError):
        routing_fallback.local_static_route(
            {"archetype": "implementer"},
            static_provider="claude_code",
            static_model="claude-sonnet-4-6",
            repo_root=tmp_path,
        )


def test_missing_routing_yaml_fails_loud(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        routing_fallback.local_static_route(
            {"archetype": "implementer"},
            static_provider="claude_code",
            static_model="claude-sonnet-4-6",
            repo_root=tmp_path,
        )
