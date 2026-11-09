"""Executable parity checks for the dg-01 vendor-registry contracts.

These tests exercise the OpenAPI and event schemas as real JSON Schema rather
than only checking that expected keys occur in the source files.  The SQL
assertions pin the storage boundary consumed by the later registry package.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from openspec_paths import change_dir, repo_root_from

_CHANGE = change_dir(
    repo_root_from(__file__, 2), "add-live-vendor-capability-and-cost-registry"
)
_CONTRACTS = _CHANGE / "contracts"
_OPENAPI = _CONTRACTS / "openapi/v1.yaml"
_EVENTS = _CONTRACTS / "events/vendor-availability.schema.json"
_DB = _CONTRACTS / "db/schema.sql"


def _openapi() -> dict[str, Any]:
    return yaml.safe_load(_OPENAPI.read_text())


def _validator(schema: dict[str, Any]) -> Draft202012Validator:
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _rate_limit_payload(**overrides: Any) -> dict[str, Any]:
    payload = {"observation_id": "obs-1", "reason": "capacity"}
    payload.update(overrides)
    return payload


def _event_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "observation_id": "obs-1",
        "agent_id": "claude-reviewer",
        "kind": "probe",
        "source_agent_id": "watchdog",
        "observed_at": "2026-09-16T12:00:00Z",
        "status": "available",
        "stale_after": "2026-09-16T12:02:00Z",
    }
    payload.update(overrides)
    return payload


def _table_body(sql: str, table: str) -> str:
    match = re.search(
        rf"CREATE TABLE IF NOT EXISTS {table}\s*\((.*?)\n\);",
        sql,
        flags=re.DOTALL,
    )
    assert match is not None, f"missing table contract for {table}"
    return match.group(1)


def test_openapi_declares_registry_routes_and_repository_auth_headers() -> None:
    document = _openapi()

    assert document["openapi"] == "3.1.0"
    assert set(document["paths"]) == {
        "/vendors",
        "/vendors/{agent_id}/availability",
        "/vendors/{agent_id}/rate-limit-observations",
    }
    assert document["security"] == [
        {"CoordinatorBearer": []},
        {"CoordinatorApiKey": []},
        {"CoordinatorLegacyApiKey": []},
    ]
    schemes = document["components"]["securitySchemes"]
    assert schemes["CoordinatorApiKey"]["name"] == "X-API-Key"
    assert schemes["CoordinatorLegacyApiKey"]["name"] == (
        "X-Coordinator-API-Key"
    )


def test_rate_limit_schema_accepts_default_lane_and_each_reset_form() -> None:
    schema = _openapi()["components"]["schemas"]["RateLimitObservation"]
    validator = _validator(schema)

    validator.validate(_rate_limit_payload())
    validator.validate(_rate_limit_payload(reset_at="2026-09-16T12:15:00Z"))
    validator.validate(_rate_limit_payload(retry_after_seconds=30))


@pytest.mark.parametrize(
    "payload",
    [
        _rate_limit_payload(
            reset_at="2026-09-16T12:15:00Z", retry_after_seconds=30
        ),
        _rate_limit_payload(retry_after_seconds=0),
        _rate_limit_payload(retry_after_seconds=604801),
    ],
)
def test_rate_limit_schema_rejects_conflicting_or_unbounded_resets(
    payload: dict[str, Any],
) -> None:
    schema = _openapi()["components"]["schemas"]["RateLimitObservation"]

    assert list(_validator(schema).iter_errors(payload))


@pytest.mark.parametrize("model", [None, "", "   "])
def test_rate_limit_schema_requires_concrete_model_for_model_scope(
    model: str | None,
) -> None:
    schema = _openapi()["components"]["schemas"]["RateLimitObservation"]
    payload = _rate_limit_payload(scope="model", model=model)

    assert list(_validator(schema).iter_errors(payload))


@pytest.mark.parametrize("model", [None, "", "   "])
def test_active_limit_schema_requires_concrete_model_for_model_scope(
    model: str | None,
) -> None:
    schema = _openapi()["components"]["schemas"]["ActiveRateLimit"]
    payload = {
        "observation_id": "obs-1",
        "scope": "model",
        "model": model,
        "reason": "capacity",
        "source_agent_id": "autopilot",
        "observed_at": "2026-09-16T12:00:00Z",
        "reset_at": "2026-09-16T12:15:00Z",
    }

    assert list(_validator(schema).iter_errors(payload))


def test_catalog_projection_requires_every_runtime_field() -> None:
    schema = _openapi()["components"]["schemas"]["CatalogModelPrice"]

    assert set(schema["required"]) == {
        "catalog_vendor",
        "model",
        "endpoint_kind",
        "base_url",
        "prompt_usd_per_mtok",
        "completion_usd_per_mtok",
        "refreshed_at",
        "available",
        "stale",
    }


def test_event_schema_accepts_probe_and_lane_limit_payloads() -> None:
    schema = json.loads(_EVENTS.read_text())
    validator = _validator(schema)

    validator.validate(_event_payload())
    validator.validate(
        {
            "observation_id": "obs-2",
            "agent_id": "claude-reviewer",
            "kind": "rate_limit",
            "source_agent_id": "autopilot",
            "observed_at": "2026-09-16T12:00:00Z",
            "reason": "capacity",
            "scope": "lane",
            "reset_at": "2026-09-16T12:15:00Z",
        }
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "rate_limit", "reason": None, "scope": "lane"},
        {"kind": "rate_limit", "reason": "capacity", "scope": "model"},
        {
            "kind": "rate_limit",
            "reason": "capacity",
            "scope": "model",
            "model": None,
        },
        {
            "kind": "rate_limit",
            "reason": "capacity",
            "scope": "model",
            "model": "",
        },
    ],
)
def test_event_schema_rejects_incomplete_rate_limit_payloads(
    overrides: dict[str, Any],
) -> None:
    schema = json.loads(_EVENTS.read_text())
    payload = {
        "observation_id": "obs-1",
        "agent_id": "claude-reviewer",
        "kind": "rate_limit",
        "source_agent_id": "autopilot",
        "observed_at": "2026-09-16T12:00:00Z",
        "reset_at": "2026-09-16T12:15:00Z",
    }
    payload.update(overrides)

    assert list(_validator(schema).iter_errors(payload))


def test_sql_contract_has_atomic_state_operations_without_price_ownership() -> None:
    sql = _DB.read_text()
    probe = _table_body(sql, "vendor_probe_state")
    limits = _table_body(sql, "vendor_rate_limits")

    for function in (
        "upsert_vendor_probe_state",
        "record_vendor_rate_limit",
        "compact_vendor_rate_limits",
    ):
        assert f"CREATE OR REPLACE FUNCTION {function}" in sql
    assert "observation_id TEXT NOT NULL" in probe
    assert "payload_hash TEXT NOT NULL" in limits
    assert not re.search(r"(?:price|cost|usd)", probe, flags=re.IGNORECASE)
    assert not re.search(r"(?:price|cost|usd)", limits, flags=re.IGNORECASE)


def test_sql_model_scope_requires_a_nonblank_model() -> None:
    limits = _table_body(_DB.read_text(), "vendor_rate_limits")

    assert "NULLIF(BTRIM(model), '') IS NOT NULL" in limits
