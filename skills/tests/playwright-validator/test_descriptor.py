"""Tests for skills/playwright-validator/scripts/descriptor.py.

Covers task 7.1: contract test for frontend-descriptor.schema.json.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from descriptor import (
    DescriptorError,
    is_frontend_descriptor,
    load_descriptor,
    load_schema,
    normalize_descriptor,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_DESCRIPTOR = (
    REPO_ROOT / "evaluation" / "gen_eval" / "descriptors" / "sample-frontend.yaml"
)
SCHEMA_PATH = (
    REPO_ROOT
    / "openspec"
    / "changes"
    / "factory-missions-architecture-alignment"
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
