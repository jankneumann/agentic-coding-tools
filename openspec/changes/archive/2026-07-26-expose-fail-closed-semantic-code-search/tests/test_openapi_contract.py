from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012


CHANGE_DIR = Path(__file__).resolve().parents[1]
OPENAPI_PATH = CHANGE_DIR / "contracts" / "openapi" / "v2.yaml"
OPENAPI = yaml.safe_load(OPENAPI_PATH.read_text())
FORMAT_CHECKER = FormatChecker()
OPENAPI_URI = "urn:code-search-openapi:v2"
REGISTRY = Registry().with_resource(
    OPENAPI_URI,
    Resource.from_contents(OPENAPI, default_specification=DRAFT202012),
)


def _schema(name: str) -> dict[str, Any]:
    return OPENAPI["components"]["schemas"][name]


def _validator(name: str) -> Draft202012Validator:
    # The component schemas retain their OpenAPI-local refs, so validation
    # resolves them against the complete document.
    return Draft202012Validator(
        {"$ref": f"{OPENAPI_URI}#/components/schemas/{name}"},
        registry=REGISTRY,
        format_checker=FORMAT_CHECKER,
    )


def _assert_valid(schema_name: str, instance: object) -> None:
    _validator(schema_name).validate(instance)


def _assert_invalid(schema_name: str, instance: object) -> None:
    with pytest.raises(ValidationError):
        _validator(schema_name).validate(instance)


def _main_request() -> dict[str, Any]:
    return {
        "query": "where is work-package scope enforced",
        "repo_slug": "agentic_coding_tools",
        "source_revision": "a" * 40,
        "namespace": {"kind": "main", "key": "main"},
        "scope": {
            "kind": "explicit",
            "read_allow": ["agent-coordinator/**"],
            "deny": ["**/.env*"],
        },
        "limit": 10,
        "offset": 0,
    }


def _index_provenance() -> dict[str, Any]:
    return {
        "index_id": "11111111-1111-4111-8111-111111111111",
        "repo_slug": "agentic_coding_tools",
        "source_revision": "a" * 40,
        "namespace": {"kind": "main", "key": "main"},
        "embedder_model": "text-embedding-model",
        "embedding_dim": 768,
        "embedder_fingerprint": "b" * 64,
        "policy_fingerprint": "c" * 64,
        "pipeline_fingerprint": "d" * 64,
        "completed_at": "2026-07-23T12:00:00Z",
    }


def _hit() -> dict[str, Any]:
    return {
        "file_path": "agent-coordinator/src/code_search.py",
        "language": "python",
        "content": "class CodeSearchService:",
        "start_line": 120,
        "end_line": 140,
        "similarity": 0.82,
        "repo_slug": "agentic_coding_tools",
        "source_revision": "a" * 40,
        "index_id": "11111111-1111-4111-8111-111111111111",
        "scope_decision": "allowed",
    }


def _response(
    state: str = "ready",
    *,
    scope_decision: str = "allowed",
) -> dict[str, Any]:
    ready = state == "ready"
    return {
        "state": state,
        "current": ready,
        "request": {
            "repo_slug": "agentic_coding_tools",
            "source_revision": "a" * 40,
            "namespace": {"kind": "main", "key": "main"},
            "index_id": None,
        },
        "index": (
            None
            if state in {"not_indexed", "scope_rejected"}
            else _index_provenance()
        ),
        "scope": {
            "decision": scope_decision,
            "source": "explicit",
            "authority": "principal_grant",
        },
        "results": [_hit()] if ready else [],
        "fallback": {
            "required": not ready,
            "strategy": "exact_search",
            "reason": None if ready else state,
        },
    }


def test_openapi_document_and_operation_boundary_are_frozen() -> None:
    assert OPENAPI["openapi"] == "3.1.0"
    post = OPENAPI["paths"]["/search/code"]["post"]
    status = OPENAPI["paths"]["/search/code/status"]["get"]

    assert post["operationId"] == "searchCodeV2"
    assert post["requestBody"]["required"] is True
    assert post["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/CodeSearchRequest"
    }
    assert post["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/CodeSearchResponse"
    }
    assert post["security"] == [
        {"bearerAuth": []},
        {"coordinatorApiKey": []},
    ]
    assert status["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/CodeSearchStatus"
    }


def test_request_accepts_exact_main_and_non_main_identity() -> None:
    _assert_valid("CodeSearchRequest", _main_request())

    non_main = _main_request()
    non_main["namespace"] = {"kind": "work_package", "key": "wp-query-service"}
    non_main["index_id"] = "11111111-1111-4111-8111-111111111111"
    non_main["scope"] = {
        "kind": "work_package",
        "change_id": "expose-fail-closed-semantic-code-search",
        "package_id": "wp-query-service",
        "scope_revision": "e" * 64,
    }
    _assert_valid("CodeSearchRequest", non_main)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda request: request.pop("source_revision"),
        lambda request: request.pop("scope"),
        lambda request: request.update(source_revision="a" * 12),
        lambda request: request.update(repo_slug="Agentic-Coding-Tools"),
        lambda request: request.update(unexpected=True),
        lambda request: request.update(
            namespace={"kind": "main", "key": "not-main"}
        ),
        lambda request: request.update(
            scope={
                "kind": "explicit",
                "read_allow": [],
            }
        ),
        lambda request: request.update(
            scope={
                "kind": "explicit",
                "read_allow": ["agent-coordinator/**"],
                "change_id": "mixed-scope-variants",
            }
        ),
    ],
)
def test_request_rejects_missing_or_malformed_exact_identity(mutate: Any) -> None:
    request = _main_request()
    mutate(request)
    _assert_invalid("CodeSearchRequest", request)


@pytest.mark.parametrize("kind", ["feature", "work_package"])
def test_non_main_request_requires_exact_index_id(kind: str) -> None:
    request = _main_request()
    request["namespace"] = {"kind": kind, "key": "bounded-key"}
    _assert_invalid("CodeSearchRequest", request)


def test_ready_response_requires_current_allowed_provenance_and_no_fallback() -> None:
    response = _response()
    _assert_valid("CodeSearchResponse", response)

    for mutation in (
        lambda value: value.update(current=False),
        lambda value: value["fallback"].update(required=True),
        lambda value: value["fallback"].update(reason="unavailable"),
        lambda value: value.update(index=None),
        lambda value: value["scope"].update(decision="rejected"),
        lambda value: value["results"][0].pop("source_revision"),
        lambda value: value["results"][0].update(similarity=1.01),
    ):
        invalid = deepcopy(response)
        mutation(invalid)
        _assert_invalid("CodeSearchResponse", invalid)


@pytest.mark.parametrize(
    "state",
    [
        "revision_mismatch",
        "not_indexed",
        "not_configured",
        "unavailable",
        "scope_rejected",
    ],
)
def test_non_ready_response_requires_zero_hits_and_matching_exact_fallback(
    state: str,
) -> None:
    scope_decision = "rejected" if state == "scope_rejected" else "allowed"
    response = _response(state, scope_decision=scope_decision)
    _assert_valid("CodeSearchResponse", response)

    for mutation in (
        lambda value: value.update(current=True),
        lambda value: value.update(results=[_hit()]),
        lambda value: value["fallback"].update(required=False),
        lambda value: value["fallback"].update(
            reason="not_indexed" if state != "not_indexed" else "unavailable"
        ),
    ):
        invalid = deepcopy(response)
        mutation(invalid)
        _assert_invalid("CodeSearchResponse", invalid)


def test_scope_rejected_is_the_only_rejected_scope_response() -> None:
    rejected = _response("scope_rejected", scope_decision="rejected")
    _assert_valid("CodeSearchResponse", rejected)

    wrong_scope = _response("unavailable", scope_decision="rejected")
    _assert_invalid("CodeSearchResponse", wrong_scope)

    wrong_index = deepcopy(rejected)
    wrong_index["index"] = _index_provenance()
    _assert_invalid("CodeSearchResponse", wrong_index)


@pytest.mark.parametrize(
    ("state", "document"),
    [
        (
            "ready",
            {
                "available": True,
                "state": "ready",
                "reason": "ready",
                "usable_index_count": 1,
            },
        ),
        (
            "disabled",
            {
                "available": False,
                "state": "disabled",
                "reason": "disabled",
                "usable_index_count": 0,
            },
        ),
        (
            "uninitialized",
            {
                "available": False,
                "state": "uninitialized",
                "reason": "uninitialized",
                "usable_index_count": 0,
            },
        ),
        (
            "not_configured",
            {
                "available": False,
                "state": "not_configured",
                "reason": "missing_configuration",
                "usable_index_count": 0,
            },
        ),
        (
            "unavailable",
            {
                "available": False,
                "state": "unavailable",
                "reason": "no_usable_index",
                "usable_index_count": 0,
            },
        ),
    ],
)
def test_status_is_body_discriminated(state: str, document: dict[str, Any]) -> None:
    assert document["state"] == state
    _assert_valid("CodeSearchStatus", document)


@pytest.mark.parametrize(
    "document",
    [
        {
            "available": True,
            "state": "ready",
            "reason": "ready",
            "usable_index_count": 0,
        },
        {
            "available": False,
            "state": "ready",
            "reason": "ready",
            "usable_index_count": 1,
        },
        {
            "available": True,
            "state": "unavailable",
            "reason": "no_usable_index",
            "usable_index_count": 1,
        },
        {
            "available": False,
            "state": "unavailable",
            "reason": "raw database exception",
            "usable_index_count": 0,
        },
    ],
)
def test_status_rejects_contradictory_or_unsanitized_documents(
    document: dict[str, Any],
) -> None:
    _assert_invalid("CodeSearchStatus", document)


def test_published_search_examples_validate_against_response_schema() -> None:
    examples = OPENAPI["paths"]["/search/code"]["post"]["responses"]["200"][
        "content"
    ]["application/json"]["examples"]
    assert {"ready", "revisionMismatch"} <= examples.keys()
    for example in examples.values():
        _assert_valid("CodeSearchResponse", example["value"])


def test_published_status_examples_validate_against_status_schema() -> None:
    examples = OPENAPI["paths"]["/search/code/status"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["examples"]
    assert {"available", "unavailable"} <= examples.keys()
    for example in examples.values():
        _assert_valid("CodeSearchStatus", example["value"])
