"""Unit tests for the ``--branch-prefix prototype`` resolution logic.

Spec scenarios covered:
- skill-workflow.PrototypeWorktreeSupport.branch-creation — branch is
  ``prototype/<change-id>/v<n>`` with a '/' separator (not '--').
- skill-workflow.PrototypeWorktreeSupport.branch-override-composition —
  ``--branch-prefix prototype`` wins over ``OPENSPEC_BRANCH_OVERRIDE``
  for the prototype variant branches; the env var still governs the
  parent feature branch (resolve_parent_branch is unaffected).

Design decisions: D4 (branch retention through feature lifecycle).

These are pure-function tests — they exercise ``resolve_branch`` with
``branch_prefix='prototype'`` and verify the new naming convention
without touching the filesystem. Integration with ``cmd_setup`` (auto-pin,
worktree creation) is covered separately in ``test_setup_prototype.py``.
"""

from __future__ import annotations

import pytest

from worktree import resolve_branch, resolve_parent_branch


class TestPrototypeBranchPrefix:
    """``branch_prefix='prototype'`` produces ``prototype/<change>/<agent>``."""

    def test_with_agent_id_uses_slash_separator(self) -> None:
        # The prototype workflow never creates a parent ``prototype/<change>``
        # branch, so '/' is safe — git's ref-storage limitation that forces
        # '--' for the openspec/<change> case doesn't apply here.
        result = resolve_branch(
            "add-foo", agent_id="v1", branch_prefix="prototype", env={}
        )
        assert result == "prototype/add-foo/v1"

    def test_without_agent_id_returns_change_root(self) -> None:
        # Edge case — the skill always passes an agent_id in practice, but
        # the function should produce a sensible value if called without one.
        result = resolve_branch("add-foo", branch_prefix="prototype", env={})
        assert result == "prototype/add-foo"

    def test_does_not_use_dash_dash_separator(self) -> None:
        # Regression guard: if someone "consolidates" with the openspec
        # naming convention, they would re-introduce '--' here. Keep it '/'.
        result = resolve_branch(
            "add-foo", agent_id="v2", branch_prefix="prototype", env={}
        )
        assert "--" not in result
        assert result == "prototype/add-foo/v2"

    def test_higher_variant_numbers(self) -> None:
        # Spec caps at 6 today, but the resolver doesn't know that and
        # shouldn't care — bounds are enforced by the prototype-feature skill.
        for vid in ("v1", "v3", "v6", "v10"):
            assert (
                resolve_branch(
                    "add-foo", agent_id=vid, branch_prefix="prototype", env={}
                )
                == f"prototype/add-foo/{vid}"
            )


class TestPrototypePrefixOverridesEnvVar:
    """``--branch-prefix prototype`` beats ``OPENSPEC_BRANCH_OVERRIDE`` for variants."""

    def test_env_override_set_but_prototype_prefix_wins(self) -> None:
        # Spec scenario: branch-override-composition. The operator may have
        # mandated ``claude/op-9P9o1`` for the parent feature branch via the
        # env var, but a prototype variant must still land on
        # ``prototype/<change>/v1`` so cleanup-feature can find and delete it.
        env = {"OPENSPEC_BRANCH_OVERRIDE": "claude/op-9P9o1"}
        result = resolve_branch(
            "add-foo", agent_id="v1", branch_prefix="prototype", env=env
        )
        assert result == "prototype/add-foo/v1"

    def test_parent_branch_still_honors_env_override(self) -> None:
        # The companion guarantee: resolve_parent_branch is the function
        # cleanup-feature / merge_worktrees use to find the integration
        # target, and that one MUST still honor the env override.
        env = {"OPENSPEC_BRANCH_OVERRIDE": "claude/op-9P9o1"}
        assert resolve_parent_branch("add-foo", env=env) == "claude/op-9P9o1"


class TestPrototypePrefixDoesNotAffectExistingBehavior:
    """Without ``branch_prefix='prototype'``, all existing precedence holds."""

    def test_default_path_unchanged(self) -> None:
        assert resolve_branch("change", env={}) == "openspec/change"
        assert (
            resolve_branch("change", agent_id="w1", env={})
            == "openspec/change--w1"
        )

    def test_env_override_unchanged_without_prototype_prefix(self) -> None:
        env = {"OPENSPEC_BRANCH_OVERRIDE": "claude/op"}
        assert resolve_branch("change", env=env) == "claude/op"
        assert (
            resolve_branch("change", agent_id="wp-backend", env=env)
            == "claude/op--wp-backend"
        )

    def test_prefix_arg_unchanged_without_prototype_prefix(self) -> None:
        # The legacy ``prefix`` arg uses '--' for agent-id composition.
        # Confirm nothing has shifted.
        assert (
            resolve_branch("change", agent_id="w1", prefix="fix", env={})
            == "fix/change--w1"
        )


class TestExplicitStillWinsOverPrototypePrefix:
    """``--branch`` (explicit) is the absolute trump card."""

    def test_explicit_branch_overrides_prototype_prefix(self) -> None:
        # Even with branch_prefix='prototype', a caller-supplied --branch
        # is taken verbatim. This preserves the existing contract that
        # explicit overrides skip ALL composition (agent suffix included).
        result = resolve_branch(
            "add-foo",
            agent_id="v1",
            branch_prefix="prototype",
            explicit="custom/exact-branch",
            env={},
        )
        assert result == "custom/exact-branch"


class TestPrototypePrefixValidation:
    """Only the literal value 'prototype' is recognized."""

    def test_unknown_branch_prefix_raises(self) -> None:
        # Anything other than 'prototype' (or None) is a programming error
        # — argparse's ``choices=['prototype']`` blocks it at the CLI layer,
        # but the function itself should also reject so library callers
        # don't silently get an openspec/... branch when they expected
        # something else.
        with pytest.raises(ValueError, match="branch_prefix"):
            resolve_branch(
                "add-foo", agent_id="v1", branch_prefix="experiment", env={}
            )

    def test_none_branch_prefix_falls_through(self) -> None:
        # Sanity: explicit None is the same as not passing it.
        assert (
            resolve_branch("change", branch_prefix=None, env={})
            == "openspec/change"
        )
