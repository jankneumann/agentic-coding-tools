"""Package-owned contract schemas are valid and the gap example validates (task 1.1)."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

import jsonschema
import pytest

SCHEMA_NAMES = [
    "results-record.schema.json",
    "capability-gap-entry.schema.json",
    "nightly-config.schema.json",
]


def load_schema(name: str) -> dict[str, Any]:
    text = (resources.files("agent_scenarios") / "schemas" / name).read_text(encoding="utf-8")
    loaded: dict[str, Any] = json.loads(text)
    return loaded


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_schema_is_valid_draft_2020_12(name: str) -> None:
    schema = load_schema(name)
    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_gap_example_validates_against_gap_schema() -> None:
    example = load_schema("capability-gap-entry.example.json")
    jsonschema.validate(example, load_schema("capability-gap-entry.schema.json"))
    assert "source:scenario-parity" in example["tags"]
