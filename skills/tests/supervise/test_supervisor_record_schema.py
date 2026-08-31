"""Contract tests for the versioned supervisor handoff record."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import pytest
from jsonschema import Draft202012Validator, FormatChecker

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DIR = (
    REPO_ROOT
    / "openspec/changes/extend-handoff-document-with-supervisor-record/contracts/schemas"
)
FIXTURE_DIR = Path(__file__).parent / "fixtures/supervisor-record"

SHARED_SKILLS = REPO_ROOT / "skills/shared"
if str(SHARED_SKILLS) not in sys.path:  # pragma: no cover - import wiring
    sys.path.insert(0, str(SHARED_SKILLS))

from trust_posture import Gate  # noqa: E402


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def full_schema() -> dict:
    return _load_json(SCHEMA_DIR / "supervisor-record.schema.json")


@pytest.fixture(scope="module")
def mirror_schema() -> dict:
    return _load_json(SCHEMA_DIR / "supervisor-record-mirror.schema.json")


def _validator(schema: dict) -> Draft202012Validator:
    return Draft202012Validator(schema, format_checker=FormatChecker())


class TestSupervisorRecordSchemas:
    def test_schemas_are_valid_draft_2020_12(
        self, full_schema: dict, mirror_schema: dict
    ) -> None:
        Draft202012Validator.check_schema(full_schema)
        Draft202012Validator.check_schema(mirror_schema)
        assert full_schema["$schema"].endswith("draft/2020-12/schema")
        assert mirror_schema["$schema"].endswith("draft/2020-12/schema")

    def test_gate_enum_matches_trust_posture(
        self, full_schema: dict, mirror_schema: dict
    ) -> None:
        expected = {gate.value for gate in Gate}
        assert set(full_schema["$defs"]["gate"]["enum"]) == expected
        assert set(mirror_schema["$defs"]["gate"]["enum"]) == expected

    def test_written_by_and_every_back_edge_member_are_required(
        self, full_schema: dict
    ) -> None:
        assert "written_by" in full_schema["required"]
        back_edge = full_schema["properties"]["back_edge"]
        assert set(back_edge["required"]) == set(back_edge["properties"])


class TestSupervisorRecordFixtures:
    @pytest.mark.parametrize("fixture_name", ["minimal.json", "full.json"])
    def test_full_record_fixture_validates(
        self, fixture_name: str, full_schema: dict
    ) -> None:
        _validator(full_schema).validate(_load_json(FIXTURE_DIR / fixture_name))

    def test_mirror_fixture_validates(self, mirror_schema: dict) -> None:
        _validator(mirror_schema).validate(_load_json(FIXTURE_DIR / "mirror.json"))

    def test_pending_gate_without_deadline_is_rejected(self, full_schema: dict) -> None:
        fixture = _load_json(FIXTURE_DIR / "invalid-missing-deadline.json")
        with pytest.raises(jsonschema.ValidationError, match="deadline"):
            _validator(full_schema).validate(fixture)

    def test_unknown_gate_is_rejected(self, full_schema: dict) -> None:
        fixture = _load_json(FIXTURE_DIR / "invalid-unknown-gate.json")
        with pytest.raises(jsonschema.ValidationError):
            _validator(full_schema).validate(fixture)

    def test_handoff_row_embeds_the_full_record(self, full_schema: dict) -> None:
        handoff = _load_json(FIXTURE_DIR / "handoff-with-record.json")
        full_record = _load_json(FIXTURE_DIR / "full.json")
        assert handoff["supervisor_record"] == full_record
        _validator(full_schema).validate(handoff["supervisor_record"])
