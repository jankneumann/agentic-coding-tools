"""Auth-flow env-var resolution for the Playwright validator.

Per the gen-eval-framework spec (Browser-Driving Behavioral Validation via
Playwright CLI), env-var references in ``auth_flow[].value`` MUST be resolved
via string-template substitution -- NOT shell expansion -- and a missing env
var MUST fail fast with a clear error before any browser is started.

This module implements that contract:

* Only the ``${VAR_NAME}`` form is recognized (the schema's regex is
  ``^[A-Z_][A-Z0-9_]*$``); other shell syntaxes (``$VAR``, ``${VAR:-foo}``,
  ``$(cmd)``) are passed through unchanged.
* Substitution is done via Python's :mod:`string` module's ``Template`` -- NEVER
  via ``subprocess`` / shell -- so no shell expansion can occur.
* Missing variables raise :class:`MissingEnvVar` whose message contains the
  exact env var name as required by the spec scenario "Auth flow with missing
  env var fails fast".
"""

from __future__ import annotations

import os
import re
from typing import Iterable, Mapping

# Matches ${VAR_NAME} per the schema: capital letter or underscore start,
# capital letters / digits / underscores after.
ENV_VAR_REF = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


class MissingEnvVar(RuntimeError):
    """Raised when ``auth_flow.value`` references an env var that isn't set.

    The pipeline contract is to exit non-zero BEFORE starting any browser
    when this is raised. The exception message MUST name the missing var.
    """

    def __init__(self, var_name: str, *, context: str = "auth_flow"):
        self.var_name = var_name
        self.context = context
        super().__init__(
            f"{context}: required env var {var_name} not set"
        )


def referenced_env_vars(template: str) -> list[str]:
    """Return the list of distinct ``${VAR}`` names referenced in ``template``.

    Order is the order of first appearance.
    """
    seen: list[str] = []
    for match in ENV_VAR_REF.finditer(template):
        name = match.group(1)
        if name not in seen:
            seen.append(name)
    return seen


def resolve_value(
    template: str, env: Mapping[str, str] | None = None
) -> str:
    """Substitute ``${VAR}`` references in ``template``.

    Args:
        template: The raw value from a descriptor's ``auth_flow[].value``.
        env: Optional explicit mapping. When ``None``, falls back to
            :data:`os.environ`.

    Returns:
        The substituted string.

    Raises:
        MissingEnvVar: If any referenced var is not present in ``env`` (or
            ``os.environ`` when ``env is None``). The pipeline interprets
            this as fail-fast -- no browser launch.
    """
    if env is None:
        env = os.environ

    needed = referenced_env_vars(template)
    for var in needed:
        if var not in env:
            raise MissingEnvVar(var)

    # Direct ``${VAR}`` substitution only -- we do NOT want
    # :class:`string.Template`'s broader behavior (which also expands
    # ``$VAR`` bare references and errors on lone ``$``). The schema's
    # value field is meant for literal text with explicit ``${VAR}``
    # placeholders; anything else is passed through unchanged.
    def _sub(match: re.Match[str]) -> str:
        return env[match.group(1)]

    return ENV_VAR_REF.sub(_sub, template)


def validate_required_env_vars(
    descriptor: Mapping[str, object],
    env: Mapping[str, str] | None = None,
) -> None:
    """Verify ``descriptor.env_vars_required`` are all present.

    Also walks ``descriptor.auth_flow[].value`` for any ``${VAR}`` references
    not declared in ``env_vars_required`` and ensures those are present too
    (defensive: the descriptor MAY omit the explicit list).

    Args:
        descriptor: A frontend-descriptor dict.
        env: Optional env mapping; defaults to :data:`os.environ`.

    Raises:
        MissingEnvVar: For the first missing var encountered. Order of
            checking is: ``env_vars_required`` first (in declaration order),
            then auth_flow refs (in flow order).
    """
    if env is None:
        env = os.environ

    required: Iterable[str] = descriptor.get("env_vars_required", []) or []  # type: ignore[assignment]
    for var in required:
        if var not in env:
            raise MissingEnvVar(var)

    auth_flow = descriptor.get("auth_flow", []) or []
    for step in auth_flow:  # type: ignore[union-attr]
        if not isinstance(step, dict):
            continue
        value = step.get("value")
        if not isinstance(value, str):
            continue
        # Detect malformed env-var refs: `${...` without a closing `}` would
        # otherwise pass through silently and end up as a literal string
        # passed to Playwright (cryptic later failure). Fail fast here by
        # counting `${` opens vs well-formed `${...}` pairs.
        open_count = value.count("${")
        close_count = sum(1 for _ in re.finditer(r"\$\{[^}]*\}", value))
        if open_count > close_count:
            raise MissingEnvVar(
                f"malformed env var reference in auth_flow value "
                f"(unclosed `${{`): {value!r}"
            )
        # resolve_value raises if any ref missing.
        resolve_value(value, env)


__all__ = [
    "ENV_VAR_REF",
    "MissingEnvVar",
    "referenced_env_vars",
    "resolve_value",
    "validate_required_env_vars",
]
