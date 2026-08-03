"""D14: a healthy, current index that yields nothing says so honestly.

Before this amendment, a ``state=ready`` response that returned zero results --
or one whose hits were all removed by this client's own dedup/budget selection
-- was reported as ``unavailable`` / ``unknown_state``: a correctly functioning
service filed under a broken one. That is the same misreporting the rest of this
roadmap exists to remove, pointed the other way, and it is worse than useless
because it sends a reader looking for an outage that never happened.

These tests pin the two facts apart. Only ``all_hits_omitted`` could have been
changed by a larger budget; ``index_returned_no_hits`` could not.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "skills" / "context-engineering" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import semantic_context as sc  # noqa: E402

_SECTION_SCHEMA = (
    _REPO_ROOT
    / "openspec"
    / "contracts"
    / "code-search"
    / "schemas"
    / "semantic-context-section.schema.json"
)

_REVISION = "a" * 40
_INDEX_ID = "9f1c0b3a-6d2e-4f81-9a44-0e1b2c3d4e5f"


def _runtime(*, results: list[dict[str, object]]) -> sc.SemanticContextRuntime:
    """A runtime whose every dependency is answered, so only relevance varies."""

    def search(_body: dict[str, object]) -> dict[str, object]:
        return {
            "status": "ok",
            "response": {
                "state": "ready",
                "current": True,
                "results": results,
                "index_id": _INDEX_ID,
                "repo_slug": "agentic_coding_tools",
                "source_revision": _REVISION,
            },
        }

    return _wire(search)


@dataclass(frozen=True)
class _Scopes:
    """ri-08's ``IndexScopes``, duck-typed.

    ``ReadScope.from_index_scopes`` reads ``read_allow``/``deny`` as *attributes*,
    not mapping keys, so a dict here resolves to an empty scope and every request
    becomes ``no_declared_scope``. That is fail-closed and therefore silent —
    which is exactly why the fixture has to match the real shape.
    """

    read_allow: tuple[str, ...] = ("skills/**",)
    deny: tuple[str, ...] = ()

    def allows(self, file_path: str) -> bool:
        """``filter_scope`` calls this; a fixture without it is not the real shape."""
        return any(
            fnmatch(file_path, pattern) or file_path.startswith(pattern.rstrip("*"))
            for pattern in self.read_allow
        ) and not any(fnmatch(file_path, pattern) for pattern in self.deny)


def _wire(search) -> sc.SemanticContextRuntime:
    """Every dependency answered, so only relevance varies across these tests."""
    return sc.SemanticContextRuntime(
        search=search,
        detect=lambda: {"CAN_CODE_SEARCH": True, "COORDINATION_TRANSPORT": "http"},
        git=lambda _repo, argv: _REVISION if "rev-parse" in argv else "",
        load_package=lambda _root, _change, _pkg: {"scope": {"read_allow": ["skills/**"]}},
        index_scopes=lambda _package: _Scopes(),
        load_checkpoint=lambda *_a, **_k: None,
        env={"SEMANTIC_CONTEXT_INJECTION": "1"},
    )


def _request() -> sc.SemanticContextRequest:
    return sc.SemanticContextRequest(
        repository=".",
        query="anything",
        consumer="implement-feature",
        change_id="inject-scoped-semantic-context-into-coding-jobs",
        package_id="wp-retrieval",
    )


def _hit(start: int, end: int, score: float = 0.9) -> dict[str, object]:
    return {
        "file_path": "skills/context-engineering/scripts/semantic_context.py",
        "start_line": start,
        "end_line": end,
        "similarity": score,
        "source_revision": _REVISION,
        "index_id": _INDEX_ID,
        "language": "python",
        "content": "def f():\n    return 1\n",
        "scope_decision": "allowed",
    }


def test_no_context_is_a_declared_trigger() -> None:
    assert "no_context" in sc.FALLBACK_TRIGGERS, (
        "`no_context` is in the published schema but not in the module's trigger "
        "table, so the renderer and the tests would disagree with the contract."
    )


@pytest.mark.parametrize("reason", ["index_returned_no_hits", "all_hits_omitted"])
def test_relevance_reasons_are_declared(reason: str) -> None:
    assert reason in sc.FALLBACK_REASONS, (
        f"{reason!r} is in the published schema but not in FALLBACK_REASONS."
    )


def test_an_empty_ready_index_is_no_context_not_unavailable() -> None:
    """The service answered, and answered well. It is not broken."""
    result = sc.collect_semantic_context(
        _request(),
        _runtime(results=[]),
    )
    assert result.status == "fallback"
    assert result.fallback is not None
    assert result.fallback.trigger == "no_context", (
        "A ready index that returned nothing is reported as "
        f"{result.fallback.trigger!r}. Reporting a working service as broken "
        "sends the reader looking for an outage that never happened."
    )
    assert result.fallback.reason == "index_returned_no_hits"
    assert result.fallback.service_state == "ready"
    assert result.fallback.strategy == "exact_search"


def test_hits_removed_by_our_own_budget_are_a_different_fact() -> None:
    """`all_hits_omitted` is the one a larger budget could have changed."""
    over_cap = sc.DEFAULT_BUDGET.max_hit_lines + 10
    result = sc.collect_semantic_context(
        _request(),
        _runtime(results=[_hit(1, over_cap)]),
    )
    assert result.status == "fallback"
    assert result.fallback is not None
    assert result.fallback.trigger == "no_context"
    assert result.fallback.reason == "all_hits_omitted", (
        "The index returned a hit and this client's own budget dropped it. "
        "Collapsing that into `index_returned_no_hits` would tell the reader "
        "the index is empty when raising the budget would have produced context."
    )
    assert result.fallback.service_state == "ready"


def test_scope_filtering_still_reports_out_of_scope_not_no_context() -> None:
    """Scope is a safety decision, not a relevance one; it keeps its trigger."""
    denied = _hit(1, 5)
    denied["file_path"] = "agent-coordinator/src/code_search.py"
    result = sc.collect_semantic_context(
        _request(),
        _runtime(results=[denied]),
    )
    assert result.status == "fallback"
    assert result.fallback is not None
    assert result.fallback.trigger == "out_of_scope", (
        "A hit dropped for being outside the declared read scope must stay "
        "`out_of_scope`. Relabelling it `no_context` would hide a scope event "
        "behind a relevance one."
    )
    assert result.fallback.reason == "all_hits_scope_filtered"


@pytest.mark.parametrize(
    ("results", "expected_reason"),
    [([], "index_returned_no_hits"), ([_hit(1, 999)], "all_hits_omitted")],
)
def test_no_context_sections_validate_against_the_published_contract(
    results: list[dict[str, object]], expected_reason: str
) -> None:
    """The schema's three conditional constraints must accept what we emit."""
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(_SECTION_SCHEMA.read_text(encoding="utf-8"))
    result = sc.collect_semantic_context(
        _request(),
        _runtime(results=results),
    )
    assert result.fallback is not None
    assert result.fallback.reason == expected_reason
    jsonschema.Draft202012Validator(schema).validate(result.to_dict())


def test_unknown_state_is_still_unavailable_not_no_context() -> None:
    """D14 must not weaken D8: an unrecognized state is still a failure."""

    def search(_body: dict[str, object]) -> dict[str, object]:
        return {
            "status": "ok",
            "response": {"state": "quantum_flux", "current": False, "results": []},
        }

    result = sc.collect_semantic_context(_request(), _wire(search))
    assert result.fallback is not None
    assert (result.fallback.trigger, result.fallback.reason) == (
        "unavailable",
        "unknown_state",
    ), "An unrecognized coordinator state must remain a failure, not become relevance."


def test_the_renderer_surfaces_no_context_with_its_reason() -> None:
    """A trigger the renderer does not know fails closed and loses the reason.

    Failing closed is right for an *unrecognized* trigger, but `no_context` is
    recognized by the contract. If the renderer's table lags the schema, a
    healthy-index fallback renders as an unexplained refusal -- which is how the
    reader loses the one fact D14 added.
    """
    render = pytest.importorskip("render_semantic_context")
    result = sc.collect_semantic_context(_request(), _runtime(results=[]))
    text = render.render_semantic_context(result.to_dict())
    assert "no_context" in text, (
        "The rendered section does not name the `no_context` trigger; the "
        "renderer's FALLBACK_TRIGGERS table has fallen behind the schema."
    )
    assert "index_returned_no_hits" in text, (
        "The rendered section does not name the reason, so a reader cannot tell "
        "an empty index from a budget that discarded everything."
    )
    assert "exact" in text.lower(), (
        "The rendered fallback does not state the exact-search strategy."
    )


def test_the_renderer_never_raises_even_on_a_hostile_section() -> None:
    """The fail-closed path must not re-trust the section that already failed.

    `render_semantic_context` documents "never raises", and every consumer
    relies on it: semantic context is an optional input, and an optional input
    that can abort its consumer is not optional. The blanket guard covered
    `_render`, but the fail-closed `_render_fallback` on the next line re-read
    the SAME untrusted section through `_requested_revision`, so a section whose
    own `.get` raises escaped the function entirely.
    """
    render = pytest.importorskip("render_semantic_context")

    class _Hostile(Mapping):
        def __getitem__(self, key: object) -> object:
            raise RuntimeError("hostile section")

        def __iter__(self):
            return iter(())

        def __len__(self) -> int:
            return 0

        def get(self, key: object, default: object = None) -> object:
            raise RuntimeError("hostile section")

    text = render.render_semantic_context(_Hostile())
    assert "Semantic code context" in text, (
        "A hostile section produced no fail-closed block at all."
    )
    assert "Not injected" in text and "exact search" in text.lower(), (
        "The fail-closed block does not tell the worker to use exact search, so "
        "an unreadable section reads as an unexplained absence."
    )


@pytest.mark.parametrize(
    ("results", "needle"),
    [
        ([], "would not have changed"),
        ([_hit(1, sc.DEFAULT_BUDGET.max_hit_lines + 10)], "may have produced context"),
    ],
)
def test_each_relevance_reason_renders_prose_not_a_raw_enum(
    results: list[dict[str, object]], needle: str
) -> None:
    """D14's distinction is only useful if the reader can see it.

    The section is produced by the real collector rather than hand-built: a
    hand-built dict missing a field the renderer validates degrades to the
    uninterpretable fallback, and the test would then be asserting against a
    block that never reaches a real worker.
    """
    render = pytest.importorskip("render_semantic_context")
    result = sc.collect_semantic_context(_request(), _runtime(results=results))
    assert result.fallback is not None
    assert result.fallback.trigger == "no_context"
    text = render.render_semantic_context(result.to_dict())
    assert needle in text, (
        f"{result.fallback.reason!r} renders without prose, so it falls back to "
        "the generic 'the retrieval helper reported `<reason>`' line -- which "
        "discards the one distinction D14 exists to draw: whether a larger "
        "budget would have helped."
    )
