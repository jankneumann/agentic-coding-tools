"""Parity test for representative ``gen_eval`` public APIs after the move.

This test pins three representative public surface points that consumers
(both ``agent-coordinator`` and the documented quickstart for
``agentic-assistant``) rely on. The post-move package MUST expose them
at the same dotted paths.

Spec scenarios:
  - gen-eval-framework.canonical-module-name
  - gen-eval-framework.module-discovery-and-import-boundary

Design decisions: D1, D3
"""

from __future__ import annotations

import inspect


def test_evaluator_class_is_importable() -> None:
    """``gen_eval.evaluator.Evaluator`` MUST exist as a class."""
    from gen_eval.evaluator import Evaluator

    assert inspect.isclass(Evaluator), "Evaluator must be a class"


def test_openspec_seed_parse_function_is_importable() -> None:
    """``gen_eval.openspec_seed.parse_openspec_change`` MUST exist as a callable."""
    from gen_eval.openspec_seed import parse_openspec_change

    assert callable(parse_openspec_change), "parse_openspec_change must be callable"


def test_models_scenario_dataclass_is_importable() -> None:
    """``gen_eval.models.Scenario`` MUST exist (used by gen-eval-scenario MCP tool)."""
    from gen_eval.models import Scenario

    assert inspect.isclass(Scenario), "Scenario must be a class"


def test_no_coordinator_imports_from_package() -> None:
    """The framework, once moved, must not import from agent_coordinator/src.

    Walks the installed gen_eval module's source and asserts no file
    imports from ``agent_coordinator`` or ``src.coordination_``. The
    coordinator is a consumer; the package must not reach back into it.

    This is asserted by ``packages/gen-eval/`` being a self-contained
    install -- if any module imports the coordinator, ``import gen_eval``
    in the isolated venv would already fail. This test re-asserts the
    invariant explicitly so future refactors can't silently re-add the
    coupling.
    """
    import gen_eval

    pkg_path = gen_eval.__file__
    assert pkg_path is not None
    # Walk all .py files under the package root.
    from pathlib import Path

    pkg_root = Path(pkg_path).parent
    offenders: list[tuple[Path, str]] = []
    for py_file in pkg_root.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("from agent_coordinator", "import agent_coordinator")):
                offenders.append((py_file, stripped))
            if stripped.startswith(("from src.coordination_", "import src.coordination_")):
                offenders.append((py_file, stripped))
    assert not offenders, f"gen_eval must not import coordinator code; found: {offenders}"
