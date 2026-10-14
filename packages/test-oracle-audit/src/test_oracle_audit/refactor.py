"""Refactor-survival stage: rename private symbols, rerun the tests (design D5).

Inside an isolated copy, :mod:`libcst` renames every eligible private symbol of the
source tree (``_name`` -> ``_name__r``), consistently across the **source** files and
never in tests. The rename is behaviour-preserving for any caller that uses public
names, so a test that passes before and fails after is coupled to implementation
details. Names that cannot be renamed safely are skipped and counted as unrenamable:

* listed in a module's ``__all__``;
* appearing in a string literal anywhere in the source tree (``getattr``, registries,
  ``patch`` targets); docstrings do not count;
* imported by a public module (a re-export).

Eligible symbols are module-level and class-level ``def``, ``class`` and assignment
names matching ``^_[^_]``. The rename is by name: a name is renamed everywhere or
nowhere, so two modules defining the same private name share one verdict.

The suite runs twice in the same copy, before and after the rename; a test that
already fails (or does not run) before the rename carries no verdict and is reported
``degraded``. Per-test counts follow the spec's per-module rule, summed over the
modules the test covers (``TestEntry.covered_modules``); ``low_confidence`` is set
when more than half of the eligible symbols of *any* covered module are unrenamable.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import libcst as cst

from test_oracle_audit.isolation import dotted_module, isolated_copy, run_suite, source_files
from test_oracle_audit.records import StageRecord, SuiteSpec, TestEntry

RENAME_SUFFIX = "__r"
_ELIGIBLE = re.compile(r"^_[^_]")


@dataclass
class _Module:
    path: Path
    name: str
    is_package: bool
    tree: ast.Module
    symbols: list[str] = field(default_factory=list)  # bare names, one per eligible definition

    @property
    def is_public(self) -> bool:
        return not any(part.startswith("_") for part in self.name.split("."))


def _target_names(target: ast.expr) -> Iterable[str]:
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, ast.Tuple | ast.List):
        for element in target.elts:
            yield from _target_names(element)
    elif isinstance(target, ast.Starred):
        yield from _target_names(target.value)


def _definitions(body: Sequence[ast.stmt]) -> Iterable[str]:
    """Names defined in one scope's statements, descending into if/try/with blocks."""
    for statement in body:
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            yield statement.name
        elif isinstance(statement, ast.Assign):
            for target in statement.targets:
                yield from _target_names(target)
        elif isinstance(statement, ast.AnnAssign | ast.AugAssign):
            yield from _target_names(statement.target)
        elif isinstance(statement, ast.If | ast.With | ast.AsyncWith | ast.For | ast.While):
            yield from _definitions([*statement.body, *getattr(statement, "orelse", [])])
        elif isinstance(statement, ast.Try):
            handlers = [s for h in statement.handlers for s in h.body]
            yield from _definitions([*statement.body, *handlers, *statement.orelse, *statement.finalbody])


def _eligible_symbols(tree: ast.Module) -> list[str]:
    """Module-level and class-level eligible names, each definition counted once."""
    names: list[str] = [n for n in _definitions(tree.body) if _ELIGIBLE.match(n)]
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            names.extend(n for n in _definitions(node.body) if _ELIGIBLE.match(n))
    return names


def _docstring_nodes(tree: ast.Module) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                ids.add(id(first.value))
    return ids


def _exported_names(tree: ast.Module) -> set[str]:
    """String entries of the module's ``__all__`` assignments."""
    exported: set[str] = set()
    for statement in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(statement, ast.Assign):
            targets, value = statement.targets, statement.value
        elif isinstance(statement, ast.AnnAssign | ast.AugAssign):
            targets, value = [statement.target], statement.value
        if value is not None and any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
            exported.update(
                n.value for n in ast.walk(value) if isinstance(n, ast.Constant) and isinstance(n.value, str)
            )
    return exported


def _resolve_import(module: _Module, node: ast.ImportFrom | cst.ImportFrom) -> str | None:
    """Dotted name of the module a ``from ... import`` refers to (None: cannot tell)."""
    if isinstance(node, ast.ImportFrom):
        level, dotted = node.level, node.module
    else:
        level = len(node.relative)
        dotted = _dotted(node.module) if node.module is not None else None
    if level == 0:
        return dotted
    package = module.name.split(".") if module.is_package else module.name.split(".")[:-1]
    if level - 1 > len(package):
        return None
    base = package[: len(package) - (level - 1)]
    return ".".join([*base, *([dotted] if dotted else [])])


def _dotted(node: cst.BaseExpression) -> str:
    if isinstance(node, cst.Attribute):
        return f"{_dotted(node.value)}.{node.attr.value}"
    assert isinstance(node, cst.Name)
    return node.value


@dataclass
class _Analysis:
    modules: list[_Module]
    renamable: set[str]  # bare names renamed everywhere
    eligible: dict[str, int]  # module name -> eligible symbol count
    unrenamable: dict[str, int]  # module name -> unrenamable symbol count


def _analyse(files: Sequence[Path], root: Path) -> _Analysis:
    modules: list[_Module] = []
    for path in files:
        try:
            tree = ast.parse(path.read_text("utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        module = _Module(path, dotted_module(path, root), path.name == "__init__.py", tree)
        module.symbols = _eligible_symbols(tree)
        modules.append(module)

    defined = {name for m in modules for name in m.symbols}
    by_name = {m.name: m for m in modules}
    blocked: set[str] = set()

    for module in modules:  # `__all__`
        blocked |= _exported_names(module.tree) & defined

    strings: list[str] = []  # string literals other than docstrings
    for module in modules:
        docstrings = _docstring_nodes(module.tree)
        strings.extend(
            node.value
            for node in ast.walk(module.tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
        )
    haystack = "\n".join(strings)
    for name in defined - blocked:
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", haystack):
            blocked.add(name)

    for module in modules:  # re-exports: a public module importing the name from a source module
        if not module.is_public:
            continue
        for node in ast.walk(module.tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            target = by_name.get(_resolve_import(module, node) or "")
            if target is None or target is module:
                continue
            blocked.update(a.name for a in node.names if a.name in target.symbols)

    renamable = defined - blocked
    eligible = {m.name: len(m.symbols) for m in modules}
    unrenamable = {m.name: sum(1 for s in m.symbols if s in blocked) for m in modules}
    return _Analysis(modules, renamable, eligible, unrenamable)


class _Renamer(cst.CSTTransformer):
    """Appends ``__r`` to every identifier token in ``names``.

    Names imported with ``from <non-source module> import ...`` are left alone, so a
    source module's use of someone else's identically named private attribute is safe.
    """

    def __init__(self, names: set[str], module: _Module, known: set[str]) -> None:
        super().__init__()
        self._names = names
        self._module = module
        self._known = known
        self._import_in_tree = True

    def visit_ImportFrom(self, node: cst.ImportFrom) -> bool:
        target = _resolve_import(self._module, node)
        self._import_in_tree = target is not None and target in self._known
        return True

    def visit_ImportFrom_module(self, node: cst.ImportFrom) -> bool:
        return False  # module paths are not symbols

    def visit_ImportFrom_names(self, node: cst.ImportFrom) -> bool:
        return self._import_in_tree

    def leave_Name(self, original_node: cst.Name, updated_node: cst.Name) -> cst.Name:
        if updated_node.value in self._names:
            return updated_node.with_changes(value=updated_node.value + RENAME_SUFFIX)
        return updated_node


def _apply_rename(analysis: _Analysis) -> None:
    """Rewrite the renamed source files in place (inside the isolated copy)."""
    known = {m.name for m in analysis.modules}
    for module in analysis.modules:
        wrapper = cst.parse_module(module.path.read_text("utf-8"))
        renamed = wrapper.visit(_Renamer(analysis.renamable, module, known))
        if renamed.code != wrapper.code:
            module.path.write_text(renamed.code, encoding="utf-8")


def _record(entry: TestEntry, status: str, payload: dict, reason: str | None = None) -> StageRecord:
    return StageRecord(test_id=entry.test_id, stage="rename", status=status, payload=payload, reason=reason)


def _degraded(entries: Sequence[TestEntry], reason: str) -> list[StageRecord]:
    return [_record(e, "degraded", {}, reason) for e in entries]


def run_rename_survival(
    suite: SuiteSpec,
    entries: Sequence[TestEntry],
    *,
    repo_root: Path,
    python: str | None = None,
) -> list[StageRecord]:
    """One ``rename`` record per entry: ``{survives, renamed_symbols, unrenamable_symbols, low_confidence}``.

    Runs only inside an isolated copy that is removed on every exit path; the audited tree
    is never touched. A suite that cannot run yields ``degraded`` records instead of raising.
    """
    entries = list(entries)
    node_ids = [e.test_id.node_id for e in entries]
    with isolated_copy(Path(repo_root)) as copy:
        try:
            before = run_suite(copy, suite, python=python, node_ids=node_ids)
            if before.timed_out or not before.results_found:
                return _degraded(entries, "baseline_timeout" if before.timed_out else "baseline_run_failed")
            analysis = _analyse(source_files(copy.root, suite), copy.root)
            _apply_rename(analysis)
            after = run_suite(copy, suite, python=python, node_ids=node_ids)
        except OSError:
            return _degraded(entries, "suite_could_not_start")
    if after.timed_out or not after.results_found:
        return _degraded(entries, "rename_timeout" if after.timed_out else "rename_run_failed")

    records = []
    for entry in entries:
        node_id = entry.test_id.node_id
        was = before.outcomes.get(node_id)
        if was is None or was == "failed":
            records.append(_record(entry, "degraded", {}, "baseline_failed" if was else "not_run"))
            continue
        if was == "skipped":
            records.append(_record(entry, "skipped", {}, "skipped_in_baseline"))
            continue
        modules = [m for m in dict.fromkeys(entry.covered_modules) if m in analysis.eligible]
        unrenamable = sum(analysis.unrenamable[m] for m in modules)
        eligible = sum(analysis.eligible[m] for m in modules)
        records.append(
            _record(
                entry,
                "ok",
                {
                    "survives": after.outcomes.get(node_id) == "passed",
                    "renamed_symbols": eligible - unrenamable,
                    "unrenamable_symbols": unrenamable,
                    "low_confidence": any(
                        analysis.unrenamable[m] * 2 > analysis.eligible[m] for m in modules
                    ),
                },
            )
        )
    return records
