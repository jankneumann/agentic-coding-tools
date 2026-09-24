"""JSON Schema tests for the add-deterministic-review-preprocessing contracts.

Covers review-packet.schema.json (v2), review-rules.schema.json,
vendor-coverage.schema.json, and fact-check-decisions.schema.json.
"""

from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator, ValidationError
from openspec_paths import change_dir, repo_root_from

REPO_ROOT = repo_root_from(__file__, 3)
CHANGE = change_dir(REPO_ROOT, "add-deterministic-review-preprocessing")
CONTRACTS = CHANGE / "contracts"


def _load(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text())


# ---------------------------------------------------------------------------
# review-packet.schema.json (v2)
# ---------------------------------------------------------------------------

PACKET_SCHEMA = _load("review-packet.schema.json")

PACKET_REQUIRED_FIELDS = (
    "schema_version",
    "change_id",
    "round",
    "body_path",
    "sha256",
    "char_length",
    "budget_chars",
    "tools_overflow",
    "includes_ledger",
    "diff_kind",
    "selection",
    "rule_groups",
)


def _valid_decision(**overrides: object) -> dict:
    doc = {
        "path": "src/foo.py",
        "status": "modified",
        "reason": "none",
        "gate": "passed",
        "est_tokens": 42,
    }
    doc.update(overrides)
    return doc


def _valid_packet(**overrides: object) -> dict:
    doc = {
        "schema_version": 2,
        "change_id": "demo-change",
        "round": 1,
        "body_path": "review-packet.md",
        "sha256": "a" * 64,
        "char_length": 100,
        "budget_chars": 320000,
        "tools_overflow": False,
        "includes_ledger": False,
        "diff_kind": "full",
        "selection": {
            "per_file_token_ceiling": 5000,
            "selected": [_valid_decision()],
            "excluded": [
                _valid_decision(
                    path="vendor/lib.lock",
                    status="modified",
                    reason="generated_path",
                    gate="generated_path",
                )
            ],
            "truncated": [],
        },
        "rule_groups": [
            {
                "group_id": 1,
                "source": "default",
                "pattern": "**/*.py",
                "files": ["src/foo.py"],
            }
        ],
    }
    doc.update(overrides)
    return doc


class TestReviewPacketSchemaV2:
    def test_schema_is_draft_2020_12(self) -> None:
        Draft202012Validator.check_schema(PACKET_SCHEMA)

    def test_valid_document(self) -> None:
        Draft202012Validator(PACKET_SCHEMA).validate(_valid_packet())

    def test_schema_version_const_is_2(self) -> None:
        assert PACKET_SCHEMA["properties"]["schema_version"]["const"] == 2
        with pytest.raises(ValidationError):
            Draft202012Validator(PACKET_SCHEMA).validate(
                _valid_packet(schema_version=1)
            )

    def test_required_fields(self) -> None:
        assert set(PACKET_SCHEMA["required"]) == set(PACKET_REQUIRED_FIELDS)
        validator = Draft202012Validator(PACKET_SCHEMA)
        for field in PACKET_REQUIRED_FIELDS:
            doc = _valid_packet()
            del doc[field]
            with pytest.raises(ValidationError):
                validator.validate(doc)

    def test_selection_requires_reason_enum(self) -> None:
        validator = Draft202012Validator(PACKET_SCHEMA)
        with pytest.raises(ValidationError):
            validator.validate(
                _valid_packet(
                    selection={
                        "per_file_token_ceiling": 100,
                        "selected": [],
                        "excluded": [_valid_decision(reason="not-a-reason")],
                        "truncated": [],
                    }
                )
            )

    def test_rule_group_source_enum(self) -> None:
        validator = Draft202012Validator(PACKET_SCHEMA)
        with pytest.raises(ValidationError):
            validator.validate(
                _valid_packet(
                    rule_groups=[
                        {
                            "group_id": 1,
                            "source": "unknown",
                            "pattern": "**/*.py",
                            "files": ["a.py"],
                        }
                    ]
                )
            )

    def test_additional_properties_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Draft202012Validator(PACKET_SCHEMA).validate(_valid_packet(extra="nope"))


# ---------------------------------------------------------------------------
# review-rules.schema.json
# ---------------------------------------------------------------------------

RULES_SCHEMA = _load("review-rules.schema.json")


def _valid_rules_doc(**overrides: object) -> dict:
    doc = {
        "schema_version": 1,
        "rules": [{"path": "**/*.py", "rule": "Check for bugs."}],
    }
    doc.update(overrides)
    return doc


class TestReviewRulesSchema:
    def test_schema_is_draft_2020_12(self) -> None:
        Draft202012Validator.check_schema(RULES_SCHEMA)

    def test_valid_document(self) -> None:
        Draft202012Validator(RULES_SCHEMA).validate(_valid_rules_doc())

    def test_rules_required_and_nonempty(self) -> None:
        validator = Draft202012Validator(RULES_SCHEMA)
        with pytest.raises(ValidationError):
            validator.validate({"schema_version": 1, "rules": []})
        with pytest.raises(ValidationError):
            validator.validate({"schema_version": 1})

    def test_rule_entry_requires_path_and_rule(self) -> None:
        validator = Draft202012Validator(RULES_SCHEMA)
        with pytest.raises(ValidationError):
            validator.validate(_valid_rules_doc(rules=[{"path": "**/*.py"}]))

    def test_optional_include_exclude_generated_paths(self) -> None:
        validator = Draft202012Validator(RULES_SCHEMA)
        validator.validate(
            _valid_rules_doc(
                include=["src/**"],
                exclude=["**/*.gen.py"],
                generated_paths=["**/*.lock"],
                coverage_quorum_threshold=0.8,
            )
        )


# ---------------------------------------------------------------------------
# vendor-coverage.schema.json
# ---------------------------------------------------------------------------

COVERAGE_SCHEMA = _load("vendor-coverage.schema.json")


class TestVendorCoverageSchema:
    def test_schema_is_draft_2020_12(self) -> None:
        Draft202012Validator.check_schema(COVERAGE_SCHEMA)

    def test_valid_coverage_block(self) -> None:
        validator = Draft202012Validator(COVERAGE_SCHEMA)
        validator.validate(
            {
                "coverage": {
                    "reviewed": ["a.py", "b.py"],
                    "skipped": [{"path": "c.py", "reason": "too large"}],
                    "rate": 0.67,
                }
            }
        )

    def test_skipped_entry_requires_reason(self) -> None:
        validator = Draft202012Validator(COVERAGE_SCHEMA)
        with pytest.raises(ValidationError):
            validator.validate(
                {
                    "coverage": {
                        "reviewed": [],
                        "skipped": [{"path": "c.py"}],
                    }
                }
            )

    def test_finding_fragment_line_resolution_enum(self) -> None:
        validator = Draft202012Validator(COVERAGE_SCHEMA)
        validator.validate(
            {
                "finding_fragment": {
                    "existing_code": "x = 1",
                    "line_resolution": "hunk_new",
                }
            }
        )
        with pytest.raises(ValidationError):
            validator.validate(
                {"finding_fragment": {"line_resolution": "not-a-value"}}
            )


# ---------------------------------------------------------------------------
# fact-check-decisions.schema.json
# ---------------------------------------------------------------------------

FACT_CHECK_SCHEMA = _load("fact-check-decisions.schema.json")


def _valid_fact_check_doc(**overrides: object) -> dict:
    doc = {
        "schema_version": 1,
        "vendor": "codex",
        "round": 1,
        "status": "ran",
        "model": "gpt-5.6-luna",
        "tokens": 512,
        "decisions": [
            {
                "finding_id": "f-1",
                "verdict": "removed",
                "ground": "B_contradicted_by_diff_line",
                "evidence_line": "+used_variable = 1",
            }
        ],
    }
    doc.update(overrides)
    return doc


class TestFactCheckDecisionsSchema:
    def test_schema_is_draft_2020_12(self) -> None:
        Draft202012Validator.check_schema(FACT_CHECK_SCHEMA)

    def test_valid_document(self) -> None:
        Draft202012Validator(FACT_CHECK_SCHEMA).validate(_valid_fact_check_doc())

    def test_status_enum(self) -> None:
        validator = Draft202012Validator(FACT_CHECK_SCHEMA)
        with pytest.raises(ValidationError):
            validator.validate(_valid_fact_check_doc(status="not-a-status"))

    def test_verdict_enum(self) -> None:
        validator = Draft202012Validator(FACT_CHECK_SCHEMA)
        with pytest.raises(ValidationError):
            validator.validate(
                _valid_fact_check_doc(
                    decisions=[{"finding_id": "f-1", "verdict": "maybe"}]
                )
            )

    def test_skipped_status_allows_null_model(self) -> None:
        validator = Draft202012Validator(FACT_CHECK_SCHEMA)
        validator.validate(
            _valid_fact_check_doc(
                status="skipped",
                skip_reason="timeout",
                model=None,
                tokens=0,
                decisions=[],
            )
        )


# ---------------------------------------------------------------------------
# README and ocr-adapter.md exist and document the same files
# ---------------------------------------------------------------------------


class TestContractsReadme:
    def test_readme_exists(self) -> None:
        assert (CONTRACTS / "README.md").is_file()

    def test_ocr_adapter_doc_exists(self) -> None:
        assert (CONTRACTS / "ocr-adapter.md").is_file()

    def test_readme_lists_every_contract_file(self) -> None:
        readme = (CONTRACTS / "README.md").read_text()
        for name in (
            "review-packet.schema.json",
            "review-rules.schema.json",
            "vendor-coverage.schema.json",
            "fact-check-decisions.schema.json",
            "ocr-adapter.md",
        ):
            assert name in readme, f"{name} not referenced in contracts/README.md"
