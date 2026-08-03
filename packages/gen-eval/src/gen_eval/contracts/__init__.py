"""Versioned JSON Schema contract for gen-eval's public data shapes.

The point of this package is to *decouple schema conformance from runtime
availability*. A consumer that wants to validate its interface descriptor,
its scenarios, or a gen-eval report it received does not need gen-eval
installed — it can read these ``.json`` files straight out of the repository
(or a raw URL), pin :data:`CONTRACT_VERSION`, and validate with nothing but
the stdlib plus a JSON Schema validator.

The files are also shipped inside the wheel, so an installed consumer can
load them via :func:`load_schema` instead of vendoring a copy.

All four artifacts are *generated* by ``scripts/generate_contract_schemas.py``
from the pydantic models that actually produce and consume the data. A test
regenerates them into a temp directory and diffs against the checked-in
copies, so the published contract cannot silently drift from the code.

Versioning
----------
:data:`CONTRACT_VERSION` is the source of truth; the ``VERSION`` file is a
generated artifact for non-Python consumers. Bump it on any *breaking* schema
change (field removed, field made required, type narrowed). Additive changes
— a new optional field — do not require a bump.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_FILENAMES",
    "load_schema",
    "schema_path",
]

#: Contract version. Source of truth for the generated ``VERSION`` file.
#:
#: 1 -> 2: the element/container models were renamed to the ``*Spec`` suffix
#: (``EndpointSpec``, ``McpToolSpec``, ``CommandSpec``, ``ServiceSpec``), which
#: changes the ``$defs`` keys and titles published in
#: ``interface-descriptor.schema.json``. Consumers pinning ``$defs`` names must
#: update; the Python names keep warning aliases for one release.
CONTRACT_VERSION = "2"

#: Logical schema name -> filename shipped in this package.
SCHEMA_FILENAMES: dict[str, str] = {
    "interface-descriptor": "interface-descriptor.schema.json",
    "scenario": "scenario.schema.json",
    "eval-report": "eval-report.schema.json",
}


def _resolve(name: str) -> str:
    try:
        return SCHEMA_FILENAMES[name]
    except KeyError:
        known = ", ".join(sorted(SCHEMA_FILENAMES))
        raise KeyError(f"unknown schema {name!r}; known schemas: {known}") from None


def schema_path(name: str) -> Any:
    """Return an ``importlib.resources`` traversable for a published schema.

    Args:
        name: One of the keys of :data:`SCHEMA_FILENAMES`.

    Raises:
        KeyError: If ``name`` is not a published schema.
    """
    return resources.files(__package__) / _resolve(name)


def load_schema(name: str) -> dict[str, Any]:
    """Load and parse a published JSON Schema document.

    Args:
        name: One of the keys of :data:`SCHEMA_FILENAMES`.

    Raises:
        KeyError: If ``name`` is not a published schema.
    """
    data: dict[str, Any] = json.loads(schema_path(name).read_text(encoding="utf-8"))
    return data
