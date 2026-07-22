from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from src.agents_config import DEFAULT_PROVIDER_MODEL_MAP


ROOT = Path(__file__).resolve().parents[3]
# The provider model map schema lives at its stable home. Never point this at
# a schema inside a change directory — change directories move on archive.
SCHEMA_PATH = ROOT / "openspec" / "schemas" / "provider-model-map.schema.json"
# The phase-dispatch contract is a design artifact of the (archived)
# vendor-neutral-autopilot change; the archive path is stable.
ARCHIVED_CHANGE = (
    ROOT / "openspec" / "changes" / "archive" / "2026-05-16-vendor-neutral-autopilot"
)


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def test_provider_model_map_schema_accepts_all_first_class_providers() -> None:
    instance = {
        "schema_version": 2,
        "tiers": ["frontier", "premium", "standard", "economy"],
        "providers": {
            "claude_code": {
                "frontier": "fable",
                "premium": "opus",
                "standard": "sonnet",
                "economy": "haiku",
            },
            "codex": {
                "frontier": {"model": "gpt-5.6-sol", "thinking": "xhigh"},
                "premium": {"model": "gpt-5.6-sol", "thinking": "medium"},
                "standard": "gpt-5.6-terra",
                "economy": "gpt-5.6-luna",
            },
            "gemini": {
                "premium": "gemini-3.1-pro-preview",
                "standard": "gemini-3-flash-preview",
                "economy": "gemini-3-flash-lite",
            },
        },
    }

    Draft202012Validator(_schema()).validate(instance)


def test_provider_model_map_schema_frontier_is_optional() -> None:
    instance = {
        "schema_version": 2,
        "tiers": ["premium", "standard", "economy"],
        "providers": {
            "gemini": {
                "premium": "gemini-3.1-pro-preview",
                "standard": "gemini-3-flash-preview",
                "economy": "gemini-3-flash-lite",
            },
        },
    }

    Draft202012Validator(_schema()).validate(instance)


def test_provider_model_map_schema_rejects_missing_tier() -> None:
    instance = {
        "schema_version": 2,
        "tiers": ["premium", "standard", "economy"],
        "providers": {
            "codex": {
                "premium": "gpt-5.5",
                "standard": "gpt-5.4",
            },
        },
    }

    errors = list(Draft202012Validator(_schema()).iter_errors(instance))

    assert errors
    assert any("economy" in str(error.message) for error in errors)


def test_default_provider_model_map_conforms_to_stable_schema() -> None:
    Draft202012Validator(_schema()).validate(DEFAULT_PROVIDER_MODEL_MAP)


def test_phase_dispatch_contract_names_provider_neutral_payload_fields() -> None:
    text = (ARCHIVED_CHANGE / "contracts" / "phase-dispatch-contract.md").read_text()

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
    text = (ARCHIVED_CHANGE / "contracts" / "phase-dispatch-contract.md").read_text()

    for field in (
        "outcome",
        "handoff_id",
        "provider",
        "model_used",
        "dispatch_tier",
        "warnings",
    ):
        assert f"`{field}`" in text
