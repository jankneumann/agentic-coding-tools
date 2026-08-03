"""Tests for the published JSON Schema contract (UP-2).

Two distinct obligations:

*Drift* — the checked-in ``.json`` files must be exactly what
``scripts/generate_contract_schemas.py`` produces from the current models. A
published schema that lags the code is worse than no published schema.

*Conformance* — the documents gen-eval actually reads and writes must validate
against those schemas. Generating a schema from a model proves nothing if the
emitter hand-builds a different shape, which is precisely the failure mode the
report emitter used to have.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from gen_eval.contracts import CONTRACT_VERSION, SCHEMA_FILENAMES, load_schema, schema_path
from gen_eval.descriptor import InterfaceDescriptor
from gen_eval.models import Scenario
from gen_eval.reports import GenEvalReport, VisibilityBreakdown, generate_json_report

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_DIR = PACKAGE_ROOT / "src" / "gen_eval" / "contracts"
GENERATOR = PACKAGE_ROOT / "scripts" / "generate_contract_schemas.py"


class TestPublishedArtifacts:
    """The contract exists on disk and is internally consistent."""

    @pytest.mark.parametrize("name", sorted(SCHEMA_FILENAMES))
    def test_schema_file_exists_and_parses(self, name: str) -> None:
        schema = load_schema(name)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"].endswith(SCHEMA_FILENAMES[name])

    @pytest.mark.parametrize("name", sorted(SCHEMA_FILENAMES))
    def test_schema_is_itself_a_valid_json_schema(self, name: str) -> None:
        Draft202012Validator.check_schema(load_schema(name))

    @pytest.mark.parametrize("name", sorted(SCHEMA_FILENAMES))
    def test_schema_carries_the_contract_version(self, name: str) -> None:
        assert load_schema(name)["x-gen-eval-contract-version"] == CONTRACT_VERSION

    def test_version_file_matches_python_constant(self) -> None:
        """VERSION is a generated artifact for non-Python consumers."""
        assert (CONTRACTS_DIR / "VERSION").read_text(encoding="utf-8").strip() == CONTRACT_VERSION

    def test_version_file_is_a_single_line(self) -> None:
        """Consumers read this with a plain ``cat``; keep it one token."""
        assert len((CONTRACTS_DIR / "VERSION").read_text(encoding="utf-8").splitlines()) == 1

    def test_load_schema_rejects_unknown_name(self) -> None:
        with pytest.raises(KeyError, match="unknown schema"):
            load_schema("no-such-schema")

    def test_schema_path_is_readable(self) -> None:
        assert schema_path("scenario").read_text(encoding="utf-8").startswith("{")


class TestNoDrift:
    """Regenerating must reproduce the checked-in files byte for byte."""

    def test_generator_check_mode_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "--check"],
            cwd=str(PACKAGE_ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            "Contract artifacts are out of date. Run:\n"
            "  python scripts/generate_contract_schemas.py\n\n" + result.stderr
        )

    def test_regenerating_into_tmpdir_matches_checked_in(self, tmp_path: Path) -> None:
        """Same assertion as above, but diffing content rather than trusting exit code."""
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "--out", str(tmp_path)],
            cwd=str(PACKAGE_ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

        for filename in [*SCHEMA_FILENAMES.values(), "VERSION"]:
            generated = (tmp_path / filename).read_text(encoding="utf-8")
            checked_in = (CONTRACTS_DIR / filename).read_text(encoding="utf-8")
            assert generated == checked_in, f"{filename} drifted from the generator output"


def _sample_report(with_visibility: bool = False) -> GenEvalReport:
    per_visibility = (
        {"public": VisibilityBreakdown(total=4, passed=3, failed=1)} if with_visibility else {}
    )
    return GenEvalReport(
        total_scenarios=2,
        passed=1,
        failed=1,
        errors=0,
        skipped=0,
        pass_rate=0.5,
        coverage_pct=50.0,
        duration_seconds=3.25,
        budget_exhausted=False,
        verdicts=[],
        per_interface={"GET /health": {"pass": 1, "fail": 0, "error": 0}},
        per_category={"smoke": {"pass": 1, "fail": 1, "error": 0, "total": 2}},
        unevaluated_interfaces=["POST /locks"],
        cost_summary={"cli_calls": 2.0, "time_minutes": 0.5, "sdk_cost_usd": 0.0},
        iterations_completed=1,
        per_visibility=per_visibility,
    )


class TestReportConformance:
    """What ``generate_json_report`` emits must satisfy the published schema."""

    @pytest.mark.parametrize("with_visibility", [False, True])
    def test_emitted_report_validates(self, with_visibility: bool) -> None:
        data = json.loads(generate_json_report(_sample_report(with_visibility)))
        Draft202012Validator(load_schema("eval-report")).validate(data)

    def test_visibility_breakdown_exposes_pass_rate(self) -> None:
        """``pass_rate`` is a computed field; it must survive serialization."""
        data = json.loads(generate_json_report(_sample_report(with_visibility=True)))
        assert data["per_visibility"]["public"]["pass_rate"] == pytest.approx(0.75)

    def test_legacy_report_without_per_visibility_still_validates(self) -> None:
        """``per_visibility`` is optional, so pre-existing reports stay valid."""
        data = json.loads(generate_json_report(_sample_report()))
        data.pop("per_visibility")
        Draft202012Validator(load_schema("eval-report")).validate(data)

    def test_schema_rejects_a_malformed_report(self) -> None:
        """Guard against a schema so permissive it validates anything."""
        data = json.loads(generate_json_report(_sample_report()))
        data["total_scenarios"] = "not-an-integer"
        with pytest.raises(Exception, match="not-an-integer|is not of type"):
            Draft202012Validator(load_schema("eval-report")).validate(data)


class TestDescriptorAndScenarioConformance:
    """Consumer-authored documents validate against the published schemas."""

    def test_sample_descriptor_validates(self, sample_descriptor: InterfaceDescriptor) -> None:
        data: dict[str, Any] = json.loads(sample_descriptor.model_dump_json())
        Draft202012Validator(load_schema("interface-descriptor")).validate(data)

    def test_descriptor_schema_rejects_missing_required_field(self) -> None:
        schema = load_schema("interface-descriptor")
        assert "project" in schema["required"]
        with pytest.raises(Exception, match="project"):
            Draft202012Validator(schema).validate({"version": "1.0"})

    def test_sample_scenario_validates(self, sample_scenario: Scenario) -> None:
        data: dict[str, Any] = json.loads(sample_scenario.model_dump_json())
        Draft202012Validator(load_schema("scenario")).validate(data)

    def test_scenario_schema_rejects_missing_required_field(self) -> None:
        schema = load_schema("scenario")
        assert "id" in schema["required"]
        with pytest.raises(Exception, match="id"):
            Draft202012Validator(schema).validate({"name": "no id here"})


class TestContractVersionBump:
    """A rename of a published model type increments the contract version (D3).

    Spec scenario:
      - gen-eval-framework.renaming-a-published-type-bumps-the-contract-version

    ``TestPublishedArtifacts`` already asserts every artifact carries
    ``CONTRACT_VERSION``, but only *relatively* — it passes for any value as
    long as all four agree. These pin the value, so silently regenerating at
    version 1 after a breaking rename fails here rather than shipping.
    """

    def test_contract_version_is_two(self) -> None:
        assert CONTRACT_VERSION == "2", (
            "renaming published model types is a breaking schema change and "
            "must bump CONTRACT_VERSION 1 -> 2"
        )

    @pytest.mark.parametrize("name", sorted(SCHEMA_FILENAMES))
    def test_every_generated_schema_carries_the_bumped_version(self, name: str) -> None:
        """D3 — the stamp lands in all three schemas, not just the descriptor.

        The generator writes ``x-gen-eval-contract-version`` into every schema,
        so regenerating only the file whose ``$defs`` changed leaves the other
        two behind and ``TestNoDrift`` failing on them.
        """
        assert load_schema(name)["x-gen-eval-contract-version"] == "2"

    def test_version_file_carries_the_bumped_version(self) -> None:
        assert (CONTRACTS_DIR / "VERSION").read_text(encoding="utf-8").strip() == "2"


class TestOfflineConsumerPath:
    """A consumer must be able to validate with no gen-eval import at all."""

    def test_schemas_are_readable_as_plain_files(self) -> None:
        """The whole point of UP-2: schema conformance without runtime coupling."""
        for filename in SCHEMA_FILENAMES.values():
            schema = json.loads((CONTRACTS_DIR / filename).read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
