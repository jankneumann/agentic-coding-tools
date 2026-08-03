"""Tests for coordination_bridge.try_code_search.

Change: inject-scoped-semantic-context-into-coding-jobs (ri-12), package
        wp-bridge-transport, tasks 1.1-1.4.
Spec: openspec/changes/inject-scoped-semantic-context-into-coding-jobs/specs/
      coordination-bridge/spec.md -- Requirement: Semantic Code Search Bridge
      Helper (scenarios code-search-helper-success,
      code-search-helper-capability-gate, code-search-helper-failures).
Design decisions: D1 (transport lives in the bridge), D8 (four fallback
      triggers, total over CodeSearchState), D13 (HTTP-only transport).

These tests exist because the failure and unavailability paths are the whole
point of the helper: a fail-open bridge would silently inject stale or
out-of-scope code into a coding job. Every assertion below is about what the
helper does when something is wrong.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

import pytest

# Make the bridge importable without needing an editable install.
_BRIDGE_DIR = Path(__file__).resolve().parents[2] / "coordination-bridge" / "scripts"
if str(_BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_DIR))

import coordination_bridge  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COORDINATOR_CODE_SEARCH = _REPO_ROOT / "agent-coordinator" / "src" / "code_search.py"

_NAMESPACE: dict[str, Any] = {"kind": "main", "key": "main"}
_SCOPE: dict[str, Any] = {
    "kind": "explicit",
    "read_allow": ["skills/coordination-bridge/**"],
    "deny": ["**/.venv/**"],
}
_REVISION = "a" * 40
_INDEX_ID = "3f1d2c4e-5a6b-4c7d-8e9f-0a1b2c3d4e5f"

# D8's mapping, pinned by hand. The *set* of states is derived from the
# coordinator source (see test_state_mapping_is_total_over_coordinator_enum);
# the trigger each state maps onto is a design decision and must be asserted
# literally, or the test would only be restating the implementation.
_EXPECTED_STATE_FALLBACKS: dict[str, tuple[str, str] | None] = {
    "ready": None,
    "not_indexed": ("stale", "revision_not_indexed"),
    "revision_mismatch": ("mismatched", "index_revision_differs"),
    "scope_rejected": ("out_of_scope", "scope_rejected"),
    "not_configured": ("unavailable", "service_unavailable"),
    "unavailable": ("unavailable", "service_unavailable"),
}


def _ready_body(results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """A response body shaped exactly like ri-03's ready CodeSearchResponse."""
    return {
        "state": "ready",
        "current": True,
        "request": {
            "repo_slug": "agentic_coding_tools",
            "source_revision": _REVISION,
            "namespace": dict(_NAMESPACE),
            "index_id": _INDEX_ID,
        },
        "index": {
            "index_id": _INDEX_ID,
            "repo_slug": "agentic_coding_tools",
            "source_revision": _REVISION,
            "namespace": dict(_NAMESPACE),
            "embedder_model": "test-embedder",
            "embedding_dim": 8,
            "embedder_fingerprint": "b" * 64,
            "policy_fingerprint": "c" * 64,
            "pipeline_fingerprint": "d" * 64,
            "completed_at": "2026-07-26T00:00:00Z",
        },
        "scope": {
            "decision": "allowed",
            "source": "explicit",
            "authority": "principal_grant",
        },
        "results": results if results is not None else [],
        "fallback": {"required": False, "strategy": "exact_search", "reason": None},
    }


def _hit(file_path: str, similarity: float) -> dict[str, Any]:
    return {
        "file_path": file_path,
        "language": "python",
        "content": "def f():\n    return 1\n",
        "start_line": 1,
        "end_line": 2,
        "similarity": similarity,
        "repo_slug": "agentic_coding_tools",
        "source_revision": _REVISION,
        "index_id": _INDEX_ID,
        "scope_decision": "allowed",
    }


def _non_ready_body(state: str) -> dict[str, Any]:
    """A response body shaped like ri-03's non-ready CodeSearchResponse."""
    return {
        "state": state,
        "current": False,
        "request": {
            "repo_slug": "agentic_coding_tools",
            "source_revision": _REVISION,
            "namespace": dict(_NAMESPACE),
            "index_id": None,
        },
        "index": None,
        "scope": {
            "decision": "allowed",
            "source": "explicit",
            "authority": "principal_grant",
        },
        "results": [],
        "fallback": {"required": True, "strategy": "exact_search", "reason": state},
    }


@pytest.fixture(autouse=True)
def _coordinator_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deterministic coordinator URL + API key for every test."""
    monkeypatch.setenv("COORDINATION_API_URL", "http://localhost:8081")
    monkeypatch.setenv("COORDINATION_API_KEY", "test-key")
    for key in (
        "COORDINATOR_HTTP_URL",
        "AGENT_COORDINATOR_API_URL",
        "AGENT_COORDINATOR_HTTP_URL",
    ):
        monkeypatch.delenv(key, raising=False)


def _stub_detect(
    monkeypatch: pytest.MonkeyPatch,
    *,
    available: bool = True,
    can_code_search: bool = True,
    transport: str = "http",
) -> dict[str, Any]:
    """Replace detect_coordination so no real probes are issued."""
    state: dict[str, Any] = {
        "status": "ok" if available else "skipped",
        "COORDINATOR_AVAILABLE": available,
        "COORDINATION_TRANSPORT": transport,
        "http_url": "http://localhost:8081",
        "reason": None,
        "CAN_CODE_SEARCH": can_code_search,
    }
    monkeypatch.setattr(
        coordination_bridge, "detect_coordination", lambda **_kwargs: dict(state)
    )
    return state


def _stub_http(
    monkeypatch: pytest.MonkeyPatch, response: dict[str, Any]
) -> list[dict[str, Any]]:
    """Replace _http_request with a stub. Returns the list of recorded calls."""
    calls: list[dict[str, Any]] = []

    def fake(
        *,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        http_url: str | None = None,
        api_key: str | None = None,
        timeout: float = coordination_bridge.DEFAULT_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        calls.append(
            {
                "method": method,
                "path": path,
                "payload": payload,
                "http_url": http_url,
                "api_key": api_key,
                "timeout": timeout,
            }
        )
        return response

    monkeypatch.setattr(coordination_bridge, "_http_request", fake)
    return calls


def _search(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "query": "how does the bridge gate on capability",
        "repo_slug": "agentic_coding_tools",
        "source_revision": _REVISION,
        "namespace": dict(_NAMESPACE),
        "scope": dict(_SCOPE),
    }
    kwargs.update(overrides)
    return coordination_bridge.try_code_search(**kwargs)


# ---------------------------------------------------------------------------
# Success path -- the response is passed through untouched
# ---------------------------------------------------------------------------


def test_ready_response_is_returned_unmodified(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: coordination-bridge.code-search-helper-success."""
    _stub_detect(monkeypatch)
    body = _ready_body([_hit("a.py", 0.9), _hit("b.py", 0.9), _hit("c.py", 0.1)])
    _stub_http(monkeypatch, {"status_code": 200, "data": body, "error": None})

    result = _search()

    assert result["status"] == "ok"
    assert result["operation"] == "try_code_search"
    assert result["status_code"] == 200
    assert result["COORDINATOR_AVAILABLE"] is True
    assert result["COORDINATION_TRANSPORT"] == "http"
    # Unmodified: same object, same hits, same order.
    assert result["response"] is body
    assert [hit["file_path"] for hit in result["response"]["results"]] == [
        "a.py",
        "b.py",
        "c.py",
    ]
    assert result["code_search_state"] == "ready"
    assert result["fallback"] is None


def test_request_is_posted_to_the_code_search_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_detect(monkeypatch)
    calls = _stub_http(
        monkeypatch, {"status_code": 200, "data": _ready_body(), "error": None}
    )

    _search()

    assert len(calls) == 1
    assert calls[0]["method"] == "POST"
    assert calls[0]["path"] == "/search/code"
    assert calls[0]["http_url"] == "http://localhost:8081"
    assert calls[0]["api_key"] == "test-key"


def test_payload_defaults_match_the_ri03_request_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Safe defaults: every optional parameter defaults to ri-03's own default."""
    _stub_detect(monkeypatch)
    calls = _stub_http(
        monkeypatch, {"status_code": 200, "data": _ready_body(), "error": None}
    )

    _search()

    assert calls[0]["payload"] == {
        "query": "how does the bridge gate on capability",
        "repo_slug": "agentic_coding_tools",
        "source_revision": _REVISION,
        "namespace": _NAMESPACE,
        "scope": _SCOPE,
        "limit": 10,
        "offset": 0,
    }


def test_optional_fields_are_sent_only_when_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_detect(monkeypatch)
    calls = _stub_http(
        monkeypatch, {"status_code": 200, "data": _ready_body(), "error": None}
    )

    _search(
        index_id=_INDEX_ID,
        limit=5,
        offset=2,
        languages=["python"],
        paths=["skills/**"],
    )

    payload = calls[0]["payload"]
    assert payload["index_id"] == _INDEX_ID
    assert payload["limit"] == 5
    assert payload["offset"] == 2
    assert payload["languages"] == ["python"]
    assert payload["paths"] == ["skills/**"]


# ---------------------------------------------------------------------------
# Capability gate -- no request at all
# ---------------------------------------------------------------------------


def test_absent_capability_skips_without_issuing_a_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: coordination-bridge.code-search-helper-capability-gate."""
    _stub_detect(monkeypatch, can_code_search=False)
    calls = _stub_http(
        monkeypatch, {"status_code": 200, "data": _ready_body(), "error": None}
    )

    result = _search()

    assert result["status"] == "skipped"
    assert result["reason"] == "capability_absent"
    assert calls == []
    assert result["fallback"] == {
        "trigger": "unavailable",
        "reason": "capability_absent",
        "strategy": "exact_search",
        "state": None,
    }


def test_unavailable_coordinator_skips_without_issuing_a_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_detect(monkeypatch, available=False, can_code_search=False, transport="none")
    calls = _stub_http(
        monkeypatch, {"status_code": 200, "data": _ready_body(), "error": None}
    )

    result = _search()

    assert result["status"] == "skipped"
    assert result["reason"] == "coordinator_unavailable"
    assert calls == []
    assert result["fallback"]["trigger"] == "unavailable"


# ---------------------------------------------------------------------------
# Failure mapping -- every cause is distinguishable, nothing raises
# ---------------------------------------------------------------------------

_FAILURE_CASES: tuple[tuple[str, dict[str, Any], str], ...] = (
    (
        "unreachable",
        {"status_code": None, "data": None, "error": "<urlopen error [Errno 61]>"},
        "coordinator_unreachable",
    ),
    ("rejected_credential", {"status_code": 401, "data": {}, "error": "e"}, "unauthorized"),
    ("forbidden_scope", {"status_code": 403, "data": {}, "error": "e"}, "forbidden"),
    ("unmounted_route", {"status_code": 404, "data": {}, "error": "e"}, "route_unavailable"),
    ("malformed_request", {"status_code": 422, "data": {}, "error": "e"}, "invalid_request"),
    ("overload", {"status_code": 429, "data": {}, "error": "e"}, "service_overloaded"),
    ("server_error", {"status_code": 500, "data": {}, "error": "e"}, "service_error"),
    ("bad_gateway", {"status_code": 503, "data": {}, "error": "e"}, "service_error"),
    ("teapot", {"status_code": 418, "data": {}, "error": "e"}, "unexpected_status"),
)


@pytest.mark.parametrize(
    ("label", "response", "expected_reason"),
    _FAILURE_CASES,
    ids=[case[0] for case in _FAILURE_CASES],
)
def test_failure_causes_map_to_distinct_reasons(
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    response: dict[str, Any],
    expected_reason: str,
) -> None:
    """Scenario: coordination-bridge.code-search-helper-failures."""
    _stub_detect(monkeypatch)
    _stub_http(monkeypatch, response)

    result = _search()

    assert result["status"] == "failed", label
    assert result["reason"] == expected_reason, label
    assert result["operation"] == "try_code_search"
    assert result["status_code"] == response["status_code"]
    # A failed result is never mistakable for an injectable one.
    assert result["fallback"] is not None
    assert result["fallback"]["trigger"] == "unavailable"


def test_the_six_distinguishable_causes_have_six_distinct_reasons() -> None:
    """The spec requires the causes be distinguishable *from one another*."""
    distinguishable = {
        "unreachable",
        "rejected_credential",
        "unmounted_route",
        "malformed_request",
        "overload",
        "server_error",
    }
    reasons = {
        reason for label, _response, reason in _FAILURE_CASES if label in distinguishable
    }
    assert len(reasons) == len(distinguishable)


@pytest.mark.parametrize(
    "data",
    [
        pytest.param({"raw": "<html>502 Bad Gateway</html>"}, id="non_json_body"),
        pytest.param([], id="list_body"),
        pytest.param(None, id="null_body"),
        pytest.param({}, id="empty_body"),
        pytest.param({"results": []}, id="missing_state"),
        pytest.param({"state": 7, "results": []}, id="non_string_state"),
    ],
)
def test_malformed_payload_is_a_failure_not_an_empty_success(
    monkeypatch: pytest.MonkeyPatch, data: Any
) -> None:
    _stub_detect(monkeypatch)
    _stub_http(monkeypatch, {"status_code": 200, "data": data, "error": None})

    result = _search()

    assert result["status"] == "failed"
    assert result["reason"] == "malformed_response"
    assert result["fallback"] is not None


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param({"current": False}, id="not_current"),
        pytest.param({"results": None}, id="results_not_a_list"),
        pytest.param(
            {"fallback": {"required": True, "strategy": "exact_search", "reason": None}},
            id="fallback_required",
        ),
    ],
)
def test_inconsistent_ready_response_is_rejected(
    monkeypatch: pytest.MonkeyPatch, mutation: dict[str, Any]
) -> None:
    """A body ri-03's own validator could not have produced is not a success.

    ri-03 makes `state=ready` imply `current`, a hit list, and no required
    fallback. Receiving otherwise means the body did not come from the
    contract, so the helper fails closed rather than reporting an injectable
    result whose provenance it cannot vouch for.
    """
    _stub_detect(monkeypatch)
    body = _ready_body()
    body.update(mutation)
    _stub_http(monkeypatch, {"status_code": 200, "data": body, "error": None})

    result = _search()

    assert result["status"] == "failed"
    assert result["reason"] == "malformed_response"
    assert result["fallback"] is not None


# ---------------------------------------------------------------------------
# D8 -- the state -> fallback mapping is total over CodeSearchState
# ---------------------------------------------------------------------------


def _coordinator_code_search_states() -> tuple[str, ...]:
    """Read CodeSearchState's members out of the coordinator source.

    Derived rather than duplicated: if ri-03 ever adds a state, this test
    module learns about it without anyone remembering to edit a literal.
    """
    tree = ast.parse(_COORDINATOR_CODE_SEARCH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "CodeSearchState":
            return tuple(
                stmt.value.value
                for stmt in node.body
                if isinstance(stmt, ast.Assign)
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)
            )
    raise AssertionError(f"CodeSearchState not found in {_COORDINATOR_CODE_SEARCH}")


def test_state_mapping_is_total_over_coordinator_enum() -> None:
    """Every shipped CodeSearchState has an explicit, asserted disposition."""
    states = _coordinator_code_search_states()
    assert states, "failed to parse CodeSearchState members"
    assert set(states) == set(_EXPECTED_STATE_FALLBACKS)


@pytest.mark.parametrize(("state", "expected"), sorted(_EXPECTED_STATE_FALLBACKS.items()))
def test_each_state_maps_to_its_designed_trigger(
    state: str, expected: tuple[str, str] | None
) -> None:
    classified = coordination_bridge.classify_code_search_state(state)
    if expected is None:
        assert classified is None
        return
    assert classified == {
        "trigger": expected[0],
        "reason": expected[1],
        "strategy": "exact_search",
        "state": state,
    }


def test_the_four_designed_triggers_are_all_produced() -> None:
    triggers = {
        value[0] for value in _EXPECTED_STATE_FALLBACKS.values() if value is not None
    }
    assert triggers == {"stale", "mismatched", "out_of_scope", "unavailable"}


@pytest.mark.parametrize(
    "state",
    [
        pytest.param("quantum_flux", id="future_state"),
        pytest.param("READY", id="wrong_case"),
        pytest.param("ready ", id="trailing_space"),
        pytest.param("", id="empty"),
        pytest.param(None, id="none"),
        pytest.param(7, id="non_string"),
    ],
)
def test_unrecognized_state_falls_back_instead_of_injecting(state: Any) -> None:
    """Totality at runtime: anything that is not exactly `ready` fails closed."""
    classified = coordination_bridge.classify_code_search_state(state)

    assert classified is not None
    assert classified["trigger"] == "unavailable"
    assert classified["reason"] == "unknown_state"
    assert classified["strategy"] == "exact_search"


def test_unknown_state_response_carries_a_fallback_not_an_empty_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unknown state must not read as `no results, all good`."""
    _stub_detect(monkeypatch)
    body = _non_ready_body("quantum_flux")
    _stub_http(monkeypatch, {"status_code": 200, "data": body, "error": None})

    result = _search()

    assert result["code_search_state"] == "quantum_flux"
    assert result["fallback"] is not None
    assert result["fallback"]["trigger"] == "unavailable"
    assert result["fallback"]["reason"] == "unknown_state"
    assert result["response"]["results"] == []


@pytest.mark.parametrize(
    "state", sorted(s for s, v in _EXPECTED_STATE_FALLBACKS.items() if v is not None)
)
def test_non_ready_response_never_reports_an_injectable_result(
    monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    """Fail-closed: a revision mismatch returns no results *as current*."""
    _stub_detect(monkeypatch)
    _stub_http(
        monkeypatch,
        {"status_code": 200, "data": _non_ready_body(state), "error": None},
    )

    result = _search()

    expected = _EXPECTED_STATE_FALLBACKS[state]
    assert expected is not None
    assert result["fallback"]["trigger"] == expected[0]
    assert result["fallback"]["reason"] == expected[1]
    assert result["fallback"]["state"] == state
    assert result["response"]["current"] is False
    assert result["response"]["results"] == []


def test_fallback_is_none_only_for_a_consistent_ready_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The single invariant every consumer relies on: `fallback is None` => inject."""
    _stub_detect(monkeypatch)
    seen: list[Any] = []
    for data in (
        _ready_body(),
        _non_ready_body("not_indexed"),
        _non_ready_body("revision_mismatch"),
        _non_ready_body("scope_rejected"),
        _non_ready_body("not_configured"),
        _non_ready_body("unavailable"),
        _non_ready_body("brand_new_state"),
    ):
        _stub_http(monkeypatch, {"status_code": 200, "data": data, "error": None})
        result = _search()
        seen.append((data["state"], result["fallback"]))

    injectable = [state for state, fallback in seen if fallback is None]
    assert injectable == ["ready"]


# ---------------------------------------------------------------------------
# The envelope contract itself
# ---------------------------------------------------------------------------


def test_helper_never_raises_on_hostile_input(monkeypatch: pytest.MonkeyPatch) -> None:
    """`try_code_search` raising is a bug, not a state."""
    _stub_detect(monkeypatch)
    hostile: list[dict[str, Any]] = [
        {"status_code": None, "data": None, "error": "boom"},
        {"status_code": 200, "data": "not-a-dict", "error": None},
        {"status_code": 200, "data": {"state": ["ready"]}, "error": None},
        {"status_code": 599, "data": {"state": "ready"}, "error": None},
        {"status_code": 204, "data": {}, "error": None},
        {"status_code": 200, "data": {"state": "ready"}, "error": None},
    ]
    for response in hostile:
        _stub_http(monkeypatch, response)
        result = _search()
        assert isinstance(result, dict)
        assert result["status"] in {"ok", "skipped", "failed"}
        assert result["operation"] == "try_code_search"


def test_every_result_shape_carries_the_transport_envelope_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_detect(monkeypatch)
    _stub_http(monkeypatch, {"status_code": 200, "data": _ready_body(), "error": None})
    ok = _search()
    _stub_http(monkeypatch, {"status_code": 429, "data": {}, "error": "e"})
    failed = _search()
    _stub_detect(monkeypatch, can_code_search=False)
    skipped = _search()

    for result in (ok, failed, skipped):
        assert "status" in result
        assert "operation" in result
        assert "fallback" in result
        assert "COORDINATOR_AVAILABLE" in result
        assert "COORDINATION_TRANSPORT" in result


def test_timeout_defaults_to_the_module_default_and_is_overridable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_detect(monkeypatch)
    calls = _stub_http(
        monkeypatch, {"status_code": 200, "data": _ready_body(), "error": None}
    )

    _search()
    _search(timeout=9.0)

    assert calls[0]["timeout"] == coordination_bridge.DEFAULT_TIMEOUT_SECONDS
    assert calls[1]["timeout"] == 9.0


def test_helper_is_exported_alongside_the_other_try_helpers() -> None:
    assert callable(coordination_bridge.try_code_search)
    assert callable(coordination_bridge.classify_code_search_state)
