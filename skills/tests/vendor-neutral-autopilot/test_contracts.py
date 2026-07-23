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


# The five-key roster the schema now closes over (propertyNames.enum + required).
_ROSTER = ("claude_code", "codex", "antigravity", "grok", "pi")


def _roster_providers(*, drop_frontier: bool = False) -> dict:
    """Build a providers block for the full roster from the live map.

    Derived from DEFAULT_PROVIDER_MODEL_MAP so no model-id literals (and no
    retired-provider names) are hardcoded here — tuning tier entries in the
    map does not invalidate these contract tests.
    """
    out: dict = {}
    for name in _ROSTER:
        entry = dict(DEFAULT_PROVIDER_MODEL_MAP["providers"][name])
        if drop_frontier:
            entry.pop("frontier", None)
        out[name] = entry
    return out


def test_provider_model_map_schema_accepts_all_first_class_providers() -> None:
    instance = {
        "schema_version": 2,
        "tiers": ["frontier", "premium", "standard", "economy"],
        "providers": _roster_providers(),
    }

    Draft202012Validator(_schema()).validate(instance)


def test_provider_model_map_schema_frontier_is_optional() -> None:
    # All five roster providers present, none carrying a frontier tier —
    # frontier is optional, so this must still validate.
    instance = {
        "schema_version": 2,
        "tiers": ["premium", "standard", "economy"],
        "providers": _roster_providers(drop_frontier=True),
    }

    Draft202012Validator(_schema()).validate(instance)


def test_provider_model_map_schema_rejects_missing_tier() -> None:
    providers = _roster_providers(drop_frontier=True)
    # Drop a required tier from one provider; the whole map must be rejected.
    providers["codex"] = {
        "premium": providers["codex"]["premium"],
        "standard": providers["codex"]["standard"],
    }
    instance = {
        "schema_version": 2,
        "tiers": ["premium", "standard", "economy"],
        "providers": providers,
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
