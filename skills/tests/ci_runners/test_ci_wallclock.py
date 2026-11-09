"""scripts/ci/ci_wallclock.py: median, compare, verify_run and the CLI (D8). No network."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest
import yaml

from ._stubs import install_gh_stub, path_with, read_calls

SELF = ["self-hosted", "linux", "ARM64", "gx10"]
HOSTED = ["ubuntu-latest"]


@pytest.fixture(scope="module")
def cw(repo_root):
    spec = importlib.util.spec_from_file_location(
        "ci_wallclock", repo_root / "scripts" / "ci" / "ci_wallclock.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ci_wallclock"] = mod
    spec.loader.exec_module(mod)
    return mod


def run(rid, seconds, conclusion="success", jobs=None):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    r = {
        "id": rid,
        "conclusion": conclusion,
        "status": "completed",
        "run_started_at": start.isoformat().replace("+00:00", "Z"),
        "updated_at": (start + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z"),
    }
    if jobs is not None:
        r["jobs"] = jobs
    return r


# ----------------------------------------------------------------------------- median


def test_median_uses_success_runs_only(cw):
    runs = [run(1, 100), run(2, 300), run(3, 200), run(4, 9999, "cancelled"), run(5, 1, "failure")]
    assert cw.median_wallclock(runs) == 200
    assert cw.median_wallclock([run(1, 10), run(2, 20)]) == 15
    assert cw.median_wallclock([run(1, 10, "failure")]) is None


# ---------------------------------------------------------------------------- compare


def _sample(seconds, n=6):
    return [run(i, seconds) for i in range(n)]


def test_compare_threshold_and_sample_size(cw):
    fail = cw.compare(_sample(600), _sample(540))
    assert fail["passed"] is False and fail["candidate_median"] == 540
    assert cw.compare(_sample(600), _sample(500))["passed"] is True
    small = cw.compare(_sample(600, 4), _sample(100))
    assert small["passed"] is False and "insufficient" in small["reason"]
    small = cw.compare(_sample(600), _sample(100, 4))
    assert small["passed"] is False and "insufficient" in small["reason"]
    assert cw.compare(_sample(600), _sample(510))["passed"] is True  # boundary: <=


def _job(name, labels, conclusion="success"):
    return {"name": name, "labels": labels, "conclusion": conclusion, "status": "completed"}


def test_compare_excludes_mixed_placement_runs(cw, manifest):
    wf = {"jobs": {j: {} for j in manifest["workflows"]["security.yml"]["jobs"]}}
    mixed = [_job("secret-scan", SELF), _job("dependency-audit-coordinator", HOSTED)]
    only_self = [_job(j, SELF) for j in wf["jobs"]]
    unassigned = [_job(j, [], "skipped") for j in wf["jobs"]]
    baseline = [run(i, 600, jobs=[_job(j, HOSTED) for j in wf["jobs"]]) for i in range(10, 16)]
    cand = [run(i, 400, jobs=only_self) for i in range(20, 26)]
    result = cw.compare(
        baseline + [run(98, 1, jobs=mixed)] + [run(99, 1, jobs=unassigned)],
        cand + [run(98, 1, jobs=mixed), run(99, 1, jobs=unassigned)],
        manifest=manifest,
        workflow=wf,
        workflow_file="security.yml",
    )
    assert result["passed"] is True
    ids = {e["run_id"]: e["reason"] for e in result["excluded_runs"]}
    assert set(ids) == {98, 99}
    assert "mixed" in ids[98] and "no routed job" in ids[99]
    assert result["n_baseline"] == 6 and result["n_candidate"] == 6


# -------------------------------------------------------------------------- verify_run

WF = yaml.safe_load(
    """
jobs:
  lint:
    runs-on: x
    strategy: {matrix: {v: [a, b]}}
  build: {runs-on: x}
  pinned: {runs-on: x}
  flaky: {runs-on: x, continue-on-error: true}
  maybe: {runs-on: x, if: "github.actor == 'dependabot[bot]'"}
  named: {runs-on: x, name: Pretty Name}
"""
)
MAN = {
    "workflows": {
        "t.yml": {
            "jobs": {
                "lint": {"lane": "routed"},
                "build": {"lane": "routed"},
                "pinned": {
                    "lane": "hosted",
                    "reason_code": "container-engine",
                    "reason": "needs docker",
                },
                "flaky": {"lane": "routed"},
                "maybe": {
                    "lane": "hosted",
                    "reason_code": "privileged-token",
                    "reason": "write token",
                },
                "named": {"lane": "routed"},
            }
        }
    }
}


def good_jobs():
    return [
        _job("lint (a)", SELF),
        _job("lint (b)", SELF),
        _job("build", SELF),
        _job("pinned", HOSTED),
        _job("flaky", SELF),
        _job("maybe", [], "skipped"),
        _job("Pretty Name", SELF),
    ]


def verify(cw, jobs, **kw):
    return cw.verify_run(jobs, MAN, WF, workflow_file="t.yml", **kw)


def test_clean_run_has_no_violations(cw):
    res = verify(cw, good_jobs())
    assert res["violations"] == [] and res["warnings"] == []


def test_misrouted_and_wrongly_self_hosted_jobs(cw):
    jobs = good_jobs()
    jobs[2] = _job("build", HOSTED)  # routed job on hosted while lane is self-hosted
    jobs[3] = _job("pinned", SELF)  # hosted job on gx10
    res = verify(cw, jobs)
    assert {v["job"] for v in res["violations"]} == {"build", "pinned"}
    text = " | ".join(v["message"] for v in res["violations"])
    assert "expected the self-hosted lane" in text


def test_conditionally_skipped_job_is_not_a_violation(cw):
    jobs = good_jobs()
    assert jobs[5] == _job("maybe", [], "skipped")  # the fixture's job-level `if:` job
    assert verify(cw, jobs)["violations"] == []
    # The same skip on a job WITHOUT a job-level `if:` is a violation, so the pass above
    # rests on the `if:` exemption and not on skipped jobs being ignored wholesale.
    jobs[3] = _job("pinned", [], "skipped")
    assert [v["job"] for v in verify(cw, jobs)["violations"]] == ["pinned"]


OTHER_SELF = ["self-hosted", "linux", "X64", "someone-elses-pool"]


def test_other_self_hosted_runner_is_never_a_valid_placement(cw):
    assert cw.job_lane(_job("x", OTHER_SELF)) == cw.OTHER_SELF_HOSTED
    jobs = good_jobs()
    jobs[3] = _job("pinned", OTHER_SELF)  # hosted-pinned job on a non-GX10 self-hosted runner
    res = verify(cw, jobs)
    assert [v["job"] for v in res["violations"]] == ["pinned"]
    hosted = [
        _job(j["name"], HOSTED if j["conclusion"] != "skipped" else [], j["conclusion"])
        for j in good_jobs()
    ]
    hosted[2] = _job("build", OTHER_SELF)  # rollback check: routed job not on GitHub-hosted
    res = verify(cw, hosted, expected_lane="hosted")
    assert [v["job"] for v in res["violations"]] == ["build"]


@pytest.mark.parametrize("expected_lane", ["self-hosted", "hosted"])
@pytest.mark.parametrize("index,name", [(2, "build"), (3, "pinned")])
def test_job_that_ran_without_labels_is_a_placement_violation(cw, expected_lane, index, name):
    jobs = good_jobs() if expected_lane == "self-hosted" else [
        _job(j["name"], HOSTED if j["conclusion"] != "skipped" else [], j["conclusion"])
        for j in good_jobs()
    ]
    jobs[index] = _job(name, [])  # concluded success, but no placement evidence
    res = verify(cw, jobs, expected_lane=expected_lane)
    assert [v["job"] for v in res["violations"]] == [name]
    assert "unproven" in res["violations"][0]["message"]


def test_compare_reports_runs_on_another_self_hosted_pool(cw, manifest):
    wf = {"jobs": {j: {} for j in manifest["workflows"]["security.yml"]["jobs"]}}
    other = ["self-hosted", "linux", "X64", "someone-elses-pool"]
    baseline = [run(i, 600, jobs=[_job(j, HOSTED) for j in wf["jobs"]]) for i in range(10, 16)]
    cand = [run(i, 400, jobs=[_job(j, SELF) for j in wf["jobs"]]) for i in range(20, 26)]
    stray = run(97, 1, jobs=[_job(j, other) for j in wf["jobs"]])
    runs = baseline + cand + [stray]
    result = cw.compare(runs, runs, manifest=manifest, workflow=wf, workflow_file="security.yml")
    reasons = {e["run_id"]: e["reason"] for e in result["excluded_runs"]}
    assert "non-GX10 self-hosted" in reasons[97]
    assert result["n_baseline"] == 6 and result["n_candidate"] == 6


def test_unconditional_skipped_job_is_a_violation(cw):
    jobs = good_jobs()
    jobs[2] = _job("build", [], "skipped")
    res = verify(cw, jobs)
    assert [v["job"] for v in res["violations"]] == ["build"]


def test_failure_is_a_violation_but_continue_on_error_is_a_warning(cw):
    jobs = good_jobs()
    jobs[2] = _job("build", SELF, "failure")
    jobs[4] = _job("flaky", SELF, "failure")
    res = verify(cw, jobs)
    assert [v["job"] for v in res["violations"]] == ["build"]
    assert [w["job"] for w in res["warnings"]] == ["flaky"]
    jobs[2] = _job("build", SELF)
    res = verify(cw, jobs)
    assert res["violations"] == [] and len(res["warnings"]) == 1


def test_missing_job_is_a_violation(cw):
    jobs = [j for j in good_jobs() if j["name"] != "build"]
    res = verify(cw, jobs)
    assert [v["job"] for v in res["violations"]] == ["build"]


def test_matrix_expansions_are_checked_individually(cw):
    jobs = good_jobs()
    jobs[1] = _job("lint (b)", HOSTED)
    res = verify(cw, jobs)
    assert [v["job"] for v in res["violations"]] == ["lint (b)"]


def test_unknown_job_is_reported(cw):
    res = verify(cw, [*good_jobs(), _job("renamed-job", SELF)])
    assert [v["job"] for v in res["violations"]] == ["renamed-job"]
    assert "unknown" in res["violations"][0]["message"]


def test_literal_name_correlation(cw):
    jobs = [j for j in good_jobs() if j["name"] != "Pretty Name"] + [_job("named", SELF)]
    res = verify(cw, jobs)
    # the literal display name is "Pretty Name": job id "named" is not what the API reports
    assert [v["job"] for v in res["violations"]] == ["named", "named"]
    assert any("unknown" in v["message"] for v in res["violations"])
    assert any("missing" in v["message"] for v in res["violations"])


def test_rollback_check_expects_hosted_placement(cw):
    jobs = good_jobs()
    res = verify(cw, jobs, expected_lane="hosted")
    flagged = {v["job"] for v in res["violations"]}
    assert flagged == {"lint (a)", "lint (b)", "build", "flaky", "Pretty Name"}
    all_hosted = [
        _job(j["name"], HOSTED if j["conclusion"] != "skipped" else [], j["conclusion"])
        for j in good_jobs()
    ]
    assert verify(cw, all_hosted, expected_lane="hosted")["violations"] == []


def test_real_manifest_dependency_update_remediation_skipped_is_clean(cw, manifest, load_workflow):
    """A realistic ci.yml run: the Dependabot-only job is skipped with no runner."""
    wf = load_workflow("ci.yml")
    jobs = []
    for job_id, entry in manifest["workflows"]["ci.yml"]["jobs"].items():
        if job_id == "dependency-update-remediation":
            jobs.append(_job(job_id, [], "skipped"))
        else:
            jobs.append(_job(job_id, SELF if entry["lane"] == "routed" else HOSTED))
    res = cw.verify_run(jobs, manifest, wf, workflow_file="ci.yml")
    assert res["violations"] == [], res["violations"]


# ------------------------------------------------------------------------------ CLI

CI_TEXT = yaml.safe_dump(WF)


def _cli(repo_root, tmp_path, config, args):
    bin_dir = tmp_path / "bin"
    env_add, log = install_gh_stub(bin_dir, config, tmp_path)
    env = {"PATH": path_with(bin_dir), "HOME": str(tmp_path), **env_add}
    res = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "ci" / "ci_wallclock.py"), *args],
        env=env,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    return res, read_calls(log)


def _write_manifest(tmp_path):
    p = tmp_path / "manifest.yaml"
    p.write_text(yaml.safe_dump({"schema_version": 1, **MAN}))
    return str(p)


def test_cli_median_filters_and_stops_at_limit(repo_root, tmp_path):
    cfg = {"total_runs": 250}
    res, calls = _cli(
        repo_root,
        tmp_path,
        cfg,
        [
            "median",
            "--workflow",
            "t.yml",
            "--event",
            "workflow_dispatch",
            "--head-sha",
            "abc123",
            "--since",
            "2026-01-01",
            "--until",
            "2026-02-01",
            "--limit",
            "10",
        ],
    )
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout)["n"] == 10
    assert len(calls) == 1, "must stop after --limit runs are collected (no fetch-all)"
    argv = " ".join(calls[0]["argv"])
    assert "-X GET" in argv or "--method GET" in argv
    for needle in (
        "event=workflow_dispatch",
        "head_sha=abc123",
        "/actions/workflows/t.yml/runs",
        "per_page=10",
        "created=2026-01-01..2026-02-01",
    ):
        assert needle in argv, needle
    assert not any(m in argv for m in ("POST", "PUT", "DELETE", "PATCH"))


def test_cli_median_pages_until_limit(repo_root, tmp_path):
    res, calls = _cli(
        repo_root,
        tmp_path,
        {"total_runs": 250},
        ["median", "--workflow", "t.yml", "--limit", "150"],
    )
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout)["n"] == 150
    assert len(calls) == 2
    # per_page must stay fixed across pages: GitHub serves page N at offset (N-1)*per_page.
    for page, call in enumerate(calls, start=1):
        argv = " ".join(call["argv"])
        assert "per_page=100" in argv and f"page={page}" in argv, argv


def test_fetch_runs_returns_distinct_contiguous_runs(cw, monkeypatch):
    from urllib.parse import parse_qs, urlparse

    def fake_gh_get(path, raw=False):
        q = {k: v[0] for k, v in parse_qs(urlparse(path).query).items()}
        per, page = int(q["per_page"]), int(q["page"])
        ids = list(range(1, 251))[(page - 1) * per : page * per]
        return {"workflow_runs": [{"id": i} for i in ids]}

    monkeypatch.setattr(cw, "gh_get", fake_gh_get)
    args = cw.build_parser().parse_args(["median", "--workflow", "t.yml", "--limit", "150"])
    assert [r["id"] for r in cw.fetch_runs(args)] == list(range(1, 151))


@pytest.mark.parametrize(
    "target,content",
    [
        ("workflow", "- just\n- a list\n"),
        ("manifest", "- not: a mapping\n"),
        ("manifest", "workflows: {t.yml: {jobs: {build: no-lane}}}\n"),
    ],
)
def test_cli_rejects_valid_yaml_of_the_wrong_shape(repo_root, tmp_path, target, content):
    bad = tmp_path / "bad.yaml"
    bad.write_text(content)
    wf_file = tmp_path / "wf.yml"
    wf_file.write_text(CI_TEXT)
    args = ["verify-run", "7", "--workflow", "t.yml"]
    if target == "workflow":
        args += ["--manifest", _write_manifest(tmp_path), "--workflow-file", str(bad)]
    else:
        args += ["--manifest", str(bad), "--workflow-file", str(wf_file)]
    res, _ = _cli(repo_root, tmp_path, {"run": {"id": 7, "head_sha": "s"}, "default_jobs": []}, args)
    assert res.returncode == 2, res.stdout + res.stderr
    assert res.stderr.startswith("error: ValueError") and "Traceback" not in res.stderr


def test_cli_reports_bad_input_files_without_traceback(repo_root, tmp_path):
    res, _ = _cli(
        repo_root,
        tmp_path,
        {"run": {"id": 7, "head_sha": "s"}, "default_jobs": []},
        ["verify-run", "7", "--workflow", "t.yml", "--manifest", str(tmp_path / "missing.yaml")],
    )
    assert res.returncode == 2
    assert res.stderr.startswith("error: ") and "Traceback" not in res.stderr


def test_cli_verify_run_fetches_definition_at_head_sha(repo_root, tmp_path):
    cfg = {
        "run": {"id": 7, "head_sha": "deadbeef", "event": "workflow_dispatch"},
        "default_jobs": good_jobs(),
        "workflow_text": CI_TEXT,
    }
    res, calls = _cli(
        repo_root,
        tmp_path,
        cfg,
        ["verify-run", "7", "--workflow", "t.yml", "--manifest", _write_manifest(tmp_path)],
    )
    assert res.returncode == 0, res.stdout + res.stderr
    joined = [" ".join(c["argv"]) for c in calls]
    assert any("/contents/.github/workflows/t.yml" in j and "ref=deadbeef" in j for j in joined)
    assert all("-X GET" in j or "--method GET" in j for j in joined)


def test_cli_verify_run_exit_codes_and_flags(repo_root, tmp_path):
    bad = good_jobs()
    bad[2] = _job("build", HOSTED)
    cfg = {"run": {"id": 7, "head_sha": "s"}, "default_jobs": bad, "workflow_text": CI_TEXT}
    wf_file = tmp_path / "wf.yml"
    wf_file.write_text(CI_TEXT)
    base = [
        "verify-run",
        "7",
        "--workflow",
        "t.yml",
        "--manifest",
        _write_manifest(tmp_path),
        "--workflow-file",
        str(wf_file),
    ]
    res, calls = _cli(repo_root, tmp_path, cfg, base)
    assert res.returncode == 1 and "build" in res.stdout
    assert not any("/contents/" in " ".join(c["argv"]) for c in calls), "local file wins"
    res, _ = _cli(repo_root, tmp_path, cfg, [*base, "--expect-lane", "hosted"])
    assert res.returncode == 1  # the other routed jobs ran on gx10


def test_cli_verify_run_warning_keeps_exit_zero(repo_root, tmp_path):
    jobs = good_jobs()
    jobs[4] = _job("flaky", SELF, "failure")
    cfg = {"run": {"id": 7, "head_sha": "s"}, "default_jobs": jobs, "workflow_text": CI_TEXT}
    res, _ = _cli(
        repo_root,
        tmp_path,
        cfg,
        ["verify-run", "7", "--workflow", "t.yml", "--manifest", _write_manifest(tmp_path)],
    )
    assert res.returncode == 0
    assert "warning" in res.stdout.lower() and "flaky" in res.stdout


def test_cli_compare_parses_all_arguments(repo_root, tmp_path):
    cfg = {"total_runs": 12, "default_jobs": [_job("build", HOSTED)]}
    wf_file = tmp_path / "wf.yml"
    wf_file.write_text(CI_TEXT)
    res, calls = _cli(
        repo_root,
        tmp_path,
        cfg,
        [
            "compare",
            "--baseline-lane",
            "hosted",
            "--candidate-lane",
            "self-hosted",
            "--workflow",
            "t.yml",
            "--event",
            "workflow_dispatch",
            "--head-sha",
            "abc",
            "--since",
            "2026-01-01",
            "--until",
            "2026-03-01",
            "--limit",
            "12",
            "--manifest",
            _write_manifest(tmp_path),
            "--workflow-file",
            str(wf_file),
        ],
    )
    out = json.loads(res.stdout)
    # Every stubbed run has a single hosted `build` job, so all 12 classify as hosted and
    # land in the baseline; the self-hosted candidate sample is empty and compare fails on
    # sample size, which is what this test needs: the CLI wiring, not a passing compare.
    assert res.returncode == 1
    assert out["passed"] is False
    assert "insufficient" in out["reason"] and out["n_candidate"] == 0
    assert len(calls) <= 1 + 12, "one listing plus at most one jobs GET per run"
    assert all("-X GET" in " ".join(c["argv"]) for c in calls)


def test_cli_issues_only_get_requests(repo_root):
    import re

    text = (repo_root / "scripts" / "ci" / "ci_wallclock.py").read_text()
    methods = re.findall(r'"-X",\s*"(\w+)"', text)
    assert methods and set(methods) == {"GET"}
    for banned in ("systemctl", "loginctl", "podman"):
        assert banned not in text
