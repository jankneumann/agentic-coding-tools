"""Static stage: six deterministic, AST-only test checks (spec "Deterministic Static Test Checks").

Test files are read as text and parsed with :mod:`ast`; they are never imported
or executed. Each rule is purely syntactic and favours precision over recall.
"""

from __future__ import annotations

import ast
import builtins
import re
import sys
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from test_oracle_audit.records import StageRecord, TestEntry, find_function

RULE_IDS: tuple[str, ...] = (
    "assertion_free",
    "mock_assertion_dominant",
    "private_attribute_assert",
    "private_import",
    "mirrored_test_file",
    "unscoped_patch",
)

_PRIVATE = re.compile(r"^_[^_]")
_PYTEST_ASSERTING_CONTEXTS = frozenset({"raises", "warns", "deprecated_call"})
_MOCK_ASSERT_METHODS = (
    "assert_called",
    "assert_not_called",
    "assert_any_call",
    "assert_has_calls",
    "assert_awaited",
)
_MOCK_ASSERT_ATTRS = frozenset({"call_count", "call_args", "call_args_list", "mock_calls", "called"})
_TEST_SEGMENTS = frozenset({"tests", "test", "conftest"})
_DEFAULT_SOURCE_ROOTS = ("src", ".")

_FuncDef = ast.FunctionDef | ast.AsyncFunctionDef


def run_static(
    entries: Sequence[TestEntry], *, repo_root: Path, source_roots: Sequence[str] | None = None
) -> list[StageRecord]:
    """One ``static`` record per entry, ordered by node id, payload ``{"rules": [sorted ids]}``.

    ``source_roots`` (relative to ``repo_root``) is only used by
    ``mirrored_test_file`` to read the mirrored module. By default the
    directories ``src`` and ``.`` under each ancestor of the test file are tried.
    """
    repo_root = Path(repo_root)
    files: dict[str, _TestFile | None] = {}
    records: list[StageRecord] = []
    for entry in sorted(entries, key=lambda e: e.test_id.node_id):
        if entry.path not in files:
            files[entry.path] = _TestFile.load(repo_root, entry.path)
        parsed = files[entry.path]
        func = find_function(parsed.tree, entry.function_name, entry.class_name) if parsed else None
        if parsed is None or func is None:
            records.append(
                StageRecord(
                    test_id=entry.test_id,
                    stage="static",
                    status="error",
                    reason="source_unavailable",
                    payload={"rules": []},
                )
            )
            continue
        assert isinstance(func, _FuncDef)
        rules = _fired_rules(entry, func, parsed, repo_root, source_roots)
        records.append(
            StageRecord(test_id=entry.test_id, stage="static", status="ok", payload={"rules": sorted(rules)})
        )
    return records


class _TestFile:
    """A parsed test module: its tree plus the import bindings the rules need."""

    def __init__(self, tree: ast.Module) -> None:
        self.tree = tree
        # local name -> qualified name, for ``import a.b as m`` / ``from a import b``
        self.bindings: dict[str, str] = {}
        # local name -> module it was imported from, for ``from m import name``
        self.from_modules: dict[str, tuple[str, str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local = alias.asname or alias.name.split(".")[0]
                    self.bindings[local] = alias.name if alias.asname else alias.name.split(".")[0]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                for alias in node.names:
                    if alias.name != "*":
                        local = alias.asname or alias.name
                        self.bindings[local] = f"{node.module}.{alias.name}"
                        self.from_modules[local] = (node.module, alias.name)

    @classmethod
    def load(cls, repo_root: Path, rel_path: str) -> _TestFile | None:
        try:
            return cls(ast.parse((repo_root / rel_path).read_text("utf-8")))
        except (OSError, UnicodeDecodeError, SyntaxError):
            return None

    def test_functions(self) -> list[_FuncDef]:
        """Every ``test*`` function of the module (top level and in ``Test*`` classes)."""
        out: list[_FuncDef] = []
        for node in self.tree.body:
            if isinstance(node, _FuncDef) and node.name.startswith("test"):
                out.append(node)
            elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                out.extend(n for n in node.body if isinstance(n, _FuncDef) and n.name.startswith("test"))
        return out


def _fired_rules(
    entry: TestEntry,
    func: _FuncDef,
    parsed: _TestFile,
    repo_root: Path,
    source_roots: Sequence[str] | None,
) -> set[str]:
    checks: dict[str, Callable[[], bool]] = {
        "assertion_free": lambda: _assertion_free(func),
        "mock_assertion_dominant": lambda: _mock_assertion_dominant(func),
        "private_attribute_assert": lambda: _private_attribute_assert(func),
        "private_import": lambda: _private_import(func, parsed, entry.covered_modules),
        "mirrored_test_file": lambda: _mirrored_test_file(entry, parsed, repo_root, source_roots),
        "unscoped_patch": lambda: _unscoped_patch(func, parsed, entry.covered_modules),
    }
    return {rule for rule, check in checks.items() if check()}


# --- shared AST helpers ---------------------------------------------------


def _called_method_name(call: ast.Call) -> str:
    """Attribute name (or bare name) a call goes through; ``""`` for anything else."""
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _is_assert_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _called_method_name(node).startswith("assert")


def _is_mock_assert_call(call: ast.Call) -> bool:
    return _called_method_name(call).startswith(_MOCK_ASSERT_METHODS)


def _reads_mock_attribute(expr: ast.AST) -> bool:
    return any(isinstance(n, ast.Attribute) and n.attr in _MOCK_ASSERT_ATTRS for n in ast.walk(expr))


def _dotted(node: ast.AST) -> str | None:
    """``a.b.c`` for a Name/Attribute chain, else ``None``."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


# --- assertion_free -------------------------------------------------------


def _assertion_free(func: _FuncDef) -> bool:
    for node in ast.walk(func):
        if isinstance(node, ast.Assert):
            return False
        if isinstance(node, ast.Call):
            name = _called_method_name(node)
            if name.startswith("assert"):
                return False
            if name in _PYTEST_ASSERTING_CONTEXTS and (_dotted(node.func) or "").startswith(
                ("pytest.", name)
            ):
                return False
    return True


# --- mock_assertion_dominant ----------------------------------------------


def _mock_assertion_dominant(func: _FuncDef) -> bool:
    mock = other = 0
    for node in ast.walk(func):
        if isinstance(node, ast.Assert):
            if _reads_mock_attribute(node.test):
                mock += 1
            else:
                other += 1
        elif _is_assert_call(node):
            assert isinstance(node, ast.Call)
            if _is_mock_assert_call(node):
                mock += 1
            else:
                other += 1
    return mock > other


# --- private_attribute_assert ---------------------------------------------


def _has_private_attribute(expr: ast.AST) -> bool:
    for node in ast.walk(expr):
        if (
            isinstance(node, ast.Attribute)
            and _PRIVATE.match(node.attr)
            and not (isinstance(node.value, ast.Name) and node.value.id == "self")
        ):
            return True
    return False


def _private_attribute_assert(func: _FuncDef) -> bool:
    for node in ast.walk(func):
        if isinstance(node, ast.Assert) and _has_private_attribute(node.test):
            return True
        if _is_assert_call(node):
            assert isinstance(node, ast.Call)
            operands: Iterable[ast.AST] = [*node.args, *(k.value for k in node.keywords)]
            if any(_has_private_attribute(arg) for arg in operands):
                return True
    return False


# --- private_import -------------------------------------------------------


def _is_test_module(module: str) -> bool:
    parts = module.split(".")
    return any(p in _TEST_SEGMENTS or p.startswith("test_") or p.endswith("_test") for p in parts)


def _is_code_under_test(module: str) -> bool:
    """Non-test, non-stdlib module (stdlib privates such as ``os._exit`` are not oracle smells)."""
    return not _is_test_module(module) and not _is_stdlib(module)


def _private_import(func: _FuncDef, parsed: _TestFile, covered_modules: Sequence[str]) -> bool:
    """The test uses a private name imported from, or a private attribute of, a non-test module."""
    for node in ast.walk(func):
        if isinstance(node, ast.Name):
            origin = parsed.from_modules.get(node.id)
            if origin and _PRIVATE.match(origin[1]) and _is_code_under_test(origin[0]):
                return True
        elif isinstance(node, ast.Attribute) and _PRIVATE.match(node.attr):
            qualified = _module_of(node.value, parsed, covered_modules)
            if qualified and _is_code_under_test(qualified):
                return True
    return False


def _module_of(node: ast.AST, parsed: _TestFile, covered_modules: Sequence[str]) -> str | None:
    """Qualified module name when ``node`` names an imported module (``import a.b as m``, ``from a import b``)."""
    dotted = _dotted(node)
    if dotted is None:
        return None
    root, _, rest = dotted.partition(".")
    base = parsed.bindings.get(root)
    if base is None:
        return None
    qualified = f"{base}.{rest}" if rest else base
    if root in parsed.from_modules and qualified not in covered_modules:
        return None  # ``from m import Thing`` binds a class/function, not a module
    return qualified


# --- mirrored_test_file ---------------------------------------------------


def _mirrored_module_name(path: str) -> str:
    """``tests/sub/test_mod.py`` -> ``sub.mod`` (segments after the last ``tests`` dir, ``test_`` prefixes dropped)."""
    parts = path.split("/")
    marks = [i for i, p in enumerate(parts[:-1]) if p in _TEST_SEGMENTS]
    parts = parts[marks[-1] + 1 :] if marks else parts[-1:]
    parts = [p.removesuffix(".py").removeprefix("test_").removesuffix("_test") for p in parts]
    return ".".join(parts)


def _mirrored_source(
    entry: TestEntry, repo_root: Path, source_roots: Sequence[str] | None
) -> ast.Module | None:
    suffix = _mirrored_module_name(entry.path)
    matches = [m for m in entry.covered_modules if m == suffix or m.endswith("." + suffix)]
    if len(matches) != 1:
        return None
    module_path = Path(*matches[0].split("."))
    for base in _source_bases(entry.path, repo_root, source_roots):
        for candidate in (base / module_path.with_suffix(".py"), base / module_path / "__init__.py"):
            if candidate.is_file():
                try:
                    return ast.parse(candidate.read_text("utf-8"))
                except (OSError, UnicodeDecodeError, SyntaxError):
                    return None
    return None


def _source_bases(test_path: str, repo_root: Path, source_roots: Sequence[str] | None) -> list[Path]:
    if source_roots is not None:
        # a root may itself be the top-level package (``.../evaluation``): its parent is a base too
        return [b for r in source_roots for b in (repo_root / r, (repo_root / r).parent)]
    ancestors = [repo_root.joinpath(*Path(test_path).parts[:n]) for n in range(len(Path(test_path).parts))]
    bases: list[Path] = []
    for ancestor in reversed(ancestors):  # deepest project directory first
        bases.extend(ancestor / r for r in _DEFAULT_SOURCE_ROOTS)
    return bases


def _called_names(func: _FuncDef) -> set[str]:
    return {
        name for node in ast.walk(func) if isinstance(node, ast.Call) and (name := _called_method_name(node))
    }


def _mirrored_test_file(
    entry: TestEntry, parsed: _TestFile, repo_root: Path, source_roots: Sequence[str] | None
) -> bool:
    module = _mirrored_source(entry, repo_root, source_roots)
    if module is None:
        return False
    public = [n.name for n in module.body if isinstance(n, _FuncDef) and not n.name.startswith("_")]
    if not public:
        return False
    called = [_called_names(f) for f in parsed.test_functions()]
    return all(sum(name in names for names in called) == 1 for name in public)


# --- unscoped_patch -------------------------------------------------------


def _patch_kind(call: ast.Call, parsed: _TestFile) -> str:
    """``"string"`` for patch("a.b")/setattr("a.b", v), ``"object"`` for patch.object/setattr(obj, "x", v), else ``""``."""
    dotted = _dotted(call.func)
    if dotted is None:
        return ""
    parts = dotted.split(".")
    if parts[-1] == "setattr" and len(parts) >= 2 and parts[-2].endswith("monkeypatch"):
        first = call.args[0] if call.args else None
        return "string" if isinstance(first, ast.Constant) and isinstance(first.value, str) else "object"
    is_object = parts[-1] == "object"
    patch_path = ".".join(parts[:-1] if is_object else parts)
    if not _is_mock_patch(patch_path, parsed):
        return ""
    return "object" if is_object else "string"


def _is_mock_patch(dotted: str, parsed: _TestFile) -> bool:
    """``patch`` / ``mock.patch`` / ``unittest.mock.patch`` / ``mocker.patch`` (not e.g. ``requests.patch``)."""
    root, _, rest = dotted.partition(".")
    if root == "mocker":
        return rest == "patch"
    base = parsed.bindings.get(root)
    if base is None:
        return False
    return (f"{base}.{rest}" if rest else base) in {"unittest.mock.patch", "mock.patch"}


def _patch_target(call: ast.Call, kind: str, parsed: _TestFile) -> str | None:
    """Qualified name of what is patched, or ``None`` when it cannot be resolved statically."""
    if not call.args:
        return None
    first = call.args[0]
    if kind == "string":
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
        return None
    dotted = _dotted(first)
    if dotted is None:
        return None
    root, _, rest = dotted.partition(".")
    base = parsed.bindings.get(root)
    if base is None:
        return root if hasattr(builtins, root) else None  # unresolvable local objects never fire
    return f"{base}.{rest}" if rest else base


def _is_in_scope(target: str, covered_modules: Sequence[str]) -> bool:
    return any(target == m or target.startswith(m + ".") for m in covered_modules)


def _is_stdlib(module: str) -> bool:
    top = module.split(".")[0]
    return top == "builtins" or top in sys.stdlib_module_names


def _unscoped_patch(func: _FuncDef, parsed: _TestFile, covered_modules: Sequence[str]) -> bool:
    for node in ast.walk(func):  # includes the function's decorators
        if not isinstance(node, ast.Call):
            continue
        kind = _patch_kind(node, parsed)
        if not kind:
            continue
        target = _patch_target(node, kind, parsed)
        if target is None:
            continue
        if _is_in_scope(target, covered_modules):
            continue
        return True
    return False
