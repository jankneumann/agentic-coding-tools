"""The load-bearing guarantee: semantic context can fail, the coding job cannot.

Every other file in this suite asks "is the fallback *correct*". This one asks
the prior question: does the job still finish? Semantic context is an optional
input, and an optional input that can abort its consumer is not optional — a
`raise` here would make an absent index able to stop work that never needed one.

`collect_semantic_context` documents that it never raises. A docstring is not a
gate, so these tests reach the guarantee through the failure modes that are not
clean fallbacks and would be the ones to break it: a transport that raises, a
coordinator that cannot be reached, a payload this client cannot represent, a
response that is not a mapping at all, a `CodeSearchState` from a future
coordinator, and a scope object that explodes when asked a question.

Two rules hold across all of them:

* **Never fail-open.** Anything unrecognized becomes a fallback, never an
  injection and never an empty success. An "injected" section with no hits would
  read to a worker as "no relevant code exists", which is a different and false
  claim from "we could not look".
* **Never block.** The job runs to completion with a rendered block in its
  prompt, in every single case.

The guarantee is over ``Exception``, not ``BaseException``: a dependency calling
``sys.exit`` still terminates the process. That is deliberate elsewhere in the
codebase (`SystemExit` is caught at the two import sites that can raise it) and
is noted here so the boundary is explicit rather than assumed.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

import pytest

_SUITE = Path(__file__).resolve().parent
if str(_SUITE) not in sys.path:
    sys.path.insert(0, str(_SUITE))

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "skills" / "context-engineering" / "scripts"
_BRIDGE = _REPO_ROOT / "skills" / "coordination-bridge" / "scripts"
for _path in (_SCRIPTS, _BRIDGE):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import coordination_bridge as cb  # noqa: E402
import render_semantic_context as rsc  # noqa: E402
import semantic_context as sc  # noqa: E402

from test_no_context_trigger import (  # noqa: E402
    _INDEX_ID,
    _REVISION,
    _Scopes,
    _hit,
    _request,
    _wire,
)

_SECTION_SCHEMA = (
    _REPO_ROOT
    / "openspec"
    / "contracts"
    / "code-search"
    / "schemas"
    / "semantic-context-section.schema.json"
)


def _raise(error: BaseException):
    def raiser(*_args: object, **_kwargs: object):
        raise error

    return raiser


class _ExplodingScopes:
    """ri-08's shape, except that asking it anything fails.

    The scope object is the one dependency consulted *inside* the result-shaping
    path rather than at a boundary, so a defect in it is the likeliest way an
    exception reaches a caller.
    """

    read_allow = ("skills/**",)
    deny = ()

    def allows(self, _file_path: str) -> bool:
        raise RuntimeError("index_scopes returned an object that cannot answer")


def _responds(response: object, results: object = None) -> sc.SemanticContextRuntime:
    """A runtime whose bridge returns `response` under an ok envelope."""
    if isinstance(response, dict) and results is not None:
        response = {**response, "results": results}
    return _wire(lambda _body: {"status": "ok", "response": response})


def _ready(results: object) -> sc.SemanticContextRuntime:
    return _responds(
        {
            "state": "ready",
            "current": True,
            "index": {"index_id": _INDEX_ID, "repo_slug": "agentic_coding_tools"},
        },
        results,
    )


#: Every way this helper can fail, named by what actually went wrong. The
#: parametrized tests below all run over this one table so a new failure mode
#: gets the whole battery at once.
FAILURE_MODES: dict[str, sc.SemanticContextRuntime] = {
    # -- the transport itself
    "transport raises": _wire(_raise(ConnectionError("connection reset"))),
    "coordinator unreachable": _wire(
        lambda _b: {
            "status": "failed",
            "operation": "try_code_search",
            "reason": "coordinator_unreachable",
            "fallback": {
                "trigger": "unavailable",
                "reason": "bridge_failed",
                "strategy": "exact_search",
                "state": None,
            },
        }
    ),
    "bridge skipped the call": _wire(
        lambda _b: {
            "status": "skipped",
            "operation": "try_code_search",
            "reason": "coordinator_unavailable",
        }
    ),
    "envelope is not a mapping": _wire(lambda _b: "service temporarily down"),
    "envelope is None": _wire(lambda _b: None),
    # -- the payload
    "response is not a mapping": _wire(lambda _b: {"status": "ok", "response": []}),
    "response is missing": _wire(lambda _b: {"status": "ok"}),
    "results is a string": _ready("not a list of hits"),
    "results is a mapping": _ready({"file_path": "skills/a.py"}),
    "a result is not a mapping": _ready([42]),
    "a result is missing fields": _ready([{"file_path": "skills/a.py"}]),
    "a result has an inverted line span": _ready([_hit(90, 10)]),
    "a result escapes the repository": _ready(
        [{**_hit(1, 5), "file_path": "../../etc/passwd"}]
    ),
    "a result has an impossible score": _ready([{**_hit(1, 5), "similarity": 42.0}]),
    "a ready response omits its index block": _wire(
        lambda _b: {
            "status": "ok",
            "response": {"state": "ready", "current": True, "results": [_hit(1, 5)]},
        }
    ),
    # -- states this client does not understand
    "a future coordinator state": _responds(
        {"state": "quantum_flux", "current": True}, [_hit(1, 5)]
    ),
    "a differently-cased ready": _responds({"state": "READY"}, [_hit(1, 5)]),
    "a non-string state": _responds({"state": 7}, [_hit(1, 5)]),
    "no state at all": _responds({"current": True}, [_hit(1, 5)]),
    # -- the local dependencies
    "detection raises": replace(_wire(lambda _b: {}), detect=_raise(RuntimeError("x"))),
    "git raises": replace(_wire(lambda _b: {}), git=_raise(OSError("git is missing"))),
    "the package file raises": replace(
        _wire(lambda _b: {}), load_package=_raise(ValueError("bad yaml"))
    ),
    "the checkpoint raises": replace(
        _wire(lambda _b: {}), load_checkpoint=_raise(ValueError("bad json"))
    ),
    "ri-08 scope resolution raises": replace(
        _wire(lambda _b: {}), index_scopes=_raise(KeyError("scope"))
    ),
    "the scope object explodes when asked": replace(
        _ready([_hit(1, 5)]), index_scopes=lambda _p: _ExplodingScopes()
    ),
    # -- the ordinary, well-behaved fallbacks, for completeness
    "the flag is off": replace(_wire(lambda _b: {}), env={}),
    "the worktree is dirty": replace(
        _wire(lambda _b: {}),
        git=lambda _r, argv: _REVISION if "rev-parse" in argv else " M a.py\n",
    ),
    "the index is behind": _responds({"state": "revision_mismatch"}, []),
    "the service refused the scope": _responds({"state": "scope_rejected"}, []),
    "the index is empty": _ready([]),
    "the declared scope is unusable": replace(
        _wire(lambda _b: {}),
        index_scopes=lambda _p: _Scopes(read_allow=("skills/**",), deny=("skills/**",)),
    ),
}

#: What each mode must report. "It fell back" is too weak a guarantee on its own:
#: a client that routed *every* surprise to `unknown_state` would satisfy every
#: never-blocks assertion while telling whoever reads the run nothing at all.
#: The split that matters here is `bridge_failed` (the transport or the payload
#: is at fault — a bug report) against `unknown_state` (this client does not
#: understand what it was handed — fail-closed of last resort).
EXPECTED_OUTCOME: dict[str, tuple[str, str]] = {
    "transport raises": ("unavailable", "bridge_failed"),
    "coordinator unreachable": ("unavailable", "bridge_failed"),
    "bridge skipped the call": ("unavailable", "bridge_failed"),
    "envelope is not a mapping": ("unavailable", "bridge_failed"),
    "envelope is None": ("unavailable", "bridge_failed"),
    "response is not a mapping": ("unavailable", "bridge_failed"),
    "response is missing": ("unavailable", "bridge_failed"),
    "results is a string": ("unavailable", "bridge_failed"),
    "results is a mapping": ("unavailable", "bridge_failed"),
    "a result is not a mapping": ("unavailable", "bridge_failed"),
    "a result is missing fields": ("unavailable", "bridge_failed"),
    "a result has an inverted line span": ("unavailable", "bridge_failed"),
    "a result escapes the repository": ("unavailable", "bridge_failed"),
    "a result has an impossible score": ("unavailable", "bridge_failed"),
    "a ready response omits its index block": ("unavailable", "bridge_failed"),
    "a future coordinator state": ("unavailable", "unknown_state"),
    "a differently-cased ready": ("unavailable", "unknown_state"),
    "a non-string state": ("unavailable", "unknown_state"),
    "no state at all": ("unavailable", "unknown_state"),
    "detection raises": ("unavailable", "unknown_state"),
    "git raises": ("unavailable", "unknown_state"),
    "the package file raises": ("unavailable", "unknown_state"),
    "the checkpoint raises": ("unavailable", "unknown_state"),
    "ri-08 scope resolution raises": ("unavailable", "unknown_state"),
    "the scope object explodes when asked": ("unavailable", "unknown_state"),
    "the flag is off": ("unavailable", "injection_disabled"),
    "the worktree is dirty": ("stale", "working_tree_dirty"),
    "the index is behind": ("mismatched", "index_revision_differs"),
    "the service refused the scope": ("out_of_scope", "scope_rejected"),
    "the index is empty": ("no_context", "index_returned_no_hits"),
    "the declared scope is unusable": ("out_of_scope", "scope_self_cancelling"),
}

_MODES = list(FAILURE_MODES)


def _coding_job(runtime: sc.SemanticContextRuntime) -> str:
    """What a consumer skill does with this helper, start to finish.

    Collect, render, splice into the prompt, carry on. If any step can raise,
    the job stops here and the missing context has become a blocking failure.
    """
    result = sc.collect_semantic_context(_request(), runtime)
    block = rsc.render_semantic_context(
        result.to_dict(),
        read_allow=("skills/**",),
        symbol="collect_semantic_context",
    )
    return "\n".join(["# Task: implement wp-fallback-tests", block, "# Proceed."])


@pytest.mark.parametrize("mode", _MODES)
def test_the_coding_job_runs_to_completion_for_every_failure_mode(mode: str) -> None:
    """The whole point. Context assembly finished and the prompt was built."""
    prompt = _coding_job(FAILURE_MODES[mode])

    assert prompt.startswith("# Task: implement wp-fallback-tests")
    assert prompt.endswith("# Proceed."), (
        f"Context assembly did not reach the end of the job for {mode!r}."
    )


@pytest.mark.parametrize("mode", _MODES)
def test_collect_semantic_context_returns_a_result_for_every_failure_mode(
    mode: str,
) -> None:
    """The guarantee itself, stated as the tests state it rather than as prose."""
    result = sc.collect_semantic_context(_request(), FAILURE_MODES[mode])

    assert isinstance(result, sc.SemanticContextResult)
    assert result.status in ("injected", "fallback")


@pytest.mark.parametrize("mode", _MODES)
def test_no_failure_mode_produces_an_empty_success(mode: str) -> None:
    """Fail-closed, in the only two shapes the contract admits.

    An `injected` section with no hits reads to a worker as "no relevant code
    exists". That is a different claim from "we could not look", and only one of
    them is true here.
    """
    result = sc.collect_semantic_context(_request(), FAILURE_MODES[mode])

    if result.status == "injected":
        assert result.hits, f"{mode!r} produced an injected section with no hits."
        assert result.provenance is not None
        assert result.fallback is None
    else:
        assert result.fallback is not None, f"{mode!r} fell back without saying why."
        assert result.fallback.trigger in sc.FALLBACK_TRIGGERS
        assert result.fallback.reason in sc.FALLBACK_REASONS
        assert result.fallback.strategy == "exact_search", (
            f"{mode!r} offered strategy {result.fallback.strategy!r}. Exact search "
            "is the only remedy this contract knows how to instruct."
        )
        assert result.hits == ()
        assert result.provenance is None


@pytest.mark.parametrize("mode", _MODES)
def test_every_failure_mode_falls_back_rather_than_injecting(mode: str) -> None:
    """None of these is a healthy retrieval, so none of them may inject."""
    result = sc.collect_semantic_context(_request(), FAILURE_MODES[mode])

    assert result.status == "fallback", (
        f"{mode!r} produced an injected section. Whatever it injected, this "
        "client could not verify it."
    )


def test_every_failure_mode_is_accounted_for() -> None:
    """A new mode with no declared outcome would silently opt out of the table."""
    assert set(FAILURE_MODES) == set(EXPECTED_OUTCOME)


@pytest.mark.parametrize("mode", _MODES)
def test_each_failure_mode_reports_the_cause_it_actually_had(mode: str) -> None:
    """Not blocking is necessary; saying something useful is what makes it usable.

    Routing every surprise to `unknown_state` would keep the job running and
    leave every operator with the same unactionable sentence. `bridge_failed`
    sends them to the transport; `unknown_state` admits this client is out of
    its depth. They are not interchangeable.
    """
    result = sc.collect_semantic_context(_request(), FAILURE_MODES[mode])

    assert result.fallback is not None
    assert (result.fallback.trigger, result.fallback.reason) == EXPECTED_OUTCOME[mode], (
        f"{mode!r} now reports "
        f"{(result.fallback.trigger, result.fallback.reason)} instead of "
        f"{EXPECTED_OUTCOME[mode]}."
    )


@pytest.mark.parametrize("mode", _MODES)
def test_the_rendered_block_never_leaves_the_worker_without_instruction(
    mode: str,
) -> None:
    """A silent absence is indistinguishable from 'no relevant code exists'."""
    result = sc.collect_semantic_context(_request(), FAILURE_MODES[mode])
    text = rsc.render_semantic_context(result.to_dict(), read_allow=("skills/**",))

    assert result.fallback is not None
    if result.fallback.reason == "injection_disabled":
        # D9's single exception: an opt-out renders nothing at all.
        assert text == ""
        return
    assert rsc.SECTION_HEADING in text
    assert f"`trigger={result.fallback.trigger}`" in text, (
        f"{mode!r} rendered a block that does not name its trigger:\n{text}"
    )
    assert f"`{result.fallback.reason}`" in text, (
        f"{mode!r} rendered a block that does not name its reason:\n{text}"
    )
    assert "exact search" in text.lower()
    assert "rg -n" in text


@pytest.mark.parametrize("mode", _MODES)
def test_the_same_inputs_produce_the_same_section_twice(mode: str) -> None:
    """No clock, no RNG, no identity. A fallback is reproducible from its cause."""
    first = sc.collect_semantic_context(_request(), FAILURE_MODES[mode])
    second = sc.collect_semantic_context(_request(), FAILURE_MODES[mode])

    assert first.to_dict() == second.to_dict()


@pytest.mark.parametrize("mode", _MODES)
def test_every_emitted_section_validates_against_the_published_contract(
    mode: str,
) -> None:
    """A fallback nobody can parse is only marginally better than an exception."""
    jsonschema = pytest.importorskip("jsonschema")
    import json

    schema = json.loads(_SECTION_SCHEMA.read_text(encoding="utf-8"))
    result = sc.collect_semantic_context(_request(), FAILURE_MODES[mode])

    jsonschema.Draft202012Validator(schema).validate(result.to_dict())


# --------------------------------------------------------------------------
# Unrecognized states specifically: the fail-open temptation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "state",
    ["quantum_flux", "READY", "ready ", " ready", "", "not_ready", "ok", "true"],
)
def test_an_unrecognized_state_never_injects_the_results_it_carries(state: str) -> None:
    """The response is otherwise perfect: real hits, right revision, in scope.

    Only the state is unfamiliar. Treating "I do not know this word" as "close
    enough to ready" is the fail-open this whole capability exists to remove, and
    it is invisible in a test whose unknown-state response happens to be empty.
    """
    result = sc.collect_semantic_context(
        _request(), _responds({"state": state, "current": True}, [_hit(1, 5)])
    )

    assert result.status == "fallback", (
        f"state={state!r} carried well-formed hits and they were injected. A "
        "state this client does not recognize is not a state it can act on."
    )
    assert result.fallback is not None
    assert (result.fallback.trigger, result.fallback.reason) == (
        "unavailable",
        "unknown_state",
    )
    assert result.fallback.service_state is None, (
        "The unrecognized string must not be echoed as a CodeSearchState; the "
        "section schema pins that field to the states this client knows."
    )


def test_the_state_mapping_is_total_over_every_declared_service_state() -> None:
    """No CodeSearchState may reach the client without a decided outcome."""
    for state in sc.SERVICE_STATES:
        if state == "ready":
            continue
        trigger, reason = sc.fallback_for_state(state)
        assert trigger in sc.FALLBACK_TRIGGERS
        assert reason in sc.FALLBACK_REASONS
        assert trigger != "no_context", (
            f"{state!r} is a service condition, not a relevance one. `no_context` "
            "claims the index is healthy and current (D14)."
        )


@pytest.mark.parametrize(
    "state", [*sc.SERVICE_STATES, "quantum_flux", "READY", "", "ready "]
)
def test_the_bridge_and_the_retrieval_helper_classify_states_identically(
    state: str,
) -> None:
    """Two skills keep the same D8 table. Drift between them is silent.

    `coordination-bridge` decides "may this be injected" for its own callers and
    `context-engineering` decides it again for the section. If they ever disagree
    about a state, one of the two paths is fail-open and neither is obviously
    wrong from inside its own tests.
    """
    bridge = cb.classify_code_search_state(state)

    if state == "ready":
        assert bridge is None
        return
    assert bridge is not None
    assert (bridge["trigger"], bridge["reason"]) == sc.fallback_for_state(state), (
        f"For state {state!r} the bridge says "
        f"{(bridge['trigger'], bridge['reason'])} and the retrieval helper says "
        f"{sc.fallback_for_state(state)}. One of the two is wrong."
    )
    assert bridge["strategy"] == "exact_search"


# --------------------------------------------------------------------------
# Coverage of the trigger vocabulary
# --------------------------------------------------------------------------


def test_every_declared_trigger_is_reachable_through_the_helper() -> None:
    """A trigger nothing can produce is documentation, not behaviour.

    Conversely, a trigger produced but not declared would fail the contract at
    the point of use rather than here.
    """
    produced = set()
    for runtime in FAILURE_MODES.values():
        result = sc.collect_semantic_context(_request(), runtime)
        if result.fallback is not None:
            produced.add(result.fallback.trigger)

    assert produced == set(sc.FALLBACK_TRIGGERS), (
        f"Unreachable triggers: {set(sc.FALLBACK_TRIGGERS) - produced}; "
        f"undeclared triggers: {produced - set(sc.FALLBACK_TRIGGERS)}."
    )


def test_a_scope_object_that_explodes_does_not_take_the_coding_job_with_it() -> None:
    """The single most likely escape: a raise from inside result shaping.

    Everything else fails at a boundary the helper already treats as hostile.
    `scopes.allows()` is called on each hit, deep inside the success path, after
    the response has been accepted -- so a defect there meets no boundary guard
    on its way out.
    """
    runtime = replace(_ready([_hit(1, 5)]), index_scopes=lambda _p: _ExplodingScopes())

    prompt = _coding_job(runtime)
    result = sc.collect_semantic_context(_request(), runtime)

    assert prompt.endswith("# Proceed.")
    assert result.status == "fallback"
    assert result.fallback is not None
    assert (result.fallback.trigger, result.fallback.reason) == (
        "unavailable",
        "unknown_state",
    ), (
        "An unexpected exception must land on the fail-closed default, not on a "
        "reason that claims to know what happened."
    )


def test_the_renderer_survives_sections_the_helper_would_never_emit() -> None:
    """The renderer is the last step, so it is the last chance to block a job.

    These inputs cannot come from `collect_semantic_context`. They can come from
    a stored result, a hand-edited fixture, or a future producer -- and the
    renderer's contract is that none of them raises either.
    """
    hostile = [
        None,
        "",
        [],
        42,
        {},
        {"status": "injected"},
        {"status": "injected", "hits": []},
        {"status": "fallback"},
        {"status": "fallback", "hits": [], "fallback": {"trigger": "made_up"}},
        {"status": "fallback", "hits": [_hit(1, 5)], "fallback": {"trigger": "stale"}},
        {"status": "future_status", "hits": []},
        {"status": "fallback", "hits": [], "fallback": None},
    ]

    for section in hostile:
        text = rsc.render_semantic_context(section)
        assert isinstance(text, str)
        assert rsc.SECTION_HEADING in text, (
            f"{section!r} rendered {text!r}. A section the renderer cannot read "
            "must fail closed to a visible refusal, never to silence -- silence "
            "reads as 'no relevant code exists'."
        )
        assert "exact search" in text.lower()


class _HostileMapping(Mapping):
    """A nested record that raises on every access.

    Not a contrivance: a section can arrive holding a lazy proxy, a view over a
    file that has since gone away, or any object that satisfies
    `isinstance(_, Mapping)` and then fails when asked. The renderer's
    structural checks all pass on it and then the *first read* raises -- which
    is the shape of failure a `_Uninterpretable`-only guard would let through.

    NOTE: this appears here only *nested* inside an otherwise readable section.
    A section object that is itself hostile still escapes `render_semantic_
    context`, because its fail-closed path re-reads the same untrusted object
    outside the guard. That is a production defect this test package reports
    rather than fixes, so no assertion here claims otherwise.
    """

    def __getitem__(self, _key: object) -> object:
        raise RuntimeError("the record cannot be read")

    def get(self, _key: object, _default: object = None) -> object:
        raise RuntimeError("the record cannot be read")

    def __iter__(self):
        raise RuntimeError("the record cannot be read")

    def __len__(self) -> int:
        return 1


class _HostileSymbol:
    def __str__(self) -> str:
        raise RuntimeError("the symbol cannot be rendered")


class _HostileGlobs(Sequence):
    def __getitem__(self, _index: object) -> str:
        raise RuntimeError("the read scope cannot be iterated")

    def __len__(self) -> int:
        return 1


def test_the_renderer_survives_inputs_that_raise_rather_than_merely_malformed() -> None:
    """The last step before the prompt, given arguments that fight back.

    Every hostile input in the previous test is *structurally* wrong and is
    rejected by an explicit check, so `_Uninterpretable` alone would handle them
    all. These raise from inside an access the renderer has already decided is
    safe, one for each of its three arguments -- and only the blanket guard
    catches those.
    """
    for section in (
        {"status": "fallback", "hits": [], "fallback": _HostileMapping()},
        {"status": "injected", "hits": [_HostileMapping()], "provenance": {}},
        {"status": "fallback", "hits": [], "omissions": _HostileMapping()},
    ):
        text = rsc.render_semantic_context(section)

        assert rsc.SECTION_HEADING in text, (
            f"A raising record rendered {text!r}. The renderer is the last step "
            "before the prompt; a raise here reintroduces the blocking failure "
            "the whole retrieval path removed."
        )
        assert "exact search" in text.lower()

    # A raising argument must not poison an otherwise readable section either:
    # `symbol` and `read_allow` are rendering niceties, not provenance.
    good = sc.collect_semantic_context(_request(), FAILURE_MODES["the index is empty"])
    text = rsc.render_semantic_context(
        good.to_dict(), read_allow=_HostileGlobs(), symbol=_HostileSymbol()
    )
    assert "`index_returned_no_hits`" in text, (
        "An unusable `symbol`/`read_allow` discarded the section's own facts. "
        f"Got:\n{text}"
    )
