#!/usr/bin/env python3
"""Verify exact-head sandbox-runtime evidence from an authoritative GitHub run."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


_SHA = re.compile(r"^[a-f0-9]{40}$")
_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_PLATFORMS = {"linux", "darwin"}


class EvidenceError(ValueError):
    """Evidence cannot authorize runtime rollout."""


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be a JSON object")
    return value


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        return _object(json.loads(path.read_text()), label)
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot read {label}: {path}") from exc


def select_authoritative_run(
    runs: Iterable[Mapping[str, Any]], head_sha: str
) -> dict[str, Any]:
    """Choose the newest successful run whose source is the exact requested SHA."""
    matches = [
        dict(run)
        for run in runs
        if run.get("headSha") == head_sha
        and run.get("conclusion") == "success"
        and isinstance(run.get("databaseId"), int)
        and not isinstance(run.get("databaseId"), bool)
    ]
    if not matches:
        raise EvidenceError(f"no successful workflow run for exact head SHA {head_sha}")
    return max(matches, key=lambda run: int(run["databaseId"]))


def _verify_probe(probe: Mapping[str, Any], platform: str) -> None:
    if probe.get("schema_version") != 1:
        raise EvidenceError(f"{platform}: unsupported probe schema")
    if probe.get("platform") != platform:
        raise EvidenceError(f"{platform}: probe platform mismatch")
    for field in ("executable", "executable_version", "event_id"):
        if not isinstance(probe.get(field), str) or not probe[field]:
            raise EvidenceError(f"{platform}: invalid {field}")
    if probe.get("sandbox_applied") is not True:
        raise EvidenceError(f"{platform}: sandbox_applied must be true")
    if probe.get("runtime_version") != "0.0.77":
        raise EvidenceError(f"{platform}: unexpected runtime_version")
    if probe.get("cleanup_status") != "succeeded":
        raise EvidenceError(f"{platform}: cleanup_status must be succeeded")
    for field in (
        "routing_context_digest",
        "endpoint_digest",
        "policy_digest",
        "settings_digest",
    ):
        value = probe.get(field)
        if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
            raise EvidenceError(f"{platform}: invalid {field}")
    workspace_digest = probe.get("workspace_content_digest")
    if workspace_digest is not None and (
        not isinstance(workspace_digest, str)
        or _DIGEST.fullmatch(workspace_digest) is None
    ):
        raise EvidenceError(f"{platform}: invalid workspace_content_digest")
    network = _object(probe.get("controlled_network"), "controlled_network")
    required = {"allowed", "denied", "private", "dns_resolved_private"}
    if set(network) != required or any(network[key] != "passed" for key in required):
        raise EvidenceError(f"{platform}: controlled network probe did not pass")
    filesystem = _object(probe.get("controlled_filesystem"), "controlled filesystem")
    required_filesystem = {
        "write_inside",
        "write_escape",
        "review_write",
        "credential_read",
    }
    if set(filesystem) != required_filesystem or any(
        filesystem[key] != "passed" for key in required_filesystem
    ):
        raise EvidenceError(f"{platform}: controlled filesystem probe did not pass")


def verify_downloaded_evidence(
    *,
    run: Mapping[str, Any],
    artifacts_root: Path,
    workflow_path: str,
    head_sha: str,
    required_platforms: set[str],
) -> dict[str, Any]:
    """Verify downloaded artifacts against authoritative run and job metadata."""
    if run.get("headSha") != head_sha:
        raise EvidenceError("run head SHA does not match requested exact head SHA")
    if run.get("conclusion") != "success":
        raise EvidenceError("run conclusion is not success")
    if run.get("workflowPath") != workflow_path:
        raise EvidenceError("run workflow path does not match requested workflow path")
    run_id = run.get("databaseId")
    if not isinstance(run_id, int) or isinstance(run_id, bool):
        raise EvidenceError("run id is invalid")
    unknown = required_platforms - _PLATFORMS
    if unknown:
        raise EvidenceError(f"unsupported required platform: {sorted(unknown)[0]}")
    jobs = run.get("jobs")
    if not isinstance(jobs, list):
        raise EvidenceError("run jobs metadata is missing")
    jobs_by_id = {
        job.get("databaseId"): job
        for job in jobs
        if isinstance(job, dict)
        and isinstance(job.get("databaseId"), int)
        and not isinstance(job.get("databaseId"), bool)
    }
    verified: list[str] = []
    for platform in sorted(required_platforms):
        artifact_name = f"sandbox-runtime-{platform}"
        artifact_dir = artifacts_root / artifact_name
        if not artifact_dir.is_dir():
            raise EvidenceError(f"missing platform artifact: {platform}")
        evidence = _load_object(artifact_dir / "evidence.json", "evidence")
        probe_path = artifact_dir / "probe.json"
        probe_bytes = probe_path.read_bytes() if probe_path.is_file() else b""
        if evidence.get("artifact_digest") != hashlib.sha256(probe_bytes).hexdigest():
            raise EvidenceError(f"{platform}: artifact digest mismatch")
        expected = {
            "schema_version": 1,
            "workflow_path": workflow_path,
            "run_id": run_id,
            "head_sha": head_sha,
            "platform": platform,
            "conclusion": "success",
            "artifact_name": artifact_name,
        }
        for field, value in expected.items():
            if evidence.get(field) != value:
                raise EvidenceError(f"{platform}: evidence {field} mismatch")
        job_id = evidence.get("job_id")
        job = jobs_by_id.get(job_id)
        if (
            job is None
            or job.get("conclusion") != "success"
            or job.get("name") != f"sandbox-runtime ({platform})"
        ):
            raise EvidenceError(f"{platform}: job identity mismatch")
        _verify_probe(_load_object(probe_path, "probe"), platform)
        verified.append(platform)
    return {"run_id": run_id, "head_sha": head_sha, "platforms": verified}


def _run_gh(args: Sequence[str]) -> str:
    try:
        completed = subprocess.run(
            ["gh", *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise EvidenceError(f"GitHub CLI command failed: gh {' '.join(args[:3])}") from exc
    return completed.stdout


def _repo_name(repo: str | None) -> str:
    if repo:
        return repo
    data = _object(
        json.loads(_run_gh(["repo", "view", "--json", "nameWithOwner"])),
        "repository metadata",
    )
    value = data.get("nameWithOwner")
    if not isinstance(value, str) or "/" not in value:
        raise EvidenceError("GitHub repository identity is unavailable")
    return value


def discover_and_verify(
    *,
    workflow_path: str,
    head_sha: str,
    required_platforms: set[str],
    repo: str | None = None,
) -> dict[str, Any]:
    """Discover the exact run, download its artifacts, and verify all identities."""
    if _SHA.fullmatch(head_sha) is None:
        raise EvidenceError("head SHA must be 40 lowercase hexadecimal characters")
    path = Path(workflow_path)
    if (
        path.is_absolute()
        or ".." in path.parts
        or path.parts[:2] != (".github", "workflows")
        or path.suffix not in {".yml", ".yaml"}
    ):
        raise EvidenceError("workflow path must name a repository Actions workflow")
    repo_name = _repo_name(repo)
    repo_args = ["--repo", repo_name]
    listed = json.loads(
        _run_gh([
            "run", "list", "--workflow", workflow_path, "--commit", head_sha,
            "--status", "success", "--limit", "20", "--json",
            "databaseId,headSha,conclusion", *repo_args,
        ])
    )
    if not isinstance(listed, list):
        raise EvidenceError("GitHub run list response is invalid")
    selected = select_authoritative_run(listed, head_sha)
    run_id = int(selected["databaseId"])
    viewed = _object(
        json.loads(_run_gh([
            "run", "view", str(run_id), "--json",
            "databaseId,headSha,conclusion,jobs", *repo_args,
        ])),
        "workflow run metadata",
    )
    api = _object(
        json.loads(_run_gh(["api", f"repos/{repo_name}/actions/runs/{run_id}"])),
        "workflow run API metadata",
    )
    viewed["workflowPath"] = api.get("path")
    with tempfile.TemporaryDirectory(prefix="sandbox-runtime-evidence-") as raw:
        root = Path(raw)
        _run_gh(["run", "download", str(run_id), "--dir", str(root), *repo_args])
        return verify_downloaded_evidence(
            run=viewed,
            artifacts_root=root,
            workflow_path=workflow_path,
            head_sha=head_sha,
            required_platforms=required_platforms,
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-path", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument(
        "--require-platform", action="append", choices=sorted(_PLATFORMS), required=True
    )
    parser.add_argument("--repo")
    args = parser.parse_args(argv)
    try:
        result = discover_and_verify(
            workflow_path=args.workflow_path,
            head_sha=args.head_sha,
            required_platforms=set(args.require_platform),
            repo=args.repo,
        )
    except (EvidenceError, json.JSONDecodeError) as exc:
        parser.exit(1, f"sandbox-runtime evidence rejected: {exc}\n")
    print(json.dumps({"status": "verified", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
