"""Per-surface subset verifiers.

Each reads a live artifact, projects it into the declared surface's vocabulary,
and reports the elements that vocabulary does not contain.
"""

from __future__ import annotations

import argparse
from typing import Any

from gen_eval.descriptor import InterfaceDescriptor
from gen_eval.verify.model import Violation, declared_elements

#: OpenAPI path-item keys that name an operation. Everything else in a path
#: item — ``parameters``, ``summary``, ``servers`` — is a sibling of the verbs,
#: not a verb, and reading it as one would invent routes.
_HTTP_METHODS = frozenset(
    {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
)

#: argparse action classes the library installs itself. The application never
#: declared them, so a contract that omits them is correct and reporting them
#: would make the verifier wrong on every argparse program.
_LIBRARY_ACTIONS: tuple[type[argparse.Action], ...] = (
    argparse._HelpAction,
    argparse._VersionAction,
)


def _action_name(action: argparse.Action) -> str | None:
    """The flag an action declares, preferring its long spelling.

    One action is one flag however many spellings it carries, so ``--quiet
    -q`` is reported once under ``--quiet``. A positional has no option strings
    and returns None: it is a different coverage unit, and the contract names
    it under ``positionals`` rather than ``flags``.
    """
    long_names = [name for name in action.option_strings if name.startswith("--")]
    if long_names:
        return long_names[0]
    return action.option_strings[0] if action.option_strings else None


def verify_argparse(
    parser: argparse.ArgumentParser,
    descriptor: InterfaceDescriptor,
    *,
    command: str = "",
) -> list[Violation]:
    """Report flags the parser declares and the tool contract does not (D1).

    ``command`` names the subcommand the parser serves, for a program whose
    contract declares more than one; a flat CLI leaves it empty and its units
    are bare flags.

    Only excess is reported. A contracted flag this parser lacks is a coverage
    gap the coverage model already names — see the package docstring.
    """
    declared = declared_elements(descriptor, "cli")
    violations: list[Violation] = []
    seen: set[str] = set()

    for action in parser._actions:
        if isinstance(action, _LIBRARY_ACTIONS):
            continue
        flag = _action_name(action)
        if flag is None:
            continue
        element = "cli:" + " ".join(part for part in (command, flag) if part)
        if element in declared or element in seen:
            continue
        seen.add(element)
        violations.append(
            Violation(
                surface="cli",
                element=element,
                message=(
                    f"{flag} is declared by the argument parser but absent from the "
                    f"tool contract. Either contract it or remove it — a flag users "
                    f"can reach that nothing documents is undocumented surface."
                ),
            )
        )
    return violations


def verify_fastapi(
    app_or_document: Any,
    descriptor: InterfaceDescriptor,
) -> list[Violation]:
    """Report routes the application serves and the service contract does not (D1).

    Takes either a FastAPI application — anything with a callable ``openapi()``
    — or the document that call already returned. Introspecting the generated
    document rather than the router is deliberate: it is the same artifact the
    contract is written against, so a route and its contracted counterpart are
    spelled identically and no path normalisation is needed between them.

    fastapi is not imported. It is a consumer dependency, not gen-eval's, and
    duck-typing ``openapi()`` keeps it out of this package's install.
    """
    document = app_or_document
    openapi = getattr(app_or_document, "openapi", None)
    if callable(openapi):
        document = openapi()

    declared = declared_elements(descriptor, "http")
    violations: list[Violation] = []

    for path, item in (document.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method in item:
            if method.lower() not in _HTTP_METHODS:
                continue
            element = f"{method.upper()} {path}"
            if element in declared:
                continue
            violations.append(
                Violation(
                    surface="http",
                    element=element,
                    message=(
                        f"{element} is served by the application but absent from the "
                        f"service contract. Either contract it or remove it — a route "
                        f"callers can reach that nothing documents is undocumented "
                        f"surface."
                    ),
                )
            )
    return violations
