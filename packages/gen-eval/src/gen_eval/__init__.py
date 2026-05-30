"""gen-eval -- Generator-evaluator testing framework for agentic systems.

This module is the public entry point for the extracted ``gen-eval`` package.
The framework code lands here in a follow-up task (wp-framework-move); for
now the package exposes only its version and is otherwise empty so that
``import gen_eval`` succeeds and the smoke test in
``tests/test_smoke.py`` can prove the canonical module name (D1) is
reachable from the new ``packages/gen-eval/`` location.

Spec scenario: gen-eval-framework.canonical-module-name
Design decisions: D1, D2
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
