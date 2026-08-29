"""The vendor review prompt must agree with review-findings.schema.json.

The prompt is the ONLY contract most review vendors ever see. Only ``grok-local``
is dispatched with ``--json-schema @review-findings-schema``; codex, antigravity
and pi receive the prompt text alone. So any required field the prompt omits is a
field those vendors cannot know to emit — and their output is then rejected by a
validator enforcing a contract they were never shown.

That is not hypothetical. On 2026-08-24 the prompt listed neither ``axis`` nor
``severity`` while the schema marked both required. Across an 8-PR review sweep
codex failed 8/8 and antigravity 7/8, every one with
``findings/0: 'axis' is a required property``. Quorum silently degraded from four
vendors to one and still reported ``quorum_met: true``.

These tests fail when the prompt and the schema disagree, so the next schema
change cannot quietly re-open that gap.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "merge-pull-requests" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

INFRA_DIR = (
    Path(__file__).resolve().parents[2] / "parallel-infrastructure" / "scripts"
)
if str(INFRA_DIR) not in sys.path:
    sys.path.insert(0, str(INFRA_DIR))

from vendor_review import (  # noqa: E402
    _FALLBACK_ENUMS,
    _FALLBACK_REQUIRED,
    _finding_contract,
    build_review_prompt,
)
from review_findings_schema import finding_item_schema  # noqa: E402

PR_SIZE = {
    "changed_files": 4,
    "additions": 120,
    "deletions": 8,
    "files": ["a.py", "b.py"],
}


@pytest.fixture(scope="module")
def prompt() -> str:
    return build_review_prompt(4242, PR_SIZE)


@pytest.fixture(scope="module")
def schema_item() -> dict:
    return finding_item_schema()


def test_every_required_field_appears_in_the_prompt(prompt, schema_item):
    """A required field the prompt never names cannot be emitted by a vendor."""
    missing = [f for f in schema_item["required"] if f'"{f}"' not in prompt]
    assert not missing, (
        f"schema requires {missing} but the prompt never names them; "
        "vendors dispatched without --json-schema will fail validation"
    )


def test_required_list_is_stated_explicitly(prompt, schema_item):
    """The prompt must spell out the required set, not just show it in an example."""
    assert "REQUIRED on every finding" in prompt
    for field in schema_item["required"]:
        assert field in prompt


def test_enum_values_match_the_schema(prompt, schema_item):
    """Each enum value the schema allows must be offered by the prompt."""
    for name, spec in (schema_item.get("properties") or {}).items():
        values = spec.get("enum") if isinstance(spec, dict) else None
        if not values:
            continue
        missing = [v for v in values if v not in prompt]
        assert not missing, f"prompt omits {name} values {missing}"


def test_prompt_offers_no_value_the_schema_rejects(prompt, schema_item):
    """The prompt must not invent enum members the validator would reject."""
    for name, spec in (schema_item.get("properties") or {}).items():
        values = spec.get("enum") if isinstance(spec, dict) else None
        if not values:
            continue
        rendered = f'"{name}": "'
        if rendered not in prompt:
            continue
        start = prompt.index(rendered) + len(rendered)
        offered = prompt[start : prompt.index('"', start)].split("|")
        unknown = [v for v in offered if v not in values]
        assert not unknown, f"prompt offers {name} values {unknown} not in schema"


def test_contract_is_derived_from_the_schema_not_hardcoded(schema_item):
    """_finding_contract must read the canonical file, not a local copy."""
    required, enums = _finding_contract()
    assert required == tuple(schema_item["required"])
    for name, spec in (schema_item.get("properties") or {}).items():
        if isinstance(spec, dict) and spec.get("enum"):
            assert enums[name] == tuple(spec["enum"])


def test_fallback_matches_the_schema(schema_item):
    """The offline fallback must not drift from the canonical schema either.

    It is only used when the schema file cannot be read, which is exactly when
    nothing else would catch it being wrong.
    """
    assert _FALLBACK_REQUIRED == tuple(schema_item["required"])
    for name, spec in (schema_item.get("properties") or {}).items():
        if isinstance(spec, dict) and spec.get("enum"):
            assert _FALLBACK_ENUMS[name] == tuple(spec["enum"]), (
                f"fallback {name} drifted from review-findings.schema.json"
            )


def test_criticality_and_severity_are_distinguished(prompt):
    """The two vocabularies overlap on "critical" — the prompt must separate them.

    Both fields are required and both accept "critical", so a vendor that treats
    them as one scale produces output that validates on severity and is wrong on
    criticality (or vice versa) with no error to reveal it.
    """
    assert "DIFFERENT vocabularies" in prompt
    assert "NOT the same scale as criticality" in prompt


def test_empty_findings_shape_is_specified(prompt):
    """"No issues" must have a valid JSON encoding, or vendors return prose."""
    assert '{"findings": []}' in prompt
