"""Guard test: every adapter-backed test function is named `uncalibrated`.

Spec: specs/system-one-decisions/spec.md
  "Adapter-backed behavioural tests are double-gated and named uncalibrated"
  Scenario: "Every adapter-backed test name signals uncalibrated probabilities"
"""

from __future__ import annotations

import ast
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent


def _imports_system_one_adapter(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name.split(".")[0] == "system_one_adapter" for alias in node.names
        ):
            return True
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[0] == "system_one_adapter"
        ):
            return True
    return False


def test_every_test_importing_the_adapter_has_uncalibrated_in_its_name() -> None:
    offenders: list[str] = []
    for path in sorted(_TESTS_DIR.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if not node.name.startswith("test_"):
                continue
            # Check only this function's own subtree, not the whole file --
            # a file could mix adapter and non-adapter tests.
            if _imports_system_one_adapter(ast.Module(body=node.body, type_ignores=[])) and (
                "uncalibrated" not in node.name
            ):
                offenders.append(f"{path.name}::{node.name}")

    assert not offenders, (
        "test function(s) import system_one_adapter but lack 'uncalibrated' "
        f"in their name: {offenders}"
    )
