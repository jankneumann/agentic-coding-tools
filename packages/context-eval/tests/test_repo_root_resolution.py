"""The executable form of the defect that killed the previous evaluation.

``openspec/changes/archive/2026-07-20-add-semantic-code-search/eval/run_eval.py``
line 31 reads::

    REPO_ROOT = HERE.parents[3]  # openspec/changes/<id>/eval -> repo root

That comment was true on the day it was written. ``openspec archive`` then moved
the directory to ``openspec/changes/archive/<date>-<id>/eval``, which added one
path segment, and the same expression began resolving to ``<repo>/openspec`` —
a directory that exists, is readable, and contains almost none of the code the
baseline was supposed to search. Nothing raised. The runner simply measured a
different, much smaller tree, and the published baseline stopped being
reproducible from the published artifact (design D1, D10).

Two defences are asserted here, and they are different claims:

1. **The root is injected.** ``ExactSearchProducer`` takes its repository root as
   a constructor parameter with no default, and no module under
   ``producers/`` derives a root from ``__file__``. Positional path arithmetic
   cannot be got wrong if it is not written.
2. **A wrong root is loud.** A root that is not a repository checkout is an
   ``ApparatusError`` — never an empty result list. ``run_eval.py`` had the
   opposite reflex: ``_rg`` returned ``[]`` when ripgrep was missing, so an
   apparatus failure and "this query genuinely matched nothing" produced the
   same number.

``test_the_archived_path_arithmetic_still_resolves_to_openspec`` is GREEN before
the producer exists, and correctly so. It is a statement about the archived
artifact, not about the rescue: it establishes that the defect this module
defends against is real and still reproducible in this tree. If the archived
runner ever stopped exhibiting it, the rest of this file would be defending
against a hazard nobody can demonstrate. Phase 2's
``test_archived_eval_set_is_the_rescue_source`` is green for the same reason.
"""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "packages" / "context-eval"
SRC = PACKAGE_ROOT / "src"
PRODUCERS = SRC / "context_eval" / "producers"

#: The archived runner whose root arithmetic is the hazard.
ARCHIVED_RUNNER = (
    REPO_ROOT
    / "openspec/changes/archive/2026-07-20-add-semantic-code-search/eval/run_eval.py"
)

if str(SRC) not in sys.path:  # pragma: no cover - import plumbing
    sys.path.insert(0, str(SRC))


def _module():
    """Import the baseline producer, reporting absence as a failure not an error."""
    try:
        from context_eval.producers import exact_search
    except Exception as exc:  # noqa: BLE001 - any import problem is the same failure
        pytest.fail(f"context_eval.producers.exact_search is not importable: {exc!r}")
    return exact_search


def _corpus_budget():
    try:
        from context_eval.loader import load_corpus
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"context_eval.loader is not importable: {exc!r}")
    return load_corpus(PACKAGE_ROOT / "corpus").budget


# --------------------------------------------------------------------------
# precondition: the archived defect is real and still reproducible
# --------------------------------------------------------------------------


def test_the_archived_path_arithmetic_still_resolves_to_openspec() -> None:
    """``parents[3]`` from the ARCHIVED location lands on ``<repo>/openspec``.

    Green before the producer exists. It proves the hazard rather than the fix:
    the same expression is correct from the pre-archive location and wrong from
    the archived one, and nothing about the expression itself changed.
    """
    assert ARCHIVED_RUNNER.is_file(), f"the archived runner is missing: {ARCHIVED_RUNNER}"

    archived_here = ARCHIVED_RUNNER.parent
    assert archived_here.parents[3] == REPO_ROOT / "openspec", (
        "the archived layout no longer reproduces the defect this module defends against"
    )

    pre_archive_here = REPO_ROOT / "openspec/changes/some-change-id/eval"
    assert pre_archive_here.parents[3] == REPO_ROOT, (
        "the same expression was correct before archival, which is why it was never noticed"
    )


def test_the_wrong_root_is_a_directory_that_really_exists() -> None:
    """The defect is silent precisely because its wrong answer is a real directory."""
    wrong = REPO_ROOT / "openspec"
    assert wrong.is_dir(), "the failure mode only bites because the wrong root resolves"
    assert not (wrong / ".git").exists()
    assert not (wrong / "openspec").is_dir()


# --------------------------------------------------------------------------
# the root is injected, never derived
# --------------------------------------------------------------------------


def test_the_producer_takes_its_repository_root_as_a_required_parameter() -> None:
    producer = _module().ExactSearchProducer
    parameters = inspect.signature(producer).parameters
    assert "repository_root" in parameters, (
        "the repository root must be a constructor parameter, not a module constant"
    )
    assert parameters["repository_root"].default is inspect.Parameter.empty, (
        "a default repository root is a derived root wearing a parameter's clothes"
    )


def test_no_producer_module_derives_a_path_from_its_own_location() -> None:
    """No ``__file__`` and no ``parents[...]`` anywhere under ``producers/``.

    Both halves matter. ``__file__`` is the input the archived arithmetic ran on,
    and ``parents[<int>]`` is the arithmetic. Forbidding only the second would
    leave ``Path(__file__).parent.parent.parent`` legal, which is the same defect
    spelled differently.
    """
    modules = sorted(PRODUCERS.rglob("*.py"))
    assert modules, f"no producer modules found under {PRODUCERS}"

    problems: list[str] = []
    for module in modules:
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "__file__":
                problems.append(f"{module.relative_to(REPO_ROOT)}:{node.lineno}: reads __file__")
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == "parents"
            ):
                problems.append(
                    f"{module.relative_to(REPO_ROOT)}:{node.lineno}: indexes .parents"
                )
    assert not problems, "\n".join(problems)


# --------------------------------------------------------------------------
# a root that is not a checkout is loud
# --------------------------------------------------------------------------


def test_a_real_checkout_is_accepted_and_carries_git_and_openspec() -> None:
    module = _module()
    resolved = module.validate_repository_root(REPO_ROOT)
    assert resolved == REPO_ROOT.resolve()
    assert (resolved / ".git").exists(), "a repository root has a .git entry"
    assert (resolved / "openspec").is_dir(), "this repository's root has openspec/"


def test_the_archived_wrong_root_is_rejected_as_an_apparatus_failure() -> None:
    """Feed the producer exactly what ``parents[3]`` produced after archival."""
    module = _module()
    wrong = ARCHIVED_RUNNER.parent.parents[3]
    assert wrong == REPO_ROOT / "openspec"
    with pytest.raises(module.ApparatusError) as caught:
        module.validate_repository_root(wrong)
    assert str(wrong) in str(caught.value), "the rejection must name the root it rejected"


@pytest.mark.parametrize("missing", ["git", "openspec"])
def test_a_root_missing_either_marker_is_rejected(tmp_path: Path, missing: str) -> None:
    module = _module()
    root = tmp_path / "checkout"
    root.mkdir()
    if missing != "git":
        (root / ".git").mkdir()
    if missing != "openspec":
        (root / "openspec").mkdir()
    with pytest.raises(module.ApparatusError):
        module.validate_repository_root(root)


def test_a_git_worktree_whose_dotgit_is_a_file_is_accepted(tmp_path: Path) -> None:
    """``.git`` is a FILE in a linked worktree, and this repository is one.

    An ``is_dir()`` check here would reject every managed worktree — which is
    where every mutating skill in this repository actually runs.
    """
    module = _module()
    root = tmp_path / "worktree"
    root.mkdir()
    (root / ".git").write_text("gitdir: /elsewhere/.git/worktrees/w\n", encoding="utf-8")
    (root / "openspec").mkdir()
    assert module.validate_repository_root(root) == root.resolve()


def test_constructing_a_producer_on_a_bad_root_fails_immediately(tmp_path: Path) -> None:
    """Not at query time. A producer that exists is a producer with a valid root."""
    module = _module()
    with pytest.raises(module.ApparatusError):
        module.ExactSearchProducer(
            repository_root=tmp_path,
            budget=_corpus_budget(),
            searcher=module.TrackedFileSearcher(file_list=()),
        )


def test_a_bad_root_never_degrades_to_an_empty_result(tmp_path: Path) -> None:
    """The archived runner's actual reflex, asserted against.

    ``run_eval.py``'s ``_rg`` caught ``FileNotFoundError`` and returned ``[]``, so
    "ripgrep is not installed" and "nothing matched" were the same measurement.
    An empty ranking is a legitimate answer; it must never be how the harness
    reports that it could not look.
    """
    module = _module()
    searcher = module.RipgrepSearcher(repository_root=tmp_path, executable="rg-does-not-exist")
    with pytest.raises(module.ApparatusError):
        searcher.count_matches("anything")
