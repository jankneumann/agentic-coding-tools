"""The canonical runs-on expression: evaluation table, drift and manifest ties (D3)."""

from __future__ import annotations

import json
import re

import pytest

from ._gha_expr import CANONICAL_RUNS_ON, evaluate, make_context, normalize

HOSTED = "ubuntu-latest"
LABELS = ["self-hosted", "linux", "ARM64", "gx10"]

# (event, fork, dispatch_input, variable, expected) -- the D3 evaluation table.
TABLE = [
    ("pull_request", True, None, "self-hosted", HOSTED),
    ("pull_request", True, None, None, HOSTED),
    ("pull_request", False, None, None, HOSTED),
    ("pull_request", False, None, "hosted", HOSTED),
    ("pull_request", False, None, "other", HOSTED),
    ("pull_request", False, None, "self-hosted", LABELS),
    ("push", False, None, "self-hosted", LABELS),
    ("push", False, None, None, HOSTED),
    ("merge_group", False, None, "self-hosted", HOSTED),
    ("merge_group", False, None, None, HOSTED),
    ("schedule", False, None, "self-hosted", HOSTED),
    ("workflow_dispatch", False, "self-hosted", None, LABELS),
    ("workflow_dispatch", False, "self-hosted", "hosted", LABELS),
    ("workflow_dispatch", False, "hosted", "self-hosted", HOSTED),
    ("workflow_dispatch", False, "auto", "self-hosted", LABELS),
    ("workflow_dispatch", False, "auto", None, HOSTED),
    ("workflow_dispatch", False, "auto", "hosted", HOSTED),
]


@pytest.mark.parametrize("event,fork,dispatch,var,expected", TABLE)
def test_evaluation_table(event, fork, dispatch, var, expected):
    ctx = make_context(event, fork=fork, dispatch_input=dispatch, variable=var)
    assert evaluate(CANONICAL_RUNS_ON, ctx) == expected


def test_evaluator_value_semantics():
    ctx = make_context("push")
    assert evaluate("${{ 'a' && 'b' || 'c' }}", ctx) == "b"
    assert evaluate("${{ '' && 'b' || 'c' }}", ctx) == "c"
    assert evaluate("${{ 'x' == 'X' }}", ctx) is True
    assert evaluate("${{ github.event_name != 'push' }}", ctx) is False
    assert evaluate('${{ fromJSON(\'["a","b"]\') }}', ctx) == ["a", "b"]
    assert evaluate("${{ !(github.missing.path) }}", ctx) is True


def _routed_jobs(manifest, load_workflow):
    for wf_name, wf in manifest["workflows"].items():
        jobs = load_workflow(wf_name)["jobs"]
        for job_id, entry in wf["jobs"].items():
            if entry["lane"] == "routed":
                yield wf_name, job_id, jobs[job_id]


def test_every_routed_job_uses_canonical_expression(manifest, load_workflow):
    expected = normalize(CANONICAL_RUNS_ON)
    seen = 0
    for wf_name, job_id, job in _routed_jobs(manifest, load_workflow):
        seen += 1
        assert normalize(str(job.get("runs-on"))) == expected, (
            f"{wf_name}:{job_id} drifted from the canonical runs-on expression"
        )
    assert seen == 23


def check_expression_ties(expr: str, routing: dict) -> list[str]:
    """Errors if the expression's literals disagree with the manifest routing block."""
    errors: list[str] = []
    m = re.search(r"fromJSON\('(\[.*?\])'\)", expr)
    labels = json.loads(m.group(1)) if m else None
    if labels != routing["self_hosted_labels"]:
        errors.append(f"fromJSON labels {labels} != self_hosted_labels")
    if f"vars.{routing['repository_variable']}" not in expr:
        errors.append("vars.<name> does not match repository_variable")
    inputs = set(re.findall(r"inputs\.([A-Za-z_]\w*)", expr))
    if inputs != {routing["dispatch_input"]}:
        errors.append(f"inputs references {inputs} != dispatch_input")
    if f"'{routing['hosted_label']}' }}}}" not in expr:
        errors.append("hosted fallback label does not match hosted_label")
    return errors


def test_expression_is_tied_to_manifest_routing(manifest):
    assert check_expression_ties(CANONICAL_RUNS_ON, manifest["routing"]) == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("self_hosted_labels", ["self-hosted", "linux", "ARM64", "gx11"]),
        ("repository_variable", "OTHER_LANE"),
        ("dispatch_input", "other_input"),
        ("hosted_label", "ubuntu-22.04"),
    ],
)
def test_mutating_any_routing_field_breaks_the_tie(manifest, field, value):
    routing = {**manifest["routing"], field: value}
    assert check_expression_ties(CANONICAL_RUNS_ON, routing), field


def test_routed_job_drift_is_detected(manifest, load_workflow):
    drifted = CANONICAL_RUNS_ON.replace("'push'", "'pull_request_target'", 1)
    assert normalize(drifted) != normalize(CANONICAL_RUNS_ON)
