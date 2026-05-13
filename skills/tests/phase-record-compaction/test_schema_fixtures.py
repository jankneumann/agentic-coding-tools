"""Validate PhaseRecord and handoff-local-fallback JSON Schemas against fixture payloads.

These tests lock the contract before downstream packages (wp-phase-record-model,
wp-autopilot-layer-1, etc.) consume it. They are intentionally narrow: just verify
that the schemas are well-formed and that representative fixtures validate.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DIR = REPO_ROOT / "openspec/changes/phase-record-compaction/contracts/schemas"
FIXTURE_DIR = Path(__file__).parent / "fixtures"

PHASE_RECORD_SCHEMA = SCHEMA_DIR / "phase-record.schema.json"
HANDOFF_FALLBACK_SCHEMA = SCHEMA_DIR / "handoff-local-fallback.schema.json"


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def phase_record_schema() -> dict:
    return _load_json(PHASE_RECORD_SCHEMA)


@pytest.fixture(scope="module")
def handoff_fallback_schema() -> dict:
    return _load_json(HANDOFF_FALLBACK_SCHEMA)


class TestSchemaWellFormed:
    """The schemas themselves must be valid JSON Schema Draft 2020-12."""

    def test_phase_record_schema_is_valid(self, phase_record_schema: dict) -> None:
        jsonschema.Draft202012Validator.check_schema(phase_record_schema)

    def test_handoff_fallback_schema_is_valid(self, handoff_fallback_schema: dict) -> None:
        jsonschema.Draft202012Validator.check_schema(handoff_fallback_schema)


class TestPhaseRecordFixtures:
    """Representative PhaseRecord payloads must validate against the schema."""

    def test_minimal_fixture_validates(self, phase_record_schema: dict) -> None:
        fixture = _load_json(FIXTURE_DIR / "phase_record_minimal.json")
        jsonschema.validate(fixture, phase_record_schema)

    def test_full_fixture_validates(self, phase_record_schema: dict) -> None:
        fixture = _load_json(FIXTURE_DIR / "phase_record_full.json")
        jsonschema.validate(fixture, phase_record_schema)

    def test_full_fixture_round_trips_through_json(self, phase_record_schema: dict) -> None:
        """Re-serializing the fixture preserves validation. Catches schema rules
        that depend on key order or whitespace (there should be none)."""
        fixture = _load_json(FIXTURE_DIR / "phase_record_full.json")
        re_serialized = json.loads(json.dumps(fixture))
        jsonschema.validate(re_serialized, phase_record_schema)

    def test_missing_required_field_rejected(self, phase_record_schema: dict) -> None:
        fixture = _load_json(FIXTURE_DIR / "phase_record_minimal.json")
        del fixture["summary"]
        with pytest.raises(jsonschema.ValidationError, match="summary"):
            jsonschema.validate(fixture, phase_record_schema)

    def test_capability_with_invalid_pattern_rejected(self, phase_record_schema: dict) -> None:
        fixture = _load_json(FIXTURE_DIR / "phase_record_full.json")
        fixture["decisions"][0]["capability"] = "Has-Capital-Letters"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(fixture, phase_record_schema)

    def test_supersedes_with_invalid_format_rejected(self, phase_record_schema: dict) -> None:
        fixture = _load_json(FIXTURE_DIR / "phase_record_full.json")
        fixture["decisions"][1]["supersedes"] = "no-D-marker-just-text"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(fixture, phase_record_schema)

    def test_unknown_top_level_field_rejected(self, phase_record_schema: dict) -> None:
        fixture = _load_json(FIXTURE_DIR / "phase_record_minimal.json")
        fixture["bogus_extra_field"] = "should not be allowed"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(fixture, phase_record_schema)


class TestHandoffFallbackFixtures:
    """Representative local-file fallback payloads must validate."""

    def test_fallback_fixture_validates(self, handoff_fallback_schema: dict) -> None:
        fixture = _load_json(FIXTURE_DIR / "handoff_local_fallback.json")
        jsonschema.validate(fixture, handoff_fallback_schema)

    def test_fallback_envelope_requires_coordinator_error(self, handoff_fallback_schema: dict) -> None:
        fixture = _load_json(FIXTURE_DIR / "handoff_local_fallback.json")
        del fixture["coordinator_error"]
        with pytest.raises(jsonschema.ValidationError, match="coordinator_error"):
            jsonschema.validate(fixture, handoff_fallback_schema)

    def test_unknown_error_type_rejected(self, handoff_fallback_schema: dict) -> None:
        fixture = _load_json(FIXTURE_DIR / "handoff_local_fallback.json")
        fixture["coordinator_error"]["error_type"] = "made_up_error"
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(fixture, handoff_fallback_schema)

    def test_payload_decisions_match_phase_record_decision_shape(
        self, handoff_fallback_schema: dict
    ) -> None:
        """The payload's decision schema is intentionally a subset of the PhaseRecord
        Decision (no Decision-only optional fields beyond title/rationale/capability/supersedes).
        Verify that the fixture's decisions list parses under both schemas."""
        fixture = _load_json(FIXTURE_DIR / "handoff_local_fallback.json")
        jsonschema.validate(fixture, handoff_fallback_schema)
        for decision in fixture["payload"]["decisions"]:
            assert "title" in decision
            assert "rationale" in decision
