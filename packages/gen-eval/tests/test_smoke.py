"""Smoke test for the gen_eval package.

This test confirms that ``import gen_eval`` resolves to the new
``packages/gen-eval/src/gen_eval/`` location -- not the legacy
``agent-coordinator/evaluation/gen_eval/`` location -- once the package
has been installed via ``uv sync`` inside this directory.

Spec scenario: gen-eval-framework.canonical-module-name
Design decisions: D1, D2

The test deliberately stays minimal: it asserts that the package is
importable and that its ``__file__`` attribute lives inside a path that
ends in ``gen_eval/__init__.py`` -- enough to prove the installed
artifact (not a stray sys.path entry into the coordinator tree) is the
one resolving.
"""

from __future__ import annotations

import importlib
from pathlib import Path


def test_gen_eval_is_importable() -> None:
    """``import gen_eval`` must succeed in the package's own venv."""
    module = importlib.import_module("gen_eval")
    assert module is not None


def test_gen_eval_resolves_to_packages_directory() -> None:
    """The installed ``gen_eval`` package must originate from this package,

    not from the legacy ``agent-coordinator/evaluation/gen_eval/`` tree.

    We can't assert the absolute path (it depends on whether the install
    is editable or wheel-based), but we can assert the path does NOT
    contain ``agent-coordinator/evaluation/gen_eval`` -- which would
    indicate the legacy location is still on sys.path ahead of us.
    """
    module = importlib.import_module("gen_eval")
    file_path = Path(module.__file__) if module.__file__ else None
    assert file_path is not None, "gen_eval.__file__ must be set"
    parts = file_path.as_posix()
    assert "agent-coordinator/evaluation/gen_eval" not in parts, (
        f"gen_eval resolved from the legacy coordinator path: {parts}. "
        "The packages/gen-eval/ install is not on sys.path or is shadowed."
    )
    # And the final component must be gen_eval/__init__.py.
    assert file_path.name == "__init__.py"
    assert file_path.parent.name == "gen_eval"
