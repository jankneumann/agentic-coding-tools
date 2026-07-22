"""Tests for schema-derived multi-vendor review prompts."""

from __future__ import annotations

import json
from pathlib import Path

from review_prompt import build_review_prompt, is_schema_derived_prompt


def test_prompt_contract_is_derived_from_supplied_schema(tmp_path: Path) -> None:
    schema = {
        "type": "object",
        "required": ["review_type", "target", "findings", "contract_revision"],
        "properties": {
            "review_type": {"type": "string", "enum": ["plan", "implementation"]},
            "target": {"type": "string"},
            "contract_revision": {"type": "integer"},
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "axis"],
                    "properties": {
                        "id": {"type": "integer"},
                        "axis": {"type": "string", "enum": ["correctness", "security"]},
                    },
                },
            },
        },
    }
    schema_path = tmp_path / "review-findings.schema.json"
    schema_path.write_text(json.dumps(schema))

    prompt = build_review_prompt(
        review_type="plan",
        target="change-123",
        context="Read proposal.md and tasks.md.",
        focus="Find contract gaps.",
        schema_path=schema_path,
    )

    assert '"contract_revision": 0' in prompt
    assert '"axis": "correctness"' in prompt
    assert '"enum": [' in prompt
    assert '"security"' in prompt
    assert "Read proposal.md and tasks.md." in prompt
    assert "Find contract gaps." in prompt
    assert is_schema_derived_prompt(prompt)


def test_canonical_prompt_includes_every_required_finding_field() -> None:
    prompt = build_review_prompt(
        review_type="implementation",
        target="wp-api",
        context="Review git diff main..HEAD.",
    )

    for field in (
        "id",
        "type",
        "criticality",
        "description",
        "disposition",
        "axis",
        "severity",
    ):
        assert f'"{field}"' in prompt
    assert '"review_type": "implementation"' in prompt
    assert '"target": "wp-api"' in prompt
