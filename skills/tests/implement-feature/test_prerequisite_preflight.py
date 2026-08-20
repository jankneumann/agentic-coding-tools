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
                "required_surface": {
                    "id": "file-tier-merge-plan-schema-and-executor",
                    "files": [
                        {"path": "contracts/merge-plan.schema.json", "kind": "json-schema"},
                        {"path": "skills/build_plan.py", "kind": "python"},
                    ],
                    "verify_at": ["authoritative-merge-sha", "feature-head"],
                },
                "blocks": ["wp-pr-delivery"],
            },
            {
                "change_id": "validate-feature-findings-gate",
                "expected_head_ref": "openspec/validate-feature-findings-gate",
                "required_surface": {
                    "id": "selected-ephemeral-validation-worktree",
                    "files": [
                        {"path": "skills/validation_worktree.py", "kind": "python"},
                        {"path": "skills/test_validation_worktree.py", "kind": "python"},
                    ],
                    "verify_at": ["authoritative-merge-sha", "feature-head"],
                },
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
    merge_shas = {1: "a" * 40, 2: "b" * 40, 3: "c" * 40, 4: "d" * 40}

    def __init__(self) -> None:
        self.mode = "ok"
        self.calls: list[tuple[str, ...]] = []
        self.gate_parents: list[str] | None = None
        self.gate_message_lines = ["fixture gate"]

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
            if self.mode == "proposal_then_implementation" and number == 1:
                implementation = {
                    **pr,
                    "number": 3,
                    "url": f"https://github.com/{self.repository}/pull/3",
                    "mergeCommit": {"oid": self.merge_shas[3]},
                }
                return self._done(args, json.dumps([pr, implementation]))
            if (
                self.mode
                in {
                    "qualified_beyond_default_page",
                    "candidate_limit_saturated",
                }
                and number == 1
            ):
                proposal_candidates = [
                    {
                        **pr,
                        "number": candidate_number,
                        "url": (f"https://github.com/{self.repository}/pull/{candidate_number}"),
                    }
                    for candidate_number in range(10, 1010)
                ]
                candidates = proposal_candidates
                if self.mode == "qualified_beyond_default_page":
                    implementation = {
                        **pr,
                        "number": 3,
                        "url": f"https://github.com/{self.repository}/pull/3",
                        "mergeCommit": {"oid": self.merge_shas[3]},
                    }
                    candidates = proposal_candidates[:30] + [implementation]
                limit = int(args[args.index("--limit") + 1]) if "--limit" in args else 30
                return self._done(args, json.dumps(candidates[:limit]))
            if self.mode == "multiple_surface_qualified" and number == 1:
                successor = {
                    **pr,
                    "number": 4,
                    "url": f"https://github.com/{self.repository}/pull/4",
                    "mergeCommit": {"oid": self.merge_shas[4]},
                }
                return self._done(args, json.dumps([pr, successor]))
            if self.mode == "open" and number == 1:
                pr.update(state="OPEN", mergedAt=None, mergeCommit=None)
            if self.mode == "wrong_repository" and number == 1:
                pr["headRepository"] = {"nameWithOwner": "fork/tools"}
            if self.mode == "wrong_base" and number == 1:
                pr["baseRefName"] = "release"
            if self.mode == "invalid_oid" and number == 1:
                pr["mergeCommit"] = {"oid": "a" * 41}
            return self._done(args, json.dumps([pr]))
        if args[:2] == ("git", "fetch"):
            return self._done(args)
        if args[:3] == ("git", "rev-parse", "FETCH_HEAD"):
            return self._done(args, f"{self.base_tip}\n")
        if args[:3] == ("git", "rev-parse", "HEAD"):
            return self._done(args, f"{self.head}\n")
        if args[:3] == ("git", "cat-file", "-p"):
            parents = self.gate_parents if self.gate_parents is not None else ["f" * 40]
            parent_lines = "".join(f"parent {parent}\n" for parent in parents)
            message = "\n".join(self.gate_message_lines)
            return self._done(args, f"tree {'1' * 40}\n{parent_lines}\n{message}\n")
        if args[:3] == ("git", "merge-base", "--is-ancestor"):
            if self.mode == "non_ancestral" and args[3] == self.merge_shas[1]:
                return self._done(args, returncode=1)
            return self._done(args)
        if args[:3] == ("git", "cat-file", "-e"):
            object_spec = args[3]
            if object_spec.endswith("^{commit}"):
                revision = object_spec.removesuffix("^{commit}")
                known_commits = {
                    "f" * 40,
                    self.head,
                    self.base_tip,
                    *self.merge_shas.values(),
                }
                return self._done(args, returncode=0 if revision in known_commits else 1)
            revision, path = object_spec.split(":", 1)
            if (
                self.mode
                in {
                    "missing_surface",
                    "proposal_then_implementation",
                    "qualified_beyond_default_page",
                    "candidate_limit_saturated",
                }
                and revision == self.merge_shas[1]
                and path == "skills/build_plan.py"
            ):
                return self._done(args, returncode=1)
            return self._done(args)
        if args[:2] == ("git", "show"):
            revision, path = args[2].split(":", 1)
            if path.endswith(".schema.json"):
                content = (
                    '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object"}'
                )
            else:
                content = "def main():\n    return 0\n"
            if self.mode == "invalid_surface_content" and revision == self.head:
                content = "def broken(:\n"
            if (
                self.mode == "invalid_python_surface"
                and revision == self.head
                and path.endswith(".py")
            ):
                content = "def broken(:\n"
            return self._done(args, content)
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
        ("invalid_surface_content", "cannot parse"),
        ("invalid_python_surface", "cannot parse"),
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
    surface_checks = [call[3] for call in runner.calls if call[:3] == ("git", "cat-file", "-e")]
    assert f"{runner.merge_shas[1]}:skills/build_plan.py" in surface_checks
    assert f"{runner.head}:skills/build_plan.py" in surface_checks
    assert not any(call[:3] == ("gh", "pr", "view") for call in runner.calls)


def test_proposal_only_pr_is_ignored_when_one_implementation_successor_qualifies(
    preflight, tmp_path: Path
) -> None:
    runner = FakeRunner()
    runner.mode = "proposal_then_implementation"

    evidence, _ = _run(preflight, tmp_path, runner)

    selected = evidence["prerequisites"][0]
    assert selected["pr_number"] == 3
    assert selected["authoritative_merge_sha"] == runner.merge_shas[3]
    assert selected["candidate_assessments"] == [
        {
            "pr_number": 1,
            "pr_url": f"https://github.com/{runner.repository}/pull/1",
            "qualified": False,
            "rejection_reasons": [
                f"required surface skills/build_plan.py is absent at {runner.merge_shas[1]}"
            ],
        },
        {
            "pr_number": 3,
            "pr_url": f"https://github.com/{runner.repository}/pull/3",
            "qualified": True,
            "rejection_reasons": [],
        },
    ]


def test_no_surface_qualified_candidate_fails_closed_with_auditable_reasons(
    preflight, tmp_path: Path
) -> None:
    runner = FakeRunner()
    runner.mode = "missing_surface"

    with pytest.raises(
        preflight.PreflightError,
        match=r"found 0.*PR #1.*required surface skills/build_plan\.py is absent",
    ):
        _run(preflight, tmp_path, runner)


def test_multiple_surface_qualified_candidates_fail_closed(preflight, tmp_path: Path) -> None:
    runner = FakeRunner()
    runner.mode = "multiple_surface_qualified"

    with pytest.raises(
        preflight.PreflightError,
        match=r"found 2.*qualified PRs: #1, #4",
    ):
        _run(preflight, tmp_path, runner)


def test_candidate_beyond_default_first_page_is_qualified(preflight, tmp_path: Path) -> None:
    runner = FakeRunner()
    runner.mode = "qualified_beyond_default_page"

    evidence, _ = _run(preflight, tmp_path, runner)

    selected = evidence["prerequisites"][0]
    assert selected["pr_number"] == 3
    assert len(selected["candidate_assessments"]) == 31


def test_candidate_query_fails_closed_when_safety_limit_is_saturated(
    preflight, tmp_path: Path
) -> None:
    runner = FakeRunner()
    runner.mode = "candidate_limit_saturated"

    with pytest.raises(preflight.PreflightError, match="candidate query reached safety limit"):
        _run(preflight, tmp_path, runner)


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
    committed = FakeRunner()
    committed.head = "c" * 40

    verified = preflight.run_preflight(
        _write_requirements(tmp_path),
        output,
        tmp_path,
        runner=committed,
        verify_only=True,
        expected_feature_head=committed.head,
    )

    assert verified["implementation_diff_base_sha"] == runner.base_tip
    assert output.read_bytes() == before


def test_verify_only_requires_an_explicit_gate_head(preflight, tmp_path: Path) -> None:
    runner = FakeRunner()
    _, output = _run(preflight, tmp_path, runner)

    with pytest.raises(preflight.PreflightError, match="exact expected feature HEAD"):
        preflight.run_preflight(
            _write_requirements(tmp_path),
            output,
            tmp_path,
            runner=FakeRunner(),
            verify_only=True,
        )


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (
            lambda evidence: evidence["prerequisites"].pop(),
            "one-to-one",
        ),
        (
            lambda evidence: evidence["prerequisites"].append(dict(evidence["prerequisites"][0])),
            "one-to-one",
        ),
        (
            lambda evidence: evidence["prerequisites"].__setitem__(
                1, dict(evidence["prerequisites"][0])
            ),
            "one-to-one",
        ),
        (
            lambda evidence: evidence["prerequisites"][1].__setitem__(
                "change_id", "unexpected-change"
            ),
            "one-to-one",
        ),
    ],
)
def test_verify_only_rejects_duplicate_omitted_or_unknown_prerequisite_ids(
    preflight, tmp_path: Path, mutate, match: str
) -> None:
    runner = FakeRunner()
    evidence, _ = _run(preflight, tmp_path, runner)
    mutate(evidence)

    with pytest.raises(preflight.PreflightError, match=match):
        preflight.verify_evidence_bytes(
            _write_requirements(tmp_path),
            json.dumps(evidence).encode(),
            tmp_path,
            runner=FakeRunner(),
            expected_feature_head=runner.head,
        )


def test_verify_only_rejects_a_stale_gate_head_binding(preflight, tmp_path: Path) -> None:
    runner = FakeRunner()
    evidence, _ = _run(preflight, tmp_path, runner)
    current = FakeRunner()
    current.head = "c" * 40
    expected_gate_head = "d" * 40

    with pytest.raises(preflight.PreflightError, match="exact feature HEAD"):
        preflight.verify_evidence_bytes(
            _write_requirements(tmp_path),
            json.dumps(evidence).encode(),
            tmp_path,
            runner=current,
            expected_feature_head=expected_gate_head,
        )


def test_verify_only_rejects_stored_heads_that_are_merely_ancestors(
    preflight, tmp_path: Path
) -> None:
    runner = FakeRunner()
    evidence, _ = _run(preflight, tmp_path, runner)
    for prerequisite in evidence["prerequisites"]:
        prerequisite["verified_head_sha"] = "0" * 40

    with pytest.raises(preflight.PreflightError, match="stored feature HEAD"):
        preflight.verify_evidence_bytes(
            _write_requirements(tmp_path),
            json.dumps(evidence).encode(),
            tmp_path,
            runner=FakeRunner(),
            expected_feature_head=runner.head,
        )


def test_generation_head_evidence_can_gate_its_distinct_commit_head(
    preflight, tmp_path: Path
) -> None:
    generation = FakeRunner()
    evidence, _ = _run(preflight, tmp_path, generation)
    committed = FakeRunner()
    committed.head = "c" * 40

    verified = preflight.verify_evidence_bytes(
        _write_requirements(tmp_path),
        json.dumps(evidence).encode(),
        tmp_path,
        runner=committed,
        expected_feature_head=committed.head,
    )

    assert {item["verified_head_sha"] for item in verified["prerequisites"]} == {generation.head}
    surface_checks = [call[3] for call in committed.calls if call[:3] == ("git", "cat-file", "-e")]
    assert f"{generation.head}:skills/build_plan.py" in surface_checks
    assert f"{committed.head}:skills/build_plan.py" in surface_checks


def test_verify_only_rejects_inconsistent_generation_heads(preflight, tmp_path: Path) -> None:
    generation = FakeRunner()
    evidence, _ = _run(preflight, tmp_path, generation)
    evidence["prerequisites"][0]["verified_head_sha"] = "a" * 40
    committed = FakeRunner()
    committed.head = "c" * 40

    with pytest.raises(preflight.PreflightError, match="one exact generation revision"):
        preflight.verify_evidence_bytes(
            _write_requirements(tmp_path),
            json.dumps(evidence).encode(),
            tmp_path,
            runner=committed,
            expected_feature_head=committed.head,
        )


def test_verify_only_rejects_modified_authoritative_metadata(preflight, tmp_path: Path) -> None:
    generation = FakeRunner()
    evidence, _ = _run(preflight, tmp_path, generation)
    evidence["prerequisites"][0]["pr_url"] = "https://github.com/acme/tools/pull/999"
    committed = FakeRunner()
    committed.head = "c" * 40

    with pytest.raises(preflight.PreflightError, match="metadata changed"):
        preflight.verify_evidence_bytes(
            _write_requirements(tmp_path),
            json.dumps(evidence).encode(),
            tmp_path,
            runner=committed,
            expected_feature_head=committed.head,
        )


def test_verify_only_rejects_changed_required_surfaces_at_gate_head(
    preflight, tmp_path: Path
) -> None:
    generation = FakeRunner()
    evidence, _ = _run(preflight, tmp_path, generation)
    committed = FakeRunner()
    committed.head = "c" * 40
    committed.mode = "invalid_surface_content"

    with pytest.raises(preflight.PreflightError, match="cannot parse"):
        preflight.verify_evidence_bytes(
            _write_requirements(tmp_path),
            json.dumps(evidence).encode(),
            tmp_path,
            runner=committed,
            expected_feature_head=committed.head,
        )


def test_verify_only_rejects_an_older_generation_ancestor_than_gate_parent(
    preflight, tmp_path: Path
) -> None:
    generation = FakeRunner()
    evidence, _ = _run(preflight, tmp_path, generation)
    for prerequisite in evidence["prerequisites"]:
        prerequisite["verified_head_sha"] = generation.base_tip
    committed = FakeRunner()
    committed.head = "c" * 40

    with pytest.raises(preflight.PreflightError, match="exact parent"):
        preflight.verify_evidence_bytes(
            _write_requirements(tmp_path),
            json.dumps(evidence).encode(),
            tmp_path,
            runner=committed,
            expected_feature_head=committed.head,
        )


def test_verify_only_rejects_a_merge_gate_commit(preflight, tmp_path: Path) -> None:
    generation = FakeRunner()
    evidence, _ = _run(preflight, tmp_path, generation)
    committed = FakeRunner()
    committed.head = "c" * 40
    committed.gate_parents = [generation.head, "a" * 40]
    committed.gate_message_lines = [f"parent {'b' * 40}", "merge message"]

    with pytest.raises(preflight.PreflightError, match="non-merge"):
        preflight.verify_evidence_bytes(
            _write_requirements(tmp_path),
            json.dumps(evidence).encode(),
            tmp_path,
            runner=committed,
            expected_feature_head=committed.head,
        )


def test_verify_only_rejects_root_gate_with_parent_like_commit_message(
    preflight, tmp_path: Path
) -> None:
    generation = FakeRunner()
    evidence, _ = _run(preflight, tmp_path, generation)
    committed = FakeRunner()
    committed.head = "c" * 40
    committed.gate_parents = []
    committed.gate_message_lines = [f"parent {generation.head}", "spoofed body"]

    with pytest.raises(preflight.PreflightError, match="exactly one parent"):
        preflight.verify_evidence_bytes(
            _write_requirements(tmp_path),
            json.dumps(evidence).encode(),
            tmp_path,
            runner=committed,
            expected_feature_head=committed.head,
        )


def test_verify_only_accepts_normal_gate_with_parent_like_commit_message(
    preflight, tmp_path: Path
) -> None:
    generation = FakeRunner()
    evidence, _ = _run(preflight, tmp_path, generation)
    committed = FakeRunner()
    committed.head = "c" * 40
    committed.gate_parents = [generation.head]
    committed.gate_message_lines = [f"parent {'a' * 40}", "ordinary body"]

    verified = preflight.verify_evidence_bytes(
        _write_requirements(tmp_path),
        json.dumps(evidence).encode(),
        tmp_path,
        runner=committed,
        expected_feature_head=committed.head,
    )

    assert verified == evidence
