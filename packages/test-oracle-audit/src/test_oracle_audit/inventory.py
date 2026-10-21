"""Inventory stage: enumerate a suite's tests (design D1, spec "Test Inventory").

Collection runs ``pytest --collect-only`` as a subprocess in the suite's own
project environment (``uv run --project <project_root> ...``), so the package's
interpreter never imports audited test modules. Everything else (content hash,
line range, fixtures, covered modules) is read from the test files' ASTs.

Node ids are made repo-relative: pytest reports them relative to its rootdir
(the suite's project root, the subprocess cwd), and the project root's path
below ``repo_root`` is prefixed so ``node_id`` and ``payload["path"]`` agree.
"""

from __future__ import annotations

import ast
import os
import posixpath
import re
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from test_oracle_audit.records import (
    StageRecord,
    SuiteSpec,
    TestEntry,
    TestId,
    content_hash,
    find_function,
    hash_source,
    split_node_id,
)

_ERROR_LINE = re.compile(r"^ERROR\s+(?:collecting\s+)?(\S+\.py)\b")
# pytest exit codes where the collection ran: 0 ok, 1/2 collection errors, 5 nothing collected.
_COLLECTED_EXIT_CODES = (0, 1, 2, 5)
_SKIPPED_PARAMS = frozenset({"self", "cls"})


def build_inventory(suite: SuiteSpec, *, repo_root: Path, python: str | None = None) -> list[StageRecord]:
    """Inventory records for ``suite``, sorted by node id.

    ``python`` selects the interpreter (``[python, "-m", "pytest", ...]``);
    ``None`` runs collection through ``uv run --project <project_root>`` with
    one ``--extra`` per ``suite.uv_extras``. An uncollectable test file yields a
    ``collection_error`` record and never aborts the stage.
    """
    repo_root = Path(repo_root)
    project_dir = (repo_root / suite.project_root).resolve()
    argv = _collect_command(suite, repo_root, project_dir, python)

    try:
        proc = subprocess.run(
            argv,
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
    except OSError as exc:
        return [_failure_record(suite, f"could not start collection: {exc}")]

    project_rel = os.path.relpath(project_dir, repo_root.resolve()).replace(os.sep, "/")
    node_ids, error_files = _parse_collection(proc.stdout or "", project_rel)

    if not node_ids and not error_files and proc.returncode not in (0, 5):
        tail = (proc.stderr or proc.stdout or "").strip()[-500:]
        return [_failure_record(suite, f"pytest exited {proc.returncode}: {tail}")]

    records: dict[str, StageRecord] = {}
    files = _FileCache(repo_root, suite)
    for node_id in node_ids:
        records.setdefault(node_id, _test_record(node_id, files))
    for rel_path in error_files:
        records.setdefault(rel_path, _file_error_record(rel_path, files))
    return [records[key] for key in sorted(records)]


# --- collection -----------------------------------------------------------


def _collect_command(suite: SuiteSpec, repo_root: Path, project_dir: Path, python: str | None) -> list[str]:
    pytest_cmd = [
        "pytest",
        "--collect-only",
        "-q",
        "--continue-on-collection-errors",
        *suite.pytest_args,
        *(os.path.relpath((repo_root / p).resolve(), project_dir) for p in suite.test_paths),
    ]
    if python is not None:
        return [python, "-m", *pytest_cmd]
    extras = [arg for extra in suite.uv_extras for arg in ("--extra", extra)]
    return ["uv", "run", "--project", str(project_dir), *extras, "--with", "pytest-cov", *pytest_cmd]


def _parse_collection(stdout: str, project_rel: str) -> tuple[list[str], list[str]]:
    """Repo-relative (node ids, files that failed to collect) from ``--collect-only -q`` output."""
    node_ids: list[str] = []
    error_files: list[str] = []
    in_listing = True
    for line in stdout.splitlines():
        if line.startswith("="):  # "=== ERRORS ===", "=== warnings summary ===", ...
            in_listing = False
            continue
        match = _ERROR_LINE.match(line)
        if match:
            rel = _repo_relative(match.group(1), project_rel)
            if rel not in error_files:
                error_files.append(rel)
        elif in_listing and "::" in line and not line[0].isspace():
            file_part = line.split("::", 1)[0]
            if file_part.endswith(".py"):
                node_ids.append(_repo_relative(file_part, project_rel) + line[len(file_part) :])
    return node_ids, error_files


def _repo_relative(path: str, project_rel: str) -> str:
    return path if project_rel == "." else posixpath.normpath(posixpath.join(project_rel, path))


def _failure_record(suite: SuiteSpec, detail: str) -> StageRecord:
    """Whole-collection failure (uv/pytest could not run): one error record, never an exception."""
    target = suite.test_paths[0] if suite.test_paths else suite.name
    return StageRecord(
        test_id=TestId(target, hash_source(target)),
        stage="inventory",
        status="error",
        reason="collection_error",
        payload={"path": target, "detail": detail},
    )


# --- per-file analysis ----------------------------------------------------


@dataclass
class _ParsedFile:
    text: str
    tree: ast.Module | None
    covered_modules: tuple[str, ...]
    usefixtures: tuple[str, ...]  # module-level pytestmark


class _FileCache:
    def __init__(self, repo_root: Path, suite: SuiteSpec) -> None:
        self.repo_root = repo_root
        self.source_roots = [(repo_root / r).resolve() for r in suite.source_roots]
        self._parsed: dict[str, _ParsedFile] = {}

    def get(self, rel_path: str) -> _ParsedFile:
        if rel_path not in self._parsed:
            try:
                text = (self.repo_root / rel_path).read_text("utf-8")
            except (OSError, UnicodeDecodeError):
                text = ""
            try:
                tree: ast.Module | None = ast.parse(text)
            except SyntaxError:
                tree = None
            covered = _covered_modules(tree, self.source_roots) if tree else ()
            marks = _module_usefixtures(tree) if tree else ()
            self._parsed[rel_path] = _ParsedFile(text, tree, covered, marks)
        return self._parsed[rel_path]


def _test_record(node_id: str, files: _FileCache) -> StageRecord:
    rel_path, class_name, func_name = split_node_id(node_id)
    parsed = files.get(rel_path)
    func = find_function(parsed.tree, func_name, class_name) if parsed.tree else None
    if func is None:
        return StageRecord(
            test_id=TestId(node_id, hash_source(node_id)),
            stage="inventory",
            status="error",
            reason="source_not_found",
            payload={"path": rel_path},
        )
    cls_node = _class_node(parsed.tree, class_name)
    entry = TestEntry(
        test_id=TestId(node_id, content_hash(parsed.text, func_name, class_name)),
        path=rel_path,
        line_start=func.lineno,
        line_end=func.end_lineno or func.lineno,
        function_name=func_name,
        class_name=class_name,
        fixtures=_fixtures(func, cls_node, parsed.usefixtures),
        covered_modules=parsed.covered_modules,
    )
    return entry.to_record()


def _file_error_record(rel_path: str, files: _FileCache) -> StageRecord:
    return StageRecord(
        test_id=TestId(rel_path, hash_source(files.get(rel_path).text)),
        stage="inventory",
        status="error",
        reason="collection_error",
        payload={"path": rel_path},
    )


def _class_node(tree: ast.Module | None, class_name: str | None) -> ast.ClassDef | None:
    if tree is None or class_name is None:
        return None
    return next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None)


# --- fixtures (static AST) ------------------------------------------------


def _mark_name(node: ast.expr) -> tuple[str, ast.Call | None]:
    """``("usefixtures", call)`` for ``pytest.mark.usefixtures("a")``; ``("", None)`` otherwise."""
    call = node if isinstance(node, ast.Call) else None
    target = call.func if call else node
    if (
        isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Attribute)
        and target.value.attr == "mark"
    ):
        return target.attr, call
    return "", call


def _string_args(call: ast.Call | None) -> list[str]:
    if call is None:
        return []
    return [a.value for a in call.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]


def _usefixtures(decorators: Iterable[ast.expr]) -> list[str]:
    out: list[str] = []
    for dec in decorators:
        name, call = _mark_name(dec)
        if name == "usefixtures":
            out.extend(_string_args(call))
    return out


def _module_usefixtures(tree: ast.Module) -> tuple[str, ...]:
    out: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets
        ):
            values = node.value.elts if isinstance(node.value, ast.List | ast.Tuple) else [node.value]
            out.extend(_usefixtures(values))
    return tuple(out)


def _parametrized_names(decorators: Iterable[ast.expr]) -> set[str]:
    names: set[str] = set()
    for dec in decorators:
        name, call = _mark_name(dec)
        if name == "parametrize" and call is not None and call.args:
            first = call.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                names.update(p.strip() for p in first.value.split(",") if p.strip())
            elif isinstance(first, ast.List | ast.Tuple):
                names.update(
                    e.value for e in first.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)
                )
    return names


def _patch_injected_count(decorators: Iterable[ast.expr]) -> int:
    """Leading params supplied by ``@patch`` / ``@patch.object`` decorators (no explicit ``new``)."""
    count = 0
    for dec in decorators:
        if not isinstance(dec, ast.Call):
            continue
        func = dec.func
        is_object = isinstance(func, ast.Attribute) and func.attr == "object"
        base = func.value if is_object and isinstance(func, ast.Attribute) else func
        base_name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", "")
        if base_name != "patch":
            continue
        new_pos = 2 if is_object else 1
        if len(dec.args) <= new_pos and not any(k.arg == "new" for k in dec.keywords):
            count += 1
    return count


def _fixtures(func: ast.AST, cls: ast.ClassDef | None, module_marks: Sequence[str]) -> tuple[str, ...]:
    """Fixtures a test names: its parameters (minus parametrize/patch-injected) plus usefixtures marks."""
    assert isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef)
    args = func.args
    params = [a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)]
    params = [p for p in params if p not in _SKIPPED_PARAMS]
    params = params[_patch_injected_count(func.decorator_list) :]
    excluded = _parametrized_names(func.decorator_list)
    if cls is not None:
        excluded |= _parametrized_names(cls.decorator_list)
    used = [p for p in params if p not in excluded]
    used += _usefixtures(func.decorator_list)
    if cls is not None:
        used += _usefixtures(cls.decorator_list)
    used += module_marks
    return tuple(sorted(set(used)))


# --- covered modules ------------------------------------------------------
# Adapted from skills/refresh-architecture/scripts/insights/test_linker.py
# (``_extract_imports`` / ``build_test_covers_edges``, direct-import linking):
# the same "test file -> modules it imports" mapping, but resolved against the
# suite's source roots on disk instead of an architecture graph, and kept as a
# local copy (no cross-tree import, design D1 "Reused code").


def _import_candidates(tree: ast.AST) -> list[tuple[str, list[str]]]:
    """``(module, [imported names])`` per absolute import statement (relative imports skipped)."""
    out: list[tuple[str, list[str]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend((alias.name, []) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.append((node.module, [a.name for a in node.names if a.name != "*"]))
    return out


def _is_module(dotted: str, source_roots: Sequence[Path]) -> bool:
    parts = dotted.split(".")
    for root in source_roots:
        bases = [root]
        if root.name == parts[0]:  # the root *is* the top-level package (e.g. ``.../evaluation``)
            bases.append(root.parent)
        for base in bases:
            target = base.joinpath(*parts)
            if target.with_suffix(".py").is_file() or (target / "__init__.py").is_file():
                return True
    return False


def _resolve_import(module: str, names: Sequence[str], source_roots: Sequence[Path]) -> list[str]:
    """Source modules reached by one import statement, deepest resolvable form."""
    reached = [f"{module}.{n}" for n in names if _is_module(f"{module}.{n}", source_roots)]
    if reached:
        return reached
    parts = module.split(".")
    for end in range(len(parts), 0, -1):
        candidate = ".".join(parts[:end])
        if _is_module(candidate, source_roots):
            return [candidate]
    return []


def _covered_modules(tree: ast.Module, source_roots: Sequence[Path]) -> tuple[str, ...]:
    covered: set[str] = set()
    for module, names in _import_candidates(tree):
        covered.update(_resolve_import(module, names, source_roots))
    return tuple(sorted(covered))
