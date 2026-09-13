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


def _cycle_section() -> str:
    return _section(
        _SOURCE_SKILL.read_text(encoding="utf-8"),
        "## Verb: `cycle`",
        "## Verb: `execute`",
    )


def _intake_section() -> str:
    return _section(
        _SOURCE_SKILL.read_text(encoding="utf-8"),
        "## Verb: `intake`",
        "## Verb: `cycle`",
    )


def test_contract_inspects_the_canonical_source_contribution() -> None:
    assert _SOURCE_SKILL == Path(__file__).resolve().parents[2] / "supervise" / "SKILL.md"
    assert ".agents" not in _SOURCE_SKILL.parts
    assert ".claude" not in _SOURCE_SKILL.parts


def test_installed_supervise_skill_mirrors_are_byte_identical_when_present() -> None:
    canonical = _SOURCE_SKILL.read_bytes()
    root = _SOURCE_SKILL.parents[2]
    for relative in (
        ".claude/skills/supervise/SKILL.md",
        ".agents/skills/supervise/SKILL.md",
    ):
        mirror = root / relative
        if mirror.is_file():
            assert mirror.read_bytes() == canonical


def test_cycle_runs_lifecycle_maintenance_before_unchanged_exit_and_sense() -> None:
    cycle = _cycle_section()

    maintenance = cycle.index("store --prune-only")
    unchanged = cycle.index("fingerprint")
    sense = cycle.index("### 2. Sense")
    assert maintenance < unchanged < sense
    assert "lifecycle_changed" in cycle
    assert "terminal" in cycle
    assert "due deferral" in cycle
    assert "cache-only" in cycle
    assert "maintained baseline" in cycle


def test_cycle_rehydrates_after_recovery_and_skips_empty_candidate_dispatch() -> None:
    cycle = _cycle_section()

    assert "rehydrate and retry" in cycle
    assert "zero-candidate" in cycle
    assert "no analyst dispatch" in cycle
    assert "valid empty digest" in cycle


def test_cycle_stores_retained_plus_fresh_and_dispatches_one_bounded_analyst() -> None:
    cycle = _cycle_section()
    pipeline = cycle[cycle.index("### 3. Dedupe") :]

    ordered = ["dedupe", "digest.py store", "prepare-batch --as-of", "rank --manifest"]
    positions = [pipeline.index(token) for token in ordered]
    assert positions == sorted(positions)
    assert "retained pending/deferred" in cycle
    assert "at most 20" in cycle
    assert "64 KiB" in cycle
    assert "analyst archetype" in cycle
    assert "120 seconds" in cycle
    assert "one retry" in cycle
    assert "omit the explicit model" in cycle
    assert "prior valid digest" in cycle
    assert "--fresh-key" in cycle
    assert "--stubs" in cycle


def test_cycle_composes_candidate_sections_without_erasing_operational_lines() -> None:
    cycle = _cycle_section()

    for operational in ("pending_gates", "deadline", "Ready now", "Blocked", "Degraded"):
        assert operational in cycle
    for candidate in ("needs_decision", "new_this_cycle", "ranked", "digest.json"):
        assert candidate in cycle
    assert "must not replace" in cycle
    assert "back_edge.digested_stubs" in cycle
    assert "record --keys" in cycle


def test_cycle_dry_run_passes_no_write_mode_through_candidate_pipeline() -> None:
    cycle = _cycle_section()

    assert "store --prune-only --dry-run" in cycle
    assert "rank --dry-run" in cycle
    assert "no candidate, cache, digest, journal, mirror, ledger, or handoff write" in cycle


def test_intake_approval_uses_exact_preview_apply_decide_sequence() -> None:
    intake = _intake_section()
    approval = _section(intake, "### Approve from digest", "###")

    ordered = [
        "stub-to-request",
        "refiner.py preview",
        "operator confirmation",
        "refiner.py apply --expect-base-sha256",
        "digest.py decide",
    ]
    positions = [approval.index(token) for token in ordered]
    assert positions == sorted(positions)
    assert '/plan-roadmap --new <slug> "<pitch>" --draft' in approval
    assert "route: plan-roadmap" in approval
    assert "roadmap_ref: null" in approval
    assert "does not dispatch an implementer" in approval


def test_execute_requires_one_durable_roadmap_altitude_approval_before_mutation() -> None:
    approval = _section(_execute_section(), "### Approval gate", "### Prepare and launch")

    assert "direct `/autopilot-roadmap` invocation" in approval
    assert "approved `/supervise` roadmap batch" in approval
    assert "inherits that approval for every dependency-ready item" in approval
    assert "without discovery, direction, plan, or per-item approval questions" in approval
    assert "before `ExecutionAdapter.prepare`" in approval
    # ri-04: execute now opens with the same roadmap_approval gate-check
    # `cycle` runs, and that gate-check's own gate-decision record IS a
    # checkpoint write -- the one write that legitimately precedes approval,
    # since recording the approval is what it does. The bare claim "before
    # any roadmap checkpoint or execution-state mutation" would now be false;
    # the qualified claim is what the section must make instead.
    assert (
        "before any roadmap checkpoint or execution-state mutation other than "
        "its own gate-decision record"
    ) in approval
    assert "gate-check" in approval
    assert "roadmap_approval_ref" in approval


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
