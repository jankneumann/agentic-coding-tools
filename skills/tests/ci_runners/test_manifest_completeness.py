"""The manifest classifies exactly the jobs the workflows declare (D1, D2, D8)."""

from __future__ import annotations

import pytest

from ._gha_expr import normalize  # noqa: F401  (package import check)


def _workflows(manifest):
    return sorted(manifest["workflows"])


def test_workflow_set_is_ci_and_security(manifest):
    assert _workflows(manifest) == ["ci.yml", "security.yml"]


def test_job_sets_match_manifest(manifest, load_workflow):
    for wf_name, wf in manifest["workflows"].items():
        declared = set(load_workflow(wf_name)["jobs"])
        classified = set(wf["jobs"])
        assert not (declared - classified), (
            f"{wf_name}: unclassified job(s) {sorted(declared - classified)}"
        )
        assert not (classified - declared), (
            f"{wf_name}: stale manifest entr(ies) {sorted(classified - declared)}"
        )


def test_job_counts(manifest):
    assert len(manifest["workflows"]["ci.yml"]["jobs"]) == 25
    assert len(manifest["workflows"]["security.yml"]["jobs"]) == 3


def test_hosted_jobs_use_literal_hosted_label(manifest, load_workflow):
    hosted_label = manifest["routing"]["hosted_label"]
    n = 0
    for wf_name, wf in manifest["workflows"].items():
        jobs = load_workflow(wf_name)["jobs"]
        for job_id, entry in wf["jobs"].items():
            if entry["lane"] == "hosted":
                n += 1
                assert jobs[job_id]["runs-on"] == hosted_label, f"{wf_name}:{job_id}"
    assert n == 5


def test_display_names_are_unique_and_literal(manifest, load_workflow):
    for wf_name in manifest["workflows"]:
        seen: dict[str, str] = {}
        for job_id, job in load_workflow(wf_name)["jobs"].items():
            name = job.get("name", job_id)
            assert "${{" not in str(name), f"{wf_name}:{job_id} has an expression in name:"
            assert name not in seen, f"{wf_name}: {job_id} and {seen[name]} share name {name!r}"
            seen[name] = job_id


@pytest.mark.parametrize("missing", ["ci.yml", "security.yml"])
def test_unclassified_job_is_reported(manifest, load_workflow, missing):
    del manifest["workflows"][missing]["jobs"][next(iter(manifest["workflows"][missing]["jobs"]))]
    declared = set(load_workflow(missing)["jobs"])
    assert declared - set(manifest["workflows"][missing]["jobs"])
