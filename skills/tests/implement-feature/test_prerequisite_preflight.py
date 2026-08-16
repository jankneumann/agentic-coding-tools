"""Contract tests for authoritative implementation-prerequisite evidence."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills/implement-feature/scripts/prerequisite_preflight.py"
SCHEMA = (
    ROOT
    / "openspec/changes/phase-scoped-worktree-lifecycle/contracts/schemas/baseline-gates.schema.json"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("prerequisite_preflight", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def preflight():
    return _load_module()


def _requirements() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "repository": "current",
        "remote_name": "configured-default",
        "base_ref": "configured-default",
        "prerequisites": [
            {
                "change_id": "add-merge-plan-orchestration",
                "expected_head_ref": "openspec/add-merge-plan-orchestration",
                "required_surface": "file-tier merge-plan schema and executor",
                "blocks": ["wp-pr-delivery"],
            },
            {
                "change_id": "validate-feature-findings-gate",
                "expected_head_ref": "openspec/validate-feature-findings-gate",
                "required_surface": "selected ephemeral validation worktree",
                "blocks": ["wp-phase-lifecycle"],
            },
        ],
    }


def _write_requirements(tmp_path: Path, mutate=None) -> Path:
    data = _requirements()
    if mutate:
        mutate(data)
    contracts = tmp_path / "contracts"
    schemas = contracts / "schemas"
    schemas.mkdir(parents=True, exist_ok=True)
    (schemas / "baseline-gates.schema.json").write_text(SCHEMA.read_text())
    path = contracts / "prerequisites.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


class FakeRunner:
    """Small command fake that preserves the authoritative CLI boundary."""

    repository = "acme/tools"
    default_branch = "main"
    remote = "origin"
    head = "f" * 40
    base_tip = "e" * 40
    merge_shas = {1: "a" * 40, 2: "b" * 40}

    def __init__(self) -> None:
        self.mode = "ok"
        self.calls: list[tuple[str, ...]] = []

    @staticmethod
    def _done(argv: tuple[str, ...], stdout: str = "", returncode: int = 0):
        return subprocess.CompletedProcess(argv, returncode, stdout, "")

    def __call__(self, argv, *, cwd: Path, check: bool = True):
        args = tuple(str(part) for part in argv)
        self.calls.append(args)
        result = self._dispatch(args)
        if check and result.returncode:
            raise subprocess.CalledProcessError(
                result.returncode, args, output=result.stdout, stderr=result.stderr
            )
        return result

    def _dispatch(self, args: tuple[str, ...]):
        if args[:3] == ("gh", "repo", "view"):
            return self._done(
                args,
                json.dumps(
                    {
                        "nameWithOwner": self.repository,
                        "defaultBranchRef": {"name": self.default_branch},
                    }
                ),
            )
        if args[:3] == ("git", "branch", "--show-current"):
            return self._done(args, "openspec/phase-scoped-worktree-lifecycle\n")
        if args[:4] == ("git", "config", "--get", "remote.pushDefault"):
            return self._done(args, "", 1)
        if args[:4] == (
            "git",
            "config",
            "--get",
            "branch.openspec/phase-scoped-worktree-lifecycle.remote",
        ):
            return self._done(args, f"{self.remote}\n")
        if args[:3] == ("git", "remote", "get-url"):
            return self._done(args, f"git@github.com:{self.repository}.git\n")
        if args[:3] == ("gh", "pr", "list"):
            head_ref = args[args.index("--head") + 1]
            number = 1 if head_ref.endswith("merge-plan-orchestration") else 2
            pr = {
                "number": number,
                "url": f"https://github.com/{self.repository}/pull/{number}",
                "headRefName": head_ref,
                "headRepository": {"nameWithOwner": self.repository},
                "baseRefName": self.default_branch,
                "state": "MERGED",
                "mergedAt": "2026-08-01T00:00:00Z",
                "mergeCommit": {"oid": self.merge_shas[number]},
            }
            if self.mode == "absent" and number == 1:
                return self._done(args, "[]")
            if self.mode == "duplicate" and number == 1:
                return self._done(args, json.dumps([pr, {**pr, "number": 99}]))
            if self.mode == "open" and number == 1:
                pr.update(state="OPEN", mergedAt=None, mergeCommit=None)
            if self.mode == "wrong_repository" and number == 1:
                pr["headRepository"] = {"nameWithOwner": "fork/tools"}
            if self.mode == "wrong_base" and number == 1:
                pr["baseRefName"] = "release"
            if self.mode == "invalid_oid" and number == 1:
                pr["mergeCommit"] = {"oid": "a" * 41}
            return self._done(args, json.dumps([pr]))
        if args[:3] == ("gh", "pr", "view"):
            number = int(args[3])
            if number == 1:
                files = [
                    {
                        "path": "openspec/changes/add-merge-plan-orchestration/contracts/schemas/merge-plan.schema.json"
                    },
                    {"path": "skills/merge-pull-requests/scripts/build_plan.py"},
                ]
            else:
                files = [
                    {"path": "skills/validate-feature/scripts/validation_worktree.py"},
                    {"path": "skills/tests/validate-feature/test_validation_worktree.py"},
                ]
            if self.mode == "missing_surface" and number == 1:
                files = [{"path": "README.md"}]
            return self._done(args, json.dumps({"files": files}))
        if args[:2] == ("git", "fetch"):
            return self._done(args)
        if args[:3] == ("git", "rev-parse", "FETCH_HEAD"):
            return self._done(args, f"{self.base_tip}\n")
        if args[:3] == ("git", "rev-parse", "HEAD"):
            return self._done(args, f"{self.head}\n")
        if args[:3] == ("git", "merge-base", "--is-ancestor"):
            if self.mode == "non_ancestral" and args[3] == self.merge_shas[1]:
                return self._done(args, returncode=1)
            return self._done(args)
        raise AssertionError(f"unexpected command: {args}")


def _run(preflight, tmp_path: Path, runner: FakeRunner, mutate=None):
    requirements = _write_requirements(tmp_path, mutate)
    output = tmp_path / "baseline-gates.json"
    evidence = preflight.run_preflight(
        requirements_path=requirements,
        output_path=output,
        repo_root=tmp_path,
        runner=runner,
    )
    return evidence, output


@pytest.mark.parametrize(
    ("mode", "match"),
    [
        ("absent", "exactly one"),
        ("open", "is not merged"),
        ("duplicate", "exactly one"),
        ("wrong_repository", "repository"),
        ("wrong_base", "base"),
        ("invalid_oid", "object id"),
        ("non_ancestral", "not ancestral"),
        ("missing_surface", "required surface"),
    ],
)
def test_preflight_fails_closed(preflight, tmp_path: Path, mode: str, match: str) -> None:
    runner = FakeRunner()
    runner.mode = mode
    with pytest.raises(preflight.PreflightError, match=match):
        _run(preflight, tmp_path, runner)


def test_caller_supplied_sha_is_rejected(preflight, tmp_path: Path) -> None:
    def mutate(data):
        data["prerequisites"][0]["merge_sha"] = "a" * 40

    with pytest.raises(preflight.PreflightError, match="caller-supplied SHA"):
        _run(preflight, tmp_path, FakeRunner(), mutate)


def test_success_uses_authoritative_metadata_and_atomically_writes_schema_valid_evidence(
    preflight, tmp_path: Path
) -> None:
    runner = FakeRunner()
    evidence, output = _run(preflight, tmp_path, runner)

    assert json.loads(output.read_text()) == evidence
    Draft202012Validator(json.loads(SCHEMA.read_text())).validate(evidence)
    assert evidence["repository"] == runner.repository
    assert evidence["implementation_diff_base_sha"] == runner.base_tip
    assert {item["authoritative_merge_sha"] for item in evidence["prerequisites"]} == {
        "a" * 40,
        "b" * 40,
    }
    assert not list(output.parent.glob(f".{output.name}.*.tmp"))
    assert all("merge_sha" not in call for call in runner.calls)


def test_failure_preserves_existing_output(preflight, tmp_path: Path) -> None:
    requirements = _write_requirements(tmp_path)
    output = tmp_path / "baseline-gates.json"
    output.write_text('{"sentinel": true}\n')
    runner = FakeRunner()
    runner.mode = "missing_surface"

    with pytest.raises(preflight.PreflightError):
        preflight.run_preflight(requirements, output, tmp_path, runner=runner)

    assert json.loads(output.read_text()) == {"sentinel": True}


def test_verify_only_rechecks_ancestry_without_rewriting(preflight, tmp_path: Path) -> None:
    runner = FakeRunner()
    _, output = _run(preflight, tmp_path, runner)
    before = output.read_bytes()

    verified = preflight.run_preflight(
        _write_requirements(tmp_path), output, tmp_path, runner=FakeRunner(), verify_only=True
    )

    assert verified["implementation_diff_base_sha"] == runner.base_tip
    assert output.read_bytes() == before
