"""Tests for skills/playwright-validator/scripts/descriptor.py.

Covers task 7.1: contract test for frontend-descriptor.schema.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from openspec_paths import change_dir, repo_root_from

from descriptor import (
    DescriptorError,
    is_frontend_descriptor,
    load_descriptor,
    load_schema,
    normalize_descriptor,
)


REPO_ROOT = repo_root_from(__file__, 3)
#: Relocated from evaluation/gen_eval/descriptors/sample-frontend.yaml when the
#: gen-eval fixtures moved under packages/gen-eval; content is byte-identical to
#: the file e087fd70 added. The constants here were left behind by that move and
#: nothing caught it, because no CI invocation reached this directory.
SAMPLE_DESCRIPTOR = (
    REPO_ROOT / "packages" / "gen-eval" / "tests" / "fixtures" / "sample-descriptor.yaml"
)
SCHEMA_PATH = (
    change_dir(REPO_ROOT, "factory-missions-architecture-alignment")
    / "contracts"
    / "frontend-descriptor.schema.json"
)


def test_schema_loads():
    schema = load_schema()
    assert schema["$id"].endswith("frontend-descriptor.schema.json")
    assert "browsers" in schema["properties"]


def test_sample_descriptor_validates():
    """The shipped sample descriptor MUST validate."""
    doc = load_descriptor(SAMPLE_DESCRIPTOR)
    assert doc["name"] == "sample-frontend"
    assert doc["lifecycle"]["bind_address"] == "127.0.0.1"


def test_invalid_descriptor_missing_required_fails(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: missing-required-fields\n")
    with pytest.raises(DescriptorError) as exc:
        load_descriptor(bad)
    # Either base_url, browsers, or selectors is the failing required field.
    msg = str(exc.value).lower()
    assert "required" in msg or "base_url" in msg or "selectors" in msg


def test_invalid_yaml_syntax_fails(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: x\nbase_url: [unterminated\n")
    with pytest.raises(DescriptorError):
        load_descriptor(bad)


def test_invalid_browser_enum_fails(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "base_url: http://127.0.0.1:8765\n"
        "browsers: [internet-explorer]\n"
        "selectors: {x: '#x'}\n"
    )
    with pytest.raises(DescriptorError) as exc:
        load_descriptor(bad)
    assert "browsers" in str(exc.value)


def test_is_frontend_descriptor_true_for_valid():
    assert is_frontend_descriptor(SAMPLE_DESCRIPTOR) is True


def test_is_frontend_descriptor_false_for_invalid(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("not: a frontend descriptor\n")
    assert is_frontend_descriptor(bad) is False


def test_is_frontend_descriptor_false_for_missing_path(tmp_path: Path):
    assert is_frontend_descriptor(tmp_path / "nonexistent.yaml") is False


def test_normalize_fills_defaults():
    doc = {
        "base_url": "http://127.0.0.1:1",
        "browsers": ["chromium"],
        "selectors": {"x": "#x"},
        "lifecycle": {"startup_command": "python -m http.server"},
    }
    norm = normalize_descriptor(doc)
    assert norm["schema_version"] == "1"
    assert norm["auth_flow"] == []
    assert norm["env_vars_required"] == []
    assert norm["test_isolation"] == "per_scenario"
    assert norm["lifecycle"]["bind_address"] == "127.0.0.1"
    assert norm["viewport"]["width"] == 1280
    assert norm["viewport"]["height"] == 720


def test_bind_address_pattern_rejects_non_ip(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "base_url: http://example.com\n"
        "browsers: [chromium]\n"
        "selectors: {x: '#x'}\n"
        "lifecycle:\n"
        "  bind_address: example.com\n"
    )
    with pytest.raises(DescriptorError):
        load_descriptor(bad)


def test_load_schema_survives_its_change_being_archived(tmp_path):
    """`descriptor.load_schema()` must resolve the schema at read time.

    The stability guard scans `test_*.py` only, so this module — production code
    in a skill's scripts/ directory — was never covered by it, and stored the
    active `openspec/changes/<id>/contracts/` path as a constant. Archiving
    factory-missions-architecture-alignment on 2026-09-09 moved that directory
    and broke six tests in this file at once. The test constant had already been
    fixed; the module had not.

    Builds both layouts under a fake repo root rather than mocking, so it asserts
    the resolution rule itself.
    """
    import descriptor

    schema = {"type": "object"}
    change_id = descriptor._SCHEMA_CHANGE_ID

    for relative in (
        Path("openspec/changes") / change_id,
        Path("openspec/changes/archive") / f"2026-09-09-{change_id}",
    ):
        root = tmp_path / relative.parts[-1].replace(".", "_")
        target = root / relative / "contracts"
        target.mkdir(parents=True)
        (target / descriptor._SCHEMA_FILENAME).write_text(
            json.dumps(schema), encoding="utf-8"
        )
        resolved = (
            descriptor._change_dir(root, change_id)
            / "contracts"
            / descriptor._SCHEMA_FILENAME
        )
        assert resolved.is_file(), f"unresolved for layout {relative}"

    # And the active spelling wins when both exist, matching the shared helper.
    both = tmp_path / "both"
    for relative in (
        Path("openspec/changes") / change_id,
        Path("openspec/changes/archive") / f"2026-09-09-{change_id}",
    ):
        (both / relative).mkdir(parents=True)
    assert descriptor._change_dir(both, change_id).name == change_id

