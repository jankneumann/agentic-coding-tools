"""Runtime policy tests for the versioned DG-04 routing rules."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.model_routing.routing_policy import load_routing_policy


def test_loader_records_canonical_checksum_and_first_matching_dimension(tmp_path: Path) -> None:
    policy_path = tmp_path / "routing.yaml"
    policy_path.write_text(
        """\
schema_version: 1
policy_version: test-v1
defaults:
  dispatch_mode: quick
  phase_dispatch_modes: {}
rules:
  - id: interactive-local
    when: {interactivity: interactive}
    constrain: {location: local}
  - id: later-cloud
    when: {interactivity: interactive}
    constrain: {location: cloud, dispatch_mode: review}
fallback:
  location_order: [local, cloud, unknown]
  isolation_order: [worktree, sandbox, none]
  dispatch_mode_order: [review, alternative, quick, sdk]
"""
    )

    policy = load_routing_policy(policy_path)
    result = policy.evaluate(
        {
            "phase": "IMPLEMENT",
            "interactivity": "interactive",
            "scope": "bounded-write",
            "secret_need": "none",
            "parallelism": 1,
            "repo_shape": "monorepo",
        }
    )

    assert len(policy.checksum) == 64
    assert policy.version == "test-v1"
    assert result.location == "local"
    assert result.dispatch_mode == "review"
    assert result.matched_rule_ids == ("interactive-local", "later-cloud")


def test_loader_rejects_duplicate_rule_ids(tmp_path: Path) -> None:
    policy_path = tmp_path / "routing.yaml"
    policy_path.write_text(
        """\
schema_version: 1
policy_version: test-v1
defaults: {dispatch_mode: quick, phase_dispatch_modes: {}}
rules:
  - {id: duplicate-rule, when: {scope: read-only}, constrain: {dispatch_mode: review}}
  - {id: duplicate-rule, when: {scope: broad-write}, constrain: {dispatch_mode: quick}}
fallback:
  location_order: [local, cloud, unknown]
  isolation_order: [worktree, sandbox, none]
  dispatch_mode_order: [review, alternative, quick, sdk]
"""
    )

    with pytest.raises(ValueError, match="duplicate routing rule id"):
        load_routing_policy(policy_path)


def test_loader_rejects_phase_default_absent_from_configured_phases(
    tmp_path: Path,
) -> None:
    policy_path = tmp_path / "routing.yaml"
    policy_path.write_text(
        """\
schema_version: 1
policy_version: test-v1
defaults: {dispatch_mode: quick, phase_dispatch_modes: {NOT_CONFIGURED: review}}
rules: []
fallback:
  location_order: [local, cloud, unknown]
  isolation_order: [worktree, sandbox, none]
  dispatch_mode_order: [review, alternative, quick, sdk]
"""
    )

    with pytest.raises(ValueError, match="unconfigured phase dispatch default"):
        load_routing_policy(policy_path)
