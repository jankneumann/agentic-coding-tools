"""Reading an OpenAPI document — the parts both the extractor and verifier need.

Two places in this package walk an OpenAPI document: ``service_descriptor``
derives the declared surface from the *contract*, and ``verify.surfaces`` reads
the document a *live application* generates. They ask different questions of
different documents, but "what operations does this document declare?" has one
correct answer, and both got it wrong the same way — iterating a path item's
keys and keeping those that look like HTTP verbs, which silently drops
``$ref`` path items and ignores path-level ``parameters``.

Sharing the traversal is right here, and is *not* the pattern the generator
scripts deliberately avoid. Those duplicate their **counting** on purpose,
because a drift guard that shares an implementation with the thing it guards
proves nothing. Nothing in this module counts anything; it is a reader, and two
readers disagreeing about what a document says is the defect, not the safeguard.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, NamedTuple

#: Path-item keys that name an operation. Everything else in a path item —
#: ``parameters``, ``summary``, ``servers``, ``$ref`` — is a sibling of the
#: verbs, not a verb, and reading one as an operation would invent routes.
HTTP_METHODS = frozenset(
    {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
)

_PATH_ITEM_REF_PREFIX = "#/components/pathItems/"


class DocumentOperation(NamedTuple):
    """One operation, with its path-item context already folded in."""

    path: str
    method: str
    #: The operation object itself.
    raw: dict[str, Any]
    #: Path-level parameters merged with the operation's own. Path-item
    #: parameters are siblings of the verbs and apply to every operation
    #: beneath them, so an operation that ignores them is published without
    #: arguments it cannot work without.
    parameters: list[dict[str, Any]]
    #: The resolved path item, so callers can read its own extension keys.
    item: dict[str, Any]


def resolve_path_item(
    item: dict[str, Any], document: dict[str, Any], path: str
) -> dict[str, Any]:
    """Resolve a ``$ref`` path item against the document that carries it.

    Only local ``#/components/pathItems/<name>`` references resolve. An
    external reference names another file, and following it would make the
    declared surface depend on filesystem state at derivation time.

    Anything unresolvable raises. Skipping it is the failure this exists to
    prevent: the operation disappears from the declared surface, coverage of
    nothing reports complete, and no error is ever printed.

    Sibling keys beside a ``$ref`` also raise, for the same reason one level
    down. Returning the target alone silently discards them, and a discarded
    ``parameters`` list means the derived operation is missing required path
    parameters that the document plainly declared. OAS 3.1 permits ``summary``
    and ``description`` beside a ``$ref`` and neither affects the declared
    surface, so those two are allowed through; anything else is a claim being
    dropped, and this refuses rather than guesses which of the two definitions
    was meant to win.
    """
    ref = item.get("$ref")
    if not ref:
        return item
    siblings = set(item) - {"$ref", "summary", "description"}
    if siblings:
        raise ValueError(
            f"{path}: path item declares {sorted(siblings)} alongside "
            f"$ref {ref!r}. Only summary and description may accompany a "
            f"$ref — everything else would be silently discarded when the "
            f"reference is resolved, and a dropped `parameters` list yields "
            f"operations missing parameters the document declares. Move them "
            f"into the referenced path item."
        )
    if not isinstance(ref, str) or not ref.startswith(_PATH_ITEM_REF_PREFIX):
        raise ValueError(
            f"{path}: cannot resolve path item $ref {ref!r}. Only local "
            f"{_PATH_ITEM_REF_PREFIX}<name> references are supported; an "
            f"external reference would make the declared surface depend on "
            f"filesystem state."
        )
    name = ref[len(_PATH_ITEM_REF_PREFIX) :]
    target = ((document.get("components") or {}).get("pathItems") or {}).get(name)
    if not isinstance(target, dict):
        raise ValueError(
            f"{path}: path item $ref {ref!r} resolves to nothing — "
            f"components.pathItems has no {name!r}"
        )
    return target


def iter_operations(document: dict[str, Any]) -> Iterator[DocumentOperation]:
    """Yield every operation the document declares, refs resolved.

    ``path`` and ``method`` come from where the reference *sits*, not from
    where its target is stored — two paths may share one path item, and each
    is its own route.
    """
    for path, item in (document.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        resolved = resolve_path_item(item, document, path)
        shared = [p for p in (resolved.get("parameters") or []) if isinstance(p, dict)]
        for method, raw in resolved.items():
            if method.lower() not in HTTP_METHODS or not isinstance(raw, dict):
                continue
            own = [p for p in (raw.get("parameters") or []) if isinstance(p, dict)]
            yield DocumentOperation(
                path=path,
                method=method,
                raw=raw,
                parameters=_merge_parameters(shared, own),
                item=resolved,
            )


def _merge_parameters(
    shared: list[dict[str, Any]], own: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Path-level parameters, overridden by the operation's own.

    OpenAPI identifies a parameter by ``(name, in)``, and an operation-level
    entry replaces the path-level one it matches rather than adding a
    duplicate.
    """
    merged = {(p.get("name"), p.get("in")): p for p in shared}
    merged.update({(p.get("name"), p.get("in")): p for p in own})
    return list(merged.values())
