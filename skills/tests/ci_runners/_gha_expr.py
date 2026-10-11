"""Minimal reference evaluator for the GitHub Actions expression grammar used by D3.

Covers only what the canonical ``runs-on`` expression needs: ``&&``/``||`` with
GitHub's value semantics (they return an operand, not a boolean), ``==``/``!=``
(string compare is case-insensitive), ``!``, parentheses, single-quoted string
literals, ``fromJSON`` of a literal, and dotted context lookups from a dict.

Also holds the canonical expression and the canonical fork-guard step so that the
routing, completeness and guard tests share one definition (design D3/D4).
"""

from __future__ import annotations

import json
import re
from typing import Any

CANONICAL_RUNS_ON = (
    "${{ (github.event_name == 'push' || github.event_name == 'workflow_dispatch' || "
    "(github.event_name == 'pull_request' && github.event.pull_request.head.repo.full_name "
    "== github.repository)) && ((github.event_name == 'workflow_dispatch' && "
    "inputs.runner_lane != 'auto') && inputs.runner_lane || vars.CI_RUNNER_LANE) == "
    '\'self-hosted\' && fromJSON(\'["self-hosted","linux","ARM64","gx10"]\') || '
    "'ubuntu-latest' }}"
)

GUARD_STEP_NAME = "Refuse ineligible events on self-hosted runner"


def normalize(text: str) -> str:
    """Collapse all whitespace runs to one space (D3: compare after normalization)."""
    return re.sub(r"\s+", " ", text).strip()


def strip_wrapper(expr: str) -> str:
    m = re.fullmatch(r"\s*\$\{\{(.*)\}\}\s*", expr, flags=re.S)
    if not m:
        raise ValueError(f"not a ${{{{ }}}} expression: {expr!r}")
    return m.group(1).strip()


def eligibility_clause(expr: str = CANONICAL_RUNS_ON) -> str:
    """The leading parenthesised event-eligibility group of a runs-on expression."""
    body = strip_wrapper(expr)
    if not body.startswith("("):
        raise ValueError("expression does not start with the eligibility group")
    depth = 0
    in_str = False
    for i, ch in enumerate(body):
        if ch == "'":
            in_str = not in_str
        elif not in_str:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return normalize(body[: i + 1])
    raise ValueError("unbalanced parentheses")


def guard_condition(expr: str = CANONICAL_RUNS_ON) -> str:
    """D4: ``runner.environment == 'self-hosted' && !(<eligibility clause>)``."""
    return f"runner.environment == 'self-hosted' && !{eligibility_clause(expr)}"


# --------------------------------------------------------------------------- tokenizer

_TOKEN = re.compile(
    r"\s*(?:(?P<op>&&|\|\||==|!=|!|\(|\)|,)|(?P<str>'(?:[^']|'')*')|(?P<ident>[A-Za-z_][\w.-]*))"
)


def _tokenize(src: str) -> list[tuple[str, str]]:
    pos, out = 0, []
    src = src.strip()
    while pos < len(src):
        m = _TOKEN.match(src, pos)
        if not m:
            raise ValueError(f"cannot tokenize at {src[pos:]!r}")
        kind = m.lastgroup
        assert kind is not None
        out.append((kind, m.group(kind)))
        pos = m.end()
    return out


# --------------------------------------------------------------------------- semantics


def _truthy(v: Any) -> bool:
    return not (v is None or v is False or v == "" or v == 0)


def _equal(a: Any, b: Any) -> bool:
    if a is None:
        a = ""  # null coerces like the empty string for our purposes
    if b is None:
        b = ""
    if isinstance(a, str) and isinstance(b, str):
        return a.lower() == b.lower()
    return a == b


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]], ctx: dict[str, Any]):
        self.t, self.i, self.ctx = tokens, 0, ctx

    def _peek(self) -> tuple[str, str] | None:
        return self.t[self.i] if self.i < len(self.t) else None

    def _eat(self, val: str | None = None) -> tuple[str, str]:
        tok = self._peek()
        if tok is None or (val is not None and tok[1] != val):
            raise ValueError(f"expected {val!r}, got {tok!r}")
        self.i += 1
        return tok

    def parse(self) -> Any:
        v = self._or()
        if self._peek() is not None:
            raise ValueError(f"trailing tokens: {self.t[self.i :]!r}")
        return v

    def _or(self) -> Any:
        left = self._and()
        while self._peek() == ("op", "||"):
            self._eat()
            right = self._and()
            left = left if _truthy(left) else right
        return left

    def _and(self) -> Any:
        left = self._eq()
        while self._peek() == ("op", "&&"):
            self._eat()
            right = self._eq()
            left = right if _truthy(left) else left
        return left

    def _eq(self) -> Any:
        left = self._unary()
        while self._peek() in (("op", "=="), ("op", "!=")):
            op = self._eat()[1]
            right = self._unary()
            res = _equal(left, right)
            left = res if op == "==" else not res
        return left

    def _unary(self) -> Any:
        if self._peek() == ("op", "!"):
            self._eat()
            return not _truthy(self._unary())
        return self._primary()

    def _primary(self) -> Any:
        kind, val = self._eat()
        if kind == "str":
            return val[1:-1].replace("''", "'")
        if kind == "op" and val == "(":
            v = self._or()
            self._eat(")")
            return v
        if kind == "ident":
            if val.lower() == "fromjson":
                self._eat("(")
                arg = self._or()
                self._eat(")")
                return json.loads(arg)
            if val in ("true", "false", "null"):
                return {"true": True, "false": False, "null": None}[val]
            return _lookup(self.ctx, val)
        raise ValueError(f"unexpected token {val!r}")


def _lookup(ctx: dict[str, Any], dotted: str) -> Any:
    cur: Any = ctx
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def evaluate(expr: str, ctx: dict[str, Any]) -> Any:
    """Evaluate a ``${{ ... }}`` expression (or bare expression) against ``ctx``."""
    body = strip_wrapper(expr) if expr.lstrip().startswith("${{") else expr
    return _Parser(_tokenize(body), ctx).parse()


def make_context(
    event: str,
    *,
    fork: bool = False,
    dispatch_input: str | None = None,
    variable: str | None = None,
    repository: str = "owner/repo",
    runner_environment: str | None = None,
) -> dict[str, Any]:
    """Build the context dict the expression reads."""
    ctx: dict[str, Any] = {
        "github": {"event_name": event, "repository": repository, "event": {}},
        "vars": {},
        "inputs": {},
    }
    if event == "pull_request":
        head = "someone/repo" if fork else repository
        ctx["github"]["event"] = {"pull_request": {"head": {"repo": {"full_name": head}}}}
    if variable is not None:
        ctx["vars"]["CI_RUNNER_LANE"] = variable
    if dispatch_input is not None:
        ctx["inputs"]["runner_lane"] = dispatch_input
    if runner_environment is not None:
        ctx["runner"] = {"environment": runner_environment}
    return ctx
