"""Verify the running HTTP API against the hand-authored OpenAPI contracts.

The contracts under ``openspec/contracts/agent-coordinator/openapi/`` are the
source of truth (derive-descriptors-from-contracts D1). ``app.openapi()`` and
the route table are the *verifier*: they describe what the app actually serves,
and every check below compares that description against the contracts.

Each check is a ratchet over ``openapi_contract_drift_baseline.yaml``:

- drift that is not in the baseline fails, so no new drift lands silently;
- a baseline entry that no longer reproduces fails as stale, so the baseline
  shrinks as drift is fixed and never hides a regression later.

Route shadowing has no baseline — a shadowed route is unreachable, never an
accepted state.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.routing import APIRoute
from gen_eval.openapi import iter_operations

from src import coordination_api
from src.coordination_api import create_coordination_api

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTRACT_DIR = _REPO_ROOT / "openspec/contracts/agent-coordinator/openapi"
_BASELINE = Path(__file__).with_name("openapi_contract_drift_baseline.yaml")

Route = str  # "METHOD /path", the spelling both documents share


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #


@cache
def _app() -> Any:
    return create_coordination_api()


@cache
def _app_document() -> dict[str, Any]:
    return _app().openapi()  # type: ignore[no-any-return]


@cache
def _contracts() -> dict[Route, tuple[str, dict[str, Any], Any]]:
    """Every contracted operation, keyed by route, with its document."""
    found: dict[Route, tuple[str, dict[str, Any], Any]] = {}
    for path in sorted(_CONTRACT_DIR.glob("*.yaml")):
        document = yaml.safe_load(path.read_text())
        for operation in iter_operations(document):
            route = f"{operation.method.upper()} {operation.path}"
            assert route not in found, (
                f"{route} is contracted in both {found[route][0]} and {path.name}"
            )
            found[route] = (path.name, document, operation)
    return found


@cache
def _served() -> dict[Route, Any]:
    return {
        f"{operation.method.upper()} {operation.path}": operation
        for operation in iter_operations(_app_document())
    }


@cache
def _baseline() -> dict[str, Any]:
    return yaml.safe_load(_BASELINE.read_text()) or {}


def _baselined(section: str) -> set[tuple[str, str]]:
    return {(entry["route"], entry["finding"]) for entry in _baseline().get(section) or []}


def _assert_ratchet(section: str, found: set[tuple[str, str]]) -> None:
    accepted = _baselined(section)
    new = sorted(found - accepted)
    stale = sorted(accepted - found)
    problems = [f"NEW   {route}: {finding}" for route, finding in new]
    problems += [
        f"STALE {route}: {finding} (fixed? remove it from the baseline)" for route, finding in stale
    ]
    assert not problems, (
        f"{section} drift between app.openapi() and the contracts "
        f"(baseline: {_BASELINE.name}):\n  " + "\n  ".join(problems)
    )


# --------------------------------------------------------------------------- #
# Schema helpers
# --------------------------------------------------------------------------- #


def _resolve(document: dict[str, Any], node: Any) -> Any:
    while isinstance(node, dict) and "$ref" in node:
        target: Any = document
        for part in node["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        node = target
    return node


def _json_body_schema(document: dict[str, Any], operation: Any) -> dict[str, Any] | None:
    body = _resolve(document, operation.raw.get("requestBody"))
    if not body:
        return None
    media = (body.get("content") or {}).get("application/json") or {}
    return _resolve(document, media.get("schema")) or {}


#: Dependencies that enforce the API key by calling ``verify_api_key`` directly
#: rather than through ``Depends``, so the dependency tree alone cannot see it.
#: They are closures inside ``create_coordination_api`` and are matched by name;
#: ``test_key_enforcing_wrappers_are_still_in_use`` keeps this set honest.
_KEY_ENFORCING_WRAPPERS = frozenset({"verify_code_search_principal"})


def _dependency_calls(route: APIRoute) -> Iterator[Any]:
    pending = list(route.dependant.dependencies)
    while pending:
        dependency = pending.pop()
        yield dependency.call
        pending.extend(dependency.dependencies)


def _requires_api_key(route: APIRoute) -> bool:
    """Whether the route's dependency tree enforces an API key.

    Read from the route, not the document: ``verify_api_key`` and
    ``optional_api_key`` declare the same optional header parameters, so the
    document cannot tell a required key from an accepted one.
    """
    return any(
        call is coordination_api.verify_api_key
        or getattr(call, "__name__", None) in _KEY_ENFORCING_WRAPPERS
        for call in _dependency_calls(route)
    )


def _api_routes() -> Iterator[APIRoute]:
    return (route for route in _app().routes if isinstance(route, APIRoute))


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #


def test_every_served_route_is_contracted() -> None:
    found = {(route, "served but not contracted") for route in set(_served()) - set(_contracts())}
    _assert_ratchet("uncontracted_routes", found)


def test_every_contracted_operation_is_served() -> None:
    found = {(route, "contracted but not served") for route in set(_contracts()) - set(_served())}
    _assert_ratchet("unserved_contract_operations", found)


def test_api_key_requirement_matches_contract_security() -> None:
    app_requires = {
        f"{method} {route.path}": _requires_api_key(route)
        for route in _api_routes()
        for method in route.methods
    }
    found: set[tuple[str, str]] = set()
    for route, (_, document, operation) in _contracts().items():
        if route not in app_requires:
            continue
        security = (
            operation.raw["security"] if "security" in operation.raw else document.get("security")
        )
        contract_requires = bool(security)
        if contract_requires != app_requires[route]:
            found.add(
                (
                    route,
                    f"contract security={'required' if contract_requires else 'none'}, "
                    f"app api key={'required' if app_requires[route] else 'not required'}",
                )
            )
    _assert_ratchet("auth_mismatches", found)


def test_request_body_fields_are_compatible() -> None:
    """Required fields on either side must be known to the other.

    A side with no declared properties (an untyped contract body, or an app
    handler taking a raw ``dict``) carries nothing to compare and is skipped —
    typing it is contract work, not drift.
    """
    served = _served()
    app_document = _app_document()
    found: set[tuple[str, str]] = set()
    for route, (_, document, operation) in _contracts().items():
        if route not in served:
            continue
        contract = _json_body_schema(document, operation)
        app = _json_body_schema(app_document, served[route])
        if (contract is None) != (app is None):
            side = "contract" if contract is not None else "app"
            found.add((route, f"request body declared only by the {side}"))
            continue
        if contract is None or app is None:
            continue
        contract_props = set(contract.get("properties") or {})
        app_props = set(app.get("properties") or {})
        if not contract_props or not app_props:
            continue
        app_only = sorted(set(app.get("required") or []) - contract_props)
        contract_only = sorted(set(contract.get("required") or []) - app_props)
        if app_only:
            found.add((route, f"app requires fields absent from the contract: {app_only}"))
        if contract_only:
            found.add((route, f"contract requires fields the app does not accept: {contract_only}"))
    _assert_ratchet("request_body_mismatches", found)


def test_no_route_is_shadowed_by_an_earlier_route() -> None:
    """A fixed path must not be captured by an earlier parameterised route.

    Starlette tries routes in registration order, so ``GET /features/{feature_id}``
    registered before ``GET /features/active`` answers every request for the
    latter with ``feature_id="active"``.
    """
    routes = list(_api_routes())
    shadowed = [
        f"{sorted(earlier.methods & route.methods)} {route.path} is captured by {earlier.path}"
        for index, route in enumerate(routes)
        for earlier in routes[:index]
        if earlier.path != route.path
        and earlier.methods & route.methods
        and earlier.path_regex.match(route.path)
    ]
    assert not shadowed, "Unreachable routes:\n  " + "\n  ".join(shadowed)


# --------------------------------------------------------------------------- #
# The verifier verifies itself
# --------------------------------------------------------------------------- #


def test_key_enforcing_wrappers_are_still_in_use() -> None:
    in_use = {
        getattr(call, "__name__", None)
        for route in _api_routes()
        for call in _dependency_calls(route)
    }
    assert _KEY_ENFORCING_WRAPPERS <= in_use, (
        f"No route depends on {sorted(_KEY_ENFORCING_WRAPPERS - in_use)} any more; "
        "drop it from _KEY_ENFORCING_WRAPPERS"
    )


def test_baseline_entries_carry_a_reason() -> None:
    missing = [
        f"{section}: {entry.get('route')}"
        for section, entries in _baseline().items()
        for entry in entries or []
        if not str(entry.get("reason") or "").strip()
    ]
    assert not missing, "Baseline entries without a reason:\n  " + "\n  ".join(missing)


@pytest.mark.parametrize(
    ("check", "section"),
    [
        (test_every_served_route_is_contracted, "uncontracted_routes"),
        (test_every_contracted_operation_is_served, "unserved_contract_operations"),
    ],
)
def test_ratchet_rejects_an_unbaselined_route(
    check: Callable[[], None], section: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Emptying a section's baseline must make its check fail when drift exists."""
    if not _baselined(section):
        pytest.skip(f"no {section} drift today to prove the ratchet with")
    emptied = {**_baseline(), section: []}
    monkeypatch.setattr(f"{__name__}._baseline", lambda: emptied)
    with pytest.raises(AssertionError, match="NEW"):
        check()
