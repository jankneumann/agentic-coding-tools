"""Fork guard, trigger allowlist and dispatch input (D4)."""

from __future__ import annotations

import pytest

from ._gha_expr import (
    CANONICAL_RUNS_ON,
    GUARD_STEP_NAME,
    eligibility_clause,
    evaluate,
    guard_condition,
    make_context,
    normalize,
)

ALLOWED_TRIGGERS = {"push", "pull_request", "merge_group", "workflow_dispatch"}
WORKFLOWS = ["ci.yml", "security.yml"]


def _routed(manifest, load_workflow):
    for wf_name, wf in manifest["workflows"].items():
        jobs = load_workflow(wf_name)["jobs"]
        for job_id, entry in wf["jobs"].items():
            if entry["lane"] == "routed":
                yield wf_name, job_id, jobs[job_id]


def test_every_routed_job_starts_with_the_guard(manifest, load_workflow):
    expected_if = normalize(guard_condition())
    for wf_name, job_id, job in _routed(manifest, load_workflow):
        step = job["steps"][0]
        where = f"{wf_name}:{job_id}"
        assert step.get("name") == GUARD_STEP_NAME, where
        assert normalize(str(step.get("if"))) == expected_if, where
        assert step.get("shell") == "bash", where
        assert step.get("working-directory") == "${{ github.workspace }}", where
        assert "exit 1" in step.get("run", ""), where


def test_guard_clause_is_negated_eligibility_of_canonical_expression():
    clause = eligibility_clause(normalize(CANONICAL_RUNS_ON))
    assert guard_condition() == f"runner.environment == 'self-hosted' && !{clause}"


@pytest.mark.parametrize(
    "event,fork,fires",
    [
        ("pull_request", True, True),
        ("merge_group", False, True),
        ("pull_request_target", False, True),
        ("schedule", False, True),
        ("pull_request", False, False),
        ("push", False, False),
        ("workflow_dispatch", False, False),
    ],
)
def test_guard_fires_only_for_ineligible_events_on_self_hosted(event, fork, fires):
    ctx = make_context(event, fork=fork, runner_environment="self-hosted")
    assert bool(evaluate(guard_condition(), ctx)) is fires
    # never fires on a GitHub-hosted runner
    hosted = make_context(event, fork=fork, runner_environment="github-hosted")
    assert not evaluate(guard_condition(), hosted)


@pytest.mark.parametrize("wf_name", WORKFLOWS)
def test_trigger_allowlist(load_workflow, wf_name):
    triggers = load_workflow(wf_name)["on"]
    names = set(triggers) if isinstance(triggers, dict) else {triggers}
    assert names <= ALLOWED_TRIGGERS, f"{wf_name}: forbidden trigger(s) {names - ALLOWED_TRIGGERS}"
    for forbidden in ("pull_request_target", "workflow_run", "issue_comment"):
        assert forbidden not in names


@pytest.mark.parametrize("wf_name", WORKFLOWS)
def test_dispatch_trigger_and_lane_input(load_workflow, manifest, wf_name):
    dispatch = load_workflow(wf_name)["on"]["workflow_dispatch"]
    inp = dispatch["inputs"][manifest["routing"]["dispatch_input"]]
    assert inp["type"] == "choice"
    assert inp["options"] == ["auto", "hosted", "self-hosted"]
    assert inp["default"] == "auto"
