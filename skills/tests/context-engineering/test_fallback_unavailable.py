"""D8 `unavailable`: the broadest trigger, and the one that must stay legible.

Seven different things can go wrong between "the operator never switched this
on" and "the coordinator returned 503", and they all land under one trigger. That
is only tolerable because each carries its own `reason`: a trigger tells the
worker *what to do* (exact search, always), the reason tells whoever reads the
run *what to fix*. `injection_disabled` is a settings change, `capability_absent`
is a deployment without an index, `service_overloaded` is "try again later", and
`bridge_failed` is a bug report. Collapsing any pair loses a remedy.

These tests also pin D8's ordering rule. Preconditions are evaluated flag →
capability → transport → revision, first match wins, so the reason is a pure
function of the environment and not of whichever check the implementation
happened to reach first.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

_SUITE = Path(__file__).resolve().parent
if str(_SUITE) not in sys.path:
    sys.path.insert(0, str(_SUITE))

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "skills" / "context-engineering" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import render_semantic_context as rsc  # noqa: E402
import semantic_context as sc  # noqa: E402

from test_no_context_trigger import _REVISION, _request, _wire  # noqa: E402

_HEALTHY_FLAGS = {"CAN_CODE_SEARCH": True, "COORDINATION_TRANSPORT": "http"}


def _envelope_runtime(envelope: object) -> sc.SemanticContextRuntime:
    """Everything healthy up to the bridge, which returns `envelope`."""
    return _wire(lambda _body: envelope)


def _state_runtime(state: str) -> sc.SemanticContextRuntime:
    return _wire(
        lambda _body: {
            "status": "ok",
            "response": {"state": state, "current": False, "results": []},
        }
    )


def _collect(runtime: sc.SemanticContextRuntime) -> sc.SemanticContextResult:
    result = sc.collect_semantic_context(_request(), runtime)
    assert result.status == "fallback"
    assert result.fallback is not None
    assert result.fallback.trigger == "unavailable", (
        f"Expected the `unavailable` trigger, got {result.fallback.trigger!r} "
        f"with reason {result.fallback.reason!r}."
    )
    assert result.fallback.strategy == "exact_search"
    return result


# --------------------------------------------------------------------------
# Local preconditions: no query is issued
# --------------------------------------------------------------------------


def test_the_flag_being_off_is_injection_disabled() -> None:
    """Default-off is a state with a name, not an absence (D9)."""
    result = _collect(replace(_wire(lambda _b: {}), env={}))

    assert result.fallback is not None
    assert result.fallback.reason == "injection_disabled"
    assert result.fallback.service_state is None


def test_the_flag_being_off_touches_nothing_at_all() -> None:
    """D9's real claim: a flag-off run behaves like a tree without this module.

    Detection, git and the bridge are all side-effecting boundaries. If the flag
    check ran after any of them, an operator who never opted in would still be
    paying for subprocesses and HTTP.
    """
    touched: list[str] = []

    runtime = sc.SemanticContextRuntime(
        search=lambda _body: touched.append("search") or {},
        detect=lambda: touched.append("detect") or _HEALTHY_FLAGS,
        git=lambda _repo, _argv: touched.append("git") or _REVISION,
        load_package=lambda *_a: touched.append("load_package") or {},
        load_checkpoint=lambda *_a, **_k: touched.append("load_checkpoint"),
        index_scopes=lambda _p: touched.append("index_scopes"),
        env={"SEMANTIC_CONTEXT_INJECTION": "0"},
    )
    result = sc.collect_semantic_context(_request(), runtime)

    assert touched == [], (
        f"With the flag off the helper still reached {touched}. Default-off must "
        "short-circuit before git, the bridge, and the network."
    )
    assert result.fallback is not None
    assert result.fallback.reason == "injection_disabled"


def test_a_coordinator_without_the_capability_is_capability_absent() -> None:
    runtime = replace(
        _wire(lambda _b: {}),
        detect=lambda: {"CAN_CODE_SEARCH": False, "COORDINATION_TRANSPORT": "http"},
    )
    result = _collect(runtime)

    assert result.fallback is not None
    assert result.fallback.reason == "capability_absent"


def test_a_non_http_transport_is_transport_unsupported() -> None:
    """D13: MCP coordination never reports a usable index, and says so."""
    runtime = replace(
        _wire(lambda _b: {}),
        detect=lambda: {"CAN_CODE_SEARCH": True, "COORDINATION_TRANSPORT": "mcp"},
    )
    result = _collect(runtime)

    assert result.fallback is not None
    assert result.fallback.reason == "transport_unsupported", (
        "An MCP-only transport cannot carry a code-search query. Reporting it as "
        f"{result.fallback.reason!r} sends the reader to the wrong subsystem."
    )


def test_a_repository_git_cannot_answer_for_is_revision_unresolvable() -> None:
    runtime = replace(_wire(lambda _b: {}), git=lambda _repo, _argv: None)
    result = _collect(runtime)

    assert result.fallback is not None
    assert result.fallback.reason == "revision_unresolvable"
    assert result.requested_revision == sc.UNRESOLVED_REVISION, (
        "No revision was resolved, so the section must carry git's null object id "
        "(D15) rather than a plausible-looking hash a reader cannot falsify."
    )


@pytest.mark.parametrize(
    ("flags", "env", "git_answer", "expected"),
    [
        # Every later precondition also fails; the earliest one must win.
        ({}, {}, None, "injection_disabled"),
        (
            {"CAN_CODE_SEARCH": False, "COORDINATION_TRANSPORT": "mcp"},
            {"SEMANTIC_CONTEXT_INJECTION": "1"},
            None,
            "capability_absent",
        ),
        (
            {"CAN_CODE_SEARCH": True, "COORDINATION_TRANSPORT": "mcp"},
            {"SEMANTIC_CONTEXT_INJECTION": "1"},
            None,
            "transport_unsupported",
        ),
    ],
)
def test_the_earliest_failing_precondition_names_the_reason(
    flags: dict[str, object],
    env: dict[str, str],
    git_answer: str | None,
    expected: str,
) -> None:
    """First match wins, so the reason is a function of the environment (D8).

    Each row fails *every* remaining precondition too. Without a fixed order the
    reported reason would depend on evaluation order rather than on the world.
    """
    runtime = replace(
        _wire(lambda _b: {}),
        detect=lambda: flags,
        git=lambda _repo, _argv: git_answer,
        env=env,
    )
    result = _collect(runtime)

    assert result.fallback is not None
    assert result.fallback.reason == expected, (
        f"Expected the earliest failing precondition ({expected!r}) to name the "
        f"reason; got {result.fallback.reason!r}."
    )


# --------------------------------------------------------------------------
# Transport outcomes: a query was attempted
# --------------------------------------------------------------------------


def test_a_failed_bridge_envelope_is_bridge_failed() -> None:
    result = _collect(_envelope_runtime({"status": "failed", "reason": "unauthorized"}))

    assert result.fallback is not None
    assert result.fallback.reason == "bridge_failed"
    assert result.fallback.service_state is None, (
        "No CodeSearchState came back, so claiming one would invent a fact about "
        "a response that never arrived."
    )


def test_a_skipped_envelope_reporting_no_capability_keeps_that_reason() -> None:
    """The bridge's own `capability_absent` is not degraded to a generic failure."""
    result = _collect(
        _envelope_runtime({"status": "skipped", "reason": "capability_absent"})
    )

    assert result.fallback is not None
    assert result.fallback.reason == "capability_absent"


def test_http_429_is_service_overloaded_not_a_generic_failure() -> None:
    """Overload is the one `unavailable` cause that is worth retrying later."""
    result = _collect(_envelope_runtime({"status": "failed", "status_code": 429}))

    assert result.fallback is not None
    assert result.fallback.reason == "service_overloaded", (
        "A 429 reported as "
        f"{result.fallback.reason!r} tells the reader the deployment has no index "
        "when in fact it has one that was momentarily busy."
    )


@pytest.mark.parametrize("status_code", [500, 502, 503])
def test_http_5xx_is_service_unavailable(status_code: int) -> None:
    result = _collect(
        _envelope_runtime({"status": "failed", "status_code": status_code})
    )

    assert result.fallback is not None
    assert result.fallback.reason == "service_unavailable"


@pytest.mark.parametrize("state", ["not_configured", "unavailable"])
def test_the_two_unavailable_service_states_are_service_unavailable(state: str) -> None:
    result = _collect(_state_runtime(state))

    assert result.fallback is not None
    assert result.fallback.reason == "service_unavailable"
    assert result.fallback.service_state == state, (
        "`not_configured` and `unavailable` share a reason, so the service state "
        "is the only field that still tells them apart. Dropping it would merge "
        "'this deployment has no index' into 'the index is down'."
    )


# --------------------------------------------------------------------------
# Distinctness and rendering
# --------------------------------------------------------------------------


def test_the_unavailable_causes_do_not_share_a_reason() -> None:
    """Six causes, six reasons. One trigger, but never one explanation."""
    reasons = {
        "flag off": _collect(replace(_wire(lambda _b: {}), env={})),
        "no capability": _collect(
            replace(
                _wire(lambda _b: {}),
                detect=lambda: {"CAN_CODE_SEARCH": False},
            )
        ),
        "mcp transport": _collect(
            replace(
                _wire(lambda _b: {}),
                detect=lambda: {
                    "CAN_CODE_SEARCH": True,
                    "COORDINATION_TRANSPORT": "mcp",
                },
            )
        ),
        "git silent": _collect(
            replace(_wire(lambda _b: {}), git=lambda _repo, _argv: None)
        ),
        "bridge failed": _collect(_envelope_runtime({"status": "failed"})),
        "overloaded": _collect(
            _envelope_runtime({"status": "failed", "status_code": 429})
        ),
    }
    seen: dict[str, str] = {}
    for cause, result in reasons.items():
        assert result.fallback is not None
        clash = seen.get(result.fallback.reason)
        assert clash is None, (
            f"{cause!r} and {clash!r} both report {result.fallback.reason!r}. "
            "They have different remedies, so a reader cannot act on a shared one."
        )
        seen[result.fallback.reason] = cause

    assert set(seen) <= set(sc.FALLBACK_REASONS), (
        f"{set(seen) - set(sc.FALLBACK_REASONS)} is not in the published reason "
        "enum, so the emitted section would not validate."
    )


def test_the_disabled_flag_renders_nothing_at_all() -> None:
    """D9's byte-identical guarantee: not even a heading (the one exception)."""
    result = _collect(replace(_wire(lambda _b: {}), env={}))

    assert rsc.render_semantic_context(result.to_dict()) == "", (
        "A flag-off run emitted a section. Then adding this capability changed "
        "the prompt of every job that never opted in."
    )


@pytest.mark.parametrize(
    ("runtime_factory", "reason"),
    [
        (lambda: replace(_wire(lambda _b: {}), detect=lambda: {}), "capability_absent"),
        (
            lambda: replace(_wire(lambda _b: {}), git=lambda _r, _a: None),
            "revision_unresolvable",
        ),
        (lambda: _envelope_runtime({"status": "failed"}), "bridge_failed"),
        (
            lambda: _envelope_runtime({"status": "failed", "status_code": 429}),
            "service_overloaded",
        ),
        (lambda: _state_runtime("unavailable"), "service_unavailable"),
    ],
)
def test_every_other_unavailable_reason_reaches_the_rendered_section(
    runtime_factory, reason: str
) -> None:
    """Only `injection_disabled` is silent; the rest must explain themselves."""
    result = _collect(runtime_factory())
    text = rsc.render_semantic_context(result.to_dict())

    assert "`trigger=unavailable`" in text
    assert f"`{reason}`" in text, (
        f"The rendered section does not name the {reason!r} reason. Got:\n{text}"
    )
    assert "exact search" in text.lower()
    assert "```" not in text, (
        "A fallback section rendered a code fence, so something was injected "
        "under a 'not injected' heading."
    )
