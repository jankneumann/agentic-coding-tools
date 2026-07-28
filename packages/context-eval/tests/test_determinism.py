"""Determinism, asserted the way it can actually fail.

"Run it twice and compare" proves almost nothing here. A ranking built by
iterating a ``set`` repeats perfectly inside one interpreter and can still differ
between two, because ``PYTHONHASHSEED`` randomizes ``str`` hashing per process.
Phase 2 already hit this with the corpus digest and answered it with separate
interpreters under different seeds; this file reuses that method rather than
inventing a weaker one.

Four independent shapes of proof, because each catches something the others miss:

1. **Hand-derived order over a tie-heavy fixture.** Four files score identically,
   so the tie-break is the only thing deciding their order. Asserted against an
   order computed from the fixture, not captured from the implementation.
2. **Seeded shuffle of the inputs.** The file list, the search backend's own
   emission order, and the per-case lists handed to each gate are all shuffled
   with a fixed seed. Identical output, or the ordering depended on arrival.
3. **Separate interpreters, different hash seeds.** The property enablement
   actually needs: a number recorded by one process and recomputed by another.
4. **Source-level hygiene.** No clock, no ``random``, no set iteration in a
   ranking or scoring path, and no model identifier written as a literal.

The last one is a heuristic and says so. It carries a positive control, so a
detector that stopped detecting fails rather than passing silently.
"""

from __future__ import annotations

import ast
import json
import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "packages" / "context-eval"
SRC = PACKAGE_ROOT / "src"
CORPUS_ROOT = PACKAGE_ROOT / "corpus"
FIXTURE_TREE = Path(__file__).resolve().parent / "fixtures" / "exact_search_tree"

#: Every module whose output a report depends on.
MEASUREMENT_MODULES = (
    SRC / "context_eval" / "producers",
    SRC / "context_eval" / "scoring",
)

if str(SRC) not in sys.path:  # pragma: no cover - import plumbing
    sys.path.insert(0, str(SRC))

from context_eval.loader import load_corpus  # noqa: E402
from context_eval.producers.exact_search import (  # noqa: E402
    ExactSearchProducer,
    TrackedFileSearcher,
)
from context_eval.scoring import relevance, scope, utility  # noqa: E402
from context_eval.scoring.arms import Arm, RenderedHit  # noqa: E402

QUERY = "lock expiry after crash"

#: Hand-derived from the fixture's contents. ``alpha.py`` leads on total matches;
#: ``beta``, ``delta``, ``gamma`` and ``phrase`` are a genuine four-way tie at
#: ``(4, 4)`` and are therefore ordered by path alone; ``epsilon.md`` precedes
#: ``zeta.py`` on total. Nothing in this tuple was read off a run.
EXPECTED_ORDER = (
    "alpha.py",
    "beta.py",
    "delta.py",
    "gamma.py",
    "phrase.md",
    "epsilon.md",
    "zeta.py",
)

SEED = 20260728

#: Shapes an embedding or chat model identifier takes. Deliberately narrow and
#: deliberately incomplete: this is a tripwire for the obvious mistake, not a
#: proof of absence, and ``test_the_model_literal_detector_detects`` keeps it
#: honest by feeding it real identifiers.
MODEL_ID_PATTERNS = (
    re.compile(r"sentence-transformers/"),
    re.compile(r"\btext-embedding-"),
    re.compile(r"\ball-(?:MiniLM|mpnet)\b", re.IGNORECASE),
    re.compile(r"\b(?:bge|gte|e5|nomic-embed|voyage)-[a-z0-9]", re.IGNORECASE),
    re.compile(r"\b(?:gpt|claude|gemini|grok|kimi|llama|mistral)-[0-9]"),
)

KNOWN_MODEL_IDS = (
    "sentence-transformers/all-MiniLM-L6-v2",
    "text-embedding-3-small",
    "bge-large-en-v1.5",
    "claude-3-opus",
)


def _budget():
    return load_corpus(CORPUS_ROOT).budget


def _checkout(tmp_path: Path) -> Path:
    root = tmp_path / "checkout"
    shutil.copytree(FIXTURE_TREE, root)
    (root / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    (root / "openspec").mkdir()
    return root


def _fixture_files() -> list[str]:
    return sorted(path.name for path in FIXTURE_TREE.iterdir() if path.is_file())


class _ShuffledSearcher:
    """A backend that emits its matches in a deliberately unhelpful order.

    Wrapping rather than replacing: the matches are the real ones, only the
    mapping's insertion order is disturbed. A ranker that sorted its inputs is
    unaffected; one that relied on the backend's emission order is not.
    """

    def __init__(self, inner, seed: int) -> None:
        self._inner = inner
        self._rng = random.Random(seed)

    def _shuffle(self, mapping):
        items = list(mapping.items())
        self._rng.shuffle(items)
        return dict(items)

    def term_matches(self, term: str):
        return self._shuffle(self._inner.term_matches(term))

    def phrase_matches(self, phrase: str):
        return self._shuffle(self._inner.phrase_matches(phrase))

    def count_matches(self, term: str):
        return self._shuffle(self._inner.count_matches(term))


def _producer(checkout: Path, files, *, shuffle_seed: int | None = None):
    searcher = TrackedFileSearcher(repository_root=checkout, file_list=tuple(files))
    if shuffle_seed is not None:
        searcher = _ShuffledSearcher(searcher, shuffle_seed)
    return ExactSearchProducer(
        repository_root=checkout, budget=_budget(), searcher=searcher
    )


def _source_modules() -> list[Path]:
    modules = [path for root in MEASUREMENT_MODULES for path in sorted(root.rglob("*.py"))]
    assert modules, "no measurement modules found; the hygiene checks would prove nothing"
    return modules


def _string_constants(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node


# --------------------------------------------------------------------------
# 1. hand-derived order over a tie-heavy fixture
# --------------------------------------------------------------------------


def test_the_tie_heavy_fixture_ranks_in_the_hand_derived_order(tmp_path: Path) -> None:
    producer = _producer(_checkout(tmp_path), _fixture_files())
    assert tuple(entry.file_path for entry in producer.rank(QUERY)) == EXPECTED_ORDER


def test_the_fixture_really_does_contain_a_tie(tmp_path: Path) -> None:
    """Otherwise the order above is decided by score and proves nothing about ties."""
    ranked = _producer(_checkout(tmp_path), _fixture_files()).rank(QUERY)
    scores = [(entry.distinct_terms, entry.total_matches) for entry in ranked]
    assert len(scores) != len(set(scores)), "the fixture must keep at least one tie"


# --------------------------------------------------------------------------
# 2. seeded shuffle of every input that could carry an order
# --------------------------------------------------------------------------


def test_shuffling_the_file_list_changes_nothing(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    files = _fixture_files()
    shuffled = list(files)
    random.Random(SEED).shuffle(shuffled)
    assert shuffled != files, "the shuffle must actually reorder something"

    ordered_arm = _producer(checkout, files).render(QUERY)
    shuffled_arm = _producer(checkout, shuffled).render(QUERY)
    assert ordered_arm == shuffled_arm


def test_shuffling_the_backends_emission_order_changes_nothing(tmp_path: Path) -> None:
    """The failure a ``set``-iterating ranker would produce, forced deliberately."""
    checkout = _checkout(tmp_path)
    files = _fixture_files()
    baseline = _producer(checkout, files).render(QUERY)
    for seed in (SEED, SEED + 1, SEED + 2):
        arm = _producer(checkout, files, shuffle_seed=seed).render(QUERY)
        assert arm == baseline
        assert tuple(e.file_path for e in _producer(
            checkout, files, shuffle_seed=seed
        ).rank(QUERY)) == EXPECTED_ORDER


def test_reordering_the_cases_a_gate_scores_changes_no_metric() -> None:
    """The spec scenario: the same results, scored in a different input order."""
    corpus = load_corpus(CORPUS_ROOT)
    thresholds = next(g for g in corpus.gates if g.kind == "retrieval_quality").thresholds
    per_case = [
        relevance.CaseRelevance(
            case_id=f"T{index}",
            consumer="implement-feature",
            semantic_hit_at_k=index % 3 != 0,
            baseline_hit_at_k=index % 4 == 0,
            semantic_must_touch_coverage=index / 10,
            baseline_must_touch_coverage=(index % 5) / 10,
        )
        for index in range(1, 11)
    ]
    shuffled = list(per_case)
    random.Random(SEED).shuffle(shuffled)
    assert [entry.case_id for entry in shuffled] != [entry.case_id for entry in per_case]

    ordered = relevance.score_relevance(per_case, thresholds)
    reordered = relevance.score_relevance(shuffled, thresholds)
    assert ordered.verdict == reordered.verdict
    assert dict(ordered.measured) == dict(reordered.measured)
    assert ordered.fail_reasons == reordered.fail_reasons


def test_reordering_a_consumers_cases_changes_no_utility_metric() -> None:
    corpus = load_corpus(CORPUS_ROOT)
    thresholds = next(g for g in corpus.gates if g.kind == "coding_context_utility").thresholds
    slice_ = corpus.slice_for("implement-feature")
    per_case = [
        utility.CaseUtility(
            case_id=f"U{index}",
            consumer="implement-feature",
            semantic_answer_coverage=index / 4,
            baseline_answer_coverage=index / 8,
            semantic_evidence_density=index / 5,
            baseline_evidence_density=index / 9,
            semantic_steps_to_evidence=index,
            baseline_steps_to_evidence=index + 1,
            win_over_baseline=index % 2 == 0,
        )
        for index in range(1, 5)
    ]
    shuffled = list(per_case)
    random.Random(SEED).shuffle(shuffled)

    ordered = utility.score_consumer(slice_, per_case, thresholds)
    reordered = utility.score_consumer(slice_, shuffled, thresholds)
    assert ordered.verdict == reordered.verdict
    assert dict(ordered.metrics or {}) == dict(reordered.metrics or {})
    assert dict(ordered.conditions or {}) == dict(reordered.conditions or {})


def test_reordering_scope_cases_changes_the_verdict_not_at_all() -> None:
    corpus = load_corpus(CORPUS_ROOT)
    thresholds = next(g for g in corpus.gates if g.kind == "scope_compliance").thresholds
    per_case = [
        scope.ScopeCaseResult(
            case_id=f"S{index}",
            consumer="implement-feature",
            violations=(),
            deny_precedence=True,
            outbound_fidelity=True,
            expectation_honored=None,
        )
        for index in range(6)
    ]
    shuffled = list(per_case)
    random.Random(SEED).shuffle(shuffled)

    ordered = scope.score_scope(per_case, thresholds, scope_adapter="resolved")
    reordered = scope.score_scope(shuffled, thresholds, scope_adapter="resolved")
    assert ordered.verdict == reordered.verdict
    assert dict(ordered.measured) == dict(reordered.measured)


def test_arm_order_is_the_arms_own_and_is_not_re_sorted() -> None:
    """Determinism is not the same as sorting: read cost depends on rank order."""
    forward = Arm(
        arm="semantic",
        status="injected",
        hits=(RenderedHit("z.py", 1, 2), RenderedHit("a.py", 1, 2)),
    )
    assert forward.rendered_files == ("z.py", "a.py")


# --------------------------------------------------------------------------
# 3. separate interpreters, different hash seeds
# --------------------------------------------------------------------------


_SUBPROCESS_PROGRAM = """
import json
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])

from context_eval.loader import load_corpus
from context_eval.producers.exact_search import ExactSearchProducer, TrackedFileSearcher

root = Path(sys.argv[2])
budget = load_corpus(sys.argv[3]).budget
files = tuple(json.loads(sys.argv[4]))
query = sys.argv[5]

producer = ExactSearchProducer(
    repository_root=root,
    budget=budget,
    searcher=TrackedFileSearcher(repository_root=root, file_list=files),
)
arm = producer.render(query)
print(
    json.dumps(
        {
            "rank": [entry.file_path for entry in producer.rank(query)],
            "hits": [[h.file_path, h.start_line, h.end_line] for h in arm.hits],
            "omissions": [[o.file_path, o.reason] for o in arm.omissions],
        }
    )
)
"""


def _render_in_subprocess(program: Path, checkout: Path, files, hash_seed: str) -> dict:
    completed = subprocess.run(
        [
            sys.executable,
            str(program),
            str(SRC),
            str(checkout),
            str(CORPUS_ROOT),
            json.dumps(list(files)),
            QUERY,
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONHASHSEED": hash_seed},
        check=False,
    )
    if completed.returncode != 0:
        pytest.fail(f"subprocess failed (seed {hash_seed}): {completed.stderr}")
    return json.loads(completed.stdout)


def test_two_interpreters_under_different_hash_seeds_agree(tmp_path: Path) -> None:
    """The property enablement needs: recorded by one process, recomputed by another.

    Different seeds on purpose. Two runs under the same seed would agree even if
    the ranking iterated a ``set``, which is the exact defect this is for.
    """
    checkout = _checkout(tmp_path)
    program = tmp_path / "render.py"
    program.write_text(_SUBPROCESS_PROGRAM, encoding="utf-8")
    files = _fixture_files()

    first = _render_in_subprocess(program, checkout, files, "0")
    second = _render_in_subprocess(program, checkout, files, "1")
    assert first == second
    assert first["rank"] == list(EXPECTED_ORDER)


def test_a_shuffled_file_list_agrees_across_hash_seeds_too(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    program = tmp_path / "render.py"
    program.write_text(_SUBPROCESS_PROGRAM, encoding="utf-8")
    shuffled = _fixture_files()
    random.Random(SEED).shuffle(shuffled)

    assert _render_in_subprocess(program, checkout, shuffled, "0") == _render_in_subprocess(
        program, checkout, _fixture_files(), "1"
    )


# --------------------------------------------------------------------------
# 4. source-level hygiene
# --------------------------------------------------------------------------


def test_no_measurement_module_reads_a_clock() -> None:
    """The report's only timestamp is an explicit ``--as-of`` input (design D16)."""
    forbidden = {
        ("datetime", "now"),
        ("datetime", "utcnow"),
        ("datetime", "today"),
        ("date", "today"),
        ("time", "time"),
        ("time", "monotonic"),
        ("time", "perf_counter"),
    }
    offenders: list[str] = []
    for module in _source_modules():
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if (node.value.id, node.attr) in forbidden:
                    offenders.append(f"{module.name}:{node.lineno}: {node.value.id}.{node.attr}")
    assert not offenders, "\n".join(offenders)


def test_no_measurement_module_imports_random_or_time() -> None:
    banned = {"random", "secrets", "time", "datetime"}
    offenders: list[str] = []
    for module in _source_modules():
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offenders += [
                    f"{module.name}:{node.lineno}: imports {alias.name}"
                    for alias in node.names
                    if alias.name.split(".")[0] in banned
                ]
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in banned:
                    offenders.append(f"{module.name}:{node.lineno}: imports from {node.module}")
    assert not offenders, "\n".join(offenders)


def test_no_measurement_module_iterates_a_set() -> None:
    """A ``for`` over a set is where process-dependent order gets in.

    Membership testing against a set is fine and is used throughout — it reads
    the set, it does not take an order from it. Only iteration is forbidden.
    """
    def is_set_expression(node: ast.expr) -> bool:
        if isinstance(node, (ast.Set, ast.SetComp)):
            return True
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("set", "frozenset")
        )

    offenders: list[str] = []
    for module in _source_modules():
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.For, ast.AsyncFor)) and is_set_expression(node.iter):
                offenders.append(f"{module.name}:{node.lineno}: iterates a set")
            if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                offenders += [
                    f"{module.name}:{node.lineno}: comprehension iterates a set"
                    for generator in node.generators
                    if is_set_expression(generator.iter)
                ]
    assert not offenders, "\n".join(offenders)


def test_no_measurement_module_contains_a_model_identifier() -> None:
    """Embedder identity is read from configuration, never asserted as a string.

    ``packages/code-search`` writes no model id as a literal either — it arrives
    through ``--embedding-model`` — so this holds the harness to the standard the
    code it measures already meets.
    """
    offenders: list[str] = []
    for module in _source_modules():
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in _string_constants(tree):
            for pattern in MODEL_ID_PATTERNS:
                if pattern.search(node.value):
                    offenders.append(
                        f"{module.name}:{node.lineno}: {pattern.pattern} matches a literal"
                    )
    assert not offenders, "\n".join(offenders)


def test_the_model_literal_detector_detects() -> None:
    """Positive control. A tripwire nobody proved can trip is decoration."""
    for identifier in KNOWN_MODEL_IDS:
        assert any(pattern.search(identifier) for pattern in MODEL_ID_PATTERNS), identifier


def test_the_hygiene_checks_run_over_every_measurement_module() -> None:
    """A module added outside these roots would escape all four checks silently."""
    names = {path.name for path in _source_modules()}
    assert {"exact_search.py", "scope_adapter.py", "arms.py", "relevance.py",
            "scope.py", "utility.py"} <= names
