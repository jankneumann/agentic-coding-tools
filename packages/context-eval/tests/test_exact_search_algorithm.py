"""The keyword ranker, pinned against a fixture tree with hand-computed output.

The number this evaluation inherited — ``keyword hit@5 = 3/10`` — was measured
on the tree of 2026-07-19 and has never been re-verified. Asserting it would
produce a test that fails on commits having nothing to do with retrieval, and a
test that fails for unrelated reasons is a test everyone learns to ignore. So
the split design D10 requires is honoured literally: **the algorithm is pinned
here, against a fixed tree; the tree-dependent number is recorded in the report
and asserted nowhere.**

The expected output below was computed by hand from the fixture's contents, not
captured from a run of the implementation. Capturing the implementation's own
output and calling it an expectation pins whatever the code does, including
whatever it does wrong.

The fixture, and the arithmetic
-------------------------------

``tests/fixtures/exact_search_tree/`` holds eight files. The query is
``lock expiry after crash``; every word survives stopword removal, so the terms
are ``(after, crash, expiry, lock)``.

===============  ========  =====  =======================================
file             distinct  total  why
===============  ========  =====  =======================================
``alpha.py``            4      5  all four terms; ``lock`` on two lines
``beta.py``             4      4  all four terms, one line each
``delta.py``            4      4  identical to ``beta.py``
``gamma.py``            4      4  identical to ``beta.py``
``phrase.md``           4      4  all four on ONE line, so four matches
``epsilon.md``          1      6  ``lock`` six times, nothing else
``zeta.py``             1      2  ``expiry`` on lines 1 and 45
``notes.txt``           —      —  excluded: not a ranked suffix
===============  ========  =====  =======================================

Ranking is ``(-distinct, -total, path)``, so ``alpha.py`` leads, then the
four-way tie at ``(4, 4)`` resolves by path — ``beta``, ``delta``, ``gamma``,
``phrase`` — then ``epsilon.md`` ahead of ``zeta.py`` on total. A four-way tie
is deliberate: a ranker whose tie-break fell through to the search backend's
emission order would be reproducible on one machine and nowhere else.

Rendering walks those files round-robin (first block of each, then second, …)
and admits each excerpt only if all four budget bounds hold. With
``max_files = 5`` the fifth file exhausts the file budget, so ``epsilon.md`` and
both of ``zeta.py``'s blocks are omitted with ``file_count_cap`` — 5 files, 18
lines, 3 omissions. That cap is the entire point of design D5: an unbounded
``rg -l`` dump compared against a section capped at five files measures the cap,
not the retrieval.

The fixture is checked in; its two checkout markers are not. Git refuses to
track any path containing a ``.git`` component, so the test copies the fixture
into ``tmp_path`` and creates ``.git`` and ``openspec/`` there. The content
under measurement is the committed content.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "packages" / "context-eval"
SRC = PACKAGE_ROOT / "src"
FIXTURE_TREE = Path(__file__).resolve().parent / "fixtures" / "exact_search_tree"

if str(SRC) not in sys.path:  # pragma: no cover - import plumbing
    sys.path.insert(0, str(SRC))

from context_eval.loader import load_corpus  # noqa: E402
from context_eval.models import Budget  # noqa: E402
from context_eval.producers.exact_search import (  # noqa: E402
    ExactSearchProducer,
    RenderedHit,
    RipgrepSearcher,
    TrackedFileSearcher,
    apply_budget,
    query_terms,
)

QUERY = "lock expiry after crash"

#: ``(file, distinct_terms, total_matches)``, hand-computed from the fixture.
EXPECTED_RANKING = (
    ("alpha.py", 4, 5),
    ("beta.py", 4, 4),
    ("delta.py", 4, 4),
    ("gamma.py", 4, 4),
    ("phrase.md", 4, 4),
    ("epsilon.md", 1, 6),
    ("zeta.py", 1, 2),
)

#: The excerpts that survive the declared budget, in render order.
EXPECTED_HITS = (
    ("alpha.py", 1, 5),
    ("beta.py", 1, 4),
    ("delta.py", 1, 4),
    ("gamma.py", 1, 4),
    ("phrase.md", 2, 2),
)

#: What the file cap pushed out, in the order the round-robin offered it.
EXPECTED_OMISSIONS = (
    ("epsilon.md", 1, 6, "file_count_cap"),
    ("zeta.py", 1, 1, "file_count_cap"),
    ("zeta.py", 45, 45, "file_count_cap"),
)

EXPECTED_RENDERED_LINES = 18


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


@pytest.fixture
def budget() -> Budget:
    """The one declared budget, from the corpus manifest. Never a literal."""
    return load_corpus(PACKAGE_ROOT / "corpus").budget


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """The fixture tree, materialized as something ``validate_repository_root`` accepts."""
    root = tmp_path / "checkout"
    shutil.copytree(FIXTURE_TREE, root)
    (root / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    (root / "openspec").mkdir()
    return root


@pytest.fixture
def fixture_files() -> tuple[str, ...]:
    """Derived from the directory, so a new fixture file cannot be silently ignored."""
    return tuple(sorted(path.name for path in FIXTURE_TREE.iterdir() if path.is_file()))


@pytest.fixture
def producer(checkout: Path, budget: Budget, fixture_files: tuple[str, ...]):
    return ExactSearchProducer(
        repository_root=checkout,
        budget=budget,
        searcher=TrackedFileSearcher(repository_root=checkout, file_list=fixture_files),
    )


# --------------------------------------------------------------------------
# tokenization
# --------------------------------------------------------------------------


def test_query_terms_are_distinct_sorted_and_stopword_free() -> None:
    assert query_terms(QUERY) == ("after", "crash", "expiry", "lock")


def test_terms_shorter_than_three_letters_are_dropped() -> None:
    """``[a-zA-Z_]{3,}``: ``to`` and ``a`` never become terms, digits never do."""
    assert query_terms("a to do 42 lock") == ("lock",)


def test_a_query_of_nothing_but_stopwords_has_no_terms() -> None:
    assert query_terms("how does it run") == ()


def test_a_query_with_no_terms_renders_a_fallback_not_an_empty_section(producer) -> None:
    """An empty section is unrepresentable; "nothing to search for" is a fallback."""
    arm = producer.render("how does it run")
    assert arm.status == "fallback"
    assert arm.hits == ()
    assert arm.fallback_trigger and arm.fallback_reason


# --------------------------------------------------------------------------
# ranking
# --------------------------------------------------------------------------


def test_the_ranking_matches_the_hand_computed_order(producer) -> None:
    ranked = producer.rank(QUERY)
    observed = tuple(
        (entry.file_path, entry.distinct_terms, entry.total_matches) for entry in ranked
    )
    assert observed == EXPECTED_RANKING


def test_the_four_way_tie_is_broken_by_path_not_by_backend_order(producer) -> None:
    """``beta``, ``delta``, ``gamma``, ``phrase`` all score ``(4, 4)``."""
    ranked = {entry.file_path: entry for entry in producer.rank(QUERY)}
    tied = [name for name in ranked if ranked[name].distinct_terms == 4]
    assert len(tied) == 5, "the fixture must keep its tie cluster for this test to mean anything"
    scores = {ranked[name].total_matches for name in tied if name != "alpha.py"}
    assert scores == {4}, "beta, delta, gamma and phrase must be genuinely tied"
    assert [name for name in tied if name != "alpha.py"] == sorted(
        name for name in tied if name != "alpha.py"
    )


def test_distinct_term_coverage_outranks_raw_match_frequency(producer) -> None:
    """``epsilon.md`` has more matches than ``beta.py`` and still ranks below it."""
    ranked = {entry.file_path: entry for entry in producer.rank(QUERY)}
    assert ranked["epsilon.md"].total_matches > ranked["beta.py"].total_matches
    order = [entry.file_path for entry in producer.rank(QUERY)]
    assert order.index("beta.py") < order.index("epsilon.md")


def test_unranked_suffixes_are_excluded_even_when_they_match(producer) -> None:
    """``notes.txt`` contains every term on one line and must not appear."""
    assert (FIXTURE_TREE / "notes.txt").read_text(encoding="utf-8").strip() == QUERY
    assert "notes.txt" not in {entry.file_path for entry in producer.rank(QUERY)}


def test_far_apart_matches_in_one_file_become_separate_excerpts(producer) -> None:
    """``zeta.py`` matches on lines 1 and 45, further apart than ``max_hit_lines``."""
    zeta = next(entry for entry in producer.rank(QUERY) if entry.file_path == "zeta.py")
    assert zeta.match_lines == (1, 45)
    blocks = producer._blocks(zeta)
    assert tuple((b.file_path, b.start_line, b.end_line) for b in blocks) == (
        ("zeta.py", 1, 1),
        ("zeta.py", 45, 45),
    )


# --------------------------------------------------------------------------
# rendering under the declared budget (design D5)
# --------------------------------------------------------------------------


def test_the_rendered_section_matches_the_hand_computed_excerpts(producer) -> None:
    arm = producer.render(QUERY)
    assert arm.status == "injected"
    observed = tuple((hit.file_path, hit.start_line, hit.end_line) for hit in arm.hits)
    assert observed == EXPECTED_HITS


def test_the_file_cap_is_applied_and_what_it_dropped_is_recorded(producer) -> None:
    """A section that silently drops material claims a completeness it lacks."""
    arm = producer.render(QUERY)
    observed = tuple(
        (o.file_path, o.start_line, o.end_line, o.reason) for o in arm.omissions
    )
    assert observed == EXPECTED_OMISSIONS


def test_the_baseline_arm_is_bounded_by_the_manifest_budget(producer, budget: Budget) -> None:
    """The equalization itself: an UNBOUNDED baseline would render more.

    Seven files rank; five are rendered. Remove the cap from this arm and the
    comparison against a capped semantic section stops measuring retrieval and
    starts measuring whose bound was tighter.
    """
    arm = producer.render(QUERY)
    assert len(producer.rank(QUERY)) > budget.max_files, (
        "the fixture must offer more files than the budget admits, or the cap is untested"
    )
    assert len(arm.rendered_files) == budget.max_files
    assert len(arm.hits) <= budget.max_hits
    assert arm.rendered_lines == EXPECTED_RENDERED_LINES
    assert arm.rendered_lines <= budget.max_total_lines
    assert all(hit.line_count <= budget.max_hit_lines for hit in arm.hits)


def test_both_arms_are_rendered_under_the_same_budget_object(producer, budget: Budget) -> None:
    """One budget, both arms — not two bounds that happen to agree today."""
    assert producer.budget == budget
    for arm in (producer.render(QUERY), producer.render_naive_phrase(QUERY)):
        assert len(arm.rendered_files) <= budget.max_files
        assert len(arm.hits) <= budget.max_hits
        assert arm.rendered_lines <= budget.max_total_lines


# --------------------------------------------------------------------------
# the naive phrase floor
# --------------------------------------------------------------------------


def test_the_phrase_arm_matches_only_the_literal_phrase(producer) -> None:
    arm = producer.render_naive_phrase(QUERY)
    assert arm.status == "injected"
    assert tuple((h.file_path, h.start_line, h.end_line) for h in arm.hits) == (
        ("phrase.md", 2, 2),
    )


def test_the_phrase_arm_falls_back_when_the_phrase_is_absent(producer) -> None:
    arm = producer.render_naive_phrase("lock expiry during crash")
    assert arm.status == "fallback"
    assert arm.hits == ()


def test_the_phrase_arm_is_weaker_than_the_keyword_arm_on_this_tree(producer) -> None:
    """Why the phrase column is recorded and never gated on (design D5)."""
    keyword = producer.render(QUERY)
    phrase = producer.render_naive_phrase(QUERY)
    assert len(phrase.rendered_files) < len(keyword.rendered_files)


# --------------------------------------------------------------------------
# the budget's own bounds
# --------------------------------------------------------------------------


def test_apply_budget_admits_by_all_four_bounds_and_never_breaks_early() -> None:
    """A large excerpt is skipped and a later small one is still admitted.

    ri-12's ``apply_budget`` has no early ``break`` for exactly this reason: with
    one, the section's contents would depend on where the first oversized hit
    landed in the ranking.
    """
    tight = Budget(max_hits=3, max_files=2, max_total_lines=10, max_hit_lines=4)
    candidates = (
        RenderedHit("a.py", 1, 2),  # 2 lines, admitted
        RenderedHit("b.py", 1, 9),  # 9 lines > max_hit_lines, skipped
        RenderedHit("c.py", 1, 3),  # 3 lines, admitted AFTER the skip
        RenderedHit("d.py", 1, 1),  # a third file, over max_files
    )
    kept, omissions = apply_budget(candidates, tight)
    assert tuple(hit.file_path for hit in kept) == ("a.py", "c.py")
    assert tuple((o.file_path, o.reason) for o in omissions) == (
        ("b.py", "hit_line_cap"),
        ("d.py", "file_count_cap"),
    )


def test_apply_budget_reports_the_hit_count_cap() -> None:
    tight = Budget(max_hits=2, max_files=9, max_total_lines=99, max_hit_lines=9)
    candidates = tuple(RenderedHit(f"{n}.py", 1, 1) for n in range(4))
    kept, omissions = apply_budget(candidates, tight)
    assert len(kept) == 2
    assert {o.reason for o in omissions} == {"hit_count_cap"}


def test_apply_budget_reports_the_total_line_cap() -> None:
    tight = Budget(max_hits=9, max_files=9, max_total_lines=5, max_hit_lines=4)
    candidates = (RenderedHit("a.py", 1, 4), RenderedHit("b.py", 1, 4))
    kept, omissions = apply_budget(candidates, tight)
    assert tuple(hit.file_path for hit in kept) == ("a.py",)
    assert tuple((o.file_path, o.reason) for o in omissions) == (("b.py", "total_line_cap"),)


# --------------------------------------------------------------------------
# the two backends agree
# --------------------------------------------------------------------------


def _ripgrep_available() -> bool:
    try:
        subprocess.run(["rg", "--version"], capture_output=True, check=False, timeout=10)
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False
    return True


@pytest.mark.skipif(not _ripgrep_available(), reason="ripgrep is not installed")
def test_the_ripgrep_backend_produces_the_same_ranking(checkout: Path, budget: Budget) -> None:
    """The algorithm is the pinned thing; the backend is an injected detail.

    Skipped rather than required, and the hermetic backend is what the pinning
    tests above run on, so this file proves the ranker with no external binary
    and additionally proves the two backends agree wherever one is available.
    """
    ripgrep = ExactSearchProducer(
        repository_root=checkout,
        budget=budget,
        searcher=RipgrepSearcher(repository_root=checkout),
    )
    observed = tuple(
        (entry.file_path, entry.distinct_terms, entry.total_matches)
        for entry in ripgrep.rank(QUERY)
    )
    assert observed == EXPECTED_RANKING
