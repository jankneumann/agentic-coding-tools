"""The lane manifest validates against its schema; bad manifests are rejected."""

from __future__ import annotations

import copy
import json

import jsonschema
import pytest
from jsonschema import Draft202012Validator


@pytest.fixture(scope="module")
def schema(repo_root):
    return json.loads((repo_root / ".github" / "runner-lanes.schema.json").read_text())


def test_schema_is_valid_draft_2020_12(schema):
    Draft202012Validator.check_schema(schema)


def test_manifest_validates(schema, manifest):
    Draft202012Validator(schema).validate(manifest)


def _first_hosted(manifest):
    for wf in manifest["workflows"].values():
        for job in wf["jobs"].values():
            if job["lane"] == "hosted":
                return job
    raise AssertionError("manifest has no hosted job")


def _mutate_missing_reason_code(m):
    del _first_hosted(m)["reason_code"]


def _mutate_empty_reason(m):
    _first_hosted(m)["reason"] = ""


def _mutate_unknown_reason_code(m):
    _first_hosted(m)["reason_code"] = "because-i-said-so"


def _mutate_hosted_label(m):
    m["routing"]["hosted_label"] = "ubuntu-22.04"


def _mutate_no_self_hosted_label(m):
    m["routing"]["self_hosted_labels"] = ["linux", "ARM64", "gx10"]


@pytest.mark.parametrize(
    "mutate",
    [
        _mutate_missing_reason_code,
        _mutate_empty_reason,
        _mutate_unknown_reason_code,
        _mutate_hosted_label,
        _mutate_no_self_hosted_label,
    ],
)
def test_negative_fixtures_rejected(schema, manifest, mutate):
    bad = copy.deepcopy(manifest)
    mutate(bad)
    with pytest.raises(jsonschema.ValidationError):
        Draft202012Validator(schema).validate(bad)
