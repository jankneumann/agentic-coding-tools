"""wp-contracts verification (tasks 1.1–1.4).

Asserts the routing contract set is well-formed and that the generated Pydantic
models stay in parity with the OpenAPI source — this is the coordination boundary
downstream packages depend on, so drift here is a contract break.

Env-safe: no DB, no network. Runs in cloud and local.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import get_args

import pytest
import yaml

_CHANGE = Path(__file__).resolve().parents[3] / "openspec/changes/add-adaptive-model-router"
_CONTRACTS = _CHANGE / "contracts"
_OPENAPI = _CONTRACTS / "openapi/v1.yaml"
_EVENTS = _CONTRACTS / "events/routing-signal.schema.json"
_DB = _CONTRACTS / "db/schema.sql"
_MODELS = _CONTRACTS / "generated/models.py"


def _load_generated():
    import sys

    spec = importlib.util.spec_from_file_location("routing_generated_models", _MODELS)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    # Register before exec so Pydantic can resolve `from __future__ import annotations`
    # forward refs (EndpointKind etc.) against the module namespace.
    sys.modules["routing_generated_models"] = module
    spec.loader.exec_module(module)
    return module


def test_openapi_parses_and_has_routing_paths():
    """model-routing.4 / agent-coordinator.1 — OpenAPI contract is valid and complete."""
    doc = yaml.safe_load(_OPENAPI.read_text())
    assert doc["openapi"].startswith("3.")
    for path in (
        "/routing/select_model",
        "/routing/catalog",
        "/routing/decisions/{decision_id}",
        "/routing/usage",
        "/routing/feedback",
    ):
        assert path in doc["paths"], f"missing routing path {path}"


def test_event_schema_is_valid_json_schema():
    """model-routing.10 — signal event schema is a valid Draft 2020-12 schema."""
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(_EVENTS.read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    assert "decision_provenance" in schema["properties"]["family"]["enum"]


def test_db_contract_declares_four_routing_tables():
    """agent-coordinator.2 — DB contract covers the four additive tables."""
    sql = _DB.read_text()
    for table in (
        "model_catalog",
        "model_posteriors",
        "routing_decisions",
        "routing_spend_ledger",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql, f"missing table {table}"


def test_generated_models_import_and_roundtrip():
    """model-routing.4 — generated models construct from a contract-shaped payload."""
    m = _load_generated()
    resp = m.SelectModelResponse(
        decision_id="3f1b7c1e-9a3d-4f9d-8b1a-2c6e5d4a9b0c",
        selected=m.Candidate(
            vendor="local", model="qwen3-coder-32b", endpoint_kind="local", score=0.66
        ),
        exploration=True,
        excluded=[
            m.ExcludedCandidate(
                vendor="claude", model="fable-5", reason="cedar:programmatic-ineligible"
            )
        ],
    )
    assert resp.selected.endpoint_kind == "local"
    assert resp.excluded[0].reason.startswith("cedar:")


def test_generated_candidate_matches_openapi_fields():
    """Parity guard: generated Candidate field set == OpenAPI Candidate schema.

    Bidirectional: the model may not drop an OpenAPI-declared field, and it may
    not silently carry a field (e.g. provenance like ``cost_source``) that the
    OpenAPI contract omits — OpenAPI-generated clients would drop/reject it.
    """
    m = _load_generated()
    doc = yaml.safe_load(_OPENAPI.read_text())
    openapi_fields = set(doc["components"]["schemas"]["Candidate"]["properties"].keys())
    model_fields = set(m.Candidate.model_fields.keys())
    missing = openapi_fields - model_fields
    extra = model_fields - openapi_fields
    assert not missing, f"generated Candidate missing OpenAPI fields: {missing}"
    assert not extra, f"generated Candidate has fields absent from OpenAPI: {extra}"


def test_generated_feedback_source_enum_matches_contract():
    """model-routing.9 — feedback source enum parity."""
    m = _load_generated()
    doc = yaml.safe_load(_OPENAPI.read_text())
    feedback_props = doc["components"]["schemas"]["FeedbackEvent"]["properties"]
    contract_enum = set(feedback_props["source"]["enum"])
    # FeedbackSource is a Literal; extract its args.
    assert set(get_args(m.FeedbackSource)) == contract_enum
