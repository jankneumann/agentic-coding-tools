from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[3]
CHANGE = ROOT / "openspec" / "changes" / "vendor-neutral-autopilot"


def test_provider_model_map_schema_accepts_all_first_class_providers() -> None:
    schema = json.loads((CHANGE / "contracts" / "provider-model-map.schema.json").read_text())
    instance = {
        "schema_version": 1,
        "tiers": ["premium", "standard", "economy"],
        "providers": {
            "claude_code": {
                "premium": "opus",
                "standard": "sonnet",
                "economy": "haiku",
            },
            "codex": {
                "premium": "gpt-5.5",
                "standard": "gpt-5.4",
                "economy": "gpt-5.4-mini",
            },
            "gemini": {
                "premium": "gemini-3.1-pro-preview",
                "standard": "gemini-3-flash-preview",
                "economy": "gemini-3-flash-lite",
            },
        },
    }

    Draft202012Validator(schema).validate(instance)


def test_provider_model_map_schema_rejects_missing_tier() -> None:
    schema = json.loads((CHANGE / "contracts" / "provider-model-map.schema.json").read_text())
    instance = {
        "schema_version": 1,
        "tiers": ["premium", "standard", "economy"],
        "providers": {
            "codex": {
                "premium": "gpt-5.5",
                "standard": "gpt-5.4",
            },
        },
    }

    errors = list(Draft202012Validator(schema).iter_errors(instance))

    assert errors
    assert any("economy" in str(error.message) for error in errors)


def test_phase_dispatch_contract_names_provider_neutral_payload_fields() -> None:
    text = (CHANGE / "contracts" / "phase-dispatch-contract.md").read_text()

    for field in (
        "schema_version",
        "change_id",
        "phase",
        "provider",
        "archetype",
        "model",
        "prompt",
        "system_prompt",
        "isolation",
        "expected_outcomes",
    ):
        assert f"`{field}`" in text


def test_phase_dispatch_contract_names_normalized_result_fields() -> None:
    text = (CHANGE / "contracts" / "phase-dispatch-contract.md").read_text()

    for field in (
        "outcome",
        "handoff_id",
        "provider",
        "model_used",
        "dispatch_tier",
        "warnings",
    ):
        assert f"`{field}`" in text
