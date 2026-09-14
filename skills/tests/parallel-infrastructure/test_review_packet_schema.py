"""JSON Schema tests for review-packet metadata documents (v2).

Repointed from the v1 contract archived under
``2026-09-13-pack-and-parallelize-vendor-review`` to the v2 contract added by
``add-deterministic-review-preprocessing`` (schema_version 2 adds
``selection`` and ``rule_groups``). See
``skills/tests/parallel-infrastructure/test_review_preprocessing_contracts.py``
for the fuller v2 test suite; this file keeps the original, narrower
regression coverage under its original name.
"""

from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator, ValidationError
from openspec_paths import change_dir, repo_root_from

REPO_ROOT = repo_root_from(__file__, 3)
CONTRACTS = change_dir(REPO_ROOT, "add-deterministic-review-preprocessing") / "contracts"
PACKET_SCHEMA = json.loads((CONTRACTS / "review-packet.schema.json").read_text())

REQUIRED_FIELDS = (
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


def _valid_selection(**overrides: object) -> dict:
    doc = {"per_file_token_ceiling": 5000, "selected": [], "excluded": [], "truncated": []}
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
        "selection": _valid_selection(),
        "rule_groups": [],
    }
    doc.update(overrides)
    return doc


class TestReviewPacketSchema:
    def test_schema_is_draft_2020_12(self) -> None:
        Draft202012Validator.check_schema(PACKET_SCHEMA)

    def test_valid_document(self) -> None:
        Draft202012Validator(PACKET_SCHEMA).validate(_valid_packet())

    def test_required_fields(self) -> None:
        assert set(PACKET_SCHEMA["required"]) == set(REQUIRED_FIELDS)
        validator = Draft202012Validator(PACKET_SCHEMA)
        for field in REQUIRED_FIELDS:
            doc = _valid_packet()
            del doc[field]
            with pytest.raises(ValidationError):
                validator.validate(doc)

    def test_budget_chars_const_is_320000(self) -> None:
        assert PACKET_SCHEMA["properties"]["budget_chars"]["const"] == 320000
        Draft202012Validator(PACKET_SCHEMA).validate(_valid_packet(budget_chars=320000))
        with pytest.raises(ValidationError):
            Draft202012Validator(PACKET_SCHEMA).validate(_valid_packet(budget_chars=80000))

    def test_tools_overflow_must_be_boolean(self) -> None:
        validator = Draft202012Validator(PACKET_SCHEMA)
        validator.validate(_valid_packet(tools_overflow=True))
        validator.validate(_valid_packet(tools_overflow=False))
        with pytest.raises(ValidationError):
            validator.validate(_valid_packet(tools_overflow="yes"))

    def test_includes_ledger_must_be_boolean(self) -> None:
        validator = Draft202012Validator(PACKET_SCHEMA)
        validator.validate(_valid_packet(includes_ledger=True))
        validator.validate(_valid_packet(includes_ledger=False))
        with pytest.raises(ValidationError):
            validator.validate(_valid_packet(includes_ledger=1))

    def test_sha256_pattern(self) -> None:
        validator = Draft202012Validator(PACKET_SCHEMA)
        validator.validate(_valid_packet(sha256="0123456789abcdef" * 4))
        with pytest.raises(ValidationError):
            validator.validate(_valid_packet(sha256="not-a-hash"))
        with pytest.raises(ValidationError):
            validator.validate(_valid_packet(sha256="A" * 64))
        with pytest.raises(ValidationError):
            validator.validate(_valid_packet(sha256="a" * 63))

    def test_diff_kind_enum(self) -> None:
        validator = Draft202012Validator(PACKET_SCHEMA)
        for kind in ("full", "last_fix", "empty"):
            validator.validate(_valid_packet(diff_kind=kind))
        with pytest.raises(ValidationError):
            validator.validate(_valid_packet(diff_kind="partial"))

    def test_additional_properties_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Draft202012Validator(PACKET_SCHEMA).validate(_valid_packet(extra="nope"))
