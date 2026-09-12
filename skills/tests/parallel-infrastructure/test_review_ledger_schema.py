"""JSON Schema tests for the gate-time review ledger documents."""

from __future__ import annotations

import json

from jsonschema import Draft202012Validator, ValidationError
import pytest
from openspec_paths import change_dir, repo_root_from

REPO_ROOT = repo_root_from(__file__, 3)
CONTRACTS = change_dir(REPO_ROOT, "ledger-driven-review-convergence") / "contracts"

LEDGER_SCHEMA = json.loads((CONTRACTS / "review-ledger.schema.json").read_text())
PARKED_SCHEMA = json.loads(
    (CONTRACTS / "parked-disagreements.schema.json").read_text()
)


def _ledger_item(**overrides: object) -> dict:
    item = {
        "id": 1,
        "status": "open",
        "axis": "correctness",
        "type": "bug",
        "criticality": "high",
        "evidence_class": "deterministic",
        "fingerprint": "abc123def456",
        "first_seen_round": 1,
        "last_seen_round": 1,
        "description": "Missing null check in parse_line",
    }
    item.update(overrides)
    return item


def _valid_ledger(**overrides: object) -> dict:
    doc = {
        "schema_version": 1,
        "change_id": "demo-change",
        "items": [_ledger_item()],
    }
    doc.update(overrides)
    return doc


def _valid_parked(**overrides: object) -> dict:
    doc = {
        "schema_version": 1,
        "change_id": "demo-change",
        "items": [
            {
                "ledger_id": 1,
                "round": 1,
                "vendor_dispositions": {"codex": "fix", "grok": "accept"},
                "description": "Vendors disagree on renaming the helper",
            }
        ],
    }
    doc.update(overrides)
    return doc


class TestReviewLedgerSchema:
    def test_schema_is_draft_2020_12(self) -> None:
        Draft202012Validator.check_schema(LEDGER_SCHEMA)

    def test_valid_document(self) -> None:
        Draft202012Validator(LEDGER_SCHEMA).validate(_valid_ledger())

    def test_valid_document_with_optional_fields(self) -> None:
        Draft202012Validator(LEDGER_SCHEMA).validate(
            _valid_ledger(
                compacted_at="2026-09-12T00:00:00Z",
                items=[
                    _ledger_item(
                        file_path="src/api.py",
                        line_start=10,
                        line_end=20,
                        vendor_hits=["codex", "grok"],
                        resolution="",
                        parked_reason="",
                        consensus_status="confirmed",
                    )
                ],
            )
        )

    def test_missing_required_top_level_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Draft202012Validator(LEDGER_SCHEMA).validate(
                {"schema_version": 1, "items": []}
            )

    def test_unknown_status_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Draft202012Validator(LEDGER_SCHEMA).validate(
                _valid_ledger(items=[_ledger_item(status="closed")])
            )

    def test_additional_item_properties_rejected(self) -> None:
        item = _ledger_item()
        item["extra"] = "nope"
        with pytest.raises(ValidationError):
            Draft202012Validator(LEDGER_SCHEMA).validate(
                _valid_ledger(items=[item])
            )

    def test_empty_items_ok(self) -> None:
        Draft202012Validator(LEDGER_SCHEMA).validate(
            _valid_ledger(items=[])
        )


class TestParkedDisagreementsSchema:
    def test_schema_is_draft_2020_12(self) -> None:
        Draft202012Validator.check_schema(PARKED_SCHEMA)

    def test_valid_document(self) -> None:
        Draft202012Validator(PARKED_SCHEMA).validate(_valid_parked())

    def test_missing_ledger_id_rejected(self) -> None:
        doc = _valid_parked()
        del doc["items"][0]["ledger_id"]
        with pytest.raises(ValidationError):
            Draft202012Validator(PARKED_SCHEMA).validate(doc)

    def test_additional_properties_rejected(self) -> None:
        doc = _valid_parked()
        doc["note"] = "nope"
        with pytest.raises(ValidationError):
            Draft202012Validator(PARKED_SCHEMA).validate(doc)
