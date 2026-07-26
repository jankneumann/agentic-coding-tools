"""Per-surface subset verifiers.

Each reads a live artifact, projects it into the declared surface's vocabulary,
and reports the elements that vocabulary does not contain.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from typing import Any

from gen_eval.descriptor import InterfaceDescriptor
from gen_eval.openapi import iter_operations
from gen_eval.verify.model import Violation, declared_elements

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
    seen: set[str] = set()

    # Shares the contract reader's traversal, so a route behind a `$ref` path
    # item is seen here exactly as it is seen there. Two readers disagreeing
    # about what a document declares is how a live route stays invisible to
    # the one check that exists to find it.
    for found in iter_operations(document):
        element = f"{found.method.upper()} {found.path}"
        if element in declared or element in seen:
            continue
        seen.add(element)
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


def _tool_name(tool: Any) -> str | None:
    """The name out of whichever shape the caller's MCP client returned."""
    if isinstance(tool, str):
        return tool
    if isinstance(tool, dict):
        name = tool.get("name")
        return name if isinstance(name, str) else None
    name = getattr(tool, "name", None)
    return name if isinstance(name, str) else None


def verify_mcp(
    tools: Iterable[Any],
    descriptor: InterfaceDescriptor,
) -> list[Violation]:
    """Report tools the server publishes and the service contract does not (D1).

    ``tools`` is the server's own listing — bare names, SDK records, or the
    dicts a ``tools/list`` response carries.

    The comparison is against the set of **bound** elements, never against one
    derived name per operation (D7). One tool may serve several operations:
    the coordinator's ``check_locks`` answers both ``list_active_locks`` and
    ``get_lock_status`` by branching on an argument being None. Comparing
    against derived names reports three findings on a conformant server — the
    tool that exists as excess, and two that do not as omissions — which is how
    a verifier trains its operators to ignore it.

    An operation the contract marks ``exposed: false`` on MCP contributes no
    element, so publishing it is a violation. That is the point of recording
    non-exposure rather than omitting the surface: the contract makes a claim
    about what agents cannot reach, and this is what checks it.
    """
    declared = declared_elements(descriptor, "mcp")
    violations: list[Violation] = []
    seen: set[str] = set()

    for tool in tools:
        name = _tool_name(tool)
        if name is None:
            continue
        element = f"mcp:{name}"
        if element in declared or element in seen:
            continue
        seen.add(element)
        violations.append(
            Violation(
                surface="mcp",
                element=element,
                message=(
                    f"{name} is published by the MCP server but absent from the "
                    f"service contract. Either contract it — on the operation it "
                    f"serves, as an mcp element binding — or stop publishing it."
                ),
            )
        )
    return violations
