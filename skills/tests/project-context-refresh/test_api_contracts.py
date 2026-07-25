"""api.contracts producer tests (tasks 3.1-3.2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from _runtime import ChangeKind, ProducerStatus
from contract import validate_producer_result
from producer_api_contracts import ApiContractsProducer

FULL_SHA = "b" * 40


def _schema(cap_id: str) -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://example.dev/{cap_id}.schema.json",
        "type": "object",
    }


def _write_contract(repo: Path, capability: str, name: str, data: dict) -> None:
    d = repo / "openspec/contracts" / capability / "schemas"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps(data, indent=2), encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _write_contract(tmp_path, "beta", "b.schema.json", _schema("beta"))
    _write_contract(tmp_path, "alpha", "a.schema.json", _schema("alpha"))
    return tmp_path


def _target(repo: Path) -> Path:
    return repo / "docs/architecture-analysis/contracts-inventory.md"


def test_generate_indexes_valid_schemas(repo: Path):
    result = ApiContractsProducer().run("generate", repo, FULL_SHA)
    validate_producer_result(result)
    assert result.status is ProducerStatus.FRESH
    text = _target(repo).read_text()
    assert text.index("alpha") < text.index("beta")  # capability-sorted rows
    assert "https://example.dev/alpha.schema.json" in text


def test_check_reports_added_drift_and_writes_nothing(repo: Path):
    result = ApiContractsProducer().run("check", repo, FULL_SHA)
    validate_producer_result(result)
    assert result.status is ProducerStatus.DEGRADED
    assert result.artifacts[0].change is ChangeKind.ADDED
    assert not _target(repo).exists()


def test_new_contract_makes_inventory_stale(repo: Path):
    ApiContractsProducer().run("generate", repo, FULL_SHA)
    before = _target(repo).read_bytes()
    _write_contract(repo, "gamma", "g.schema.json", _schema("gamma"))
    result = ApiContractsProducer().run("check", repo, FULL_SHA)
    assert result.status is ProducerStatus.DEGRADED
    assert result.artifacts[0].change is ChangeKind.MODIFIED
    assert _target(repo).read_bytes() == before  # check wrote nothing


def test_malformed_json_schema_fails(repo: Path):
    bad = repo / "openspec/contracts/broken/schemas"
    bad.mkdir(parents=True, exist_ok=True)
    (bad / "bad.schema.json").write_text("{not json", encoding="utf-8")
    result = ApiContractsProducer().run("check", repo, FULL_SHA)
    assert result.status is ProducerStatus.FAILED
    assert result.error is not None
    assert "invalid JSON" in result.error.summary


def test_invalid_schema_fails(repo: Path):
    bad = repo / "openspec/contracts/broken/schemas"
    bad.mkdir(parents=True, exist_ok=True)
    # Valid JSON, invalid JSON Schema (type must be a known keyword value).
    (bad / "bad.schema.json").write_text(
        json.dumps({"type": 123}), encoding="utf-8"
    )
    result = ApiContractsProducer().run("check", repo, FULL_SHA)
    assert result.status is ProducerStatus.FAILED
    assert "invalid JSON Schema" in result.error.summary


def test_repeat_generation_byte_identical(repo: Path):
    ApiContractsProducer().run("generate", repo, FULL_SHA)
    first = _target(repo).read_bytes()
    ApiContractsProducer().run("generate", repo, FULL_SHA)
    assert _target(repo).read_bytes() == first
