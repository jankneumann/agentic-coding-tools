"""Tests for validate_work_result.py."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import validate_work_result
from validate_work_result import (
    derive_outcome,
    effective_outcome,
    load_schema,
    validate_commit_resolves,
    validate_outcome_consistency,
    validate_result,
    validate_schema,
    validate_scope_compliance,
    validate_verification_consistency,
)


@pytest.fixture
def schema():
    return load_schema()


@pytest.fixture
def valid_result():
    """A minimal valid work-queue result payload."""
    return {
        "schema_version": 1,
        "feature_id": "FEAT-test-001",
        "package_id": "wp-backend",
        "plan_revision": 1,
        "contracts_revision": 1,
        "status": "completed",
        "locks": {
            "files": ["src/api/users.py"],
            "keys": ["api:GET /v1/users"],
        },
        "scope": {
            "write_allow": ["src/api/**", "tests/api/**"],
            "read_allow": ["src/**"],
            "deny": ["src/frontend/**"],
        },
        "files_modified": ["src/api/users.py", "tests/api/test_users.py"],
        "git": {
            "base": {"ref": "main"},
            "head": {"commit": "abc1234", "branch": "openspec/feat-test"},
        },
        "verification": {
            "tier": "A",
            "passed": True,
            "steps": [
                {
                    "name": "unit-tests",
                    "kind": "command",
                    "passed": True,
                    "command": "pytest tests/api/ -v",
                    "exit_code": 0,
                    "evidence": {
                        "artifacts": ["artifacts/wp-backend/pytest.xml"],
                        "metrics": {"test_count": 12, "pass_count": 12},
                    },
                }
            ],
        },
        "escalations": [],
    }


# --- Schema validation ---


class TestSchemaValidation:
    def test_valid_result(self, schema, valid_result):
        errors = validate_schema(valid_result, schema)
        assert errors == [], f"Unexpected errors: {errors}"

    def test_missing_required_field(self, schema, valid_result):
        data = deepcopy(valid_result)
        del data["package_id"]
        errors = validate_schema(data, schema)
        assert any("package_id" in e for e in errors)

    def test_invalid_status(self, schema, valid_result):
        data = deepcopy(valid_result)
        data["status"] = "unknown"
        errors = validate_schema(data, schema)
        assert len(errors) > 0

    def test_invalid_commit_hash(self, schema, valid_result):
        data = deepcopy(valid_result)
        data["git"]["head"]["commit"] = "not-a-hash!"
        errors = validate_schema(data, schema)
        assert len(errors) > 0

    def test_failed_result_with_error_code(self, schema, valid_result):
        data = deepcopy(valid_result)
        data["status"] = "failed"
        data["error_code"] = "VERIFICATION_FAILED"
        errors = validate_schema(data, schema)
        assert errors == []

    def test_verification_tier_invalid(self, schema, valid_result):
        data = deepcopy(valid_result)
        data["verification"]["tier"] = "X"
        errors = validate_schema(data, schema)
        assert len(errors) > 0


# --- Scope compliance ---


class TestScopeCompliance:
    def test_valid_scope(self, valid_result):
        errors = validate_scope_compliance(valid_result)
        assert errors == []

    def test_file_outside_write_allow(self, valid_result):
        data = deepcopy(valid_result)
        data["files_modified"].append("config/settings.yaml")
        errors = validate_scope_compliance(data)
        assert len(errors) == 1
        assert "config/settings.yaml" in errors[0]

    def test_file_in_deny(self, valid_result):
        data = deepcopy(valid_result)
        data["files_modified"].append("src/frontend/App.tsx")
        errors = validate_scope_compliance(data)
        assert len(errors) == 1
        assert "deny" in errors[0]

    def test_empty_files_modified(self, valid_result):
        data = deepcopy(valid_result)
        data["files_modified"] = []
        errors = validate_scope_compliance(data)
        assert errors == []


# --- Verification consistency ---


class TestVerificationConsistency:
    def test_consistent_pass(self, valid_result):
        errors = validate_verification_consistency(valid_result)
        assert errors == []

    def test_overall_pass_but_step_failed(self, valid_result):
        data = deepcopy(valid_result)
        data["verification"]["steps"][0]["passed"] = False
        errors = validate_verification_consistency(data)
        assert len(errors) == 1
        assert "verification.passed=true" in errors[0]

    def test_overall_fail_but_all_steps_pass(self, valid_result):
        data = deepcopy(valid_result)
        data["verification"]["passed"] = False
        errors = validate_verification_consistency(data)
        assert len(errors) == 1
        assert "verification.passed=false" in errors[0]

    def test_consistent_fail(self, valid_result):
        data = deepcopy(valid_result)
        data["verification"]["passed"] = False
        data["verification"]["steps"][0]["passed"] = False
        errors = validate_verification_consistency(data)
        assert errors == []


# --- Full validation ---


class TestFullValidation:
    def test_valid_result(self, schema, valid_result):
        results = validate_result(valid_result, schema)
        assert results["valid"] is True
        assert all(c["passed"] for c in results["checks"].values())

    def test_invalid_schema_reports(self, schema, valid_result):
        data = deepcopy(valid_result)
        del data["status"]
        results = validate_result(data, schema)
        assert results["valid"] is False
        assert not results["checks"]["schema"]["passed"]

    def test_scope_violation_reports(self, schema, valid_result):
        data = deepcopy(valid_result)
        data["files_modified"].append("outside/scope.txt")
        results = validate_result(data, schema)
        assert results["valid"] is False
        assert not results["checks"]["scope_compliance"]["passed"]


# --- CLI ---


class TestCLI:
    def test_valid_json_output(self, tmp_path, valid_result):
        import subprocess

        result_file = tmp_path / "result.json"
        result_file.write_text(json.dumps(valid_result))

        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parent.parent / "validate_work_result.py"),
                str(result_file),
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["valid"] is True

    def test_text_output(self, tmp_path, valid_result):
        import subprocess

        result_file = tmp_path / "result.json"
        result_file.write_text(json.dumps(valid_result))

        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parent.parent / "validate_work_result.py"),
                str(result_file),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "VALID" in result.stdout


# --- Vacuous verification (empty steps, not_run steps) ---


class TestVacuousVerification:
    @pytest.mark.parametrize("claimed", [True, False])
    def test_empty_steps_is_an_error(self, valid_result, claimed):
        data = deepcopy(valid_result)
        data["verification"]["steps"] = []
        data["verification"]["passed"] = claimed
        errors = validate_verification_consistency(data)
        assert len(errors) == 1
        assert "no verification steps" in errors[0]

    @pytest.mark.parametrize("claimed", [True, False])
    def test_empty_steps_makes_result_invalid(self, schema, valid_result, claimed):
        data = deepcopy(valid_result)
        data["verification"]["steps"] = []
        data["verification"]["passed"] = claimed
        results = validate_result(data, schema)
        assert results["valid"] is False
        check = results["checks"]["verification_consistency"]
        assert check["passed"] is False
        assert any("no verification steps" in e for e in check["errors"])

    def test_empty_steps_invalid_even_with_loose_schema(self, valid_result):
        data = deepcopy(valid_result)
        data["verification"]["steps"] = []
        results = validate_result(data, {"type": "object"})
        assert results["checks"]["schema"]["passed"] is True
        assert results["valid"] is False

    def test_not_run_step_claiming_pass_is_rejected(self, valid_result):
        data = deepcopy(valid_result)
        data["verification"]["steps"][0]["method"] = "not_run"
        errors = validate_verification_consistency(data)
        assert len(errors) == 1
        assert "unit-tests" in errors[0]
        assert "not_run" in errors[0]

    def test_not_run_step_failing_is_consistent(self, valid_result):
        data = deepcopy(valid_result)
        data["verification"]["passed"] = False
        data["verification"]["steps"][0]["passed"] = False
        data["verification"]["steps"][0]["method"] = "not_run"
        assert validate_verification_consistency(data) == []

    def test_nonzero_exit_code_claiming_pass_is_rejected(self, schema, valid_result):
        data = deepcopy(valid_result)
        data["verification"]["steps"][0]["exit_code"] = 1
        errors = validate_verification_consistency(data)
        assert len(errors) == 1
        assert "unit-tests" in errors[0]
        assert "exit_code=1" in errors[0]
        assert validate_result(data, schema)["valid"] is False

    def test_nonzero_exit_code_failing_is_consistent(self, valid_result):
        data = deepcopy(valid_result)
        data["verification"]["passed"] = False
        data["verification"]["steps"][0]["exit_code"] = 2
        data["verification"]["steps"][0]["passed"] = False
        assert validate_verification_consistency(data) == []

    @pytest.mark.parametrize("kind", ["command", "manual"])
    def test_empty_evidence_claiming_pass_is_rejected(
        self, schema, valid_result, kind,
    ):
        data = deepcopy(valid_result)
        step = data["verification"]["steps"][0]
        step["evidence"] = {"artifacts": [], "metrics": {}}
        if kind == "manual":
            for key in ("command", "exit_code"):
                step.pop(key)
            step["kind"] = "manual"
            step["manual"] = {"instructions": "look at it"}
        errors = validate_verification_consistency(data)
        assert len(errors) == 1
        assert "unit-tests" in errors[0]
        assert "no evidence" in errors[0]
        assert validate_result(data, schema)["valid"] is False

    @pytest.mark.parametrize(
        "evidence",
        [
            {"artifacts": ["artifacts/pytest.xml"], "metrics": {}},
            {"artifacts": [], "metrics": {"test_count": 3}},
        ],
    )
    def test_any_artifact_or_metric_is_evidence(self, valid_result, evidence):
        data = deepcopy(valid_result)
        data["verification"]["steps"][0]["evidence"] = evidence
        assert validate_verification_consistency(data) == []

    def test_empty_evidence_failing_is_consistent(self, valid_result):
        data = deepcopy(valid_result)
        data["verification"]["passed"] = False
        data["verification"]["steps"][0]["passed"] = False
        data["verification"]["steps"][0]["exit_code"] = 1
        data["verification"]["steps"][0]["evidence"] = {"artifacts": [], "metrics": {}}
        assert validate_verification_consistency(data) == []


# --- Commit resolution ---


def _git(cwd: Path, *args: str) -> str:
    import subprocess

    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
    ).stdout.strip()


PACKAGE_BRANCH = "openspec/feat-test"


def _commit(path: Path, name: str) -> str:
    (path / name).write_text(f"{name}\n")
    _git(path, "add", name)
    _git(path, "commit", "-q", "-m", name)
    return _git(path, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    """A package worktree: a base commit on ``main`` and one package commit on
    ``PACKAGE_BRANCH`` (checked out); returns (path, package_head_sha)."""
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "-q")
    _git(path, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(path, "config", "user.email", "test@example.invalid")
    _git(path, "config", "user.name", "Test")
    _commit(path, "README")
    _git(path, "checkout", "-q", "-b", PACKAGE_BRANCH)
    return path, _commit(path, "work")


ABSENT_SHA = "0123456789abcdef0123456789abcdef01234567"


class TestCommitResolves:
    def test_head_commit_passes(self, repo, valid_result):
        path, sha = repo
        data = deepcopy(valid_result)
        data["git"]["head"]["commit"] = sha
        check = validate_commit_resolves(data, path)
        assert check["passed"] is True
        assert check["errors"] == []

    def test_abbreviated_head_commit_passes(self, repo, valid_result):
        path, sha = repo
        data = deepcopy(valid_result)
        data["git"]["head"]["commit"] = sha[:10]
        assert validate_commit_resolves(data, path)["passed"] is True

    def test_absent_commit_fails(self, schema, repo, valid_result):
        path, _ = repo
        data = deepcopy(valid_result)
        data["git"]["head"]["commit"] = ABSENT_SHA
        results = validate_result(data, schema, worktree_path=path)
        check = results["checks"]["commit_resolves"]
        assert check["passed"] is False
        assert ABSENT_SHA in check["errors"][0]
        assert str(path) in check["errors"][0]
        assert results["valid"] is False

    def test_present_commit_keeps_result_valid(self, schema, repo, valid_result):
        path, sha = repo
        data = deepcopy(valid_result)
        data["git"]["head"]["commit"] = sha
        results = validate_result(data, schema, worktree_path=path)
        assert results["checks"]["commit_resolves"]["passed"] is True
        assert results["checks"]["commit_resolves"].get("skipped") is not True
        assert results["valid"] is True

    def test_non_repository_directory_fails(self, tmp_path, valid_result):
        plain = tmp_path / "plain"
        plain.mkdir()
        check = validate_commit_resolves(deepcopy(valid_result), plain)
        assert check["passed"] is False
        assert str(plain) in check["errors"][0]

    def test_inherited_git_dir_does_not_redirect_the_check(
        self, tmp_path, monkeypatch, valid_result
    ):
        # A GIT_DIR inherited from the caller (as inside a git hook) must not
        # make the check resolve the commit in a repository other than the
        # worktree it names.
        other = tmp_path / "other"
        other.mkdir()
        _git(other, "init", "-q")
        _git(other, "config", "user.email", "test@example.invalid")
        _git(other, "config", "user.name", "Test")
        (other / "README").write_text("other\n")
        _git(other, "add", "README")
        _git(other, "commit", "-q", "-m", "other")
        other_sha = _git(other, "rev-parse", "HEAD")
        plain = tmp_path / "plain"
        plain.mkdir()
        monkeypatch.setenv("GIT_DIR", str(other / ".git"))
        data = deepcopy(valid_result)
        data["git"]["head"]["commit"] = other_sha
        check = validate_commit_resolves(data, plain)
        assert check["passed"] is False
        assert str(plain) in check["errors"][0]

    def test_missing_directory_fails(self, tmp_path, valid_result):
        missing = tmp_path / "missing"
        check = validate_commit_resolves(deepcopy(valid_result), missing)
        assert check["passed"] is False
        assert str(missing) in check["errors"][0]

    @pytest.mark.parametrize("commit", ["--help", "HEAD", "abc", "", None])
    def test_non_hex_commit_fails_without_invoking_git(
        self, monkeypatch, repo, valid_result, commit,
    ):
        path, _ = repo

        def _forbidden(*args, **kwargs):
            raise AssertionError("git must not be invoked for a non-hex commit")

        monkeypatch.setattr(validate_work_result.subprocess, "run", _forbidden)
        data = deepcopy(valid_result)
        data["git"]["head"]["commit"] = commit
        check = validate_commit_resolves(data, path)
        assert check["passed"] is False
        assert check["errors"]

    def test_no_worktree_records_skipped(self, schema, valid_result):
        results = validate_result(deepcopy(valid_result), schema)
        check = results["checks"]["commit_resolves"]
        assert check["skipped"] is True
        assert check["passed"] is True
        assert check["errors"] == []
        assert "no worktree_path" in check["reason"]
        assert results["valid"] is True

    def test_commit_on_another_branch_is_not_reachable(self, repo, valid_result):
        path, _ = repo
        _git(path, "checkout", "-q", "-b", "elsewhere", "main")
        other = _commit(path, "elsewhere")
        _git(path, "checkout", "-q", PACKAGE_BRANCH)
        data = deepcopy(valid_result)
        data["git"]["head"]["commit"] = other
        check = validate_commit_resolves(data, path)
        assert check["passed"] is False
        assert "not reachable" in check["errors"][0]
        assert PACKAGE_BRANCH in check["errors"][0]

    def test_unreported_branch_checks_the_worktree_head(self, repo, valid_result):
        path, sha = repo
        _git(path, "checkout", "-q", "-b", "elsewhere", "main")
        other = _commit(path, "elsewhere")
        _git(path, "checkout", "-q", PACKAGE_BRANCH)
        data = deepcopy(valid_result)
        del data["git"]["head"]["branch"]
        data["git"]["head"]["commit"] = other
        check = validate_commit_resolves(data, path)
        assert check["passed"] is False
        assert "HEAD" in check["errors"][0]
        data["git"]["head"]["commit"] = sha
        assert validate_commit_resolves(data, path)["passed"] is True

    def test_dangling_commit_is_not_reachable(self, repo, valid_result):
        path, _ = repo
        dangling = _commit(path, "dangling")
        _git(path, "reset", "-q", "--hard", "HEAD~1")
        data = deepcopy(valid_result)
        data["git"]["head"]["commit"] = dangling
        check = validate_commit_resolves(data, path)
        assert check["passed"] is False
        assert "not reachable" in check["errors"][0]

    def test_head_equal_to_base_is_refused(self, schema, repo, valid_result):
        path, _ = repo
        base = _git(path, "rev-parse", "main")
        _git(path, "reset", "-q", "--hard", "main")  # the branch holds no commit
        data = deepcopy(valid_result)
        data["git"]["head"]["commit"] = base
        results = validate_result(data, schema, worktree_path=path)
        check = results["checks"]["commit_resolves"]
        assert check["passed"] is False
        assert "made no commit" in check["errors"][0]
        assert results["valid"] is False

    def test_unresolvable_base_ref_fails(self, repo, valid_result):
        path, sha = repo
        data = deepcopy(valid_result)
        data["git"]["head"]["commit"] = sha
        data["git"]["base"]["ref"] = "no-such-base"
        check = validate_commit_resolves(data, path)
        assert check["passed"] is False
        assert "no-such-base" in check["errors"][0]

    def test_unresolvable_branch_fails(self, repo, valid_result):
        path, sha = repo
        data = deepcopy(valid_result)
        data["git"]["head"]["commit"] = sha
        data["git"]["head"]["branch"] = "no-such-branch"
        check = validate_commit_resolves(data, path)
        assert check["passed"] is False
        assert "no-such-branch" in check["errors"][0]

    def test_option_like_base_ref_fails_without_invoking_git(
        self, monkeypatch, repo, valid_result,
    ):
        path, sha = repo

        def _forbidden(*args, **kwargs):
            raise AssertionError("git must not be invoked for an option-like ref")

        monkeypatch.setattr(validate_work_result.subprocess, "run", _forbidden)
        data = deepcopy(valid_result)
        data["git"]["head"]["commit"] = sha
        data["git"]["base"]["ref"] = "--output=x"
        check = validate_commit_resolves(data, path)
        assert check["passed"] is False


# --- Outcome derivation and consistency ---


class TestOutcome:
    def test_completed_with_passing_steps_derives_pass(self, valid_result):
        assert derive_outcome(valid_result) == "PASS"

    def test_failed_status_derives_blocked(self, valid_result):
        data = deepcopy(valid_result)
        data["status"] = "failed"
        assert derive_outcome(data) == "BLOCKED"

    def test_failing_step_derives_issues(self, valid_result):
        data = deepcopy(valid_result)
        data["verification"]["passed"] = False
        data["verification"]["steps"][0]["passed"] = False
        assert derive_outcome(data) == "ISSUES"

    def test_empty_steps_derives_issues(self, valid_result):
        data = deepcopy(valid_result)
        data["verification"]["steps"] = []
        assert derive_outcome(data) == "ISSUES"

    def test_verification_passed_false_derives_issues(self, valid_result):
        data = deepcopy(valid_result)
        data["verification"]["passed"] = False
        assert derive_outcome(data) == "ISSUES"

    def test_failed_scope_check_derives_issues(self, valid_result):
        data = deepcopy(valid_result)
        data["scope_check"] = {"passed": False, "violations": ["x.py"]}
        assert derive_outcome(data) == "ISSUES"

    def test_passing_scope_check_still_pass(self, valid_result):
        data = deepcopy(valid_result)
        data["scope_check"] = {"passed": True, "violations": []}
        assert derive_outcome(data) == "PASS"

    def test_effective_outcome_prefers_explicit(self, valid_result):
        data = deepcopy(valid_result)
        data["outcome"] = "ISSUES"
        assert effective_outcome(data) == "ISSUES"
        del data["outcome"]
        assert effective_outcome(data) == "PASS"

    @pytest.mark.parametrize("contradiction", ["failing_step", "scope", "failed"])
    def test_pass_contradicted_by_evidence_is_error(
        self, schema, valid_result, contradiction,
    ):
        data = deepcopy(valid_result)
        data["outcome"] = "PASS"
        if contradiction == "failing_step":
            data["verification"]["passed"] = False
            data["verification"]["steps"][0]["passed"] = False
        elif contradiction == "scope":
            data["scope_check"] = {"passed": False, "violations": ["x.py"]}
        else:
            data["status"] = "failed"
        errors = validate_outcome_consistency(data)
        assert errors
        assert any("outcome" in e for e in errors)
        results = validate_result(data, schema)
        assert results["checks"]["outcome_consistency"]["passed"] is False
        assert results["valid"] is False

    def test_failed_status_with_issues_outcome_is_error(self, valid_result):
        data = deepcopy(valid_result)
        data["status"] = "failed"
        data["outcome"] = "ISSUES"
        errors = validate_outcome_consistency(data)
        assert any("BLOCKED" in e for e in errors)

    def test_failed_status_with_blocked_outcome_is_consistent(self, valid_result):
        data = deepcopy(valid_result)
        data["status"] = "failed"
        data["outcome"] = "BLOCKED"
        assert validate_outcome_consistency(data) == []

    @pytest.mark.parametrize("downgrade", ["ISSUES", "BLOCKED"])
    def test_downgrade_over_passing_evidence_is_allowed(
        self, schema, valid_result, downgrade,
    ):
        data = deepcopy(valid_result)
        data["outcome"] = downgrade
        assert validate_outcome_consistency(data) == []
        results = validate_result(data, schema)
        assert results["valid"] is True
        assert effective_outcome(data) == downgrade

    def test_legacy_result_without_new_fields(self, schema, valid_result):
        assert "outcome" not in valid_result
        assert "method" not in valid_result["verification"]["steps"][0]
        assert validate_schema(valid_result, schema) == []
        assert validate_outcome_consistency(valid_result) == []
        assert effective_outcome(valid_result) == "PASS"


class TestOutcomeSchemaFields:
    @pytest.mark.parametrize("outcome", ["PASS", "ISSUES", "BLOCKED"])
    def test_outcome_values_accepted(self, schema, valid_result, outcome):
        data = deepcopy(valid_result)
        data["outcome"] = outcome
        assert validate_schema(data, schema) == []

    def test_unknown_outcome_rejected(self, schema, valid_result):
        data = deepcopy(valid_result)
        data["outcome"] = "MAYBE"
        assert validate_schema(data, schema)

    @pytest.mark.parametrize("method", ["executed", "ci", "inspected", "not_run"])
    def test_method_values_accepted(self, schema, valid_result, method):
        data = deepcopy(valid_result)
        data["verification"]["steps"][0]["method"] = method
        assert validate_schema(data, schema) == []

    def test_unknown_method_rejected(self, schema, valid_result):
        data = deepcopy(valid_result)
        data["verification"]["steps"][0]["method"] = "guessed"
        assert validate_schema(data, schema)

    def test_schema_version_still_one(self, schema):
        assert schema["properties"]["schema_version"]["const"] == 1


# --- CLI --worktree ---


class TestCLIWorktree:
    def _run(self, *args: str):
        import subprocess

        return subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parent.parent / "validate_work_result.py"),
                *args,
            ],
            capture_output=True,
            text=True,
        )

    def test_absent_commit_exits_one(self, tmp_path, repo, valid_result):
        path, _ = repo
        data = deepcopy(valid_result)
        data["git"]["head"]["commit"] = ABSENT_SHA
        result_file = tmp_path / "result.json"
        result_file.write_text(json.dumps(data))
        proc = self._run(str(result_file), "--worktree", str(path))
        assert proc.returncode == 1
        assert "commit_resolves" in proc.stdout
        assert "FAIL" in proc.stdout

    def test_present_commit_exits_zero(self, tmp_path, repo, valid_result):
        path, sha = repo
        data = deepcopy(valid_result)
        data["git"]["head"]["commit"] = sha
        result_file = tmp_path / "result.json"
        result_file.write_text(json.dumps(data))
        proc = self._run(str(result_file), "--worktree", str(path), "--json")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert json.loads(proc.stdout)["checks"]["commit_resolves"]["passed"] is True
