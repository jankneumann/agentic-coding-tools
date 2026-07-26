"""The violation record and the declared surface every verifier compares against."""

from __future__ import annotations

from pydantic import BaseModel

from gen_eval.descriptor import InterfaceDescriptor

#: Identifier prefix per surface. HTTP elements carry none — they are spelled
#: ``"METHOD /path"`` — which is why membership is decided by *absence* of a
#: known prefix rather than by a prefix of its own.
_PREFIX = {"mcp": "mcp:", "cli": "cli:"}


class Violation(BaseModel):
    """One element the implementation exposes and the contract does not.

    Always excess, never omission — see the package docstring. There is no
    ``kind`` field because a second kind would be a second meaning for the same
    report, and coverage already owns the other one.
    """

    surface: str
    #: The element identifier, in the declared surface's vocabulary, so an
    #: operator can grep the contract for it directly.
    element: str
    message: str


def declared_elements(descriptor: InterfaceDescriptor, surface: str) -> set[str]:
    """Elements the contract declares on one surface.

    For a service descriptor this reads the operations' surface bindings, so a
    many-to-one binding contributes its **bound** element once rather than one
    derived name per operation. Comparing an implementation against derived
    names would report the tool that genuinely exists as undocumented excess
    and the names that do not exist as missing (D7).

    For a tool or hand-authored descriptor there are no operations, so the flat
    declared surface is filtered by identifier prefix.
    """
    operations = getattr(descriptor, "operations", None)
    if operations:
        return {
            element
            for operation in operations
            if (element := operation.interface_id(surface)) is not None
        }

    prefix = _PREFIX.get(surface)
    if prefix is None:
        # HTTP: everything that is not another surface's namespaced identifier.
        return {
            element
            for element in descriptor.all_interfaces()
            if not any(element.startswith(p) for p in _PREFIX.values())
        }
    return {element for element in descriptor.all_interfaces() if element.startswith(prefix)}
