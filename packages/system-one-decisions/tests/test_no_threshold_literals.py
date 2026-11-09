"""Guard test: no threshold float literal in scoring logic.

Spec: specs/system-one-decisions/spec.md
  "Threshold defaults resolve from a package-owned data file, never a literal"
  Scenario: "No threshold literal in scoring logic"
"""

from __future__ import annotations

import ast
from pathlib import Path

_CORE = Path(__file__).resolve().parents[1] / "src" / "system_one_decisions" / "_core.py"
_THRESHOLD_PARAM_NAMES = {"act_floor", "approve_floor"}


def _default_values_for_threshold_params(tree: ast.Module) -> list[ast.expr]:
    """Collect the default-value AST nodes for any `act_floor`/`approve_floor`
    keyword-only parameter across every function definition in the module."""
    defaults: list[ast.expr] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        args = node.args
        kwonly_defaults = dict(zip(args.kwonlyargs, args.kw_defaults, strict=True))
        for arg, default in kwonly_defaults.items():
            if arg.arg in _THRESHOLD_PARAM_NAMES and default is not None:
                defaults.append(default)
    return defaults


def test_no_bare_float_literal_used_as_a_threshold_default() -> None:
    tree = ast.parse(_CORE.read_text(encoding="utf-8"), filename=str(_CORE))
    defaults = _default_values_for_threshold_params(tree)
    assert defaults, "expected to find act_floor/approve_floor keyword params in _core.py"
    for default in defaults:
        assert not isinstance(default, ast.Constant), (
            f"threshold default at line {default.lineno} is a bare literal "
            f"({ast.dump(default)}); it must reference a named constant "
            f"imported from _config"
        )
