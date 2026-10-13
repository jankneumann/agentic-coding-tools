"""Mutation stage with per-test kill attribution (design D4, spec "Mutation Runner ...").

``run_mutation`` works inside an :func:`isolated_copy` that is always removed. A
backend (``MutationRunner``) is chosen by probing: ``MutmutRunner`` first, then
``AstMutantRunner`` when that probe fails (spike 3.1: mutmut relocates sources and
tests into ``mutants/`` and its baseline fails for suites that read repo-relative
files, so the AST runner is the expected backend for the pilot suites).

``AstMutantRunner`` needs no third-party packages:

1. one *baseline* run of the audited tests records each test's outcome and the source
   functions it calls (a ``sys.monitoring`` pytest plugin, see :mod:`isolation`);
   tests that do not pass at baseline cannot attribute kills and are reported
   ``degraded``;
2. candidate mutants (comparison flip, boolean negate, constant perturbation,
   ``return`` -> ``return None``) are enumerated from the suite's source roots, then
   sampled with a seeded, module-stratified round robin among mutants whose function
   some passing test calls (uncovered candidates only fill a budget the covered ones
   leave over, as ``no_coverage`` results);
3. each sampled mutant is written into the copy and the covering tests run once;
   a covering test that fails (or whose file no longer collects) *killed* the mutant.

Per-test payload: ``covering_mutants`` / ``killed_mutants`` count mutants in the
sample, and ``kill_rate`` is their ratio, or ``"insufficient"`` below five covering
mutants.
"""

from __future__ import annotations

import ast
import os
import random
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from test_oracle_audit.isolation import (
    IsolatedCopy,
    SuiteRun,
    can_collect,
    dotted_module,
    isolated_copy,
    pytest_launcher,
    run_command,
    run_environment,
    run_suite,
    source_files,
)
from test_oracle_audit.records import SCHEMA_VERSION, StageRecord, SuiteSpec, TestEntry

MIN_COVERING_MUTANTS = 5
DEFAULT_MAX_MUTANTS = 400
MIN_MUTANT_TIMEOUT_SECONDS = 60.0
MUTANT_TIMEOUT_FACTOR = 10.0


# --- result type (schemas/mutation-result.schema.json) ---------------------------


@dataclass(frozen=True)
class MutantResult:
    """One line of ``mutants.jsonl``; the public contract reused by ri-07 (design D4)."""

    mutant_id: str
    backend: str
    module: str
    function: str
    operator: str
    covered_by: list[str] = field(default_factory=list)
    killed_by: list[str] = field(default_factory=list)
    status: str = "survived"
    seed: int = 0

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "mutant_id": self.mutant_id,
            "backend": self.backend,
            "module": self.module,
            "function": self.function,
            "operator": self.operator,
            "covered_by": list(self.covered_by),
            "killed_by": list(self.killed_by),
            "status": self.status,
            "seed": self.seed,
        }


class BackendUnavailable(RuntimeError):
    """A backend passed its probe but cannot produce results; the next backend is tried."""


@dataclass
class RunOutcome:
    """What a backend returns: sampled results plus tests that cannot be attributed."""

    results: list[MutantResult]
    unusable: dict[str, str] = field(default_factory=dict)  # node id -> degraded reason


class MutationRunner(Protocol):
    """A mutation backend (design D4). ``probe`` must return False rather than raise."""

    name: str

    def probe(self, copy: IsolatedCopy, suite: SuiteSpec, *, python: str | None = None) -> bool: ...

    def run(
        self,
        copy: IsolatedCopy,
        suite: SuiteSpec,
        entries: Sequence[TestEntry],
        *,
        max_mutants: int,
        seed: int,
        python: str | None = None,
    ) -> RunOutcome: ...


# --- AST mutation operators --------------------------------------------------------

_COMPARE_FLIP: dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Lt: ast.GtE,
    ast.LtE: ast.Gt,
    ast.Gt: ast.LtE,
    ast.GtE: ast.Lt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
}


@dataclass(frozen=True)
class _Site:
    qualname: str
    ordinal: int
    operator: str
    lineno: int


class _SiteMutator(ast.NodeTransformer):
    """Enumerates mutation sites inside function bodies; applies the one named by ``target``.

    A site belongs to its *outermost* enclosing function (``Class.method`` for methods), the
    unit at which coverage is attributed. Decorators, defaults and annotations are not mutated.
    Enumeration (``target=None``) and application share one traversal, so ordinals agree.
    """

    def __init__(self, target: tuple[str, int] | None = None) -> None:
        self.target = target
        self.sites: list[_Site] = []
        self.applied = False
        self._classes: list[str] = []
        self._function: str | None = None
        self._counts: dict[str, int] = {}

    def _hit(self, operator: str, node: ast.AST) -> bool:
        assert self._function is not None
        ordinal = self._counts.get(self._function, 0)
        self._counts[self._function] = ordinal + 1
        self.sites.append(_Site(self._function, ordinal, operator, getattr(node, "lineno", 0)))
        chosen = self.target == (self._function, ordinal)
        self.applied = self.applied or chosen
        return chosen

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        if self._function is not None:
            return self.generic_visit(node)
        self._classes.append(node.name)
        try:
            return self.generic_visit(node)
        finally:
            self._classes.pop()

    def _visit_function(self, node: Any) -> ast.AST:
        if self._function is not None:
            return self.generic_visit(node)
        self._function = ".".join([*self._classes, node.name])
        try:
            node.body = [self.visit(statement) for statement in node.body]
        finally:
            self._function = None
        return node

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        if self._function is not None:
            for index, op in enumerate(node.ops):
                flipped = _COMPARE_FLIP.get(type(op))
                if flipped is not None and self._hit("comparison_flip", node):
                    node.ops[index] = flipped()
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if self._function is None:
            return node
        if isinstance(node.value, bool):
            if self._hit("boolean_negate", node):
                return ast.copy_location(ast.Constant(value=not node.value), node)
        elif isinstance(node.value, int | float) and self._hit("constant_perturb", node):
            return ast.copy_location(ast.Constant(value=node.value + 1), node)
        return node

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:
        self.generic_visit(node)
        if self._function is not None and isinstance(node.op, ast.Not) and self._hit("boolean_negate", node):
            return node.operand
        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        self.generic_visit(node)
        if self._function is not None and self._hit("boolean_negate", node):
            node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        return node

    def visit_Return(self, node: ast.Return) -> ast.AST:
        self.generic_visit(node)
        returns_none = node.value is None or (
            isinstance(node.value, ast.Constant) and node.value.value is None
        )
        if self._function is not None and not returns_none and self._hit("return_none", node):
            node.value = ast.copy_location(ast.Constant(value=None), node.value)
        return node


def _mutated_source(text: str, qualname: str, ordinal: int) -> str | None:
    tree = ast.parse(text)
    mutator = _SiteMutator((qualname, ordinal))
    mutator.visit(tree)
    return ast.unparse(tree) if mutator.applied else None


@dataclass(frozen=True)
class _Candidate:
    index: int
    mutant_id: str
    module: str
    file: str  # repo-relative, posix
    qualname: str
    ordinal: int
    operator: str


def _candidates(root: Path, suite: SuiteSpec) -> list[_Candidate]:
    found: list[_Candidate] = []
    for path in source_files(root, suite):
        try:
            tree = ast.parse(path.read_text("utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        mutator = _SiteMutator()
        mutator.visit(tree)
        module = dotted_module(path, root)
        rel = path.relative_to(root).as_posix()
        for site in mutator.sites:
            found.append(
                _Candidate(
                    index=len(found),
                    mutant_id=f"{module}.{site.qualname}:{site.ordinal}",
                    module=module,
                    file=rel,
                    qualname=site.qualname,
                    ordinal=site.ordinal,
                    operator=site.operator,
                )
            )
    return found


def _stratified_sample(pool: Sequence[_Candidate], limit: int, seed: int) -> list[_Candidate]:
    """Seeded round robin over modules: no module can take the whole budget (spec .26)."""
    if limit <= 0 or not pool:
        return []
    rng = random.Random(seed)
    by_module: dict[str, list[_Candidate]] = {}
    for candidate in pool:
        by_module.setdefault(candidate.module, []).append(candidate)
    queues = []
    for module in sorted(by_module):
        members = by_module[module]
        rng.shuffle(members)
        queues.append(deque(members))
    picked: list[_Candidate] = []
    while len(picked) < limit and any(queues):
        for queue in queues:
            if queue and len(picked) < limit:
                picked.append(queue.popleft())
    return picked


# --- backends -------------------------------------------------------------------------


class AstMutantRunner:
    """Dependency-free backend: mutates files in the full isolated repo copy (design D4)."""

    name = "ast"

    def probe(self, copy: IsolatedCopy, suite: SuiteSpec, *, python: str | None = None) -> bool:
        try:
            return can_collect(copy, suite, python=python)
        except OSError:
            return False

    def run(
        self,
        copy: IsolatedCopy,
        suite: SuiteSpec,
        entries: Sequence[TestEntry],
        *,
        max_mutants: int,
        seed: int,
        python: str | None = None,
    ) -> RunOutcome:
        node_ids = [e.test_id.node_id for e in entries]
        try:
            baseline = run_suite(copy, suite, python=python, node_ids=node_ids, trace=True)
        except OSError:
            return RunOutcome([], {nid: "baseline_run_failed" for nid in node_ids})
        if baseline.timed_out or not baseline.results_found:
            reason = "baseline_timeout" if baseline.timed_out else "baseline_run_failed"
            return RunOutcome([], {nid: reason for nid in node_ids})
        if baseline.tracer != "monitoring":
            return RunOutcome([], {nid: "no_function_coverage" for nid in node_ids})

        unusable: dict[str, str] = {}
        passing: set[str] = set()
        for nid in node_ids:
            outcome = baseline.outcomes.get(nid)
            if outcome == "passed":
                passing.add(nid)
            elif outcome == "failed":
                unusable[nid] = "baseline_failed"
            elif outcome is None:
                unusable[nid] = "not_run"

        covering = _FunctionIndex(baseline, passing)
        candidates = _candidates(copy.root, suite)
        covered = [c for c in candidates if covering.tests_for(c.file, c.qualname)]
        uncovered = [c for c in candidates if not covering.tests_for(c.file, c.qualname)]
        sample = _stratified_sample(covered, max_mutants, seed)
        sample += _stratified_sample(uncovered, max_mutants - len(sample), seed)
        sample.sort(key=lambda c: c.index)

        timeout = max(MIN_MUTANT_TIMEOUT_SECONDS, MUTANT_TIMEOUT_FACTOR * baseline.seconds)
        originals: dict[str, str] = {}
        results = [
            self._run_one(
                copy, suite, c, covering.tests_for(c.file, c.qualname), seed, python, timeout, originals
            )
            for c in sample
        ]
        return RunOutcome(results, unusable)

    def _run_one(
        self,
        copy: IsolatedCopy,
        suite: SuiteSpec,
        candidate: _Candidate,
        tests: list[str],
        seed: int,
        python: str | None,
        timeout: float,
        originals: dict[str, str],
    ) -> MutantResult:
        def result(status: str, killed: list[str] | None = None) -> MutantResult:
            return MutantResult(
                mutant_id=candidate.mutant_id,
                backend=self.name,
                module=candidate.module,
                function=candidate.qualname,
                operator=candidate.operator,
                covered_by=tests,
                killed_by=killed or [],
                status=status,
                seed=seed,
            )

        if not tests:
            return result("no_coverage")
        path = copy.root / candidate.file
        original = originals.setdefault(candidate.file, path.read_text("utf-8"))
        mutated = _mutated_source(original, candidate.qualname, candidate.ordinal)
        if mutated is None:
            return result("error")
        path.write_text(mutated, encoding="utf-8")
        try:
            run = run_suite(copy, suite, python=python, node_ids=tests, timeout=timeout)
        except OSError:
            return result("error")
        finally:
            path.write_text(original, encoding="utf-8")
        if run.timed_out:
            return result("timeout")
        if not run.results_found:
            return result("error")
        killed = [t for t in tests if _killed(t, run)]
        return result("killed" if killed else "survived", killed)


def _killed(node_id: str, run: SuiteRun) -> bool:
    """A test killed the mutant when it failed, or when its file no longer collects."""
    return run.outcomes.get(node_id) == "failed" or node_id.split("::", 1)[0] in run.collect_errors


class _FunctionIndex:
    """Which passing tests called which source function (a function's nested code included)."""

    def __init__(self, baseline: SuiteRun, passing: set[str]) -> None:
        self._by_file: dict[str, dict[str, set[str]]] = {}
        for node_id, calls in baseline.coverage.items():
            if node_id not in passing:
                continue
            for file, qualname in calls:
                self._by_file.setdefault(file, {}).setdefault(qualname, set()).add(node_id)
        self._cache: dict[tuple[str, str], list[str]] = {}

    def tests_for(self, file: str, function: str) -> list[str]:
        key = (file, function)
        if key not in self._cache:
            tests: set[str] = set()
            for qualname, node_ids in self._by_file.get(file, {}).items():
                if qualname == function or qualname.startswith(function + "."):
                    tests |= node_ids
            self._cache[key] = sorted(tests)
        return self._cache[key]


class MutmutRunner:
    """mutmut 3.x backend (design D4). ``probe`` is mutmut's own baseline stats run.

    Only the probe is implemented: the pilot suites fail mutmut's relocated baseline
    (spike 3.1), and attributing kills per test through mutmut's trampolines is not
    built. A passing probe whose ``run`` raises :class:`BackendUnavailable` makes
    ``run_mutation`` fall back to the AST backend, which records ``backend: ast``.
    """

    name = "mutmut"
    probe_timeout_seconds = 900.0
    _OVERLAY = ("pytest-cov", "mutmut>=3.8,<4")

    def probe(self, copy: IsolatedCopy, suite: SuiteSpec, *, python: str | None = None) -> bool:
        try:
            return self._probe(copy, suite, python)
        except Exception:  # noqa: BLE001 - an unavailable backend is a False verdict, never an error
            return False

    def _launcher(self, copy: IsolatedCopy, suite: SuiteSpec, python: str | None) -> list[str]:
        if python is not None:
            return [python, "-m", "mutmut"]
        return [*pytest_launcher(copy, suite, python=None, overlay=self._OVERLAY)[:-1], "mutmut"]

    def _probe(self, copy: IsolatedCopy, suite: SuiteSpec, python: str | None) -> bool:
        project = (copy.root / suite.project_root).resolve()
        env = run_environment(copy, python=python)
        if python is not None:
            code, _ = run_command([python, "-c", "import mutmut"], cwd=project, env=env, timeout=120)
            if code != 0:
                return False
        self._write_config(project, copy.root, suite)
        argv = [
            *self._launcher(copy, suite, python),
            "run",
            "--max-children",
            "1",
            "probe.nonexistent__mutmut_1",
        ]
        code, output = run_command(argv, cwd=project, env=env, timeout=self.probe_timeout_seconds)
        failed = "failed to collect stats" in output or "Stopping early" in output
        return code == 0 and not failed

    @staticmethod
    def _write_config(project: Path, root: Path, suite: SuiteSpec) -> None:
        def rel(path: str) -> str:
            return os.path.relpath((root / path).resolve(), project).replace(os.sep, "/")

        pyproject = project / "pyproject.toml"
        text = pyproject.read_text("utf-8") if pyproject.is_file() else ""
        if "[tool.mutmut]" in text:
            return
        sources = ", ".join(f'"{rel(p)}"' for p in suite.source_roots)
        tests = ", ".join(f'"{rel(p)}"' for p in suite.test_paths)
        section = (
            f"\n[tool.mutmut]\nsource_paths = [{sources}]\npytest_add_cli_args_test_selection = [{tests}]\n"
        )
        pyproject.write_text(text + section, encoding="utf-8")

    def run(
        self,
        copy: IsolatedCopy,
        suite: SuiteSpec,
        entries: Sequence[TestEntry],
        *,
        max_mutants: int,
        seed: int,
        python: str | None = None,
    ) -> RunOutcome:
        raise BackendUnavailable("per-test kill attribution through mutmut is not implemented")


# --- stage entry point ----------------------------------------------------------------


def _probe(
    runner: MutationRunner, copy: IsolatedCopy, suite: SuiteSpec, python: str | None, notes: list[str]
) -> bool:
    try:
        return bool(runner.probe(copy, suite, python=python))
    except Exception as exc:  # noqa: BLE001 - no stage raises on unavailable dependencies (D1)
        notes.append(f"{runner.name} probe raised {type(exc).__name__}: {exc}")
        return False


def _rate(covering: int, killed: int) -> float | str:
    return killed / covering if covering >= MIN_COVERING_MUTANTS else "insufficient"


def _records(entries: Sequence[TestEntry], outcome: RunOutcome, backend: str) -> list[StageRecord]:
    covering: dict[str, int] = {}
    killed: dict[str, int] = {}
    for result in outcome.results:
        for node_id in result.covered_by:
            covering[node_id] = covering.get(node_id, 0) + 1
        for node_id in result.killed_by:
            killed[node_id] = killed.get(node_id, 0) + 1
    records = []
    for entry in entries:
        node_id = entry.test_id.node_id
        if node_id in outcome.unusable:
            records.append(
                StageRecord(
                    test_id=entry.test_id,
                    stage="mutation",
                    status="degraded",
                    reason=outcome.unusable[node_id],
                    payload={"backend": backend},
                )
            )
            continue
        n_covering, n_killed = covering.get(node_id, 0), killed.get(node_id, 0)
        records.append(
            StageRecord(
                test_id=entry.test_id,
                stage="mutation",
                status="ok",
                payload={
                    "backend": backend,
                    "covering_mutants": n_covering,
                    "killed_mutants": n_killed,
                    "kill_rate": _rate(n_covering, n_killed),
                },
            )
        )
    return records


def run_mutation(
    suite: SuiteSpec,
    entries: Sequence[TestEntry],
    *,
    repo_root: Path,
    max_mutants: int = DEFAULT_MAX_MUTANTS,
    seed: int = 0,
    runner: MutationRunner | None = None,
    python: str | None = None,
) -> tuple[list[MutantResult], list[StageRecord]]:
    """Mutation results and one ``mutation`` record per entry.

    ``runner=None`` probes :class:`MutmutRunner` and falls back to :class:`AstMutantRunner`.
    When no backend can run, every entry gets a ``degraded`` / ``no_backend`` record and no
    result is produced. The audited tree is never touched: all work happens in an isolated
    copy that is removed on every exit path.
    """
    entries = list(entries)
    candidates: list[MutationRunner] = [runner] if runner is not None else [MutmutRunner(), AstMutantRunner()]
    notes: list[str] = []
    with isolated_copy(Path(repo_root)) as copy:
        for backend in candidates:
            if not _probe(backend, copy, suite, python, notes):
                continue
            try:
                outcome = backend.run(copy, suite, entries, max_mutants=max_mutants, seed=seed, python=python)
            except BackendUnavailable as exc:
                notes.append(f"{backend.name}: {exc}")
                continue
            return outcome.results, _records(entries, outcome, backend.name)
    detail = "; ".join(notes)
    return [], [
        StageRecord(
            test_id=entry.test_id,
            stage="mutation",
            status="degraded",
            reason="no_backend",
            payload={"detail": detail} if detail else {},
        )
        for entry in entries
    ]
