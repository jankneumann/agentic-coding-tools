"""D8 `out_of_scope`: the trigger whose failure mode is a leak, not a gap.

The other three triggers fail by giving a worker nothing. This one fails by
giving a worker something it was not allowed to read, so its tests are written
the other way round: they are less interested in the fallback record than in
proving no path quietly widens the scope on the way to producing one.

Four causes, four reasons. `scope_rejected` is the service refusing what we
asked for; `no_declared_scope` is a job that never had a boundary and did not get
one invented for it; `scope_self_cancelling` is a declared boundary that resolves
to nothing (and must not resolve to *everything*); `all_hits_scope_filtered` is
the local deny re-check catching what the service returned.

That local re-check is deliberately redundant with the service's own filtering.
It is what makes the skill's boundary claim self-verifying rather than a claim
about somebody else's code.
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

from test_no_context_trigger import (  # noqa: E402
    _INDEX_ID,
    _Scopes,
    _hit,
    _request,
    _wire,
)

#: Inside the fixture's ``skills/**`` allow list, and outside it.
_IN_SCOPE = "skills/context-engineering/scripts/semantic_context.py"
_OUT_OF_SCOPE = "agent-coordinator/src/code_search.py"


def _search(results: list[dict[str, object]], calls: list[dict[str, object]] | None = None):
    def search(body: dict[str, object]) -> dict[str, object]:
        if calls is not None:
            calls.append(body)
        return {
            "status": "ok",
            "response": {
                "state": "ready",
                "current": True,
                "results": results,
                "index": {"index_id": _INDEX_ID, "repo_slug": "agentic_coding_tools"},
            },
        }

    return search


def _state_runtime(state: str) -> sc.SemanticContextRuntime:
    return _wire(
        lambda _body: {
            "status": "ok",
            "response": {"state": state, "current": False, "results": []},
        }
    )


def _at(
    file_path: str, start: int = 1, end: int = 5, content: str | None = None
) -> dict[str, object]:
    """A hit the *service* vouches for, at a path the client may not accept."""
    hit = _hit(start, end)
    hit["file_path"] = file_path
    hit["scope_decision"] = "allowed"
    if content is not None:
        hit["content"] = content
    return hit


def _out_of_scope(runtime: sc.SemanticContextRuntime, request=None) -> sc.ContextFallback:
    result = sc.collect_semantic_context(request or _request(), runtime)
    assert result.status == "fallback"
    assert result.fallback is not None
    assert result.fallback.trigger == "out_of_scope", (
        f"Expected the `out_of_scope` trigger, got {result.fallback.trigger!r} "
        f"with reason {result.fallback.reason!r}."
    )
    assert result.fallback.strategy == "exact_search"
    return result.fallback


# --------------------------------------------------------------------------
# The four causes
# --------------------------------------------------------------------------


def test_a_service_that_refuses_the_scope_is_scope_rejected() -> None:
    fallback = _out_of_scope(_state_runtime("scope_rejected"))

    assert fallback.reason == "scope_rejected"
    assert fallback.service_state == "scope_rejected", (
        "The service made this decision, and the state is what says so. Without "
        "it the record is indistinguishable from a scope this client rejected."
    )


@pytest.mark.parametrize(
    ("label", "override"),
    [
        ("no package is registered", {"load_package": lambda *_a: None}),
        ("ri-08 resolves no scope", {"index_scopes": lambda _p: None}),
        ("the declared scope is empty", {"index_scopes": lambda _p: _Scopes(read_allow=())}),
    ],
)
def test_a_job_without_a_resolvable_scope_is_no_declared_scope(
    label: str, override: dict[str, object]
) -> None:
    """Absent, unresolvable and empty all mean the same thing: no boundary.

    They must not mean "no restriction". Downstream an empty ``read_allow`` reads
    as unscoped, so the one outcome forbidden here is a successful query.
    """
    fallback = _out_of_scope(replace(_wire(_search([])), **override))

    assert fallback.reason == "no_declared_scope", f"({label})"
    assert fallback.service_state is None, (
        f"({label}) No query was issued, so no service state can be reported."
    )


def test_a_job_with_no_change_or_package_is_no_declared_scope() -> None:
    """`quick-task` and ad-hoc debugging have no package. That is not a licence."""
    request = sc.SemanticContextRequest(
        repository=".", query="anything", consumer="quick-task"
    )

    fallback = _out_of_scope(_wire(_search([])), request=request)

    assert fallback.reason == "no_declared_scope"


def test_a_scopeless_job_never_reaches_the_service() -> None:
    """The failure this capability exists to prevent is a query with no boundary.

    A widened scope is not visible in the returned fallback — it is visible in
    what was sent. So the assertion is on the wire, not on the record.
    """
    calls: list[dict[str, object]] = []
    request = sc.SemanticContextRequest(
        repository=".", query="anything", consumer="quick-task"
    )

    sc.collect_semantic_context(request, _wire(_search([], calls)))

    assert calls == [], (
        f"A job with no declared read scope still sent {calls!r} to the service. "
        "Whatever scope that request carried, this job did not declare it."
    )


def test_a_scope_that_denies_everything_it_allows_is_self_cancelling() -> None:
    """Rejected, not normalised to empty — empty means 'no restriction' downstream."""
    calls: list[dict[str, object]] = []
    runtime = replace(
        _wire(_search([], calls)),
        index_scopes=lambda _p: _Scopes(read_allow=("skills/**",), deny=("skills/**",)),
    )

    fallback = _out_of_scope(runtime)

    assert fallback.reason == "scope_self_cancelling", (
        "A scope whose deny list cancels its allow list must be refused by name. "
        f"Got {fallback.reason!r}."
    )
    assert calls == [], (
        "The self-cancelling scope was still sent to the service. Its resolved "
        "read_allow is empty, which reads downstream as 'search everything'."
    )


def test_a_partially_cancelled_scope_is_still_a_scope() -> None:
    """The boundary case: deny removing *some* globs is narrowing, not cancelling."""
    calls: list[dict[str, object]] = []
    runtime = replace(
        _wire(_search([_at(_IN_SCOPE)], calls)),
        index_scopes=lambda _p: _Scopes(
            read_allow=("skills/**", "docs/**"), deny=("docs/**",)
        ),
    )

    result = sc.collect_semantic_context(_request(), runtime)

    assert result.status == "injected", (
        "A scope narrowed from two globs to one was treated as cancelled. That "
        "turns every deny rule into a reason to give up."
    )
    assert len(calls) == 1
    assert calls[0]["scope"] == {
        "kind": "explicit",
        "read_allow": ["skills/**"],
        "deny": ["docs/**"],
    }, (
        "The scope on the wire is not the resolved, explicit scope. "
        f"Got {calls[0]['scope']!r}."
    )


# --------------------------------------------------------------------------
# The local deny re-check
# --------------------------------------------------------------------------


def test_the_client_re_checks_paths_the_service_already_vouched_for() -> None:
    """`scope_decision: allowed` from the service is not the client's answer.

    A same-revision index cannot return a path its own scope excluded, so this
    check should be unreachable in production. It is here so that the skill's
    boundary claim does not depend on that being true of somebody else's code.
    """
    result = sc.collect_semantic_context(
        _request(), _wire(_search([_at(_OUT_OF_SCOPE)]))
    )

    assert result.status == "fallback", (
        f"{_OUT_OF_SCOPE!r} was returned marked `allowed` and rendered on the "
        "service's word alone. The local re-check is what makes the boundary "
        "claim checkable."
    )
    assert result.fallback is not None
    assert result.fallback.reason == "all_hits_scope_filtered"
    assert result.fallback.service_state == "ready"


def test_a_mixed_response_injects_only_the_in_scope_hits() -> None:
    """The partial case, which no fallback record can show.

    An all-or-nothing implementation would pass every fallback assertion in this
    file and still leak here, or still discard usable context here.
    """
    secret = "API_TOKEN = 'nobody-outside-the-scope-should-read-this'"
    result = sc.collect_semantic_context(
        _request(),
        _wire(
            _search(
                [
                    _at(_IN_SCOPE, 1, 5, content="def in_scope():\n    return 1\n"),
                    _at(_OUT_OF_SCOPE, 20, 24, content=secret),
                ]
            )
        ),
    )

    assert result.status == "injected"
    assert [hit.file_path for hit in result.hits] == [_IN_SCOPE], (
        "The injected section carries a path outside the declared read scope: "
        f"{[hit.file_path for hit in result.hits]}."
    )
    assert [(o.file_path, o.reason) for o in result.omissions] == [
        (_OUT_OF_SCOPE, "scope_filtered")
    ], (
        "The dropped path is not recorded as scope-filtered, so the section "
        "implies a completeness it does not have."
    )

    # The omissions block names the path and the reason on purpose — that is the
    # audit trail. What must never survive is the excerpt itself.
    text = rsc.render_semantic_context(result.to_dict())
    assert secret not in text, (
        "The out-of-scope excerpt's contents reached the rendered section. "
        "Filtering that leaves the code in the prompt has filtered nothing."
    )
    assert "def in_scope():" in text


def test_deny_beats_allow_in_the_local_re_check() -> None:
    """Deny precedence, checked on the value the client actually filters with."""
    denied = "skills/context-engineering/scripts/secrets.py"
    runtime = replace(
        _wire(_search([_at(denied)])),
        index_scopes=lambda _p: _Scopes(read_allow=("skills/**",), deny=(denied,)),
    )

    fallback = _out_of_scope(runtime)

    assert fallback.reason == "all_hits_scope_filtered", (
        f"{denied!r} is matched by both the allow glob and the deny list, and was "
        "kept. Deny must win, or a deny rule is decorative."
    )


# --------------------------------------------------------------------------
# Distinctness and rendering
# --------------------------------------------------------------------------


def test_the_four_out_of_scope_causes_carry_four_reasons() -> None:
    causes = {
        "service refused": _out_of_scope(_state_runtime("scope_rejected")),
        "no package": _out_of_scope(
            replace(_wire(_search([])), load_package=lambda *_a: None)
        ),
        "self-cancelling": _out_of_scope(
            replace(
                _wire(_search([])),
                index_scopes=lambda _p: _Scopes(
                    read_allow=("skills/**",), deny=("skills/**",)
                ),
            )
        ),
        "all filtered": _out_of_scope(_wire(_search([_at(_OUT_OF_SCOPE)]))),
    }
    seen: dict[str, str] = {}
    for cause, fallback in causes.items():
        clash = seen.get(fallback.reason)
        assert clash is None, (
            f"{cause!r} and {clash!r} both report {fallback.reason!r}. One is a "
            "missing declaration, one is a bad declaration, one is a refusal and "
            "one is a leak that was caught — four different things to fix."
        )
        seen[fallback.reason] = cause

    assert set(seen) <= set(sc.FALLBACK_REASONS)


@pytest.mark.parametrize(
    ("runtime_factory", "reason"),
    [
        (lambda: _state_runtime("scope_rejected"), "scope_rejected"),
        (
            lambda: replace(_wire(_search([])), load_package=lambda *_a: None),
            "no_declared_scope",
        ),
        (
            lambda: replace(
                _wire(_search([])),
                index_scopes=lambda _p: _Scopes(
                    read_allow=("skills/**",), deny=("skills/**",)
                ),
            ),
            "scope_self_cancelling",
        ),
        (lambda: _wire(_search([_at(_OUT_OF_SCOPE)])), "all_hits_scope_filtered"),
    ],
)
def test_every_out_of_scope_reason_reaches_the_rendered_section(
    runtime_factory, reason: str
) -> None:
    result = sc.collect_semantic_context(_request(), runtime_factory())
    text = rsc.render_semantic_context(result.to_dict())

    assert "`trigger=out_of_scope`" in text, (
        f"The rendered section does not name the trigger. Got:\n{text}"
    )
    assert f"`{reason}`" in text, (
        f"The rendered section does not name the {reason!r} reason. Got:\n{text}"
    )
    assert "exact search" in text.lower()
    assert sc.FULL_REVISION_RE.match(result.requested_revision) is not None


def test_the_unscoped_fallback_suggests_an_unscoped_search_and_says_so() -> None:
    """The rendered `rg` must not substitute a boundary the job never declared."""
    request = sc.SemanticContextRequest(
        repository=".", query="anything", consumer="quick-task"
    )
    result = sc.collect_semantic_context(request, _wire(_search([])))

    text = rsc.render_semantic_context(result.to_dict(), read_allow=())

    assert "--glob" not in text, (
        f"The suggested command invents globs for a job with no scope:\n{text}"
    )
    assert "no declared read scope" in text, (
        "The suggestion does not tell the worker it is unscoped, so an unbounded "
        f"`rg` reads as an endorsed boundary. Got:\n{text}"
    )
