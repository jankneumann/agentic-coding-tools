"""Mutation-runner tests for ``test_oracle_audit.mutation`` (tasks 3.4-3.6).

Derived from the "Mutation Runner With Per-Test Kill Attribution" requirement
(spec scenarios test-oracle-audit.24 to .28), the "Read-Only Audit Execution"
requirement (.7), design D3/D4, ``mutation-result.schema.json`` and the
``MutationPayload`` of ``stage-record.schema.json``.

The module under test does not exist yet; these tests define its public API:

    MutantResult(schema fields...).to_json()
    AstMutantRunner / MutmutRunner: .name ("ast" / "mutmut"),
        .probe(copy: IsolatedCopy, suite: SuiteSpec, *, python=None) -> bool
    run_mutation(suite, entries, *, repo_root, max_mutants=400, seed=0,
                 runner=None, python=None) -> (list[MutantResult], list[StageRecord])

``runner=None`` tries ``MutmutRunner`` first and falls back to ``AstMutantRunner``
when its probe fails. ``python=sys.executable`` makes pytest run as
``[python, "-m", "pytest", ...]`` so no uv, mutmut or network is needed.

Fixture ``tests/fixtures/execution/mutation_proj``:

* ``mini.calc``: ``clamp``, ``sign``, ``percent``, ``bucket`` (many candidate mutants) and
  ``is_adult`` (few).
* ``mini.tiny``: ``flag`` (two candidate mutants at most).
* ``test_arithmetic_strong`` asserts exact values for clamp/sign/percent;
  ``test_arithmetic_not_none_only`` calls the same functions but only asserts
  ``is not None``; ``test_is_adult_boundary`` covers only ``is_adult``;
  ``test_flag_is_true`` covers only ``flag``.
"""

from __future__ import annotations

import ast
import contextlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from test_oracle_audit.isolation import IsolatedCopy, isolated_copy
from test_oracle_audit.mutation import AstMutantRunner, MutantResult, MutmutRunner, run_mutation

from test_oracle_audit import mutation
from test_oracle_audit.records import StageRecord, SuiteSpec, TestEntry, TestId, content_hash

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "execution"
PROJECT = "mutation_proj"

STRONG = "tests/test_calc.py::test_arithmetic_strong"
WEAK = "tests/test_calc.py::test_arithmetic_not_none_only"
ADULT = "tests/test_calc.py::test_is_adult_boundary"
FLAG = "tests/test_tiny.py::test_flag_is_true"

COVERED_MODULES = {
    "test_arithmetic_strong": ("mini.calc",),
    "test_arithmetic_not_none_only": ("mini.calc",),
    "test_is_adult_boundary": ("mini.calc",),
    "test_flag_is_true": ("mini.tiny",),
}

MIN_COVERING_MUTANTS = 5

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin"),
}


# --- helpers ---------------------------------------------------------------


def _git(cwd: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={**_GIT_ENV, "HOME": str(cwd)},
    )
    return out.stdout


def _make_repo(dest: Path) -> Path:
    shutil.copytree(
        FIXTURES / PROJECT,
        dest,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
    )
    _git(dest, "init", "-q", "-b", "main")
    _git(dest, "add", "-A")
    _git(dest, "commit", "-q", "-m", "fixture: initial commit")
    return dest


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and ".git" not in p.relative_to(root).parts
    }


def _worktree_count(repo: Path) -> int:
    listing = _git(repo, "worktree", "list", "--porcelain")
    return sum(1 for line in listing.splitlines() if line.startswith("worktree "))


def _suite() -> SuiteSpec:
    return SuiteSpec(
        name=PROJECT,
        project_root=".",
        test_paths=("tests",),
        source_roots=("src/mini",),
        pytest_args=("-p", "no:cacheprovider"),
    )


def _entries(repo: Path) -> list[TestEntry]:
    entries: list[TestEntry] = []
    for rel in ("tests/test_calc.py", "tests/test_tiny.py"):
        source = (repo / rel).read_text("utf-8")
        for node in ast.parse(source).body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                entries.append(
                    TestEntry(
                        test_id=TestId(f"{rel}::{node.name}", content_hash(source, node.name)),
                        path=rel,
                        line_start=node.lineno,
                        line_end=node.end_lineno or node.lineno,
                        function_name=node.name,
                        covered_modules=COVERED_MODULES[node.name],
                    )
                )
    return entries


def _json(results: list[MutantResult]) -> list[dict[str, Any]]:
    return [r.to_json() for r in results]


def _module_key(result: dict[str, Any]) -> str:
    for key in ("calc", "tiny"):
        if key in result["module"]:
            return key
    raise AssertionError(f"unexpected module {result['module']!r}")


def _by_test(records: list[StageRecord]) -> dict[str, StageRecord]:
    return {r.test_id.node_id: r for r in records}


@dataclass
class World:
    repo: Path
    suite: SuiteSpec
    entries: list[TestEntry]
    before: dict[str, bytes]
    full_results: list[MutantResult]
    full_records: list[StageRecord]
    leftover: list[Path]
    sample_a: tuple[list[MutantResult], list[StageRecord]]
    sample_b: tuple[list[MutantResult], list[StageRecord]]


SAMPLE_SEED = 7
SAMPLE_SIZE = 6


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> World:
    """One full AST run plus two identically-seeded sampled runs, shared by the module."""
    base = tmp_path_factory.mktemp("mutation")
    repo = _make_repo(base / "repo")
    scratch = base / "systmp"
    scratch.mkdir()
    suite = _suite()
    entries = _entries(repo)
    before = _snapshot(repo)
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TMPDIR", str(scratch))
        mp.setattr(tempfile, "tempdir", str(scratch))
        kwargs: dict[str, Any] = {"repo_root": repo, "runner": AstMutantRunner(), "python": sys.executable}
        full = run_mutation(suite, entries, **kwargs)
        a = run_mutation(suite, entries, max_mutants=SAMPLE_SIZE, seed=SAMPLE_SEED, **kwargs)
        b = run_mutation(suite, entries, max_mutants=SAMPLE_SIZE, seed=SAMPLE_SEED, **kwargs)
    return World(
        repo=repo,
        suite=suite,
        entries=entries,
        before=before,
        full_results=full[0],
        full_records=full[1],
        leftover=list(scratch.iterdir()),
        sample_a=a,
        sample_b=b,
    )


# --- result shape and schema (contract) -------------------------------------


def test_mutant_result_serialises_to_the_schema(schema_validator: Callable[..., None]) -> None:
    """test-oracle-audit.24: a MutantResult carries the schema fields and ``to_json`` validates."""
    result = MutantResult(
        mutant_id="mini.calc.clamp:0",
        backend="ast",
        module="mini.calc",
        function="clamp",
        operator="comparison_flip",
        covered_by=["tests/test_calc.py::a", "tests/test_calc.py::b"],
        killed_by=["tests/test_calc.py::a"],
        status="killed",
        seed=3,
    )
    data = result.to_json()
    schema_validator(data, "mutation-result")
    assert data["schema_version"] == 1
    assert list(data["covered_by"]) == ["tests/test_calc.py::a", "tests/test_calc.py::b"]
    assert list(data["killed_by"]) == ["tests/test_calc.py::a"]
    assert data["seed"] == 3


def test_runner_names_identify_the_backend() -> None:
    """test-oracle-audit.27: each backend reports the name that is recorded on results."""
    assert AstMutantRunner().name == "ast"
    assert MutmutRunner().name == "mutmut"


def test_every_result_validates_and_records_its_backend_and_seed(
    world: World, schema_validator: Callable[..., None]
) -> None:
    """test-oracle-audit.24, .27: results are schema-valid, name the backend, and carry the seed."""
    assert world.full_results, "the fixture has mutable code, so the full run must yield mutants"
    for data in _json(world.full_results):
        schema_validator(data, "mutation-result")
        assert data["backend"] == "ast"
        assert data["seed"] == 0
    ids = [d["mutant_id"] for d in _json(world.full_results)]
    assert len(ids) == len(set(ids)), "mutant ids must be unique"


# --- kill attribution (scenario .24) ----------------------------------------


def test_kill_is_attributed_to_the_failing_test_only(world: World) -> None:
    """test-oracle-audit.24: a mutant covered by A and B that only A fails lists A and B in
    ``covered_by`` and only A in ``killed_by``."""
    attributed = [
        d
        for d in _json(world.full_results)
        if STRONG in d["covered_by"]
        and WEAK in d["covered_by"]
        and STRONG in d["killed_by"]
        and WEAK not in d["killed_by"]
    ]
    assert attributed, "some mutant must be killed by the strong test while the weak test also covers it"
    for d in attributed:
        assert d["status"] == "killed"
        assert set(d["killed_by"]) < set(d["covered_by"])


def test_killed_by_is_always_a_subset_of_covered_by(world: World) -> None:
    """test-oracle-audit.24: a test cannot kill a mutant it does not cover."""
    for d in _json(world.full_results):
        assert set(d["killed_by"]) <= set(d["covered_by"]), d


def test_status_agrees_with_the_attribution_lists(world: World) -> None:
    """test-oracle-audit.24: ``killed`` means somebody killed it, ``survived`` means covered but nobody did."""
    for d in _json(world.full_results):
        if d["status"] == "killed":
            assert d["killed_by"], d
        if d["status"] == "survived":
            assert d["covered_by"] and not d["killed_by"], d
        if d["status"] == "no_coverage":
            assert not d["covered_by"] and not d["killed_by"], d


def test_the_assertion_poor_test_never_outkills_the_strong_one(world: World) -> None:
    """test-oracle-audit.24: killing is counted per test, so a test with only ``is not None``
    checks kills strictly fewer of the shared mutants than the strong one."""
    data = _json(world.full_results)
    strong_kills = sum(STRONG in d["killed_by"] for d in data)
    weak_kills = sum(WEAK in d["killed_by"] for d in data)
    assert strong_kills > 0
    assert weak_kills < strong_kills


def test_covered_by_follows_the_functions_a_test_calls(world: World) -> None:
    """test-oracle-audit.24: coverage is per function, not per module.

    ``test_is_adult_boundary`` imports ``mini.calc`` but only calls ``is_adult``, so it must
    not be listed against mutants of ``clamp``, ``sign``, ``percent`` or ``bucket`` (and vice versa).
    """
    data = _json(world.full_results)
    in_is_adult = [d for d in data if d["function"] == "is_adult"]
    in_arith = [d for d in data if d["function"] in {"clamp", "sign", "percent", "bucket"}]
    in_flag = [d for d in data if d["function"] == "flag"]
    assert in_is_adult and in_arith and in_flag
    for d in in_is_adult:
        assert set(d["covered_by"]) == {ADULT}, d
    for d in in_arith:
        assert set(d["covered_by"]) == {STRONG, WEAK}, d
    for d in in_flag:
        assert set(d["covered_by"]) == {FLAG}, d


def test_results_do_not_cover_tests_outside_the_entry_list(world: World) -> None:
    """test-oracle-audit.24: attribution uses the audited tests' node ids."""
    known = {e.test_id.node_id for e in world.entries}
    for d in _json(world.full_results):
        assert set(d["covered_by"]) <= known


# --- per-test payload and `insufficient` (scenario .28) ----------------------


def test_one_mutation_record_per_test(world: World, schema_validator: Callable[..., None]) -> None:
    """test-oracle-audit.28: every inventoried test gets exactly one schema-valid ``mutation`` record."""
    assert {r.test_id for r in world.full_records} == {e.test_id for e in world.entries}
    assert len(world.full_records) == len(world.entries)
    for record in world.full_records:
        assert record.stage == "mutation"
        assert record.status == "ok"
        assert record.evidence_class == "execution"
        schema_validator(record.to_json())
        assert record.payload["backend"] == "ast"


def test_test_covering_fewer_than_five_mutants_is_insufficient(world: World) -> None:
    """test-oracle-audit.28: tests that only reach a handful of mutants report ``insufficient``."""
    records = _by_test(world.full_records)
    for node_id in (ADULT, FLAG):
        payload = records[node_id].payload
        assert 0 < payload["covering_mutants"] < MIN_COVERING_MUTANTS, payload
        assert payload["kill_rate"] == "insufficient", payload


def test_test_covering_enough_mutants_gets_a_numeric_kill_rate(world: World) -> None:
    """test-oracle-audit.28: with at least five covering mutants the rate is killed / covering."""
    records = _by_test(world.full_records)
    for node_id in (STRONG, WEAK):
        payload = records[node_id].payload
        assert payload["covering_mutants"] >= MIN_COVERING_MUTANTS, payload
        rate = payload["kill_rate"]
        assert isinstance(rate, int | float) and not isinstance(rate, bool)
        assert rate == pytest.approx(payload["killed_mutants"] / payload["covering_mutants"])
    strong, weak = records[STRONG].payload, records[WEAK].payload
    assert strong["killed_mutants"] > weak["killed_mutants"]
    assert strong["kill_rate"] > weak["kill_rate"]


@pytest.mark.parametrize("which", ["full", "sample"])
def test_payload_counts_are_derived_from_the_mutant_results(world: World, which: str) -> None:
    """test-oracle-audit.24, .28: covering/killed counts equal the number of mutants listing the test,
    and ``insufficient`` is reported exactly when fewer than five mutants cover it."""
    results, records = (world.full_results, world.full_records) if which == "full" else world.sample_a
    data = _json(results)
    for record in records:
        node_id = record.test_id.node_id
        covering = sum(node_id in d["covered_by"] for d in data)
        killed = sum(node_id in d["killed_by"] for d in data)
        payload = record.payload
        assert payload["covering_mutants"] == covering, node_id
        assert payload["killed_mutants"] == killed, node_id
        if covering < MIN_COVERING_MUTANTS:
            assert payload["kill_rate"] == "insufficient", node_id
        else:
            assert payload["kill_rate"] == pytest.approx(killed / covering), node_id


# --- bounded, seeded, stratified sampling (scenarios .25, .26) ---------------


def test_sample_respects_the_mutant_bound(world: World) -> None:
    """test-oracle-audit.25 (bounds): ``max_mutants`` caps the number of mutants run."""
    sampled = _json(world.sample_a[0])
    assert 0 < len(sampled) <= SAMPLE_SIZE
    assert len(sampled) < len(world.full_results)


def test_seeded_sampling_is_reproducible(world: World) -> None:
    """test-oracle-audit.25: the same seed and max-mutants select the same mutant ids."""
    ids_a = sorted(d["mutant_id"] for d in _json(world.sample_a[0]))
    ids_b = sorted(d["mutant_id"] for d in _json(world.sample_b[0]))
    assert ids_a == ids_b
    assert {d["seed"] for d in _json(world.sample_a[0])} == {SAMPLE_SEED}


def test_sampled_mutants_come_from_the_full_candidate_set(world: World) -> None:
    """test-oracle-audit.25: sampling picks candidates, it does not invent mutant ids."""
    full_ids = {d["mutant_id"] for d in _json(world.full_results)}
    assert {d["mutant_id"] for d in _json(world.sample_a[0])} <= full_ids


def test_sampling_is_spread_across_modules(world: World) -> None:
    """test-oracle-audit.26: with one module having ten times the candidates of another, both
    appear in a sample that is smaller than the candidate total."""
    full = _json(world.full_results)
    n_calc = sum(_module_key(d) == "calc" for d in full)
    n_tiny = sum(_module_key(d) == "tiny" for d in full)
    assert n_tiny >= 1, "fixture premise: the small module has candidates"
    assert n_calc >= 10 * n_tiny, f"fixture premise: calc={n_calc} vs tiny={n_tiny}"
    sampled = _json(world.sample_a[0])
    assert len(sampled) < len(full)
    assert {_module_key(d) for d in sampled} == {"calc", "tiny"}


def test_sampling_is_spread_across_modules_for_every_seed(world: World, tmp_path: Path) -> None:
    """test-oracle-audit.26: stratification does not depend on a lucky seed."""
    repo = _make_repo(tmp_path / "repo")
    for seed in (1, 2):
        results, _ = run_mutation(
            world.suite,
            _entries(repo),
            repo_root=repo,
            max_mutants=SAMPLE_SIZE,
            seed=seed,
            runner=AstMutantRunner(),
            python=sys.executable,
        )
        assert {_module_key(d) for d in _json(results)} == {"calc", "tiny"}, seed


# --- backend selection and fallback (scenario .27) ---------------------------


def test_ast_probe_succeeds_on_the_fixture_suite(world: World, tmp_path: Path) -> None:
    """test-oracle-audit.27: the dependency-free backend can always run the fixture suite."""
    with isolated_copy(world.repo, scratch_root=tmp_path / "scratch") as copy:
        assert AstMutantRunner().probe(copy, world.suite, python=sys.executable) is True


def test_mutmut_probe_returns_a_bool_and_never_raises(world: World, tmp_path: Path) -> None:
    """test-oracle-audit.27: an unavailable mutmut is reported through the probe, not an exception."""
    with isolated_copy(world.repo, scratch_root=tmp_path / "scratch") as copy:
        verdict = MutmutRunner().probe(copy, world.suite, python=sys.executable)
    assert isinstance(verdict, bool)
    if importlib.util.find_spec("mutmut") is None:
        assert verdict is False


def test_ast_backend_runs_when_the_mutmut_probe_fails(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    """test-oracle-audit.27: with ``runner=None`` a failing mutmut probe falls back to AST and every
    result and record says ``ast``."""
    probes: list[tuple[bool, SuiteSpec]] = []

    def failing_probe(self: Any, copy: IsolatedCopy, suite: SuiteSpec, *, python: str | None = None) -> bool:
        probes.append((copy.root.is_dir(), suite))
        return False

    monkeypatch.setattr(MutmutRunner, "probe", failing_probe)
    results, records = run_mutation(
        world.suite,
        world.entries,
        repo_root=world.repo,
        max_mutants=4,
        seed=1,
        runner=None,
        python=sys.executable,
    )
    assert probes == [(True, world.suite)], "mutmut must be probed once, inside an isolated copy"
    assert results, "the fallback backend must still produce mutants"
    assert {d["backend"] for d in _json(results)} == {"ast"}
    assert records and {r.payload["backend"] for r in records} == {"ast"}


def test_no_backend_available_degrades_instead_of_raising(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """test-oracle-audit.27 and D1 ("No stage raises on unavailable dependencies"): when neither
    probe passes, every test gets a ``degraded`` record with reason ``no_backend``."""

    def failing_probe(self: Any, copy: IsolatedCopy, suite: SuiteSpec, *, python: str | None = None) -> bool:
        return False

    monkeypatch.setattr(MutmutRunner, "probe", failing_probe)
    monkeypatch.setattr(AstMutantRunner, "probe", failing_probe)
    results, records = run_mutation(
        world.suite, world.entries, repo_root=world.repo, runner=None, python=sys.executable
    )
    assert list(results) == []
    assert len(records) == len(world.entries)
    assert {(r.status, r.reason) for r in records} == {("degraded", "no_backend")}


# --- read-only execution (scenarios .6, .7) ----------------------------------


def test_the_audited_tree_is_untouched_by_the_full_run(world: World) -> None:
    """test-oracle-audit.6: mutating source in the copy never changes the audited tree."""
    assert _snapshot(world.repo) == world.before
    assert _git(world.repo, "status", "--porcelain") == ""


def test_the_stage_leaves_no_copy_or_worktree_behind(world: World) -> None:
    """test-oracle-audit.7: after the stage returns, the scratch location is empty and
    ``git worktree`` knows only the main checkout."""
    assert world.leftover == []
    assert _worktree_count(world.repo) == 1


class _ExplodingRunner:
    name = "ast"

    def probe(self, copy: IsolatedCopy, suite: SuiteSpec, *, python: str | None = None) -> bool:
        assert copy.root.is_dir()
        raise RuntimeError("probe exploded midway")


def _scratch_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    scratch = tmp_path / "systmp"
    scratch.mkdir()
    monkeypatch.setenv("TMPDIR", str(scratch))
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    return scratch


def test_copy_is_removed_when_the_mutation_stage_raises_midway(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """test-oracle-audit.7: a mutation stage that raises midway leaves no isolated copy."""
    repo = _make_repo(tmp_path / "repo")
    scratch = _scratch_env(tmp_path, monkeypatch)
    before = _snapshot(repo)
    with contextlib.suppress(Exception):  # the stage may raise or degrade; both are allowed
        run_mutation(
            _suite(), _entries(repo), repo_root=repo, runner=_ExplodingRunner(), python=sys.executable
        )
    assert list(scratch.iterdir()) == []
    assert _worktree_count(repo) == 1
    assert _snapshot(repo) == before


def test_copy_is_removed_when_the_test_interpreter_cannot_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """test-oracle-audit.7: a stage whose test runs cannot even start still cleans up."""
    repo = _make_repo(tmp_path / "repo")
    scratch = _scratch_env(tmp_path, monkeypatch)
    with contextlib.suppress(Exception):  # the stage may raise or degrade; both are allowed
        run_mutation(
            _suite(),
            _entries(repo),
            repo_root=repo,
            max_mutants=2,
            runner=AstMutantRunner(),
            python=str(tmp_path / "no-such-python"),
        )
    assert list(scratch.iterdir()) == []
    assert _worktree_count(repo) == 1
    assert _git(repo, "status", "--porcelain") == ""


def test_mutation_module_exposes_the_runner_interface() -> None:
    """test-oracle-audit.24 (public contract reused by ri-07): the module exports the runner types."""
    for name in ("MutantResult", "AstMutantRunner", "MutmutRunner", "run_mutation"):
        assert hasattr(mutation, name), name
