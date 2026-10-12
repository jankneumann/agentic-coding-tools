"""Pin the evidence-ledger schema copies (design D2).

``openspec/schemas/evidence-ledger.schema.json`` is the canonical copy. The skill's
``install_assets`` copy is what the validator loads and what ``install.sh`` ships, and
install.sh only *reports* drift, so this test has to fail on it. The change-local draft
under ``contracts/schemas/`` is what the plan was written against. All three copies are
byte-identical. The change directory is located with ``change_dir()``, so archival does
not break this test.
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from openspec_paths import change_dir, repo_root_from

REPO_ROOT = repo_root_from(__file__, 3)
CHANGE_ID = "define-evidence-ledger-schema-with-immutable-facts"
NAME = "evidence-ledger.schema.json"

CANONICAL = REPO_ROOT / "openspec" / "schemas" / NAME
SHIPPED = (
    REPO_ROOT / "skills" / "evidence-ledger" / "install_assets" / "openspec" / "schemas" / NAME
)


def _draft() -> Path:
    return change_dir(REPO_ROOT, CHANGE_ID) / "contracts" / "schemas" / NAME


def test_schema_copies_are_byte_identical() -> None:
    canonical = CANONICAL.read_bytes()
    assert SHIPPED.read_bytes() == canonical, "install_assets copy drifted"
    assert _draft().read_bytes() == canonical, "change-local draft drifted"


def test_schema_is_valid_draft_2020_12() -> None:
    schema = json.loads(CANONICAL.read_text(encoding="utf-8"))
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)
    assert schema["properties"]["schema_version"] == {"const": 1}


def test_every_object_with_properties_closes_additional_properties() -> None:
    schema = json.loads(CANONICAL.read_text(encoding="utf-8"))
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
    # root, fact, time_window, signal, hypothesis, reverify_request
    assert len(closed) == 6, closed
