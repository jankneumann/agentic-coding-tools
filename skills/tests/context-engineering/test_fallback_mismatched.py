"""D8 `mismatched`: the index answered, about a different revision.

`mismatched` and `stale` read almost identically — both mean "no usable results"
— and D8 explicitly refuses to collapse them, because their remedies point in
opposite directions. `stale` is *this agent's* problem: commit, or ask for an
index of what you are editing. `mismatched` is the *index's* problem: it is
behind, and the fix lives in the coordinator. A worker handed the wrong one of
those two chases the wrong system.

There are two ways to learn about the mismatch, and both must produce it:
the coordinator saying so (`state=revision_mismatch`), and the coordinator
claiming `ready` while shipping a hit stamped with another commit. The second is
the dangerous one: it is the only path where believing the response would inject
real, attributable, *wrong* code.
"""

from __future__ import annotations

import sys
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

from test_no_context_trigger import _INDEX_ID, _REVISION, _hit, _request, _wire  # noqa: E402

#: A different, equally valid full revision. Not a corrupted string: the point is
#: that this is a *legitimate* commit the index is honestly stamped with, so
#: nothing but the comparison against the requested revision can reject it.
_OTHER_REVISION = "b" * 40


def _response_runtime(
    state: str, results: list[dict[str, object]]
) -> sc.SemanticContextRuntime:
    return _wire(
        lambda _body: {
            "status": "ok",
            "response": {
                "state": state,
                "current": state == "ready",
                "results": results,
                "index": {"index_id": _INDEX_ID, "repo_slug": "agentic_coding_tools"},
            },
        }
    )


def _at_revision(revision: str, start: int = 1, end: int = 5) -> dict[str, object]:
    hit = _hit(start, end)
    hit["source_revision"] = revision
    return hit


def test_a_revision_mismatch_state_is_mismatched_index_revision_differs() -> None:
    result = sc.collect_semantic_context(
        _request(), _response_runtime("revision_mismatch", [])
    )

    assert result.status == "fallback"
    assert result.fallback is not None
    assert result.fallback.trigger == "mismatched", (
        "`revision_mismatch` means the index is behind the tree being edited. "
        f"Reported as {result.fallback.trigger!r} instead."
    )
    assert result.fallback.reason == "index_revision_differs"
    assert result.fallback.strategy == "exact_search"
    assert result.fallback.service_state == "revision_mismatch"


def test_mismatched_is_not_folded_into_stale() -> None:
    """Two states that read alike must not report alike (D8, explicitly)."""
    mismatched = sc.collect_semantic_context(
        _request(), _response_runtime("revision_mismatch", [])
    )
    stale = sc.collect_semantic_context(_request(), _response_runtime("not_indexed", []))

    assert mismatched.fallback is not None
    assert stale.fallback is not None
    assert mismatched.fallback.trigger != stale.fallback.trigger, (
        "`revision_mismatch` and `not_indexed` both report "
        f"{mismatched.fallback.trigger!r}. One is fixed in the coordinator and "
        "one is fixed in this worktree; a shared trigger picks the wrong system."
    )
    assert mismatched.fallback.reason != stale.fallback.reason


def test_a_ready_response_stamped_with_another_commit_is_still_mismatched() -> None:
    """`state=ready` is a claim, not a proof. The hits are the evidence.

    This is the only failure path where the response is internally plausible:
    the hits are well-formed, in scope, and fully attributed. Trusting the state
    over the stamp would inject real code from the wrong revision, which is worse
    than injecting nothing.
    """
    result = sc.collect_semantic_context(
        _request(), _response_runtime("ready", [_at_revision(_OTHER_REVISION)])
    )

    assert result.status == "fallback", (
        "A well-formed hit stamped with a different commit was injected because "
        "the coordinator said `ready`. The stamp is the checkable fact."
    )
    assert result.fallback is not None
    assert result.fallback.trigger == "mismatched"
    assert result.fallback.reason == "index_revision_differs"
    assert result.fallback.service_state == "ready", (
        "The service state that was actually reported must survive, otherwise a "
        "reader cannot tell a self-contradicting `ready` from an honest "
        "`revision_mismatch` — and only the first is a coordinator bug."
    )


def test_one_stale_hit_fails_the_whole_section_closed() -> None:
    """No partial injection. A section is trustworthy as a unit or not at all.

    Dropping the odd hit and rendering the rest would make the section's contents
    depend on a defect in the producer, and there is no omission reason that
    honestly says "this one was from another commit".
    """
    results = [
        _at_revision(_REVISION, 1, 5),
        _at_revision(_REVISION, 20, 24),
        _at_revision(_OTHER_REVISION, 40, 44),
    ]

    result = sc.collect_semantic_context(_request(), _response_runtime("ready", results))

    assert result.status == "fallback", (
        "Two good hits and one from another commit produced an injected section. "
        "A section that silently drops what it cannot vouch for is claiming "
        "completeness it does not have."
    )
    assert result.hits == ()
    assert result.omissions == ()
    assert result.fallback is not None
    assert result.fallback.reason == "index_revision_differs"


def test_a_mismatched_state_discards_results_the_coordinator_returned() -> None:
    """Even hits stamped with the *right* revision are refused under this state.

    Without results in the response every ordering of the checks yields a
    fallback, so this is what separates "we checked the state" from "we had
    nothing to inject anyway".
    """
    result = sc.collect_semantic_context(
        _request(),
        _response_runtime("revision_mismatch", [_at_revision(_REVISION)]),
    )

    assert result.status == "fallback"
    assert result.hits == ()
    assert result.provenance is None
    assert result.fallback is not None
    assert result.fallback.trigger == "mismatched"


def test_the_rendered_mismatched_section_instructs_an_exact_search() -> None:
    """The coding job must be told to proceed by hand, and told why."""
    for runtime in (
        _response_runtime("revision_mismatch", []),
        _response_runtime("ready", [_at_revision(_OTHER_REVISION)]),
    ):
        result = sc.collect_semantic_context(_request(), runtime)
        text = rsc.render_semantic_context(result.to_dict())

        assert "`trigger=mismatched`" in text, (
            f"The rendered section does not name the trigger. Got:\n{text}"
        )
        assert "`index_revision_differs`" in text, (
            f"The rendered section does not name the reason. Got:\n{text}"
        )
        assert "exact search" in text.lower(), (
            f"The worker is not told to fall back to exact search. Got:\n{text}"
        )
        assert "rg -n" in text, (
            "The fallback carries no runnable exact-search command, so 'fall back "
            f"to exact search' is advice without a next step. Got:\n{text}"
        )
        assert _OTHER_REVISION not in text, (
            "The section names the index's own revision, which invites the reader "
            "to treat content from it as relevant to the tree they are editing."
        )


def test_the_mismatched_fallback_names_the_revision_that_was_asked_for() -> None:
    """The fallback is only actionable if it says which revision went unanswered."""
    result = sc.collect_semantic_context(
        _request(), _response_runtime("revision_mismatch", [])
    )
    text = rsc.render_semantic_context(result.to_dict())

    assert result.requested_revision == _REVISION
    assert _REVISION in text, (
        "The rendered section does not state the requested revision, so nobody "
        f"can tell the coordinator what to index. Got:\n{text}"
    )
