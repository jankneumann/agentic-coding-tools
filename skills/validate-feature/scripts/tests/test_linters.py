"""Tests for structural architecture linters — dependency direction, file-size, naming conventions.

TDD tests written before implementation (task 4.1).
Tests cover:
- Dependency direction: skills must not import from agent-coordinator internals
- File size: files exceeding configured max line count are flagged
- Naming conventions: skill dirs (kebab-case), scripts (snake_case .py), schemas (kebab-case .json/.yaml)
- run_all_linters orchestrator function
- Review-findings schema conformance
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema
import pytest

# Ensure scripts dir is importable
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from linters import run_all_linters  # noqa: E402
from linters.dependency_direction import check_dependency_direction  # noqa: E402
from linters.file_size import check_file_size  # noqa: E402
from linters.naming_conventions import check_naming_conventions  # noqa: E402

# Path to the review-findings schema for validation.
# Resolved by walking up to the repo root rather than a fixed parent index —
# the previous fixed index pointed above the repo, and because nothing ever
# called the loader the broken path went unnoticed.
_SCHEMA_RELATIVE = Path("openspec") / "schemas" / "review-findings.schema.json"


def _resolve_schema_path() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / _SCHEMA_RELATIVE
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Could not locate {_SCHEMA_RELATIVE} above {__file__}")


_SCHEMA_PATH = _resolve_schema_path()


def _load_review_findings_schema() -> dict[str, Any]:
    """Load the review-findings JSON schema."""
    with open(_SCHEMA_PATH) as f:
        return json.load(f)


def _as_review_document(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap bare linter findings in a review-findings envelope for validation."""
    return {
        "review_type": "implementation",
        "target": "wp-architecture-linters",
        "reviewer_vendor": "structural-linter",
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# Dependency Direction Linter
# ---------------------------------------------------------------------------


class TestDependencyDirection:
    """Test dependency direction enforcement: skills must not import coordinator internals."""

    def test_valid_import_passes(self, tmp_path: Path) -> None:
        """A skill file with normal stdlib/third-party imports should produce no findings."""
        skill_file = tmp_path / "skills" / "my-skill" / "scripts" / "helper.py"
        skill_file.parent.mkdir(parents=True)
        skill_file.write_text(
            "import os\n"
            "import json\n"
            "from pathlib import Path\n"
            "from skills.shared.utils import some_helper\n"
        )

        findings = check_dependency_direction([str(skill_file)])
        assert findings == []

    def test_direct_import_from_coordinator_src_fails(self, tmp_path: Path) -> None:
        """Importing from agent-coordinator/src should produce a finding with remediation."""
        skill_file = tmp_path / "skills" / "my-skill" / "scripts" / "bad_import.py"
        skill_file.parent.mkdir(parents=True)
        skill_file.write_text(
            "import os\n"
            "from agent_coordinator.src.locks import acquire_lock\n"
            "print('hello')\n"
        )

        findings = check_dependency_direction([str(skill_file)])
        assert len(findings) == 1

        finding = findings[0]
        assert finding["type"] == "architecture"
        assert finding["criticality"] == "high"
        assert finding["disposition"] == "fix"
        assert "agent_coordinator" in finding["description"] or "agent-coordinator" in finding["description"]
        assert finding["file_path"] == str(skill_file)
        assert finding["line_range"]["start"] == 2
        assert finding["line_range"]["end"] == 2
        # Must include remediation
        assert "resolution" in finding
        assert len(finding["resolution"]) > 0
        assert "MCP" in finding["resolution"] or "HTTP" in finding["resolution"] or "API" in finding["resolution"]

    def test_from_src_dot_import_in_skill_fails(self, tmp_path: Path) -> None:
        """'from src.' import inside a skills/ file should be flagged."""
        skill_file = tmp_path / "skills" / "another-skill" / "scripts" / "runner.py"
        skill_file.parent.mkdir(parents=True)
        skill_file.write_text(
            "from src.memory import MemoryService\n"
        )

        findings = check_dependency_direction([str(skill_file)])
        assert len(findings) == 1
        assert findings[0]["line_range"]["start"] == 1

    def test_import_agent_coordinator_module_fails(self, tmp_path: Path) -> None:
        """'import agent_coordinator' should be flagged in skills files."""
        skill_file = tmp_path / "skills" / "test-skill" / "scripts" / "do_thing.py"
        skill_file.parent.mkdir(parents=True)
        skill_file.write_text(
            "import agent_coordinator\n"
            "result = agent_coordinator.some_function()\n"
        )

        findings = check_dependency_direction([str(skill_file)])
        assert len(findings) == 1

    def test_non_skill_file_is_ignored(self, tmp_path: Path) -> None:
        """Files outside skills/ should not be checked."""
        non_skill_file = tmp_path / "agent-coordinator" / "src" / "internal.py"
        non_skill_file.parent.mkdir(parents=True)
        non_skill_file.write_text(
            "from src.memory import MemoryService\n"
        )

        findings = check_dependency_direction([str(non_skill_file)])
        assert findings == []

    def test_skills_shared_import_is_allowed(self, tmp_path: Path) -> None:
        """Importing from skills/shared/ is allowed."""
        skill_file = tmp_path / "skills" / "my-skill" / "scripts" / "okay.py"
        skill_file.parent.mkdir(parents=True)
        skill_file.write_text(
            "from skills.shared.environment_profile import detect\n"
        )

        findings = check_dependency_direction([str(skill_file)])
        assert findings == []

    def test_multiple_violations_in_one_file(self, tmp_path: Path) -> None:
        """Multiple bad imports produce multiple findings."""
        skill_file = tmp_path / "skills" / "bad-skill" / "scripts" / "many_bad.py"
        skill_file.parent.mkdir(parents=True)
        skill_file.write_text(
            "import os\n"
            "from agent_coordinator.src.locks import acquire_lock\n"
            "from agent_coordinator.src.memory import MemoryService\n"
            "print('hello')\n"
        )

        findings = check_dependency_direction([str(skill_file)])
        assert len(findings) == 2
        assert findings[0]["line_range"]["start"] == 2
        assert findings[1]["line_range"]["start"] == 3

    @pytest.mark.parametrize(
        ("suffix", "content", "needle"),
        [
            (".py", 'sys.path.insert(0, str(root / "agent-coordinator"))\n', "agent-coordinator"),
            (".py", 'subprocess.run(["python", "-c", "from src.agents_config import load"])\n', "src"),
            (".sh", 'python3 skills/validate-feature/scripts/phase_smoke.py\n', "canonical skills/"),
            (".json", '{"command": "python3 skills/langfuse/scripts/hook.py"}\n', "canonical skills/"),
            (".md", 'Run `skills/.venv/bin/python <skill-base-dir>/scripts/check.py`.\n', "skills/.venv"),
            (".sh", '$REPO_ROOT/skills/.venv/bin/python check.py\n', "skills/.venv"),
            (".md", 'Run `bash skills/install.sh`.\n', "canonical skills/"),
            (".md", 'Run `python3 skills/shared/active_agents.py`.\n', "canonical skills/"),
        ],
    )
    def test_installed_payload_escape_patterns_fail(
        self, tmp_path: Path, suffix: str, content: str, needle: str
    ) -> None:
        skill_file = tmp_path / "skills" / "portable-skill" / f"runtime{suffix}"
        skill_file.parent.mkdir(parents=True)
        skill_file.write_text(content)

        findings = check_dependency_direction([str(skill_file)])

        assert len(findings) == 1
        assert needle in findings[0]["description"]

    def test_installed_sibling_and_explicit_project_paths_pass(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "skills" / "portable-skill" / "SKILL.md"
        skill_file.parent.mkdir(parents=True)
        skill_file.write_text(
            'python3 "<skill-base-dir>/../worktree/scripts/worktree.py" list\n'
            'python3 "<project-root>/scripts/project_check.py"\n'
        )

        assert check_dependency_direction([str(skill_file)]) == []

    def test_explicit_source_contribution_command_passes(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "skills" / "portable-skill" / "SKILL.md"
        skill_file.parent.mkdir(parents=True)
        skill_file.write_text(
            "Test (**source-contribution-only**): `skills/.venv/bin/python -m pytest`\n"
        )
        assert check_dependency_direction([str(skill_file)]) == []


# ---------------------------------------------------------------------------
# File Size Linter
# ---------------------------------------------------------------------------


class TestFileSize:
    """Test file size enforcement."""

    def test_file_under_limit_passes(self, tmp_path: Path) -> None:
        """A file under the max line count should produce no findings."""
        small_file = tmp_path / "small.py"
        small_file.write_text("line\n" * 100)

        findings = check_file_size([str(small_file)], max_lines=500)
        assert findings == []

    def test_file_over_limit_fails(self, tmp_path: Path) -> None:
        """A file over the max line count should produce a finding with decomposition suggestion."""
        big_file = tmp_path / "big.py"
        big_file.write_text("line\n" * 600)

        findings = check_file_size([str(big_file)], max_lines=500)
        assert len(findings) == 1

        finding = findings[0]
        assert finding["type"] == "architecture"
        assert finding["criticality"] == "medium"
        assert finding["disposition"] == "fix"
        assert "600" in finding["description"]
        assert "500" in finding["description"]
        assert finding["file_path"] == str(big_file)
        # Should suggest decomposition
        assert "split" in finding["resolution"].lower() or "decompos" in finding["resolution"].lower() or "module" in finding["resolution"].lower()

    def test_file_at_exact_limit_passes(self, tmp_path: Path) -> None:
        """A file at exactly the max line count should pass."""
        exact_file = tmp_path / "exact.py"
        exact_file.write_text("line\n" * 500)

        findings = check_file_size([str(exact_file)], max_lines=500)
        assert findings == []

    def test_custom_max_lines(self, tmp_path: Path) -> None:
        """Custom max_lines should be respected."""
        file_200 = tmp_path / "medium.py"
        file_200.write_text("line\n" * 200)

        # At 300 limit -> passes
        assert check_file_size([str(file_200)], max_lines=300) == []
        # At 150 limit -> fails
        findings = check_file_size([str(file_200)], max_lines=150)
        assert len(findings) == 1

    def test_default_max_lines_is_500(self, tmp_path: Path) -> None:
        """Default max should be 500 lines."""
        file_501 = tmp_path / "just_over.py"
        file_501.write_text("line\n" * 501)

        findings = check_file_size([str(file_501)])
        assert len(findings) == 1

        file_500 = tmp_path / "just_right.py"
        file_500.write_text("line\n" * 500)

        findings = check_file_size([str(file_500)])
        assert findings == []

    def test_nonexistent_file_is_skipped(self) -> None:
        """Nonexistent files should be silently skipped."""
        findings = check_file_size(["/nonexistent/file.py"])
        assert findings == []

    def test_line_range_covers_entire_file(self, tmp_path: Path) -> None:
        """Line range should cover from 1 to the file's line count."""
        big_file = tmp_path / "big.py"
        big_file.write_text("line\n" * 600)

        findings = check_file_size([str(big_file)], max_lines=500)
        assert findings[0]["line_range"]["start"] == 1
        assert findings[0]["line_range"]["end"] == 600


# ---------------------------------------------------------------------------
# Naming Conventions Linter
# ---------------------------------------------------------------------------


class TestNamingConventions:
    """Test naming convention enforcement."""

    def test_correct_skill_directory_passes(self, tmp_path: Path) -> None:
        """kebab-case skill directories should pass."""
        skill_file = tmp_path / "skills" / "my-awesome-skill" / "scripts" / "helper.py"
        skill_file.parent.mkdir(parents=True)
        skill_file.write_text("")

        findings = check_naming_conventions([str(skill_file)])
        assert findings == []

    def test_underscore_skill_directory_fails(self, tmp_path: Path) -> None:
        """snake_case skill directories should fail with correct pattern in message."""
        skill_file = tmp_path / "skills" / "my_bad_skill" / "scripts" / "helper.py"
        skill_file.parent.mkdir(parents=True)
        skill_file.write_text("")

        findings = check_naming_conventions([str(skill_file)])
        assert len(findings) >= 1

        dir_finding = [f for f in findings if "directory" in f["description"].lower() or "skill" in f["description"].lower()]
        assert len(dir_finding) >= 1
        finding = dir_finding[0]
        assert finding["type"] == "architecture"
        assert finding["disposition"] == "fix"
        # Must mention kebab-case pattern
        assert "kebab" in finding["resolution"].lower() or "kebab-case" in finding["resolution"].lower()

    def test_correct_script_file_passes(self, tmp_path: Path) -> None:
        """snake_case .py files should pass."""
        script = tmp_path / "skills" / "my-skill" / "scripts" / "analyze_failures.py"
        script.parent.mkdir(parents=True)
        script.write_text("")

        findings = check_naming_conventions([str(script)])
        assert findings == []

    def test_kebab_case_script_file_fails(self, tmp_path: Path) -> None:
        """kebab-case .py files should fail."""
        script = tmp_path / "skills" / "my-skill" / "scripts" / "analyze-failures.py"
        script.parent.mkdir(parents=True)
        script.write_text("")

        findings = check_naming_conventions([str(script)])
        assert len(findings) >= 1

        script_findings = [f for f in findings if "script" in f["description"].lower() or ".py" in f["description"].lower()]
        assert len(script_findings) >= 1
        finding = script_findings[0]
        assert finding["type"] == "architecture"
        assert "snake_case" in finding["resolution"].lower() or "snake" in finding["resolution"].lower()

    def test_correct_schema_file_passes(self, tmp_path: Path) -> None:
        """kebab-case .json and .yaml schema files should pass."""
        schema_json = tmp_path / "openspec" / "schemas" / "review-findings.schema.json"
        schema_json.parent.mkdir(parents=True)
        schema_json.write_text("{}")

        findings = check_naming_conventions([str(schema_json)])
        assert findings == []

    def test_underscore_schema_file_fails(self, tmp_path: Path) -> None:
        """snake_case schema files should fail."""
        schema_json = tmp_path / "openspec" / "schemas" / "review_findings.schema.json"
        schema_json.parent.mkdir(parents=True)
        schema_json.write_text("{}")

        findings = check_naming_conventions([str(schema_json)])
        assert len(findings) >= 1

        schema_findings = [f for f in findings if "schema" in f["description"].lower()]
        assert len(schema_findings) >= 1
        finding = schema_findings[0]
        assert "kebab" in finding["resolution"].lower()

    def test_init_py_passes(self, tmp_path: Path) -> None:
        """__init__.py should not be flagged for naming."""
        init = tmp_path / "skills" / "my-skill" / "scripts" / "__init__.py"
        init.parent.mkdir(parents=True)
        init.write_text("")

        findings = check_naming_conventions([str(init)])
        assert findings == []

    def test_conftest_passes(self, tmp_path: Path) -> None:
        """conftest.py should not be flagged."""
        conftest = tmp_path / "skills" / "my-skill" / "scripts" / "conftest.py"
        conftest.parent.mkdir(parents=True)
        conftest.write_text("")

        findings = check_naming_conventions([str(conftest)])
        assert findings == []

    def test_non_skills_non_schema_file_ignored(self, tmp_path: Path) -> None:
        """Files outside skills/ and schema directories should not be checked for naming."""
        other_file = tmp_path / "docs" / "some-doc.py"
        other_file.parent.mkdir(parents=True)
        other_file.write_text("")

        findings = check_naming_conventions([str(other_file)])
        assert findings == []


# ---------------------------------------------------------------------------
# run_all_linters Orchestrator
# ---------------------------------------------------------------------------


class TestRunAllLinters:
    """Test the run_all_linters orchestrator function."""

    def test_clean_files_return_empty_findings(self, tmp_path: Path) -> None:
        """Files that pass all linters should produce zero findings."""
        good_file = tmp_path / "skills" / "my-skill" / "scripts" / "good_file.py"
        good_file.parent.mkdir(parents=True)
        good_file.write_text("import os\nprint('hello')\n")

        result = run_all_linters([str(good_file)])
        assert result["review_type"] == "implementation"
        assert result["reviewer_vendor"] == "structural-linter"
        assert result["findings"] == []

    def test_combines_findings_from_all_linters(self, tmp_path: Path) -> None:
        """Findings from multiple linters should be combined and have unique ids."""
        # Create a file with both a bad import and exceeding size limit
        bad_file = tmp_path / "skills" / "bad_skill" / "scripts" / "huge-bad.py"
        bad_file.parent.mkdir(parents=True)
        lines = ["from agent_coordinator.src.locks import acquire_lock\n"]
        lines += ["x = 1\n"] * 550
        bad_file.write_text("".join(lines))

        result = run_all_linters([str(bad_file)], config={"max_lines": 500})

        # Should have findings from dependency_direction, file_size, and naming_conventions
        assert len(result["findings"]) >= 3  # at least one per linter

        # All IDs should be unique
        ids = [f["id"] for f in result["findings"]]
        assert len(ids) == len(set(ids))

        # All findings should have the required fields
        for finding in result["findings"]:
            assert "id" in finding
            assert finding["type"] == "architecture"
            assert finding["criticality"] in ("low", "medium", "high", "critical")
            assert finding["disposition"] in ("fix", "regenerate", "accept", "escalate")
            assert "description" in finding
            assert "resolution" in finding
            assert "file_path" in finding
            assert "line_range" in finding

    def test_config_max_lines_passed_through(self, tmp_path: Path) -> None:
        """Config max_lines should be passed to the file_size linter."""
        medium_file = tmp_path / "skills" / "my-skill" / "scripts" / "medium.py"
        medium_file.parent.mkdir(parents=True)
        medium_file.write_text("line\n" * 200)

        # With default 500 limit -> no file_size findings
        result_default = run_all_linters([str(medium_file)])
        size_findings_default = [f for f in result_default["findings"] if "line" in f["description"].lower() and "200" in f["description"]]
        assert size_findings_default == []

        # With 150 limit -> file_size finding
        result_low = run_all_linters([str(medium_file)], config={"max_lines": 150})
        size_findings_low = [f for f in result_low["findings"] if "200" in f["description"]]
        assert len(size_findings_low) == 1

    def test_output_conforms_to_review_findings_schema(self, tmp_path: Path) -> None:
        """Output should have the top-level fields from review-findings schema."""
        good_file = tmp_path / "skills" / "my-skill" / "scripts" / "ok.py"
        good_file.parent.mkdir(parents=True)
        good_file.write_text("import os\n")

        result = run_all_linters([str(good_file)])

        # Required top-level fields
        assert "review_type" in result
        assert "target" in result
        assert "findings" in result
        assert result["review_type"] == "implementation"
        assert isinstance(result["findings"], list)

    def test_target_is_configurable(self, tmp_path: Path) -> None:
        """The target field should be configurable."""
        good_file = tmp_path / "skills" / "my-skill" / "scripts" / "ok.py"
        good_file.parent.mkdir(parents=True)
        good_file.write_text("import os\n")

        result = run_all_linters(
            [str(good_file)],
            config={"target": "wp-custom-target"},
        )
        assert result["target"] == "wp-custom-target"

    def test_empty_file_list(self) -> None:
        """Empty file list should produce empty findings."""
        result = run_all_linters([])
        assert result["findings"] == []


# ---------------------------------------------------------------------------
# Integration: Review-Findings Schema Conformance
# ---------------------------------------------------------------------------


class TestSchemaConformance:
    """Verify linter output conforms to the review-findings JSON schema."""

    def test_finding_has_all_schema_required_fields(self, tmp_path: Path) -> None:
        """Each finding should have all required fields per the schema."""
        bad_file = tmp_path / "skills" / "test-skill" / "scripts" / "bad.py"
        bad_file.parent.mkdir(parents=True)
        bad_file.write_text("from agent_coordinator.src.locks import acquire_lock\n")

        findings = check_dependency_direction([str(bad_file)])
        assert len(findings) == 1

        finding = findings[0]
        # Check required fields from schema
        assert isinstance(finding["id"], int)
        assert finding["type"] in [
            "spec_gap", "contract_mismatch", "architecture", "security",
            "performance", "style", "correctness", "observability",
            "compatibility", "resilience", "behavioral_failure",
            "simplification", "test_quality",
        ]
        assert finding["criticality"] in ["low", "medium", "high", "critical"]
        assert isinstance(finding["description"], str)
        assert isinstance(finding["resolution"], str)
        assert finding["disposition"] in ["fix", "regenerate", "accept", "escalate"]


# ---------------------------------------------------------------------------
# Integration: jsonschema.validate against review-findings.schema.json
#
# The pre-existing conformance tests above hand-check a few keys, which let the
# linters ship findings missing the schema-required `axis` and `severity`
# fields. These tests call jsonschema.validate for real, plus a negative
# control so a vacuously-passing assertion cannot hide the gap again.
# ---------------------------------------------------------------------------


class TestJsonSchemaValidation:
    """Every linter's emitted findings must validate against the schema."""

    def test_dependency_direction_findings_validate(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "skills" / "test-skill" / "scripts" / "bad.py"
        bad_file.parent.mkdir(parents=True)
        bad_file.write_text("from agent_coordinator.src.locks import acquire_lock\n")

        findings = check_dependency_direction([str(bad_file)])
        assert findings, "fixture must produce at least one finding"

        jsonschema.validate(
            instance=_as_review_document(findings),
            schema=_load_review_findings_schema(),
        )

    def test_file_size_findings_validate(self, tmp_path: Path) -> None:
        big_file = tmp_path / "big.py"
        big_file.write_text("line\n" * 600)

        findings = check_file_size([str(big_file)], max_lines=500)
        assert findings, "fixture must produce at least one finding"

        jsonschema.validate(
            instance=_as_review_document(findings),
            schema=_load_review_findings_schema(),
        )

    def test_naming_conventions_findings_validate(self, tmp_path: Path) -> None:
        script = tmp_path / "skills" / "my_bad_skill" / "scripts" / "analyze-failures.py"
        script.parent.mkdir(parents=True)
        script.write_text("")

        findings = check_naming_conventions([str(script)])
        assert findings, "fixture must produce at least one finding"

        jsonschema.validate(
            instance=_as_review_document(findings),
            schema=_load_review_findings_schema(),
        )

    def test_run_all_linters_output_validates(self, tmp_path: Path) -> None:
        """The orchestrator's full document validates end to end."""
        bad_file = tmp_path / "skills" / "bad_skill" / "scripts" / "huge-bad.py"
        bad_file.parent.mkdir(parents=True)
        lines = ["from agent_coordinator.src.locks import acquire_lock\n"]
        lines += ["x = 1\n"] * 550
        bad_file.write_text("".join(lines))

        result = run_all_linters([str(bad_file)], config={"max_lines": 500})
        assert len(result["findings"]) >= 3

        jsonschema.validate(
            instance=result,
            schema=_load_review_findings_schema(),
        )

    @pytest.mark.parametrize("dropped_field", ["axis", "severity", "criticality"])
    def test_finding_missing_required_field_is_rejected(
        self, tmp_path: Path, dropped_field: str
    ) -> None:
        """Negative control — validation must actually reject an invalid finding.

        Without this, the assertions above could pass vacuously if the schema
        were loaded but never enforced.
        """
        big_file = tmp_path / "big.py"
        big_file.write_text("line\n" * 600)

        findings = check_file_size([str(big_file)], max_lines=500)
        broken = copy.deepcopy(findings)
        broken[0].pop(dropped_field)

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                instance=_as_review_document(broken),
                schema=_load_review_findings_schema(),
            )

    def test_axis_and_severity_use_schema_vocabulary(self, tmp_path: Path) -> None:
        """Emitted axis/severity values come from the 8-axis / 5-severity enums."""
        schema = _load_review_findings_schema()
        item_props = schema["properties"]["findings"]["items"]["properties"]
        axis_values = set(item_props["axis"]["enum"])
        severity_values = set(item_props["severity"]["enum"])

        bad_file = tmp_path / "skills" / "bad_skill" / "scripts" / "huge-bad.py"
        bad_file.parent.mkdir(parents=True)
        lines = ["from agent_coordinator.src.locks import acquire_lock\n"]
        lines += ["x = 1\n"] * 550
        bad_file.write_text("".join(lines))

        result = run_all_linters([str(bad_file)], config={"max_lines": 500})
        assert result["findings"]

        for finding in result["findings"]:
            assert finding["axis"] in axis_values
            assert finding["severity"] in severity_values


class TestSeverityPrefix:
    """`parallel-review-implementation` requires every finding's description to
    begin with the marker matching its `severity`, and treats prose that
    disagrees with the enum as a red flag. The linters emit both, so the two
    must agree by construction."""

    _PREFIX = {"critical": "Critical:", "nit": "Nit:", "optional": "Optional:", "fyi": "FYI:"}

    def test_every_finding_description_carries_its_severity_prefix(
        self, tmp_path: Path
    ) -> None:
        bad_file = tmp_path / "skills" / "bad_skill" / "scripts" / "huge-bad.py"
        bad_file.parent.mkdir(parents=True)
        lines = ["from agent_coordinator.src.locks import acquire_lock\n"]
        lines += ["x = 1\n"] * 550
        bad_file.write_text("".join(lines))

        findings = run_all_linters(
            [str(bad_file)], config={"max_lines": 500}
        )["findings"]
        assert findings, "deterministic violating fixture must produce findings"

        for finding in findings:
            expected = self._PREFIX.get(finding["severity"])
            if expected is None:
                continue
            assert finding["description"].startswith(expected), (
                f"finding {finding['id']} has severity {finding['severity']!r} but its "
                f"description starts {finding['description'][:40]!r}"
            )

    def test_prefixing_is_idempotent(self) -> None:
        from linters.severity import prefix_description

        once = prefix_description("file is too long", "critical")
        assert once == "Critical: file is too long"
        assert prefix_description(once, "critical") == once, "double-prefixing"
