"""Pin the two ownership-map schemas and exercise their boundaries.

Design D2 / D12: ``openspec/schemas/*.schema.json`` is the canonical copy; the skill's
``install_assets`` copy is what ``install.sh`` ships (it only *reports* drift, so a test
must fail it); the draft under the change's ``contracts/schemas/`` is what the plan was
written against. All three are byte-identical. The change directory is located with
``change_dir()`` so archival does not break this test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from openspec_paths import change_dir, repo_root_from

REPO_ROOT = repo_root_from(__file__, 3)
CHANGE_ID = "ownership-map"
SCHEMAS = ("owners.schema.json", "human-principals.schema.json")
FIXTURES = Path(__file__).resolve().parent / "fixtures"

CANONICAL = REPO_ROOT / "openspec" / "schemas"
SHIPPED = REPO_ROOT / "skills" / "ownership-runtime" / "install_assets" / "openspec" / "schemas"


def _draft(name: str) -> Path:
    return change_dir(REPO_ROOT, CHANGE_ID) / "contracts" / "schemas" / name


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _fixtures(kind: str, outcome: str) -> list[Path]:
    return sorted((FIXTURES / kind / outcome).glob("*.json"))


@pytest.mark.parametrize("name", SCHEMAS)
def test_schema_copies_are_byte_identical(name: str) -> None:
    canonical = (CANONICAL / name).read_bytes()
    assert (SHIPPED / name).read_bytes() == canonical, "install_assets copy drifted"
    assert _draft(name).read_bytes() == canonical, "change-local draft drifted"


@pytest.mark.parametrize("name", SCHEMAS)
def test_schemas_are_valid_draft_2020_12(name: str) -> None:
    schema = _load(CANONICAL / name)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)


def test_fixture_directories_are_populated() -> None:
    for kind in ("owners", "humans"):
        for outcome in ("valid", "invalid"):
            assert _fixtures(kind, outcome), f"no {kind}/{outcome} fixtures"


@pytest.mark.parametrize("path", _fixtures("owners", "valid"), ids=lambda p: p.stem)
def test_owners_valid_fixtures_pass(path: Path) -> None:
    Draft202012Validator(_load(CANONICAL / "owners.schema.json")).validate(_load(path))


@pytest.mark.parametrize("path", _fixtures("owners", "invalid"), ids=lambda p: p.stem)
def test_owners_invalid_fixtures_rejected(path: Path) -> None:
    validator = Draft202012Validator(_load(CANONICAL / "owners.schema.json"))
    with pytest.raises(ValidationError):
        validator.validate(_load(path))


@pytest.mark.parametrize("path", _fixtures("humans", "valid"), ids=lambda p: p.stem)
def test_humans_valid_fixtures_pass(path: Path) -> None:
    Draft202012Validator(_load(CANONICAL / "human-principals.schema.json")).validate(_load(path))


@pytest.mark.parametrize("path", _fixtures("humans", "invalid"), ids=lambda p: p.stem)
def test_humans_invalid_fixtures_rejected(path: Path) -> None:
    validator = Draft202012Validator(_load(CANONICAL / "human-principals.schema.json"))
    with pytest.raises(ValidationError):
        validator.validate(_load(path))


def test_unknown_key_error_names_the_offending_path() -> None:
    validator = Draft202012Validator(_load(CANONICAL / "owners.schema.json"))
    errors = list(
        validator.iter_errors(_load(FIXTURES / "owners/invalid/unknown_assignment_key.json"))
    )
    assert errors
    assert "reviewers" in errors[0].message
    assert list(errors[0].absolute_path) == ["assignments", "capabilities", "x"]


def test_every_object_in_owners_schema_closes_additional_properties() -> None:
    """Every explicit object boundary rejects unknown keys (spec: 'at every level')."""
    schema = _load(CANONICAL / "owners.schema.json")
    closed: list[str] = []

    def walk(node: object, where: str) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                assert node.get("additionalProperties") is False, where
                closed.append(where)
            for key, value in node.items():
                walk(value, f"{where}/{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{where}[{index}]")

    walk(schema, "#")
    assert len(closed) >= 3
