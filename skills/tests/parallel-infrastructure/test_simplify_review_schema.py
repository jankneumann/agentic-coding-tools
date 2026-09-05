"""Contract tests for `contracts/events/simplify-review.schema.json`.

The simplify review artifact is the coordination boundary between the Review
role of `simplify-implementation` (which writes it) and the Apply role (which
consumes it, and renders `test-prune-ledger.md` from it). The contract is
composed by `allOf` over the canonical `review-findings.schema.json` by `$id`,
so a validator must register both documents — these tests do that and then
exercise the four conditional rules the contract adds on top of the canonical
envelope.

RED before the enum additions land: the fixtures use `review_type: simplify`
and `type: simplification | test_quality`, none of which the canonical schema
allowed before this change.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012


def _repo_root() -> Path:
    """Walk up from this test file until the `openspec/` tree appears."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "openspec").is_dir():
            return candidate
    raise RuntimeError("could not locate the repo root (no openspec/ ancestor)")


REPO_ROOT = _repo_root()
CANONICAL_SCHEMA_PATH = (
    REPO_ROOT / "openspec" / "schemas" / "review-findings.schema.json"
)
CONTRACT_DIR = (
    REPO_ROOT
    / "openspec"
    / "changes"
    / "add-autopilot-simplify-phase"
    / "contracts"
)
CONTRACT_SCHEMA_PATH = CONTRACT_DIR / "events" / "simplify-review.schema.json"
VALID_FIXTURE_PATH = CONTRACT_DIR / "fixtures" / "simplify-review.valid.json"
INVALID_FIXTURE_PATH = CONTRACT_DIR / "fixtures" / "simplify-review.invalid.json"


@pytest.fixture(scope="module")
def canonical_schema() -> dict:
    return json.loads(CANONICAL_SCHEMA_PATH.read_text())


@pytest.fixture(scope="module")
def contract_schema() -> dict:
    return json.loads(CONTRACT_SCHEMA_PATH.read_text())


@pytest.fixture(scope="module")
def contract_validator(canonical_schema, contract_schema) -> Draft202012Validator:
    """A validator for the contract, with the canonical schema resolvable by `$id`."""
    registry = Registry().with_resources(
        [
            (doc["$id"], Resource.from_contents(doc, default_specification=DRAFT202012))
            for doc in (canonical_schema, contract_schema)
        ]
    )
    return Draft202012Validator(contract_schema, registry=registry)


@pytest.fixture(scope="module")
def canonical_validator(canonical_schema) -> Draft202012Validator:
    return Draft202012Validator(canonical_schema)


@pytest.fixture(scope="module")
def valid_fixture() -> dict:
    return json.loads(VALID_FIXTURE_PATH.read_text())


@pytest.fixture(scope="module")
def invalid_fixture() -> dict:
    return json.loads(INVALID_FIXTURE_PATH.read_text())


def test_contract_is_a_valid_2020_12_schema(contract_schema):
    Draft202012Validator.check_schema(contract_schema)


def test_valid_fixture_passes_the_contract(contract_validator, valid_fixture):
    errors = sorted(contract_validator.iter_errors(valid_fixture), key=str)
    assert not errors, [f"{list(e.absolute_path)}: {e.message}" for e in errors]


def test_valid_fixture_passes_the_canonical_schema_alone(
    canonical_validator, valid_fixture
):
    """The artifact is a review-findings document first; the contract only narrows it."""
    errors = sorted(canonical_validator.iter_errors(valid_fixture), key=str)
    assert not errors, [f"{list(e.absolute_path)}: {e.message}" for e in errors]


def test_invalid_fixture_is_rejected_on_covered_by(contract_validator, invalid_fixture):
    """`prune.reason: change-detector` with a null `covered_by` is the only defect."""
    errors = list(contract_validator.iter_errors(invalid_fixture))
    assert len(errors) == 1, [
        f"{list(e.absolute_path)}: {e.message}" for e in errors
    ]
    (error,) = errors
    assert list(error.absolute_path) == ["findings", 0, "prune", "covered_by"], (
        f"expected the covered_by rule to fail, got {list(error.absolute_path)}: "
        f"{error.message}"
    )


def test_specified_consumer_cannot_be_dispositioned_fix(
    contract_validator, valid_fixture
):
    """A seam with a specified consumer must stay `keep` / non-`fix`."""
    document = json.loads(json.dumps(valid_fixture))
    seam = next(f for f in document["findings"] if f["id"] == 3)
    assert seam["consumer"]["specified"], "fixture must carry a specified consumer"
    seam["disposition"] = "fix"
    seam["fence"]["verdict"] = "remove"

    failed_paths = {
        tuple(error.absolute_path)
        for error in contract_validator.iter_errors(document)
    }
    assert ("findings", 2, "fence", "verdict") in failed_paths, (
        f"a specified consumer must force fence.verdict keep; failures were {failed_paths}"
    )
    assert ("findings", 2, "disposition") in failed_paths, (
        f"a specified consumer must forbid disposition fix; failures were {failed_paths}"
    )
