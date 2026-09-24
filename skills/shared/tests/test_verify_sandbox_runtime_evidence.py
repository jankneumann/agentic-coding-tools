"""Contract tests for authoritative sandbox runtime workflow evidence."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "verify_sandbox_runtime_evidence.py"
SPEC = importlib.util.spec_from_file_location("verify_sandbox_runtime_evidence", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


def _write_artifact(root: Path, platform: str, *, run_id: int = 42, job_id: int = 101) -> None:
    artifact = root / f"sandbox-runtime-{platform}"
    artifact.mkdir(parents=True)
    probe = {
        "schema_version": 1,
        "platform": platform,
        "executable": "python3",
        "executable_version": "Python 3.12.12",
        "event_id": f"runtime-{platform}",
        "sandbox_applied": True,
        "runtime_version": "0.0.77",
        "cleanup_status": "succeeded",
        "routing_context_digest": "1" * 64,
        "workspace_content_digest": None,
        "endpoint_digest": "4" * 64,
        "policy_digest": "2" * 64,
        "settings_digest": "3" * 64,
        "controlled_network": {
            "allowed": "passed",
            "denied": "passed",
            "private": "passed",
            "dns_resolved_private": "passed",
        },
        "controlled_filesystem": {
            "write_inside": "passed",
            "write_escape": "passed",
            "review_write": "passed",
            "credential_read": "passed",
        },
    }
    payload = json.dumps(probe, sort_keys=True, separators=(",", ":")).encode()
    (artifact / "probe.json").write_bytes(payload)
    evidence = {
        "schema_version": 1,
        "workflow_path": ".github/workflows/sandbox-runtime.yml",
        "run_id": run_id,
        "job_id": job_id,
        "head_sha": "a" * 40,
        "platform": platform,
        "conclusion": "success",
        "artifact_name": f"sandbox-runtime-{platform}",
        "artifact_digest": hashlib.sha256(payload).hexdigest(),
    }
    (artifact / "evidence.json").write_text(json.dumps(evidence))


def _run_metadata() -> dict:
    return {
        "databaseId": 42,
        "headSha": "a" * 40,
        "conclusion": "success",
        "event": "push",
        "workflowPath": ".github/workflows/sandbox-runtime.yml",
        "jobs": [
            {"databaseId": 101, "name": "sandbox-runtime (linux)", "conclusion": "success"},
            {"databaseId": 102, "name": "sandbox-runtime (darwin)", "conclusion": "success"},
        ],
    }


def test_verifies_exact_run_job_platform_and_artifact_identity(tmp_path: Path) -> None:
    _write_artifact(tmp_path, "linux", job_id=101)
    _write_artifact(tmp_path, "darwin", job_id=102)

    result = verifier.verify_downloaded_evidence(
        run=_run_metadata(), artifacts_root=tmp_path,
        workflow_path=".github/workflows/sandbox-runtime.yml",
        head_sha="a" * 40, required_platforms={"linux", "darwin"},
    )

    assert result == {"run_id": 42, "head_sha": "a" * 40, "platforms": ["darwin", "linux"]}


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("headSha", "b" * 40, "head SHA"),
        ("conclusion", "failure", "conclusion"),
        ("event", "pull_request", "push-triggered"),
        ("workflowPath", ".github/workflows/other.yml", "workflow path"),
    ],
)
def test_rejects_non_authoritative_run_identity(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    _write_artifact(tmp_path, "linux")
    run = _run_metadata()
    run[field] = value

    with pytest.raises(verifier.EvidenceError, match=message):
        verifier.verify_downloaded_evidence(
            run=run, artifacts_root=tmp_path,
            workflow_path=".github/workflows/sandbox-runtime.yml",
            head_sha="a" * 40, required_platforms={"linux"},
        )


def test_rejects_missing_platform_and_mismatched_job(tmp_path: Path) -> None:
    _write_artifact(tmp_path, "linux", job_id=999)
    with pytest.raises(verifier.EvidenceError, match="job identity"):
        verifier.verify_downloaded_evidence(
            run=_run_metadata(), artifacts_root=tmp_path,
            workflow_path=".github/workflows/sandbox-runtime.yml",
            head_sha="a" * 40, required_platforms={"linux"},
        )

    (tmp_path / "sandbox-runtime-linux").rename(tmp_path / "saved")
    with pytest.raises(verifier.EvidenceError, match="missing platform"):
        verifier.verify_downloaded_evidence(
            run=_run_metadata(), artifacts_root=tmp_path,
            workflow_path=".github/workflows/sandbox-runtime.yml",
            head_sha="a" * 40, required_platforms={"linux", "darwin"},
        )


def test_rejects_non_exact_job_name(tmp_path: Path) -> None:
    _write_artifact(tmp_path, "linux")
    run = _run_metadata()
    run["jobs"][0]["name"] = "sandbox-runtime (linux-extra)"

    with pytest.raises(verifier.EvidenceError, match="job identity"):
        verifier.verify_downloaded_evidence(
            run=run, artifacts_root=tmp_path,
            workflow_path=".github/workflows/sandbox-runtime.yml",
            head_sha="a" * 40, required_platforms={"linux"},
        )


def test_rejects_tampered_payload_and_false_probe_claim(tmp_path: Path) -> None:
    _write_artifact(tmp_path, "linux")
    payload = tmp_path / "sandbox-runtime-linux" / "probe.json"
    probe = json.loads(payload.read_text())
    probe["sandbox_applied"] = False
    payload.write_text(json.dumps(probe, sort_keys=True, separators=(",", ":")))

    with pytest.raises(verifier.EvidenceError, match="artifact digest"):
        verifier.verify_downloaded_evidence(
            run=_run_metadata(), artifacts_root=tmp_path,
            workflow_path=".github/workflows/sandbox-runtime.yml",
            head_sha="a" * 40, required_platforms={"linux"},
        )

    evidence_path = tmp_path / "sandbox-runtime-linux" / "evidence.json"
    evidence = json.loads(evidence_path.read_text())
    evidence["artifact_digest"] = hashlib.sha256(payload.read_bytes()).hexdigest()
    evidence_path.write_text(json.dumps(evidence))
    with pytest.raises(verifier.EvidenceError, match="sandbox_applied"):
        verifier.verify_downloaded_evidence(
            run=_run_metadata(), artifacts_root=tmp_path,
            workflow_path=".github/workflows/sandbox-runtime.yml",
            head_sha="a" * 40, required_platforms={"linux"},
        )


def test_rejects_incomplete_runtime_audit_identity(tmp_path: Path) -> None:
    _write_artifact(tmp_path, "linux")
    payload = tmp_path / "sandbox-runtime-linux" / "probe.json"
    probe = json.loads(payload.read_text())
    probe["endpoint_digest"] = "not-a-digest"
    payload.write_text(json.dumps(probe, sort_keys=True, separators=(",", ":")))
    evidence_path = tmp_path / "sandbox-runtime-linux" / "evidence.json"
    evidence = json.loads(evidence_path.read_text())
    evidence["artifact_digest"] = hashlib.sha256(payload.read_bytes()).hexdigest()
    evidence_path.write_text(json.dumps(evidence))

    with pytest.raises(verifier.EvidenceError, match="endpoint_digest"):
        verifier.verify_downloaded_evidence(
            run=_run_metadata(), artifacts_root=tmp_path,
            workflow_path=".github/workflows/sandbox-runtime.yml",
            head_sha="a" * 40, required_platforms={"linux"},
        )


@pytest.mark.parametrize("mutation", ["missing", "tampered"])
def test_rejects_missing_or_tampered_filesystem_evidence(
    tmp_path: Path,
    mutation: str,
) -> None:
    _write_artifact(tmp_path, "linux")
    artifact = tmp_path / "sandbox-runtime-linux"
    payload = artifact / "probe.json"
    probe = json.loads(payload.read_text())
    if mutation == "missing":
        del probe["controlled_filesystem"]
    else:
        probe["controlled_filesystem"]["credential_read"] = "failed"
    payload.write_text(json.dumps(probe, sort_keys=True, separators=(",", ":")))
    evidence_path = artifact / "evidence.json"
    evidence = json.loads(evidence_path.read_text())
    evidence["artifact_digest"] = hashlib.sha256(payload.read_bytes()).hexdigest()
    evidence_path.write_text(json.dumps(evidence))

    with pytest.raises(verifier.EvidenceError, match="controlled filesystem"):
        verifier.verify_downloaded_evidence(
            run=_run_metadata(), artifacts_root=tmp_path,
            workflow_path=".github/workflows/sandbox-runtime.yml",
            head_sha="a" * 40, required_platforms={"linux"},
        )

def test_select_run_requires_exact_successful_head() -> None:
    runs = [
        {"databaseId": 40, "headSha": "b" * 40, "conclusion": "success", "event": "push"},
        {"databaseId": 41, "headSha": "a" * 40, "conclusion": "failure", "event": "push"},
        {"databaseId": 42, "headSha": "a" * 40, "conclusion": "success", "event": "push"},
        {
            "databaseId": 43,
            "headSha": "a" * 40,
            "conclusion": "success",
            "event": "pull_request",
        },
    ]
    assert verifier.select_authoritative_run(runs, "a" * 40)["databaseId"] == 42
    with pytest.raises(verifier.EvidenceError, match="successful workflow run"):
        verifier.select_authoritative_run(runs, "c" * 40)
