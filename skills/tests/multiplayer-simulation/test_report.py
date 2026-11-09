"""Report builder tests (D.2; design D8)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import pytest
from openspec_paths import repo_root_from

from mpsim.report import ReportError, new_report, render

REPO = repo_root_from(__file__, 3)
SCHEMA = json.loads(
    (REPO / "openspec/contracts/multiplayer-simulation/schemas/sim-report.schema.json").read_text()
)
PRINCIPALS = [
    {"name": "alice", "agent_id": "alice-agent-1", "change_id": "sim-alice-notes"},
    {"name": "bob", "agent_id": "bob-agent-1", "change_id": "sim-bob-notes"},
]


def _valid(**over):
    base = dict(principals=PRINCIPALS, timeline=[])
    base.update(over)
    return new_report("same-requirement-collision", **base)


def test_new_report_has_every_schema_property_with_null_for_inapplicable_fields():
    report = _valid()
    assert set(report) == set(SCHEMA["properties"])
    assert report["blocked_ticks"] is None
    assert report["unblocked"] is None
    assert report["final_tick"] is None
    assert report["error"] is None
    assert report["schema_version"] == "1"


def test_render_emits_sorted_keys_without_trailing_whitespace():
    out = render(_valid())
    parsed = json.loads(out)
    assert list(parsed) == sorted(parsed)
    assert out.endswith("\n") and not out.endswith("\n\n")
    assert all(line == line.rstrip() for line in out.splitlines())
    assert out == render(_valid())  # stable


def test_rendered_report_validates_against_the_promoted_schema():
    out = render(_valid(collision_present=True, collision_detected=False, probes=[]))
    jsonschema.Draft202012Validator(SCHEMA).validate(json.loads(out))


def test_error_report_may_have_no_principals_and_null_timeline():
    out = render(new_report("same-requirement-collision", error="fixture lost the requirement"))
    jsonschema.Draft202012Validator(SCHEMA).validate(json.loads(out))


def test_error_free_report_with_one_principal_fails_schema_validation():
    out = render(_valid(principals=PRINCIPALS[:1]))
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(SCHEMA).validate(json.loads(out))


def test_unknown_field_is_rejected_by_the_builder():
    with pytest.raises(TypeError):
        new_report("x", bogus=1)


def test_render_rejects_a_value_containing_the_world_root(tmp_path: Path):
    root = tmp_path / "world"
    report = _valid(error=f"git failed in {root}/principals/alice")
    with pytest.raises(ReportError, match="world"):
        render(report, forbidden_paths=[str(root)])


def test_render_rejects_a_forty_character_hex_string():
    sha = "a" * 20 + "0123456789" + "b" * 10
    assert len(sha) == 40 and re.fullmatch(r"[0-9a-f]{40}", sha)
    with pytest.raises(ReportError, match="hex"):
        render(_valid(error=f"bad ref {sha}"))


def test_render_allows_shorter_hex_and_ordinary_text():
    out = render(_valid(error="ref abc123 not found"))
    assert "abc123" in out
