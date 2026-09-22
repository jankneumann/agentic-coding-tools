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

import copy
import shutil
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
    },
    # Must cover every key routing.yaml's defaults.phase_dispatch_modes uses
    # (here just IMPL_REVIEW) -- load_routing_policy_document cross-checks
    # phase_dispatch_modes against this roster the same way the coordinator's
    # strict loader does.
    "phase_mapping": {"IMPL_REVIEW": {}},
}


def _write_canonical_contract(coordinator_dir: Path) -> None:
    source_dir = coordinator_dir / "src"
    source_dir.mkdir(exist_ok=True)
    canonical_contract = (
        Path(__file__).resolve().parents[3]
        / "agent-coordinator"
        / "src"
        / "isolation_contract.py"
    )
    shutil.copyfile(canonical_contract, source_dir / "isolation_contract.py")


@pytest.fixture()
def checkout(tmp_path: Path) -> Path:
    coordinator_dir = tmp_path / "agent-coordinator"
    coordinator_dir.mkdir()
    _write_canonical_contract(coordinator_dir)
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


def test_mode_override_matches_reachable_router_assignment(checkout: Path) -> None:
    agents = copy.deepcopy(_AGENTS_YAML)
    local_modes = agents["agents"]["claude-local"]["cli"]["dispatch_modes"]
    local_modes["review"]["isolation"] = "sandbox"
    local_modes["alternative"]["isolation"] = "none"
    (checkout / "agent-coordinator" / "agents.yaml").write_text(
        yaml.safe_dump(agents)
    )

    review = _route(checkout)
    alternative = _route(
        checkout,
        routing_profile={
            "scope": "bounded-write",
            "required_dispatch_mode": "alternative",
        },
    )

    assert review["assignment"]["agent_id"] == "claude-local"
    assert review["assignment"]["dispatch_mode"] == "review"
    assert review["assignment"]["isolation"] == "sandbox"
    assert alternative["assignment"]["agent_id"] == "claude-local"
    assert alternative["assignment"]["dispatch_mode"] == "alternative"
    assert alternative["assignment"]["isolation"] == "none"


def test_invalid_present_mode_override_names_agents_yaml_rung(checkout: Path) -> None:
    agents = copy.deepcopy(_AGENTS_YAML)
    agents["agents"]["claude-local"]["cli"]["dispatch_modes"]["review"][
        "isolation"
    ] = "container"
    (checkout / "agent-coordinator" / "agents.yaml").write_text(
        yaml.safe_dump(agents)
    )

    with pytest.raises(ValueError, match="agents_yaml.*container"):
        _route(checkout)


def test_rule_derived_location_constrains_selection(checkout: Path) -> None:
    result = _route(checkout, routing_profile={"secret_need": "direct"})

    assert result["selected"]["assignment"]["location"] == "local"
    # scope defaults to "read-only" (TaskRoutingProfile default), so
    # read-only-review also fires alongside direct-secrets-local.
    assert result["provenance"]["matched_rule_ids"] == [
        "direct-secrets-local",
        "read-only-review",
    ]
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


def test_missing_routing_profile_applies_task_routing_profile_defaults(checkout: Path) -> None:
    # No routing_profile at all -- the coordinator is unreachable, so nothing
    # ever ran this through SelectModelRequest/TaskRoutingProfile validation.
    # scope must still default to "read-only" (TaskRoutingProfile's pydantic
    # default), matching the read-only-review rule, exactly as a reachable
    # coordinator would have. Evaluating against an empty profile instead
    # would silently fall through to the "quick" default dispatch mode --
    # an outage weakening routing constraints (Codex review on PR #605).
    result = _route(checkout)

    assert result["selected"]["assignment"]["dispatch_mode"] == "review"
    assert "rule:read-only-review:dispatch_mode=review" in result["provenance"]["rationale"]


def test_partial_routing_profile_defaults_only_fill_omitted_fields(checkout: Path) -> None:
    # secret_need is supplied explicitly; scope is omitted and must still
    # default to "read-only" -- both rules fire, proving defaults apply
    # alongside caller-supplied fields rather than only when the profile is
    # entirely absent.
    result = _route(checkout, routing_profile={"secret_need": "direct"})

    assert result["selected"]["assignment"]["dispatch_mode"] == "review"
    assert set(result["provenance"]["matched_rule_ids"]) == {
        "direct-secrets-local",
        "read-only-review",
    }


def test_explicit_non_default_scope_is_not_overridden_by_defaults(checkout: Path) -> None:
    # An explicit, non-default scope must be preserved -- defaults fill gaps,
    # they never clobber a caller-supplied value.
    result = _route(checkout, routing_profile={"scope": "broad-write"})

    assert result["provenance"]["matched_rule_ids"] == []
    assert "default:dispatch_mode=quick" in result["provenance"]["rationale"]


def test_default_dispatch_mode_used_when_no_rule_matches(checkout: Path) -> None:
    # scope must be a non-default value here so read-only-review does not
    # fire and mask the phase-default path this test targets.
    result = _route(
        checkout,
        task_signals={"archetype": "implementer", "phase": "IMPL_REVIEW"},
        routing_profile={"scope": "broad-write"},
    )

    assert result["selected"]["assignment"]["dispatch_mode"] == "review"
    assert "default:dispatch_mode=review" in result["provenance"]["rationale"]


def test_no_exact_model_match_raises_bounded_error(checkout: Path) -> None:
    with pytest.raises(routing_fallback.LocalRoutingFallbackError):
        _route(checkout, static_model="model-nobody-configured")


def test_no_matching_vendor_type_raises_bounded_error(checkout: Path) -> None:
    with pytest.raises(routing_fallback.LocalRoutingFallbackError):
        _route(checkout, static_provider="codex")


def test_alternatives_are_bounded_to_the_response_contract_limit(tmp_path: Path) -> None:
    """Codex review on PR #605 (round 6): contracts/openapi/v1.1.yaml caps
    SelectModelResponse.alternatives at 64 items. A checkout configuring more
    than 65 exact lanes for the caller's provider/model must not emit a
    contract-invalid response during an outage."""
    coordinator_dir = tmp_path / "agent-coordinator"
    coordinator_dir.mkdir()
    _write_canonical_contract(coordinator_dir)
    (coordinator_dir / "routing.yaml").write_text(yaml.safe_dump(_ROUTING_YAML))
    agents = {
        f"claude-local-{i}": {
            "type": "claude_code",
            "location": "local",
            "policy_vendor": "claude",
            "catalog_vendor": "claude_code",
            "endpoint_kind": "vendor-cli",
            "isolation": "worktree",
            "cli": {
                "model": "claude-sonnet-4-6",
                "dispatch_modes": {"review": {}, "alternative": {}, "quick": {}},
            },
        }
        for i in range(70)
    }
    (coordinator_dir / "agents.yaml").write_text(yaml.safe_dump({"agents": agents}))
    (coordinator_dir / "archetypes.yaml").write_text(yaml.safe_dump(_ARCHETYPES_YAML))

    result = routing_fallback.local_static_route(
        {"archetype": "implementer", "phase": "IMPLEMENT"},
        static_provider="claude_code",
        static_model="claude-sonnet-4-6",
        repo_root=tmp_path,
    )

    assert len(result["alternatives"]) == 64


def test_malformed_agents_yaml_entry_fails_loud(tmp_path: Path) -> None:
    """Codex review on PR #605 (round 3): a schema-invalid agents.yaml entry
    must fail the whole load loud, mirroring load_agents_config()'s own
    strict validation -- not silently produce a successful local assignment
    from whatever partial data happens to coerce cleanly."""
    coordinator_dir = tmp_path / "agent-coordinator"
    coordinator_dir.mkdir()
    _write_canonical_contract(coordinator_dir)
    (coordinator_dir / "routing.yaml").write_text(yaml.safe_dump(_ROUTING_YAML))
    agents = {"agents": dict(_AGENTS_YAML["agents"])}
    agents["agents"]["claude-local"] = dict(agents["agents"]["claude-local"])
    agents["agents"]["claude-local"]["location"] = ["not", "a", "string"]
    (coordinator_dir / "agents.yaml").write_text(yaml.safe_dump(agents))
    (coordinator_dir / "archetypes.yaml").write_text(yaml.safe_dump(_ARCHETYPES_YAML))

    with pytest.raises(ValueError, match="location must be a string"):
        routing_fallback.local_static_route(
            {"archetype": "implementer", "phase": "IMPLEMENT"},
            static_provider="claude_code",
            static_model="claude-sonnet-4-6",
            repo_root=tmp_path,
        )


def test_roadmap_policy_allowed_locations_excludes_prohibited_lane(checkout: Path) -> None:
    """Codex review on PR #605: an outage must not route onto a location the
    caller's roadmap policy prohibits, even though claude-local (location=local)
    would otherwise win by fallback.location_order."""
    result = _route(
        checkout,
        routing_profile={"roadmap_policy": {"allowed_locations": ["cloud"]}},
    )

    assert result["selected"]["assignment"]["agent_id"] == "claude-remote"
    assert result["selected"]["assignment"]["location"] == "cloud"
    assert result["alternatives"] == []


def test_roadmap_policy_excluded_agent_ids_excludes_prohibited_lane(checkout: Path) -> None:
    result = _route(
        checkout,
        routing_profile={"roadmap_policy": {"excluded_agent_ids": ["claude-local"]}},
    )

    assert result["selected"]["assignment"]["agent_id"] == "claude-remote"


def test_roadmap_policy_excluded_vendor_types_yields_no_candidates(checkout: Path) -> None:
    with pytest.raises(routing_fallback.LocalRoutingFallbackError):
        _route(
            checkout,
            routing_profile={"roadmap_policy": {"excluded_vendor_types": ["claude_code"]}},
        )


def test_roadmap_policy_allowed_agent_ids_yields_no_candidates_when_unmatched(
    checkout: Path,
) -> None:
    with pytest.raises(routing_fallback.LocalRoutingFallbackError):
        _route(
            checkout,
            routing_profile={"roadmap_policy": {"allowed_agent_ids": ["some-other-agent"]}},
        )


def test_non_mapping_roadmap_policy_fails_loud_not_attributeerror(checkout: Path) -> None:
    """Codex review on PR #605 (round 3): routing_profile is caller-supplied
    and never passes through SelectModelRequest's pydantic validation on this
    path, so a malformed shape must raise ValueError, not leak an
    AttributeError that would break try_select_model_for_task's
    never-raises contract."""
    with pytest.raises(ValueError, match="roadmap_policy must be a mapping"):
        _route(checkout, routing_profile={"roadmap_policy": "invalid"})


def test_non_list_roadmap_policy_field_fails_loud_not_typeerror(checkout: Path) -> None:
    with pytest.raises(ValueError, match="allowed_agent_ids must be a list of strings"):
        _route(checkout, routing_profile={"roadmap_policy": {"allowed_agent_ids": 1}})


def test_non_string_roadmap_policy_list_item_fails_loud(checkout: Path) -> None:
    with pytest.raises(ValueError, match="excluded_agent_ids must be a list of strings"):
        _route(checkout, routing_profile={"roadmap_policy": {"excluded_agent_ids": [123]}})


def test_sdk_only_lane_is_selectable_via_sdk_dispatch_mode(tmp_path: Path) -> None:
    coordinator_dir = tmp_path / "agent-coordinator"
    coordinator_dir.mkdir()
    _write_canonical_contract(coordinator_dir)
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
    (coordinator_dir / "archetypes.yaml").write_text(
        yaml.safe_dump({"model_aliases": {}, "phase_mapping": {"IMPL_REVIEW": {}}})
    )

    result = routing_fallback.local_static_route(
        {"archetype": "implementer"},
        static_provider="grok",
        static_model="grok-5",
        # scope must be non-default here, or read-only-review's rule-derived
        # dispatch_mode="review" conflicts with the explicit "sdk" request.
        routing_profile={"required_dispatch_mode": "sdk", "scope": "broad-write"},
        repo_root=tmp_path,
    )

    assert result["selected"]["assignment"]["dispatch_mode"] == "sdk"
    assert result["selected"]["assignment"]["agent_id"] == "grok-remote"


def test_malformed_routing_yaml_fails_loud(tmp_path: Path) -> None:
    coordinator_dir = tmp_path / "agent-coordinator"
    coordinator_dir.mkdir()
    _write_canonical_contract(coordinator_dir)
    (coordinator_dir / "routing.yaml").write_text(yaml.safe_dump({"schema_version": 2}))
    (coordinator_dir / "agents.yaml").write_text(yaml.safe_dump(_AGENTS_YAML))

    with pytest.raises(ValueError):
        routing_fallback.local_static_route(
            {"archetype": "implementer"},
            static_provider="claude_code",
            static_model="claude-sonnet-4-6",
            repo_root=tmp_path,
        )


def _write_routing_yaml(tmp_path: Path, document: dict[str, Any]) -> Path:
    coordinator_dir = tmp_path / "agent-coordinator"
    coordinator_dir.mkdir(exist_ok=True)
    _write_canonical_contract(coordinator_dir)
    (coordinator_dir / "routing.yaml").write_text(yaml.safe_dump(document))
    (coordinator_dir / "agents.yaml").write_text(yaml.safe_dump(_AGENTS_YAML))
    (coordinator_dir / "archetypes.yaml").write_text(yaml.safe_dump(_ARCHETYPES_YAML))
    return tmp_path


def test_duplicate_rule_id_fails_loud(tmp_path: Path) -> None:
    document = dict(_ROUTING_YAML)
    document["rules"] = [
        {"id": "dup-rule", "when": {"scope": "read-only"}, "constrain": {"dispatch_mode": "review"}},
        {"id": "dup-rule", "when": {"secret_need": "direct"}, "constrain": {"location": "local"}},
    ]
    root = _write_routing_yaml(tmp_path, document)

    with pytest.raises(ValueError, match="duplicate rule id"):
        routing_fallback.load_routing_policy_document(root)


def test_unknown_top_level_field_fails_loud(tmp_path: Path) -> None:
    document = dict(_ROUTING_YAML)
    document["unexpected_field"] = True
    root = _write_routing_yaml(tmp_path, document)

    with pytest.raises(ValueError, match="unknown field"):
        routing_fallback.load_routing_policy_document(root)


def test_unknown_rule_when_field_fails_loud(tmp_path: Path) -> None:
    document = dict(_ROUTING_YAML)
    document["rules"] = [{"id": "bad-rule", "when": {"not_a_real_field": "x"}, "constrain": {"location": "local"}}]
    root = _write_routing_yaml(tmp_path, document)

    with pytest.raises(ValueError, match="unknown field"):
        routing_fallback.load_routing_policy_document(root)


def test_invalid_rule_when_enum_fails_loud(tmp_path: Path) -> None:
    document = dict(_ROUTING_YAML)
    document["rules"] = [{"id": "bad-rule", "when": {"scope": "not-a-real-scope"}, "constrain": {"location": "local"}}]
    root = _write_routing_yaml(tmp_path, document)

    with pytest.raises(ValueError, match="invalid value"):
        routing_fallback.load_routing_policy_document(root)


def test_invalid_rule_constrain_enum_fails_loud(tmp_path: Path) -> None:
    document = dict(_ROUTING_YAML)
    document["rules"] = [
        {"id": "bad-rule", "when": {"scope": "read-only"}, "constrain": {"location": "mars"}}
    ]
    root = _write_routing_yaml(tmp_path, document)

    with pytest.raises(ValueError, match="invalid value"):
        routing_fallback.load_routing_policy_document(root)


def test_rule_duration_min_greater_than_max_fails_loud(tmp_path: Path) -> None:
    document = dict(_ROUTING_YAML)
    document["rules"] = [
        {
            "id": "bad-rule",
            "when": {"min_duration_seconds": 100, "max_duration_seconds": 10},
            "constrain": {"location": "local"},
        }
    ]
    root = _write_routing_yaml(tmp_path, document)

    with pytest.raises(ValueError, match="min_duration_seconds greater than max_duration_seconds"):
        routing_fallback.load_routing_policy_document(root)


def test_invalid_phase_dispatch_mode_value_fails_loud(tmp_path: Path) -> None:
    document = dict(_ROUTING_YAML)
    document["defaults"] = {
        "dispatch_mode": "quick",
        "phase_dispatch_modes": {"IMPL_REVIEW": "not-a-real-mode"},
    }
    root = _write_routing_yaml(tmp_path, document)

    with pytest.raises(ValueError, match="phase_dispatch_modes"):
        routing_fallback.load_routing_policy_document(root)


def test_unconfigured_phase_dispatch_default_fails_loud(tmp_path: Path) -> None:
    """Codex review on PR #605: a typo'd phase key (IMPL_REVEIW) must fail
    loud here exactly as it would against the coordinator's strict loader,
    which cross-checks phase_dispatch_modes against the authored phase
    roster (get_phase_mapping) -- not merely check the dispatch-mode value."""
    document = dict(_ROUTING_YAML)
    document["defaults"] = {
        "dispatch_mode": "quick",
        "phase_dispatch_modes": {"IMPL_REVEIW": "review"},
    }
    root = _write_routing_yaml(tmp_path, document)

    with pytest.raises(ValueError, match="unconfigured phase dispatch default"):
        routing_fallback.load_routing_policy_document(root)


def test_duplicate_fallback_order_value_fails_loud(tmp_path: Path) -> None:
    document = dict(_ROUTING_YAML)
    document["fallback"] = dict(_ROUTING_YAML["fallback"])
    document["fallback"]["location_order"] = ["local", "local", "cloud"]
    root = _write_routing_yaml(tmp_path, document)

    with pytest.raises(ValueError, match="duplicate value"):
        routing_fallback.load_routing_policy_document(root)


def test_missing_routing_yaml_fails_loud(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        routing_fallback.local_static_route(
            {"archetype": "implementer"},
            static_provider="claude_code",
            static_model="claude-sonnet-4-6",
            repo_root=tmp_path,
        )
