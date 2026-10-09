"""Contract tests: CLI contract, report schema, traceability and promotion (G.4, A.1).

Everything is read through ``repo_root_from`` and ``change_dir`` so the tests
survive archival of this change (design D10). The contract and schema are read
from their promoted paths under ``openspec/contracts/multiplayer-simulation/``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import pytest
import yaml
from referencing import Registry, Resource
from openspec_paths import change_dir, repo_root_from

CHANGE_ID = "multiplayer-simulation-harness"
CAPABILITY = "multiplayer-simulation"

REPO = repo_root_from(__file__, 3)
PROMOTED = REPO / "openspec" / "contracts" / CAPABILITY
CLI_CONTRACT = PROMOTED / "cli" / "mpsim.yaml"
REPORT_SCHEMA = PROMOTED / "schemas" / "sim-report.schema.json"
CLI_CONTRACT_SCHEMA = (
    REPO / "openspec" / "contracts" / "gen-eval-framework" / "schemas" / "cli-contract.schema.json"
)


def _local_registry() -> Registry:
    """Resolve the schema's sibling $refs from disk; the harness runs offline (D9)."""
    registry: Registry = Registry()
    for path in sorted(CLI_CONTRACT_SCHEMA.parent.glob("*.schema.json")):
        doc = json.loads(path.read_text())
        registry = registry.with_resource(doc["$id"], Resource.from_contents(doc))
    return registry


def _change_local(rel: str) -> Path:
    return change_dir(REPO, CHANGE_ID) / "contracts" / rel


def _slug(heading: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")


def _spec_requirement_slugs() -> set[str]:
    spec = change_dir(REPO, CHANGE_ID) / "specs" / CAPABILITY / "spec.md"
    headings = re.findall(r"^### Requirement:\s*(.+?)\s*$", spec.read_text(), re.MULTILINE)
    assert headings, f"no requirement headings found in {spec}"
    return {f"{CAPABILITY}.{_slug(h)}" for h in headings}


def _citations(node) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "traceability":
                found.extend(value.get("requirements", []))
            else:
                found.extend(_citations(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_citations(item))
    return found


def test_cli_contract_validates_against_the_cli_contract_schema():
    schema = json.loads(CLI_CONTRACT_SCHEMA.read_text())
    contract = yaml.safe_load(CLI_CONTRACT.read_text())
    validator = jsonschema.Draft202012Validator(schema, registry=_local_registry())
    errors = [e.message for e in validator.iter_errors(contract)]
    assert errors == []


def test_report_schema_is_a_valid_draft_2020_12_schema():
    schema = json.loads(REPORT_SCHEMA.read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema["$schema"].endswith("2020-12/schema")


def test_every_traceability_citation_resolves_to_a_requirement_heading():
    contract = yaml.safe_load(CLI_CONTRACT.read_text())
    cited = _citations(contract)
    assert cited, "the contract cites no requirements"
    known = _spec_requirement_slugs()
    unresolved = sorted(set(cited) - known)
    assert unresolved == []


@pytest.mark.parametrize(
    ("promoted", "local"),
    [
        (CLI_CONTRACT, "cli/mpsim.yaml"),
        (REPORT_SCHEMA, "schemas/sim-report.schema.json"),
    ],
)
def test_promoted_copy_is_byte_identical_to_the_change_local_copy(promoted: Path, local: str):
    assert promoted.read_bytes() == _change_local(local).read_bytes()
