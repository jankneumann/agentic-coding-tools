#!/usr/bin/env python3
"""Resolve and verify authoritative prerequisite pull-request evidence."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

import yaml
from jsonschema import Draft202012Validator


OID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
FORBIDDEN_SHA_KEYS = {
    "merge_sha",
    "merge_commit",
    "authoritative_merge_sha",
    "fetched_base_tip_sha",
    "verified_head_sha",
    "implementation_diff_base_sha",
}


class PreflightError(RuntimeError):
    """Raised when prerequisite evidence cannot be proven authoritatively."""


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _default_runner(
    argv: Sequence[str], *, cwd: Path, check: bool = True
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(list(argv), cwd=cwd, check=check, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "command failed").strip()
        raise PreflightError(f"{' '.join(argv)}: {detail}") from exc


def _command(
    runner: Runner, argv: Sequence[str], repo_root: Path, *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    try:
        return runner(tuple(argv), cwd=repo_root, check=check)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "command failed").strip()
        raise PreflightError(f"{' '.join(argv)}: {detail}") from exc


def _json_command(runner: Runner, argv: Sequence[str], repo_root: Path) -> Any:
    completed = _command(runner, argv, repo_root)
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise PreflightError(f"{' '.join(argv)} returned invalid JSON") from exc


def _git_output(runner: Runner, repo_root: Path, *args: str) -> str:
    return _command(runner, ("git", *args), repo_root).stdout.strip()


def _git_optional(runner: Runner, repo_root: Path, *args: str) -> str | None:
    completed = _command(runner, ("git", *args), repo_root, check=False)
    return completed.stdout.strip() if completed.returncode == 0 else None


def _require_oid(value: Any, label: str) -> str:
    if not isinstance(value, str) or OID_RE.fullmatch(value) is None:
        raise PreflightError(f"{label} is not a 40- or 64-character lowercase Git object id")
    return value


def _load_requirements(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise PreflightError(f"cannot read requirements: {exc}") from exc
    if not isinstance(data, dict):
        raise PreflightError("requirements must be a mapping")

    for scope in (data, *data.get("prerequisites", [])):
        if not isinstance(scope, dict):
            raise PreflightError("each prerequisite must be a mapping")
        supplied = sorted(FORBIDDEN_SHA_KEYS.intersection(scope))
        if supplied:
            raise PreflightError(f"caller-supplied SHA fields are forbidden: {', '.join(supplied)}")

    prerequisites = data.get("prerequisites")
    if not isinstance(prerequisites, list) or not prerequisites:
        raise PreflightError("requirements contain no prerequisites")
    change_ids = [item.get("change_id") for item in prerequisites]
    head_refs = [item.get("expected_head_ref") for item in prerequisites]
    if len(change_ids) != len(set(change_ids)) or len(head_refs) != len(set(head_refs)):
        raise PreflightError("prerequisite change IDs and head refs must be unique")
    return data


def _schema_for(requirements_path: Path) -> dict[str, Any]:
    path = requirements_path.parent / "schemas" / "baseline-gates.schema.json"
    try:
        schema = json.loads(path.read_text())
        Draft202012Validator.check_schema(schema)
    except (OSError, json.JSONDecodeError, Exception) as exc:
        raise PreflightError(f"cannot load baseline evidence schema {path}: {exc}") from exc
    return schema


def _repository_context(
    requirements: dict[str, Any], repo_root: Path, runner: Runner
) -> tuple[str, str, str]:
    if requirements.get("repository") != "current":
        raise PreflightError("only repository: current is supported")
    repo = _json_command(
        runner,
        ("gh", "repo", "view", "--json", "nameWithOwner,defaultBranchRef"),
        repo_root,
    )
    repository = repo.get("nameWithOwner")
    default_branch = (repo.get("defaultBranchRef") or {}).get("name")
    if not repository or not default_branch:
        raise PreflightError("GitHub did not return the current repository and default branch")

    if requirements.get("base_ref") != "configured-default":
        raise PreflightError("only base_ref: configured-default is supported")
    if requirements.get("remote_name") != "configured-default":
        raise PreflightError("only remote_name: configured-default is supported")

    branch = _git_output(runner, repo_root, "branch", "--show-current")
    remote = _git_optional(runner, repo_root, "config", "--get", "remote.pushDefault")
    if not remote:
        remote = _git_optional(runner, repo_root, "config", "--get", f"branch.{branch}.remote")
    remote = remote or "origin"
    remote_url = _git_output(runner, repo_root, "remote", "get-url", remote)
    normalized_url = remote_url.removesuffix(".git").replace(":", "/")
    if not normalized_url.lower().endswith(f"/{repository}".lower()):
        raise PreflightError(
            f"configured remote {remote!r} points outside current repository {repository}"
        )
    return repository, default_branch, remote


def _validate_surface_content(
    *, change_id: str, path: str, kind: str, revision: str, content: str
) -> None:
    try:
        if kind == "python":
            ast.parse(content, filename=path)
        elif kind == "json-schema":
            schema = json.loads(content)
            Draft202012Validator.check_schema(schema)
        else:
            raise PreflightError(f"{change_id}: unsupported required surface kind {kind!r}")
    except (SyntaxError, UnicodeError, json.JSONDecodeError, Exception) as exc:
        if isinstance(exc, PreflightError):
            raise
        raise PreflightError(
            f"{change_id}: cannot parse required surface {path} at {revision}: {exc}"
        ) from exc


def _required_surface_files(surface: Any, *, change_id: str) -> tuple[str, list[dict[str, str]]]:
    """Validate and return one prerequisite's declared surface."""
    if not isinstance(surface, dict) or not isinstance(surface.get("id"), str):
        raise PreflightError(f"{change_id}: required surface must have an id")
    files = surface.get("files")
    if not isinstance(files, list) or not files:
        raise PreflightError(f"{change_id}: required surface files must be non-empty")
    if surface.get("verify_at") != [
        "authoritative-merge-sha",
        "feature-head",
    ]:
        raise PreflightError(
            f"{change_id}: required surface must verify at merge SHA and feature HEAD"
        )
    paths = [item.get("path") for item in files if isinstance(item, dict)]
    if len(paths) != len(files) or len(paths) != len(set(paths)):
        raise PreflightError(f"{change_id}: required surface paths must be unique")
    for item in files:
        path = item.get("path")
        kind = item.get("kind")
        if (
            not isinstance(path, str)
            or not path
            or kind
            not in (
                "python",
                "json-schema",
            )
        ):
            raise PreflightError(f"{change_id}: invalid required surface file declaration")
    return surface["id"], files


def _verify_surface_at_revision(
    surface: Any,
    *,
    change_id: str,
    revision: str,
    repo_root: Path,
    runner: Runner,
) -> str:
    surface_id, files = _required_surface_files(surface, change_id=change_id)
    for item in files:
        path = item["path"]
        kind = item["kind"]
        object_spec = f"{revision}:{path}"
        present = _command(
            runner,
            ("git", "cat-file", "-e", object_spec),
            repo_root,
            check=False,
        )
        if present.returncode != 0:
            raise PreflightError(f"{change_id}: required surface {path} is absent at {revision}")
        content = _command(runner, ("git", "show", object_spec), repo_root).stdout
        _validate_surface_content(
            change_id=change_id,
            path=path,
            kind=kind,
            revision=revision,
            content=content,
        )
    return surface_id


def _verify_required_surface(
    surface: Any,
    *,
    change_id: str,
    merge_sha: str,
    feature_head: str,
    repo_root: Path,
    runner: Runner,
) -> str:
    surface_id = _required_surface_files(surface, change_id=change_id)[0]
    for revision in (merge_sha, feature_head):
        _verify_surface_at_revision(
            surface,
            change_id=change_id,
            revision=revision,
            repo_root=repo_root,
            runner=runner,
        )
    return surface_id


def _is_ancestor(runner: Runner, repo_root: Path, ancestor: str, descendant: str) -> bool:
    result = _command(
        runner,
        ("git", "merge-base", "--is-ancestor", ancestor, descendant),
        repo_root,
        check=False,
    )
    if result.returncode not in (0, 1):
        raise PreflightError("git merge-base failed while checking prerequisite ancestry")
    return result.returncode == 0


def _resolve_prerequisite(
    config: dict[str, Any],
    *,
    repository: str,
    base_ref: str,
    remote: str,
    base_tip: str,
    feature_head: str,
    repo_root: Path,
    runner: Runner,
    verified_at: str,
) -> dict[str, Any]:
    head_ref = config.get("expected_head_ref")
    change_id = config.get("change_id")
    surface = config.get("required_surface")
    if not all(isinstance(value, str) and value for value in (head_ref, change_id)):
        raise PreflightError("prerequisite identity fields must be non-empty strings")
    _required_surface_files(surface, change_id=change_id)

    prs = _json_command(
        runner,
        (
            "gh",
            "pr",
            "list",
            "--repo",
            repository,
            "--state",
            "all",
            "--head",
            head_ref,
            "--json",
            "number,url,headRefName,headRepository,baseRefName,state,mergedAt,mergeCommit",
        ),
        repo_root,
    )
    if not isinstance(prs, list):
        raise PreflightError(f"{change_id}: pull request query returned invalid metadata")

    candidate_assessments: list[dict[str, Any]] = []
    qualified: list[tuple[dict[str, Any], str]] = []
    for pr in prs:
        reasons: list[str] = []
        merge_sha: str | None = None
        if not isinstance(pr, dict):
            pr = {}
            reasons.append("candidate metadata is not an object")
        if pr.get("state") != "MERGED" or not pr.get("mergedAt") or not pr.get("mergeCommit"):
            reasons.append("pull request is not merged with authoritative merge metadata")
        head_repository = (pr.get("headRepository") or {}).get("nameWithOwner")
        if head_repository != repository:
            reasons.append(f"head repository {head_repository!r} is not {repository!r}")
        if pr.get("headRefName") != head_ref:
            reasons.append(f"authoritative head ref does not match {head_ref}")
        if pr.get("baseRefName") != base_ref:
            reasons.append(f"pull request base {pr.get('baseRefName')!r} is not {base_ref!r}")
        if not reasons:
            try:
                merge_sha = _require_oid(
                    (pr.get("mergeCommit") or {}).get("oid"), "merge object id"
                )
            except PreflightError as exc:
                reasons.append(str(exc))
        if merge_sha is not None:
            if not _is_ancestor(runner, repo_root, merge_sha, base_tip):
                reasons.append("merge SHA is not ancestral to fetched base")
            if not _is_ancestor(runner, repo_root, merge_sha, feature_head):
                reasons.append("merge SHA is not ancestral to feature HEAD")
        if merge_sha is not None and not reasons:
            try:
                _verify_surface_at_revision(
                    surface,
                    change_id=change_id,
                    revision=merge_sha,
                    repo_root=repo_root,
                    runner=runner,
                )
            except PreflightError as exc:
                prefix = f"{change_id}: "
                detail = str(exc)
                reasons.append(detail.removeprefix(prefix))

        assessment = {
            "pr_number": pr.get("number") if isinstance(pr.get("number"), int) else None,
            "pr_url": pr.get("url") if isinstance(pr.get("url"), str) else None,
            "qualified": not reasons,
            "rejection_reasons": reasons,
        }
        candidate_assessments.append(assessment)
        if not reasons and merge_sha is not None:
            qualified.append((pr, merge_sha))

    if len(qualified) != 1:
        qualified_numbers = (
            ", ".join(f"#{pr.get('number')}" for pr, _merge_sha in qualified) or "none"
        )
        rejected = (
            "; ".join(
                f"PR #{item['pr_number']}: {', '.join(item['rejection_reasons'])}"
                for item in candidate_assessments
                if not item["qualified"]
            )
            or "none"
        )
        raise PreflightError(
            f"{change_id}: expected exactly one surface-qualified merged pull request, "
            f"found {len(qualified)}; qualified PRs: {qualified_numbers}; "
            f"rejected candidates: {rejected}"
        )

    pr, merge_sha = qualified[0]
    surface_id = _verify_required_surface(
        surface,
        change_id=change_id,
        merge_sha=merge_sha,
        feature_head=feature_head,
        repo_root=repo_root,
        runner=runner,
    )

    return {
        "change_id": change_id,
        "repository": repository,
        "remote_name": remote,
        "configured_base_ref": base_ref,
        "pr_number": pr["number"],
        "pr_url": pr["url"],
        "head_ref": head_ref,
        "base_ref": pr["baseRefName"],
        "merged_at": pr["mergedAt"],
        "authoritative_merge_sha": merge_sha,
        "fetched_base_tip_sha": base_tip,
        "verified_head_sha": feature_head,
        "surface_assertion": surface_id,
        "candidate_assessments": candidate_assessments,
        "verified_at": verified_at,
    }


def _resolve(requirements: dict[str, Any], repo_root: Path, runner: Runner) -> dict[str, Any]:
    repository, base_ref, remote = _repository_context(requirements, repo_root, runner)
    _command(runner, ("git", "fetch", remote, base_ref), repo_root)
    base_tip = _require_oid(
        _git_output(runner, repo_root, "rev-parse", "FETCH_HEAD"),
        "fetched base object id",
    )
    feature_head = _require_oid(
        _git_output(runner, repo_root, "rev-parse", "HEAD"),
        "feature HEAD object id",
    )
    verified_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    resolved = [
        _resolve_prerequisite(
            config,
            repository=repository,
            base_ref=base_ref,
            remote=remote,
            base_tip=base_tip,
            feature_head=feature_head,
            repo_root=repo_root,
            runner=runner,
            verified_at=verified_at,
        )
        for config in requirements["prerequisites"]
    ]
    return {
        "schema_version": 1,
        "repository": repository,
        "implementation_diff_base_sha": base_tip,
        "verified_at": verified_at,
        "prerequisites": resolved,
    }


def _validate_evidence(evidence: dict[str, Any], schema: dict[str, Any]) -> None:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(evidence),
        key=lambda error: list(error.path),
    )
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise PreflightError(
            f"baseline evidence is not schema-valid at {location}: {first.message}"
        )


def _verify_existing(
    evidence: dict[str, Any],
    requirements: dict[str, Any],
    repo_root: Path,
    runner: Runner,
    schema: dict[str, Any],
    expected_feature_head: str,
) -> dict[str, Any]:
    required_ids = [item["change_id"] for item in requirements["prerequisites"]]
    raw_prerequisites = evidence.get("prerequisites", [])
    evidence_ids = (
        [item.get("change_id") for item in raw_prerequisites if isinstance(item, dict)]
        if isinstance(raw_prerequisites, list)
        else []
    )
    if (
        len(evidence_ids) != len(required_ids)
        or len(evidence_ids) != len(set(evidence_ids))
        or set(evidence_ids) != set(required_ids)
    ):
        raise PreflightError("baseline evidence prerequisite IDs are not an exact one-to-one match")
    _validate_evidence(evidence, schema)
    expected_feature_head = _require_oid(expected_feature_head, "expected feature HEAD object id")
    generation_heads = {
        _require_oid(item["verified_head_sha"], "stored verified_head_sha")
        for item in evidence["prerequisites"]
    }
    if len(generation_heads) != 1:
        raise PreflightError(
            "baseline evidence prerequisites must attest one exact generation revision"
        )
    generation_head = next(iter(generation_heads))
    if generation_head == expected_feature_head:
        raise PreflightError(
            "baseline evidence generation revision must precede its committed gate HEAD"
        )
    generation_commit = _command(
        runner,
        ("git", "cat-file", "-e", f"{generation_head}^{{commit}}"),
        repo_root,
        check=False,
    )
    if generation_commit.returncode != 0:
        raise PreflightError("stored feature HEAD is not an available generation commit")
    gate_commit = _command(
        runner,
        ("git", "cat-file", "-p", expected_feature_head),
        repo_root,
    ).stdout
    gate_headers, separator, _message = gate_commit.partition("\n\n")
    if not separator:
        raise PreflightError("committed evidence gate has malformed commit headers")
    gate_lines = gate_headers.splitlines()
    if not gate_lines or not gate_lines[0].startswith("tree "):
        raise PreflightError("committed evidence gate is not a commit object")
    gate_parents = [
        line.removeprefix("parent ") for line in gate_lines if line.startswith("parent ")
    ]
    if len(gate_parents) != 1:
        raise PreflightError(
            "committed evidence gate must be a non-merge commit with exactly one parent"
        )
    if gate_parents[0] != generation_head:
        raise PreflightError(
            "baseline evidence generation revision is not the exact parent of the gate commit"
        )

    # Resolve again at the committed gate HEAD. This independently verifies
    # every required surface at B; the stored evidence continues to attest A.
    current = _resolve(requirements, repo_root, runner)
    current_feature_heads = {item["verified_head_sha"] for item in current["prerequisites"]}
    if current_feature_heads != {expected_feature_head}:
        raise PreflightError("baseline verification is not bound to the exact feature HEAD")
    if evidence.get("repository") != current["repository"]:
        raise PreflightError("baseline evidence belongs to a different repository")
    current_by_change = {item["change_id"]: item for item in current["prerequisites"]}
    requirements_by_change = {item["change_id"]: item for item in requirements["prerequisites"]}
    immutable = (
        "repository",
        "remote_name",
        "configured_base_ref",
        "pr_number",
        "pr_url",
        "head_ref",
        "base_ref",
        "merged_at",
        "authoritative_merge_sha",
        "surface_assertion",
        "candidate_assessments",
    )
    for stored in evidence["prerequisites"]:
        fresh = current_by_change.get(stored["change_id"])
        if fresh is None or any(stored[key] != fresh[key] for key in immutable):
            raise PreflightError(f"{stored['change_id']}: authoritative PR metadata changed")
        for key in (
            "fetched_base_tip_sha",
            "verified_head_sha",
            "authoritative_merge_sha",
        ):
            _require_oid(stored[key], f"stored {key}")
        _verify_required_surface(
            requirements_by_change[stored["change_id"]]["required_surface"],
            change_id=stored["change_id"],
            merge_sha=stored["authoritative_merge_sha"],
            feature_head=generation_head,
            repo_root=repo_root,
            runner=runner,
        )
        if not _is_ancestor(
            runner,
            repo_root,
            stored["fetched_base_tip_sha"],
            fresh["fetched_base_tip_sha"],
        ):
            raise PreflightError(
                f"{stored['change_id']}: stored base is not ancestral to fetched base"
            )
    _require_oid(
        evidence["implementation_diff_base_sha"],
        "implementation diff base object id",
    )
    if not _is_ancestor(
        runner,
        repo_root,
        evidence["implementation_diff_base_sha"],
        current["implementation_diff_base_sha"],
    ):
        raise PreflightError("implementation diff base is not ancestral to fetched base")
    return evidence


def verify_evidence_bytes(
    requirements_path: Path,
    evidence_bytes: bytes,
    repo_root: Path,
    *,
    runner: Runner = _default_runner,
    expected_feature_head: str,
) -> dict[str, Any]:
    """Verify immutable evidence bytes against one exact feature HEAD."""
    requirements_path = Path(requirements_path)
    try:
        evidence = json.loads(evidence_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PreflightError(f"baseline evidence is not valid JSON: {exc}") from exc
    requirements = _load_requirements(requirements_path)
    schema = _schema_for(requirements_path)
    return _verify_existing(
        evidence,
        requirements,
        Path(repo_root),
        runner,
        schema,
        expected_feature_head,
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    finally:
        temporary.unlink(missing_ok=True)


def run_preflight(
    requirements_path: Path,
    output_path: Path,
    repo_root: Path,
    *,
    runner: Runner = _default_runner,
    verify_only: bool = False,
    expected_feature_head: str | None = None,
) -> dict[str, Any]:
    requirements_path = Path(requirements_path)
    output_path = Path(output_path)
    repo_root = Path(repo_root)
    requirements = _load_requirements(requirements_path)
    schema = _schema_for(requirements_path)
    if verify_only:
        if expected_feature_head is None:
            raise PreflightError("verify-only requires an exact expected feature HEAD")
        try:
            evidence_bytes = output_path.read_bytes()
        except OSError as exc:
            raise PreflightError(f"cannot read baseline evidence: {exc}") from exc
        return verify_evidence_bytes(
            requirements_path,
            evidence_bytes,
            repo_root,
            runner=runner,
            expected_feature_head=expected_feature_head,
        )

    evidence = _resolve(requirements, repo_root, runner)
    _validate_evidence(evidence, schema)
    _atomic_write_json(output_path, evidence)
    return evidence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--expected-feature-head")
    args = parser.parse_args(argv)
    try:
        evidence = run_preflight(
            args.requirements,
            args.output,
            args.repo_root,
            verify_only=args.verify_only,
            expected_feature_head=args.expected_feature_head,
        )
    except PreflightError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
