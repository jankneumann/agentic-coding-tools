"""Guard test: every adapter-backed test function is named `uncalibrated`.

Spec: specs/system-one-decisions/spec.md
  "Adapter-backed behavioural tests are double-gated and named uncalibrated"
  Scenario: "Every adapter-backed test name signals uncalibrated probabilities"
"""

from __future__ import annotations

import ast
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_ADAPTER_MODULE = "system_one_adapter"


def _module_level_imports(tree: ast.Module) -> set[str]:
    """Top-level names bound by `import x` / `from x import ...` at module
    scope (not inside any function) -- these are visible to every function
    in the file without a local import."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def _function_imports(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Names bound by an `import x` / `from x import ...` anywhere inside
    this function's own body (a local, lazy import)."""
    names: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def _function_references_name(func: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> bool:
    """True if `name` is loaded anywhere in the function body -- covers
    `system_one_adapter.Choice(...)`, `system_one_adapter.SystemOneAdapterClient(...)`,
    etc., since attribute access always starts with a Name load of the root."""
    return any(
        isinstance(node, ast.Name) and node.id == name for node in ast.walk(func)
    )


def _test_function_uses_adapter(
    module_level_imports: set[str], func: ast.FunctionDef | ast.AsyncFunctionDef
) -> bool:
    """A test uses the adapter if it imports it locally, OR the module
    imports it at top level *and* the function actually references the name
    (module-level import alone, on an unrelated function, is not a hit)."""
    if _ADAPTER_MODULE in _function_imports(func):
        return True
    return _ADAPTER_MODULE in module_level_imports and _function_references_name(
        func, _ADAPTER_MODULE
    )


def _offending_test_functions(source: str, filename: str = "<test>") -> list[str]:
    tree = ast.parse(source, filename=filename)
    module_level = _module_level_imports(tree)
    offenders: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not node.name.startswith("test_"):
            continue
        if _test_function_uses_adapter(module_level, node) and "uncalibrated" not in node.name:
            offenders.append(node.name)
    return offenders


def test_guard_catches_a_module_level_import_used_without_the_local_import() -> None:
    """Regression for the exact gap a Codex review found on PR #585: a file
    that imports system_one_adapter at module scope and constructs a client
    inside the test body (a normal pytest pattern) must still be caught,
    even though there is no import statement inside the function itself."""
    synthetic_source = (
        "import system_one_adapter\n\n"
        "def test_missing_the_required_name(monkeypatch):\n"
        "    client = system_one_adapter.SystemOneAdapterClient()\n"
        "    return client\n"
    )
    assert _offending_test_functions(synthetic_source) == ["test_missing_the_required_name"]


def test_guard_does_not_flag_a_correctly_named_function() -> None:
    synthetic_source = (
        "import system_one_adapter\n\n"
        "def test_wiring_uncalibrated(monkeypatch):\n"
        "    return system_one_adapter.SystemOneAdapterClient()\n"
    )
    assert _offending_test_functions(synthetic_source) == []


def test_guard_does_not_flag_an_unrelated_test_in_the_same_file() -> None:
    """A module-level import must not make every test in the file a false
    positive -- only functions that actually reference the name."""
    synthetic_source = (
        "import system_one_adapter\n\n"
        "def test_uncalibrated_adapter_call(monkeypatch):\n"
        "    return system_one_adapter.SystemOneAdapterClient()\n\n"
        "def test_unrelated_thing():\n"
        "    return 1 + 1\n"
    )
    assert _offending_test_functions(synthetic_source) == []


def test_every_test_importing_the_adapter_has_uncalibrated_in_its_name() -> None:
    offenders: list[str] = []
    for path in sorted(_TESTS_DIR.glob("test_*.py")):
        source = path.read_text(encoding="utf-8")
        for name in _offending_test_functions(source, filename=str(path)):
            offenders.append(f"{path.name}::{name}")

    assert not offenders, (
        "test function(s) use system_one_adapter but lack 'uncalibrated' "
        f"in their name: {offenders}"
    )
