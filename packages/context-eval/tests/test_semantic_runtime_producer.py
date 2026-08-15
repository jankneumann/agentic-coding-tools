"""``SemanticRuntimeProducer``: the harness's own wiring of ri-12's seams.

Issue #333. ``_ResolvedScope`` (this module's stub for ri-08's
``IndexScopes``) carried ``read_allow``/``deny`` but no ``allows(path)``
method, while ``semantic_context.py``'s local deny re-check (D2,
``filter_scope`` at ``semantic_context.py:454``) calls
``scopes.allows(hit.file_path)``. Every case that reached the re-check raised
``AttributeError``, which ``collect_semantic_context``'s never-raises
guarantee (D8, the bare ``except Exception`` at ``semantic_context.py:1359``)
swallows into a ``fallback``/``unavailable``/``unknown_state`` arm -- empty,
and therefore *vacuously compliant* under
``context_eval.scoring.scope.score_scope``, which finds no violations in an
arm that rendered no hits at all. The ``scope_compliance`` gate was passing
without ever scoring a single rendered hit.

These tests drive ``SemanticRuntimeProducer`` itself -- not
``collect_semantic_context`` called directly with a hand-built scopes stub, as
``test_scope_scorer.py`` does -- against the corpus's adversarial recorded
responses, and assert the rendered arm is non-empty and ``status ==
"injected"``. So an empty arm can never again be mistaken for a compliant one.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "packages" / "context-eval"
SRC = PACKAGE_ROOT / "src"
CORPUS_ROOT = PACKAGE_ROOT / "corpus"

for _path in (SRC,):
    if str(_path) not in sys.path:  # pragma: no cover - import plumbing
        sys.path.insert(0, str(_path))

from context_eval.loader import load_corpus  # noqa: E402
from context_eval.models import Case  # noqa: E402
from context_eval.producers.semantic_runtime import (  # noqa: E402
    SemanticRuntimeProducer,
    _ResolvedScope,
    load_semantic_context,
    module_path_for,
    recorded_response,
)
from context_eval.scoring import scope as scoring  # noqa: E402


def _corpus():
    return load_corpus(CORPUS_ROOT)


def _producer(evaluated_revision: str) -> SemanticRuntimeProducer:
    module = load_semantic_context(module_path_for(REPO_ROOT))
    return SemanticRuntimeProducer(
        module=module,
        repository_root=REPO_ROOT,
        evaluated_revision=evaluated_revision,
        budget=_corpus().budget,
    )


def _render(case: Case) -> tuple:
    """Render *case* through the real producer, returning ``(arm, request_body)``."""
    body = recorded_response(CORPUS_ROOT, case)
    assert body is not None, f"{case.case_id} has no recorded response"
    revision = body["request"]["source_revision"]
    producer = _producer(revision)
    arm = producer.render(case, body)
    return arm, producer.last_request_body


# --------------------------------------------------------------------------
# _ResolvedScope.allows: the stub must actually implement the seam it claims
# --------------------------------------------------------------------------


def test_resolved_scope_exposes_allows() -> None:
    """ri-12 calls ``scopes.allows(path)``; the duck-typed stub must have one.

    Before the fix this raised ``AttributeError`` on the very first call.
    """
    scope = _ResolvedScope(read_allow=("a/**",), deny=("a/b/**",))
    assert hasattr(scope, "allows")
    assert scope.allows("a/c.py") is True
    assert scope.allows("a/b/c.py") is False  # deny wins even though allow also matches
    assert scope.allows("z/c.py") is False  # matches neither allow nor deny


def test_resolved_scope_allows_agrees_with_the_scorer_it_is_scored_against() -> None:
    """The stub must delegate to, not merely resemble, ``scoring.scope.allows``.

    A hand-rolled reimplementation could quietly diverge from the semantics the
    gate itself applies; this table exercises the same deny-precedence cases
    ``test_scope_scorer.py::test_the_glob_matcher_agrees_with_the_repositorys_own``
    and ``test_deny_beats_allow_even_when_both_match`` cover, through the stub.
    """
    table = (
        (("a/**",), (), "a/b.py", True),
        (("a/**",), ("a/**",), "a/b.py", False),
        ((), (), "a/b.py", False),
        (
            ("skills/parallel-infrastructure/**",),
            ("skills/parallel-infrastructure/scripts/tests/**",),
            "skills/parallel-infrastructure/scripts/tests/x.py",
            False,
        ),
        (
            ("skills/parallel-infrastructure/**",),
            ("skills/parallel-infrastructure/scripts/tests/**",),
            "skills/parallel-infrastructure/scripts/y.py",
            True,
        ),
    )
    for read_allow, deny, path, expected in table:
        scope = _ResolvedScope(read_allow=read_allow, deny=deny)
        assert scope.allows(path) == expected == scoring.allows(path, read_allow, deny)


# --------------------------------------------------------------------------
# the regression: an adversarial case must render, not vanish into fallback
# --------------------------------------------------------------------------


def test_deny_precedence_case_renders_a_nonempty_injected_arm() -> None:
    """``ADV-DENY-PRECEDENCE`` driven through the real producer, not a stub."""
    case = _corpus().case_by_id("ADV-DENY-PRECEDENCE")
    body = recorded_response(CORPUS_ROOT, case)
    assert body is not None
    denied = body["results"][0]["file_path"]

    arm, _ = _render(case)

    assert arm.status == "injected", (
        "an AttributeError in the client-side deny re-check would swallow this "
        f"case into fallback instead; got status={arm.status!r}, "
        f"trigger={arm.fallback_trigger!r}, reason={arm.fallback_reason!r}"
    )
    assert arm.hits, "an empty arm passes scope_compliance vacuously (issue #333)"
    assert len(arm.hits) == case.expectation.rendered_hits
    assert denied not in arm.rendered_files
    assert denied in arm.scope_filtered_paths()


def test_leaked_hit_case_renders_a_nonempty_injected_arm() -> None:
    """``ADV-LEAKED-HIT`` driven through the real producer, not a stub."""
    case = _corpus().case_by_id("ADV-LEAKED-HIT")
    leaked = "skills/autopilot/SKILL.md"

    arm, _ = _render(case)

    assert arm.status == "injected", (
        f"got status={arm.status!r}, trigger={arm.fallback_trigger!r}, "
        f"reason={arm.fallback_reason!r}"
    )
    assert arm.hits, "an empty arm passes scope_compliance vacuously (issue #333)"
    assert len(arm.hits) == case.expectation.rendered_hits
    assert leaked not in arm.rendered_files
    assert leaked in arm.scope_filtered_paths()


def test_scope_gate_scores_actual_hits_not_an_empty_arm() -> None:
    """End to end: the ``scope_compliance`` gate must see real hits to mean anything.

    A gate that passes on ``cases_scored == 1`` with zero rendered hits is the
    exact failure mode issue #333 describes: green for the wrong reason.
    """
    case = _corpus().case_by_id("ADV-DENY-PRECEDENCE")
    arm, request_body = _render(case)
    assert arm.hits, "the gate must be scoring a non-empty arm to mean anything"

    result = scoring.score_case(case, arm, request_body=request_body)
    thresholds = next(g for g in _corpus().gates if g.kind == "scope_compliance").thresholds
    gate = scoring.score_scope([result], thresholds, scope_adapter="resolved")

    assert gate.measured["cases_scored"] == 1
    assert gate.verdict == "pass"
