"""Behavioral source contract for the supervised execution host protocol."""

from __future__ import annotations

from pathlib import Path


_SOURCE_SKILL = Path(__file__).resolve().parents[2] / "supervise" / "SKILL.md"


def _section(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def _execute_section() -> str:
    return _section(
        _SOURCE_SKILL.read_text(encoding="utf-8"),
        "## Verb: `execute`",
        "## Idempotency",
    )


def test_contract_inspects_the_canonical_source_contribution() -> None:
    assert _SOURCE_SKILL == Path(__file__).resolve().parents[2] / "supervise" / "SKILL.md"
    assert ".agents" not in _SOURCE_SKILL.parts
    assert ".claude" not in _SOURCE_SKILL.parts


def test_execute_requires_one_durable_roadmap_altitude_approval_before_mutation() -> None:
    approval = _section(_execute_section(), "### Approval gate", "### Prepare and launch")

    assert "direct `/autopilot-roadmap` invocation" in approval
    assert "approved `/supervise` roadmap batch" in approval
    assert "inherits that approval for every dependency-ready item" in approval
    assert "without discovery, direction, plan, or per-item approval questions" in approval
    assert "before `ExecutionAdapter.prepare`" in approval
    assert "before any roadmap checkpoint or execution-state mutation" in approval


def test_execute_starts_an_isolated_batch_before_awaiting_any_child() -> None:
    launch = _section(_execute_section(), "### Prepare and launch", "### Child lifecycle")

    ordered = [
        "`ExecutionAdapter.prepare`",
        "exact `change_id`",
        "distinct verified worktree path and branch",
        "Start every admitted request",
        "Record every durable task handle",
        "await any child",
    ]
    positions = [launch.index(token) for token in ordered]
    assert positions == sorted(positions)
    assert "bounded correlated `failed` result before `/autopilot` starts" in launch
    assert "must not share or reuse that failed worktree" in launch


def test_execute_pins_the_ack_go_entry_sequence() -> None:
    lifecycle = _section(_execute_section(), "### Child lifecycle", "### Collect and apply")

    ordered = [
        "`child-start`",
        "`acknowledge`",
        "go release",
        "`enter`",
        "`/autopilot <change-id>`",
    ]
    positions = [lifecycle.index(token) for token in ordered]
    assert positions == sorted(positions)
    assert "must not enter Autopilot before the durable handle acknowledgement" in lifecycle


def test_execute_preserves_router_context_and_uses_existing_fallback() -> None:
    launch = _section(_execute_section(), "### Prepare and launch", "### Child lifecycle")

    assert "Preserve every router-owned context key and value unchanged" in launch
    assert "existing archetype/provider resolution path" in launch
    for forbidden_choice in ("vendor", "model", "location", "cost policy"):
        assert f"must not invent a {forbidden_choice}" in launch


def test_execute_collects_only_bounded_outcomes_and_applies_each_once() -> None:
    collection = _section(_execute_section(), "### Collect and apply", "### Reconcile and resume")

    assert "schema-valid `success`, `parked`, or `failed` result" in collection
    assert "bounded reason and optional `handoff_id`" in collection
    assert "Discard the child transcript" in collection
    assert "outcome-only parent session" in collection
    assert "no transcript in the supervisor record" in collection
    assert "in-memory result lookup" in collection
    assert "synchronous `dispatch_fn` exactly once per returned generation" in collection
    assert "`pending_gate` or `policy_pause`" in collection
    assert "nonfailure" in collection


def test_execute_requires_canonical_committed_loop_state_evidence() -> None:
    collection = _section(_execute_section(), "### Collect and apply", "### Reconcile and resume")

    assert "openspec/changes/<change-id>/loop-state.json" in collection
    assert "current worktree commit" in collection
    assert "SHA-256 digest" in collection


def test_execute_documents_safe_reconciliation_and_authorized_resume() -> None:
    reconciliation = _section(_execute_section(), "### Reconcile and resume", "---")

    for state in ("live", "terminal", "dead", "unknown"):
        assert f"`{state}`" in reconciliation
    assert "quarantine" in reconciliation
    assert "never infer death from an absent or expired post-go heartbeat" in reconciliation
    assert "durable `approval_ref`" in reconciliation
    assert "generation increment" in reconciliation
    assert "same dispatch ID, attempt, launch token, worktree, and branch" in reconciliation
