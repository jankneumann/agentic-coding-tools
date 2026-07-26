"""Enforcement tests for the context-impact gate (ri-08).

One test per row of design decision D3's enforcement table, plus the CLI
surface. The CLI is exercised with explicit ``--changed-file`` arguments rather
than a git range so these run without a repository; the git path is what
``--base`` adds on top.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from wp_fixtures import SCRIPTS_DIR, minimal_document, minimal_package

from context_impact import load_rules
from validate_context_impact import evaluate

CLI = SCRIPTS_DIR / "validate_context_impact.py"

DOC_FILE = "docs/guides/workflow.md"
CODE_FILE = "agent-coordinator/src/service.py"


@pytest.fixture(scope="module")
def rules():
    return load_rules()


def _package(**context_impact):
    """A package whose write scope covers everything, so scope never masks."""
    kwargs = {"scope": {"write_allow": ["**"], "read_allow": ["**"]}}
    if context_impact:
        kwargs["context_impact"] = context_impact
    return minimal_package(**kwargs)


class TestEnforcementTable:
    def test_declared_surface_passes(self, rules):
        package = _package(surfaces=["documentation"])
        result = evaluate(package, [DOC_FILE], rules)
        assert result.status == "declared"
        assert not result.failed

    def test_undeclared_implied_surface_fails(self, rules):
        package = _package(surfaces=["apis"])
        result = evaluate(package, [DOC_FILE], rules)
        assert result.status == "undeclared"
        assert result.failed
        assert "documentation" in result.undeclared

    def test_the_failure_names_the_files_that_implied_the_surface(self, rules):
        package = _package(surfaces=[])
        result = evaluate(package, [DOC_FILE], rules)
        assert DOC_FILE in result.implied["documentation"]

    def test_an_approved_rationale_permits_omission(self, rules):
        package = _package(
            surfaces=[],
            rationale={
                "documentation": {
                    "reason": "Guide reformatting only.",
                    "approved_by": "jankneumann",
                }
            },
        )
        result = evaluate(package, [DOC_FILE], rules)
        assert result.status == "rationalized"
        assert not result.failed
        assert "documentation" in result.rationalized

    def test_a_rationale_for_a_surface_that_is_not_implied_fails(self, rules):
        package = _package(
            surfaces=["documentation"],
            rationale={
                "apis": {"reason": "Not an API change.", "approved_by": "jankneumann"}
            },
        )
        result = evaluate(package, [DOC_FILE], rules)
        assert result.status == "spurious_rationale"
        assert result.failed
        assert "apis" in result.spurious

    def test_an_empty_declaration_is_strict_not_unmigrated(self, rules):
        package = _package(surfaces=[])
        result = evaluate(package, [DOC_FILE], rules)
        assert result.status == "undeclared"
        assert result.failed

    def test_an_empty_declaration_with_no_impact_passes(self, rules):
        package = _package(surfaces=[])
        result = evaluate(package, [], rules)
        assert result.status == "declared"
        assert not result.failed

    def test_a_package_without_the_block_is_unmigrated(self, rules):
        result = evaluate(_package(), [DOC_FILE], rules)
        assert result.status == "unmigrated"
        assert not result.failed

    def test_an_unmigrated_package_reports_the_inferred_surfaces(self, rules):
        result = evaluate(_package(), [DOC_FILE, CODE_FILE], rules)
        assert {"documentation", "semantic_code"} <= set(result.implied)

    def test_an_unmigrated_package_fails_under_strict_legacy(self, rules):
        result = evaluate(_package(), [DOC_FILE], rules)
        assert result.failed_under(strict_legacy=True)

    def test_undeclared_outranks_spurious_when_both_apply(self, rules):
        package = _package(
            surfaces=[],
            rationale={
                "apis": {"reason": "Not an API change.", "approved_by": "jankneumann"}
            },
        )
        result = evaluate(package, [DOC_FILE], rules)
        assert result.status == "undeclared"
        assert "documentation" in result.undeclared
        assert "apis" in result.spurious


class TestScopeInteraction:
    def test_a_file_outside_write_allow_does_not_trigger_the_gate(self, rules):
        package = minimal_package(
            scope={"write_allow": ["agent-coordinator/**"], "read_allow": ["**"]},
            context_impact={"surfaces": []},
        )
        result = evaluate(package, [DOC_FILE], rules)
        assert result.status == "declared"

    def test_a_contract_file_implies_apis_for_the_gate(self, rules):
        package = minimal_package(
            scope={"write_allow": ["contracts/**"], "read_allow": ["**"]},
            context_impact={"surfaces": []},
        )
        result = evaluate(
            package,
            ["contracts/openapi/v1.yaml"],
            rules,
            contract_files=["contracts/openapi/v1.yaml"],
        )
        assert result.status == "undeclared"
        assert "apis" in result.undeclared


def _write_doc(tmp_path: Path, *packages) -> Path:
    path = tmp_path / "work-packages.yaml"
    path.write_text(yaml.safe_dump(minimal_document(*packages), sort_keys=False))
    return path


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args], capture_output=True, text=True, check=False
    )


class TestCli:
    def test_a_declared_package_exits_zero(self, tmp_path):
        doc = _write_doc(tmp_path, _package(surfaces=["documentation"]))
        result = _run(str(doc), "--changed-file", DOC_FILE)
        assert result.returncode == 0, result.stderr

    def test_an_undeclared_package_exits_one(self, tmp_path):
        doc = _write_doc(tmp_path, _package(surfaces=["apis"]))
        result = _run(str(doc), "--changed-file", DOC_FILE)
        assert result.returncode == 1
        assert "documentation" in result.stdout + result.stderr

    def test_an_unmigrated_package_exits_zero_by_default(self, tmp_path):
        doc = _write_doc(tmp_path, _package())
        result = _run(str(doc), "--changed-file", DOC_FILE)
        assert result.returncode == 0, result.stderr
        assert "unmigrated" in result.stdout

    def test_an_unmigrated_package_exits_one_under_strict_legacy(self, tmp_path):
        doc = _write_doc(tmp_path, _package())
        result = _run(str(doc), "--changed-file", DOC_FILE, "--strict-legacy")
        assert result.returncode == 1

    def test_json_output_is_machine_readable(self, tmp_path):
        doc = _write_doc(tmp_path, _package(surfaces=["apis"]))
        result = _run(str(doc), "--changed-file", DOC_FILE, "--json")
        payload = json.loads(result.stdout)
        assert payload["exit_code"] == 1
        entry = payload["packages"][0]
        assert entry["package_id"] == "wp-example"
        assert entry["status"] == "undeclared"
        assert entry["undeclared"] == ["documentation"]
        assert entry["implied"]["documentation"] == [DOC_FILE]

    def test_no_changed_files_passes(self, tmp_path):
        doc = _write_doc(tmp_path, _package(surfaces=[]))
        result = _run(str(doc), "--json")
        assert result.returncode == 0, result.stderr

    def test_a_missing_work_packages_file_is_an_error(self, tmp_path):
        result = _run(str(tmp_path / "absent.yaml"), "--changed-file", DOC_FILE)
        assert result.returncode != 0
        assert "not found" in (result.stdout + result.stderr).lower()

    def test_base_and_changed_file_are_mutually_exclusive(self, tmp_path):
        doc = _write_doc(tmp_path, _package(surfaces=[]))
        result = _run(str(doc), "--base", "main", "--changed-file", DOC_FILE)
        assert result.returncode != 0
