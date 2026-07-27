"""D8 `stale`: the tree the agent is editing is not the tree any index holds.

Two causes, one trigger, and deliberately *not* one reason. A dirty worktree is
this agent's own uncommitted edit and is fixed by committing or re-indexing; a
`not_indexed` response is a revision the coordinator has never seen and is fixed
by asking for an index. Collapsing them would leave the reader of a fallback with
no way to tell which of the two remedies applies.

`stale` is also the one trigger with a *pre-query* cause, so these tests pin the
local-precondition ordering of D8 as well: a dirty tree short-circuits before the
bridge is touched. Querying anyway would be worse than wasteful -- the
coordinator would answer truthfully for `HEAD` and the agent would silently
receive pre-edit content for the very files it just changed.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

_SUITE = Path(__file__).resolve().parent
if str(_SUITE) not in sys.path:
    sys.path.insert(0, str(_SUITE))

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "skills" / "context-engineering" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import render_semantic_context as rsc  # noqa: E402
import semantic_context as sc  # noqa: E402

# The fixture shape is defined once, next to the D14 tests. Re-declaring it here
# would let the two copies drift, and the ways this fixture can be subtly wrong
# (a dict instead of an attribute-bearing object; a scope object without
# `allows`) all fail *closed*, i.e. silently.
from test_no_context_trigger import (  # noqa: E402
    _INDEX_ID,
    _REVISION,
    _hit,
    _request,
    _wire,
)

_DIRTY_PORCELAIN = " M skills/context-engineering/scripts/semantic_context.py\n"


def _ready_search(calls: list[dict[str, object]]):
    """A search client that would succeed, and records that it was reached."""

    def search(body: dict[str, object]) -> dict[str, object]:
        calls.append(body)
        return {
            "status": "ok",
            "response": {
                "state": "ready",
                "current": True,
                "results": [_hit(1, 5)],
                "index": {"index_id": _INDEX_ID, "repo_slug": "agentic_coding_tools"},
            },
        }

    return search


def _dirty_runtime(calls: list[dict[str, object]]) -> sc.SemanticContextRuntime:
    """Everything healthy except the worktree, which has uncommitted changes."""
    return replace(
        _wire(_ready_search(calls)),
        git=lambda _repo, argv: _REVISION if "rev-parse" in argv else _DIRTY_PORCELAIN,
    )


def _state_runtime(
    state: str, results: list[dict[str, object]] | None = None
) -> sc.SemanticContextRuntime:
    """Everything healthy; the coordinator answers with `state`.

    ``results`` defaults to a *renderable* hit rather than an empty list. A
    non-ready state that also carries results is the case that separates "we
    checked the state" from "we happened to have nothing to inject": with an
    empty list every ordering of the two checks produces a fallback, so the
    assertions below would hold for a client that never looked at the state.
    """
    payload = [_hit(1, 5)] if results is None else results

    def search(_body: dict[str, object]) -> dict[str, object]:
        return {
            "status": "ok",
            "response": {
                "state": state,
                "current": False,
                "results": payload,
                "index": {"index_id": _INDEX_ID, "repo_slug": "agentic_coding_tools"},
            },
        }

    return _wire(search)


def test_a_dirty_worktree_is_stale_working_tree_dirty() -> None:
    result = sc.collect_semantic_context(_request(), _dirty_runtime([]))

    assert result.status == "fallback"
    assert result.fallback is not None
    assert result.fallback.trigger == "stale", (
        "Uncommitted changes mean no index can match the tree being edited. "
        f"Reported as {result.fallback.trigger!r} instead."
    )
    assert result.fallback.reason == "working_tree_dirty"
    assert result.fallback.strategy == "exact_search"
    assert result.fallback.service_state is None, (
        "No query was issued, so there is no CodeSearchState to report. A state "
        "here would be a claim about a service that was never asked."
    )


def test_a_dirty_worktree_short_circuits_before_the_bridge_is_touched() -> None:
    """The local precondition ordering of D8, made observable.

    If the dirty check moved after the query, this passes a request for `HEAD`
    to a coordinator that would answer it truthfully -- and the agent would get
    pre-edit content for files it has already changed.
    """
    calls: list[dict[str, object]] = []

    result = sc.collect_semantic_context(_request(), _dirty_runtime(calls))

    assert calls == [], (
        f"The dirty worktree still issued {len(calls)} code-search request(s). "
        "A pre-query precondition that queries anyway is not a precondition."
    )
    assert result.fallback is not None
    assert result.fallback.reason == "working_tree_dirty"


def test_a_not_indexed_response_is_stale_revision_not_indexed() -> None:
    result = sc.collect_semantic_context(_request(), _state_runtime("not_indexed"))

    assert result.status == "fallback"
    assert result.fallback is not None
    assert result.fallback.trigger == "stale", (
        "`not_indexed` means the coordinator has no index for this revision. "
        f"Reported as {result.fallback.trigger!r} instead."
    )
    assert result.fallback.reason == "revision_not_indexed"
    assert result.fallback.strategy == "exact_search"
    assert result.fallback.service_state == "not_indexed", (
        "A query *was* issued here, so the CodeSearchState that caused the "
        "fallback must be carried through to whoever reads it."
    )
    assert result.requested_revision == _REVISION, (
        "The revision resolved before the query and must be reported, otherwise "
        "a reader cannot tell the coordinator which revision to index."
    )


def test_the_two_stale_causes_carry_different_reasons() -> None:
    """One trigger, two remedies. A shared reason would erase the difference."""
    dirty = sc.collect_semantic_context(_request(), _dirty_runtime([]))
    not_indexed = sc.collect_semantic_context(_request(), _state_runtime("not_indexed"))

    assert dirty.fallback is not None
    assert not_indexed.fallback is not None
    assert dirty.fallback.trigger == not_indexed.fallback.trigger == "stale"
    assert dirty.fallback.reason != not_indexed.fallback.reason, (
        "Both stale causes report "
        f"{dirty.fallback.reason!r}. `working_tree_dirty` is fixed by committing; "
        "`revision_not_indexed` is fixed by indexing. One reason cannot say which."
    )


def test_a_stale_state_discards_results_the_coordinator_still_returned() -> None:
    """`not_indexed` wins over renderable content, not merely over its absence.

    A coordinator may answer a non-ready state and still populate `results`
    (a stale index has rows in it). Injecting them would hand the agent excerpts
    from a revision nobody claimed matches -- the exact confusion `stale` exists
    to announce.
    """
    result = sc.collect_semantic_context(
        _request(), _state_runtime("not_indexed", [_hit(1, 5), _hit(20, 24)])
    )

    assert result.status == "fallback", (
        "Two renderable hits arrived under `state=not_indexed` and were injected "
        "anyway. The state is the claim about whether they can be trusted."
    )
    assert result.hits == ()
    assert result.provenance is None
    assert result.fallback is not None
    assert result.fallback.reason == "revision_not_indexed"


def test_every_stale_fallback_reports_a_schema_valid_revision() -> None:
    """The section schema requires a full-revision `requested_revision` (D15)."""
    for result in (
        sc.collect_semantic_context(_request(), _dirty_runtime([])),
        sc.collect_semantic_context(_request(), _state_runtime("not_indexed")),
    ):
        assert sc.FULL_REVISION_RE.match(result.requested_revision) is not None, (
            f"{result.requested_revision!r} is not a full git revision, so the "
            "emitted section would fail the published contract."
        )


def test_the_rendered_stale_section_names_its_trigger_reason_and_remedy() -> None:
    """The coding job reads markdown, not a dataclass. The facts must survive it."""
    for runtime, reason in (
        (_dirty_runtime([]), "working_tree_dirty"),
        (_state_runtime("not_indexed"), "revision_not_indexed"),
    ):
        result = sc.collect_semantic_context(_request(), runtime)
        text = rsc.render_semantic_context(result.to_dict())

        assert "`trigger=stale`" in text, (
            "The rendered section does not name the `stale` trigger, so the "
            f"worker cannot tell it apart from any other refusal. Got:\n{text}"
        )
        assert f"`{reason}`" in text, (
            f"The rendered section does not name the {reason!r} reason, so the "
            f"remedy is unrecoverable from the text. Got:\n{text}"
        )
        assert "exact search" in text.lower(), (
            "The rendered section does not instruct the worker to fall back to "
            f"exact search, which is the whole point of the block. Got:\n{text}"
        )
