"""wp-contracts verification (tasks 1.1–1.3).

Asserts the routing contract set is well-formed and that the generated Pydantic
models stay in parity with the OpenAPI source — this is the coordination boundary
downstream packages depend on, so drift here is a contract break.

Env-safe: no DB, no network. Runs in cloud and local.
"""

from __future__ import annotations

import importlib.util
import json
from typing import get_args

import pytest
import yaml
from openspec_paths import change_dir, repo_root_from

_CHANGE = change_dir(repo_root_from(__file__, 3), "add-adaptive-model-router")
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


def _load_openapi() -> dict:
    return yaml.safe_load(_OPENAPI.read_text())


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


def test_openapi_declares_bearer_auth_for_every_routing_operation():
    doc = _load_openapi()
    assert doc["components"]["securitySchemes"]["CoordinatorBearer"] == {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "API key",
    }
    assert doc["security"] == [{"CoordinatorBearer": []}]


def test_openapi_documents_actual_auth_and_unavailable_json_bodies():
    doc = _load_openapi()
    for path_item in doc["paths"].values():
        for operation in path_item.values():
            assert operation["responses"]["401"] == {
                "$ref": "#/components/responses/Unauthorized"
            }

    select_responses = doc["paths"]["/routing/select_model"]["post"]["responses"]
    assert select_responses["503"] == {
        "$ref": "#/components/responses/RoutingUnavailable"
    }
    for name in ("Unauthorized", "RoutingUnavailable"):
        content = doc["components"]["responses"][name]["content"]
        assert set(content) == {"application/json"}
        assert content["application/json"]["schema"] == {
            "$ref": "#/components/schemas/HTTPError"
        }


def test_openapi_31_uses_json_schema_null_unions_not_nullable_keyword():
    def assert_no_nullable(value: object, path: str = "$") -> None:
        if isinstance(value, dict):
            assert "nullable" not in value, f"OpenAPI 3.1 nullable keyword at {path}"
            for key, child in value.items():
                assert_no_nullable(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                assert_no_nullable(child, f"{path}[{index}]")

    assert_no_nullable(_load_openapi())


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
        alternatives=[],
        exploration=True,
        excluded=[
            m.ExcludedCandidate(
                vendor="claude", model="fable-5", reason="cedar:programmatic-ineligible"
            )
        ],
    )
    assert resp.selected.endpoint_kind == "local"
    assert resp.excluded[0].reason.startswith("cedar:")


@pytest.mark.parametrize(
    ("schema_name", "model_name"),
    [
        ("SelectModelRequest", "SelectModelRequest"),
        ("Candidate", "Candidate"),
        ("SelectModelResponse", "SelectModelResponse"),
        ("CatalogRow", "CatalogRow"),
        ("RoutingDecision", "RoutingDecision"),
        ("UsageAggregate", "UsageAggregate"),
        ("FeedbackEvent", "FeedbackEvent"),
    ],
)
def test_generated_models_match_openapi_fields_and_requiredness(
    schema_name: str, model_name: str
):
    """Parity guard covers fields and required/default semantics."""
    m = _load_generated()
    schema = _load_openapi()["components"]["schemas"][schema_name]
    model_fields_by_name = getattr(m, model_name).model_fields
    openapi_fields = set(schema["properties"])
    model_fields = set(model_fields_by_name)
    missing = openapi_fields - model_fields
    extra = model_fields - openapi_fields
    assert not missing, f"generated {model_name} missing OpenAPI fields: {missing}"
    assert not extra, f"generated {model_name} has fields absent from OpenAPI: {extra}"
    generated_required = {
        name for name, field in model_fields_by_name.items() if field.is_required()
    }
    assert generated_required == set(schema.get("required", []))


def test_excluded_candidate_requiredness_matches_generated_model():
    m = _load_generated()
    excluded = _load_openapi()["components"]["schemas"]["SelectModelResponse"][
        "properties"
    ]["excluded"]["items"]
    generated_required = {
        name
        for name, field in m.ExcludedCandidate.model_fields.items()
        if field.is_required()
    }
    assert generated_required == set(excluded.get("required", []))


def test_posterior_sample_size_preserves_fractional_effective_counts():
    candidate = _load_openapi()["components"]["schemas"]["Candidate"]
    assert candidate["properties"]["posterior_sample_size"]["type"] == [
        "number",
        "null",
    ]
    annotation = _load_generated().Candidate.model_fields[
        "posterior_sample_size"
    ].annotation
    assert float in get_args(annotation)


def test_feedback_contract_states_dg00_audit_only_semantics():
    feedback = _load_openapi()["components"]["schemas"]["FeedbackEvent"]
    assert "does not associate feedback with a catalog row" in feedback["description"]


def test_generated_feedback_source_enum_matches_contract():
    """model-routing.9 — feedback source enum parity."""
    m = _load_generated()
    doc = yaml.safe_load(_OPENAPI.read_text())
    feedback_props = doc["components"]["schemas"]["FeedbackEvent"]["properties"]
    contract_enum = set(feedback_props["source"]["enum"])
    # FeedbackSource is a Literal; extract its args.
    assert set(get_args(m.FeedbackSource)) == contract_enum
