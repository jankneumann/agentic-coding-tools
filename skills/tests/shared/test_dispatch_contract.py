"""skills/shared/dispatch_contract.py (dispatch-contract D1-D4, D6, D9, D10a).

Covers: the byte-unchanged v1 fixtures through the published schemas, the v1
upgrade (both scenarios), every row of the D4 loop-state mapping, the slug
rule, launch digests, escalation fingerprints, command redaction, the launch
marker reader, and the schema locator's install_assets fallback.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "skills"))

from shared import dispatch_contract as dc  # noqa: E402
from shared.dispatch_contract import DispatchContractError  # noqa: E402

_FIXTURES = REPO_ROOT / "skills" / "tests" / "supervise" / "fixtures" / "execution" / "contracts"
_COMMIT = "0123456789abcdef0123456789abcdef01234567"
_DIGEST = "ab" * 32


def _fixture(name: str) -> Any:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def _ctx(**overrides: Any) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "dispatch_id": "batch-0123456789abcdef01234567:ri-01:attempt-1",
        "change_id": "add-alpha",
        "attempt": 1,
        "lease_generation": 2,
        "worktree_ref": "add-alpha",
        "branch": "openspec/add-alpha",
        "host_id": "host-a",
        "evidence": {
            "loop_state_path": "openspec/changes/add-alpha/loop-state.json",
            "commit": _COMMIT,
            "loop_state_digest": _DIGEST,
        },
    }
    ctx.update(overrides)
    return ctx


# --------------------------------------------------------------------------- #
# Published schemas, existing fixtures (outcome 1)
# --------------------------------------------------------------------------- #


def test_existing_v1_fixtures_validate_on_any_host() -> None:
    request = _fixture("valid-request.json")
    assert dc.validate_request(request) == request
    for kind in ("success", "parked"):
        result = _fixture("valid-results.json")[kind]
        assert dc.validate_result(result) == result


def test_invalid_fixture_is_rejected_naming_the_pointer() -> None:
    with pytest.raises(DispatchContractError) as excinfo:
        dc.validate_request(_fixture("invalid-continuation-without-kind.json"))
    assert excinfo.value.pointer == "/continuation"
    assert "/continuation" in str(excinfo.value)


def test_unknown_schema_version_is_rejected() -> None:
    result = _fixture("valid-results.json")["success"]
    result["schema_version"] = 3
    with pytest.raises(DispatchContractError, match="schema_version"):
        dc.validate_result(result)


def test_oversized_result_is_rejected() -> None:
    result = dc.result_from_loop_state({"current_phase": "DONE", "goal_gate": {"verdict": "abandoned"}}, _ctx())
    assert result is not None
    result["outcome"] = "failed:" + "x" * 1000
    result["degradations"] = [
        {"code": "review_skipped", "phase": "PLAN_REVIEW", "detail": "d" * 512}
    ] * 32
    with pytest.raises(DispatchContractError, match="16 KiB"):
        dc.validate_result(result)


def test_registry_resolves_cross_directory_refs() -> None:
    attempt_schema = dc.load_schema(dc.ATTEMPT)
    registry = dc.schema_registry()
    for schema_id in (
        attempt_schema["$id"],
        dc.load_schema(dc.RESULT_V2)["$id"],
        dc.load_schema(dc.REQUEST_V2)["$id"],
        "https://agentic-coding-tools.dev/contracts/bounded-dispatch-context.schema.json",
    ):
        assert registry.contents(schema_id)


def test_locator_falls_back_to_install_assets(tmp_path: Path) -> None:
    path = dc.find_schema_path(dc.RESULT_V2, tmp_path)
    assert path.is_file()
    mirror = REPO_ROOT / "skills" / "roadmap-runtime" / "install_assets" / "openspec" / dc.RESULT_V2
    assert path.read_bytes() == mirror.read_bytes()


# --------------------------------------------------------------------------- #
# v1 upgrade (D1)
# --------------------------------------------------------------------------- #


def test_v1_success_inside_the_managed_root_is_upgraded() -> None:
    result = _fixture("valid-results.json")["success"]
    upgraded = dc.upgrade_v1(
        result,
        repo_root=Path("/workspace"),
        managed_root=Path("/workspace/.git-worktrees"),
        host_id="host-b",
    )
    assert upgraded["schema_version"] == 2
    assert upgraded["degradations"] == []
    assert upgraded["worktree_ref"] == "add-alpha-capability"
    assert upgraded["host_id"] == "host-b"
    assert upgraded["evidence"]["loop_state_path"] == (
        "openspec/changes/add-alpha-capability/loop-state.json"
    )
    assert "worktree_path" not in upgraded


def test_v1_result_outside_both_roots_is_rejected() -> None:
    result = _fixture("valid-results.json")["success"]
    before = copy.deepcopy(result)
    with pytest.raises(DispatchContractError, match="v1 result worktree_path is not repo-relative"):
        dc.upgrade_v1(
            result, repo_root=Path("/elsewhere"), managed_root=Path("/elsewhere/wt"), host_id="h"
        )
    assert result == before


def test_v1_request_upgrade_gains_empty_profile_and_portable_isolation() -> None:
    upgraded = dc.upgrade_v1(
        _fixture("valid-request.json"),
        repo_root=Path("/workspace"),
        managed_root=Path("/workspace/.git-worktrees"),
        host_id="host-a",
    )
    assert upgraded["execution_profile"] == {}
    assert upgraded["review_requirements"] == {}
    assert upgraded["isolation"] == {
        "mode": "managed_worktree",
        "worktree_ref": "add-alpha-capability",
        "branch": "openspec/add-alpha-capability",
        "host_id": "host-a",
    }


def test_harness_provided_isolation_at_the_repo_root_round_trips_as_dot(tmp_path: Path) -> None:
    """A cloud worker's harness checkout IS the repo root: its portable ref is
    ``.`` (schema-valid) and resolves back to the repo root on any host."""
    repo = tmp_path / "host-a" / "repo"
    ref = dc.portable_ref(repo, mode="harness_provided", repo_root=repo, managed_root=repo / ".git-worktrees")
    assert ref == "."
    assert dc.is_portable_path(ref)
    isolation = {"mode": "harness_provided", "worktree_ref": ref, "branch": "claude/x", "host_id": "host-a"}
    other = tmp_path / "host-b" / "checkout"
    assert dc.resolve_worktree(isolation, repo_root=repo, managed_root=None) == repo
    assert dc.resolve_worktree(isolation, repo_root=other, managed_root=None) == other
    # A managed worktree can never be the managed root itself.
    assert dc.portable_ref(repo / ".git-worktrees", mode="managed_worktree", repo_root=repo,
                           managed_root=repo / ".git-worktrees") is None


def test_a_v1_request_at_the_repo_root_upgrades_to_a_schema_valid_dot_ref() -> None:
    """upgrade_v1 validates the upgraded request, so this is the schema check."""
    document = _fixture("valid-request.json")
    document["isolation"] = {"mode": "harness_provided", "worktree_path": "/workspace", "branch": "claude/x"}
    upgraded = dc.upgrade_v1(
        document, repo_root=Path("/workspace"), managed_root=Path("/workspace/.git-worktrees"), host_id="host-a",
    )
    assert upgraded["isolation"]["worktree_ref"] == "."


# --------------------------------------------------------------------------- #
# D4 mapping, one test per row
# --------------------------------------------------------------------------- #


def test_park_wins_over_pending_gate() -> None:
    state = {
        "current_phase": "PLAN_REVIEW",
        "park": {
            "kind": "capability_unavailable",
            "phase": "PLAN_REVIEW",
            "missing_lanes": ["codex"],
            "reason": "review quorum 2 unmet",
        },
        "pending_gate": {"gate": "proposal_approval", "prompt": "Approve?"},
    }
    result = dc.result_from_loop_state(state, _ctx())
    assert result["outcome"] == "parked"
    assert result["parked"]["kind"] == "capability_unavailable"
    assert result["parked"]["missing_lanes"] == ["codex"]


def test_permission_blocked_park_maps_with_its_payload() -> None:
    state = {
        "current_phase": "IMPLEMENT",
        "park": {
            "kind": "permission_blocked",
            "tool": "Bash",
            "rule": "Bash(env *)",
            "classifier_reason": "reads credentials",
            "command": "env | grep KEY",
            "reason": "permission denied",
        },
    }
    parked = dc.result_from_loop_state(state, _ctx())["parked"]
    assert parked == {
        "kind": "permission_blocked",
        "gate": None,
        "tool": "Bash",
        "rule": "Bash(env *)",
        "classifier_reason": "reads credentials",
        "command": "env | grep KEY",
        "reason": "permission denied",
        "deadline": None,
        "resume_hint": None,
    }


@pytest.mark.parametrize(
    "gate",
    [
        "gatekeeper_escalation",
        "proposal_approval",
        "plan_review_convergence_failure",
        "validation_failure",
        "escalate_resume",
        "replan_required",
        "pr_creation",
        "merge",
    ],
)
def test_pending_gate_maps_to_parked_pending_gate(gate: str) -> None:
    state = {"current_phase": "PLAN", "pending_gate": {"gate": gate, "prompt": "Approve?"}}
    result = dc.result_from_loop_state(state, _ctx())
    assert result["parked"]["kind"] == "pending_gate"
    assert result["parked"]["gate"] == gate


def test_escalate_maps_to_policy_pause_with_previous_phase() -> None:
    state = {"current_phase": "ESCALATE", "previous_phase": "PLAN_REVIEW", "escalation_reason": "max_iter"}
    result = dc.result_from_loop_state(state, _ctx())
    assert result["parked"]["kind"] == "policy_pause"
    assert "PLAN_REVIEW" in result["parked"]["resume_hint"]
    assert result["parked"]["reason"] == "max_iter"


def test_abandoned_done_is_failed_not_success() -> None:
    state = {"current_phase": "DONE", "goal_gate": {"verdict": "abandoned"}, "last_handoff_id": "h-1"}
    assert dc.result_from_loop_state(state, _ctx())["outcome"] == "failed:abandoned"


def test_passed_done_with_handoff_is_success() -> None:
    state = {
        "current_phase": "DONE",
        "goal_gate": {"verdict": "passed"},
        "last_handoff_id": "h-1",
        "degradations": [{"code": "single_vendor_review", "phase": "PLAN_REVIEW", "detail": "one lane"}],
    }
    result = dc.result_from_loop_state(state, _ctx())
    assert result["outcome"] == "success"
    assert result["handoff_id"] == "h-1"
    assert result["degradations"][0]["code"] == "single_vendor_review"


@pytest.mark.parametrize(
    "state",
    [
        {"current_phase": "DONE", "goal_gate": {"verdict": "refused"}, "last_handoff_id": "h-1"},
        {"current_phase": "DONE", "goal_gate": None, "last_handoff_id": "h-1"},
        {"current_phase": "DONE", "goal_gate": {"verdict": "passed"}, "last_handoff_id": None},
    ],
)
def test_other_done_is_goal_gate_unverified(state: dict[str, Any]) -> None:
    assert dc.result_from_loop_state(state, _ctx())["outcome"] == "failed:goal_gate_unverified"


def test_non_terminal_phase_has_no_result() -> None:
    assert dc.result_from_loop_state({"current_phase": "IMPLEMENT"}, _ctx()) is None


# --------------------------------------------------------------------------- #
# Slug, digests, fingerprints, redaction
# --------------------------------------------------------------------------- #


def test_dispatch_slug_replaces_unsafe_characters() -> None:
    assert dc.dispatch_slug("batch-abc:ri-01:attempt-1") == "batch-abc-ri-01-attempt-1"
    assert dc.dispatch_slug("a/b c.d_e") == "a-b-c.d_e"
    assert dc.result_relpath("add-alpha", "batch-abc:ri-01:attempt-1", 3) == (
        "openspec/changes/add-alpha/dispatch-results/batch-abc-ri-01-attempt-1-g3.json"
    )


def test_launch_digest_round_trip() -> None:
    digest = dc.launch_digest("raw-launch-nonce-0001")
    assert digest.startswith("sha256:") and len(digest) == 71
    assert dc.verify_launch_token("raw-launch-nonce-0001", digest)
    assert not dc.verify_launch_token("raw-launch-nonce-0002", digest)
    assert not dc.verify_launch_token("raw-launch-nonce-0001", "launch-token-0001")


def test_dedupe_fingerprints() -> None:
    blocked = {"kind": "permission_blocked", "tool": "Bash", "rule": "Bash(env *)", "classifier_reason": "r"}
    same_rule_other_command = dict(blocked, command="env | grep OTHER")
    assert dc.dedupe_fingerprint(blocked) == dc.dedupe_fingerprint(same_rule_other_command)
    lanes_a = {"kind": "capability_unavailable", "phase": "PLAN_REVIEW", "missing_lanes": ["gemini", "codex"]}
    lanes_b = {"kind": "capability_unavailable", "phase": "PLAN_REVIEW", "missing_lanes": ["codex", "gemini"]}
    lanes_c = {"kind": "capability_unavailable", "phase": "PLAN_REVIEW", "missing_lanes": ["codex"]}
    assert dc.dedupe_fingerprint(lanes_a) == dc.dedupe_fingerprint(lanes_b)
    assert dc.dedupe_fingerprint(lanes_a) != dc.dedupe_fingerprint(lanes_c)
    assert dc.dedupe_fingerprint({"kind": "pending_gate", "gate": "merge"}) is None


def test_redacted_command_drops_the_bearer_value() -> None:
    redacted = dc.redact_command('curl -H "Authorization: Bearer abc123def456ghi789"')
    assert "abc123" not in redacted
    assert "[REDACTED:" in redacted
    assert len(dc.redact_command("x" * 1000)) <= 256


@pytest.mark.parametrize(
    ("command", "secret"),
    [
        ("curl -u admin:hunter2pass https://example.invalid", "hunter2pass"),
        ("curl --user admin:hunter2pass https://example.invalid", "hunter2pass"),
        ("curl https://bob:s3cr3tpw@example.invalid/a", "s3cr3tpw"),
        ("git clone https://x-access:ghs_shortval@example.invalid/r.git", "ghs_shortval"),
        ("tool --password hunter2 run", "hunter2"),
        ("tool --token=abcd1234 run", "abcd1234"),
        ("tool --api-key abcd1234 run", "abcd1234"),
        ("aws configure set aws_secret_access_key wJalrXUtnFEMI", "wJalrXUtnFEMI"),
        ("deploy client_secret: abc123 now", "abc123"),
    ],
)
def test_redacted_command_drops_short_credentials_the_sanitizer_misses(
    command: str, secret: str
) -> None:
    """Short credentials below the sanitizer's entropy threshold: URL userinfo,
    ``-u user:pass``, credential-named flags and keyed values (D9)."""
    redacted = dc.redact_command(command)
    assert secret not in redacted
    assert "[REDACTED:" in redacted


def test_redaction_keeps_the_non_secret_shape_of_the_command() -> None:
    redacted = dc.redact_command("curl -u admin:hunter2pass https://example.invalid/path")
    assert redacted.startswith("curl -u admin:")
    assert "https://example.invalid/path" in redacted


# --------------------------------------------------------------------------- #
# Launch marker reader (D10a)
# --------------------------------------------------------------------------- #


def _marker(root: Path, name: str, record: Any) -> None:
    folder = root / ".supervised-dispatch" / "add-alpha"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(json.dumps(record) if not isinstance(record, str) else record)


def test_marker_reader_returns_the_highest_valid_generation(tmp_path: Path) -> None:
    assert dc.read_launch_marker("add-alpha", repo_root=tmp_path) is None
    base = {"dispatch_id": "d-1", "owner_nonce": "owner-nonce-000000001"}
    _marker(tmp_path, "ri-01-attempt-1.marker", dict(base, generation=1))
    _marker(tmp_path, "ri-01-attempt-2.marker", dict(base, generation=3, roadmap_approval_ref="gate-decision:x"))
    _marker(tmp_path, "bad.marker", "{not json")
    _marker(tmp_path, "forged.marker", {"dispatch_id": "d-1", "generation": 9, "owner_nonce": "short"})
    marker = dc.read_launch_marker("add-alpha", repo_root=tmp_path)
    assert marker["generation"] == 3
    assert marker["roadmap_approval_ref"] == "gate-decision:x"
    assert dc.read_launch_marker("../add-alpha", repo_root=tmp_path) is None


# --------------------------------------------------------------------------- #
# Closure enumeration
# --------------------------------------------------------------------------- #


def test_permitted_combinations_are_derived_from_the_schema() -> None:
    combos = dc.permitted_result_combinations()
    assert ("success", None, None) in combos
    assert ("failed", None, None) in combos
    assert ("vendor_limit", None, None) in combos
    assert ("parked", "pending_gate", "escalate_resume") in combos
    assert ("parked", "pending_gate", "roadmap_approval") not in combos
    assert ("parked", "policy_pause", None) in combos
    assert ("parked", "policy_pause", "escalate_resume") in combos
    assert ("parked", "permission_blocked", None) in combos
    assert ("parked", "capability_unavailable", None) in combos
    assert len(combos) == 3 + 8 + 2 + 1 + 1
