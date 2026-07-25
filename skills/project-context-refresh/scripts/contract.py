"""Offline validation of adapter output against the ri-06 ``ProducerResult`` def.

ri-05 MUST NOT define a producer-result wire model (design D2, contract
``contracts/README.md``). Instead every adapter returns the strict ri-06
:class:`ProducerResult`, and this module proves the serialized form validates
directly against
``context-refresh-types.schema.json#/$defs/ProducerResult`` — the same installed
schema the durable operation store uses — with no network fetch and no local
copy of the schema.

Validation here is deliberately redundant with ``ProducerResult.__post_init__``:
the dataclass enforces the *conditional* Python invariants, while this check
proves the *wire contract* the orchestrator (ri-07) will record without any
field-name or status translation layer.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from _runtime import ProducerResult, RUNTIME_SCRIPTS_DIR

_SCHEMA_DIR = RUNTIME_SCRIPTS_DIR.parent / "install_assets" / "openspec" / "schemas"
_TYPES_SCHEMA = "context-refresh-types.schema.json"
_PRODUCER_RESULT_POINTER = "#/$defs/ProducerResult"


class ContractValidationError(Exception):
    """An adapter result failed the canonical ri-06 ProducerResult schema."""


@functools.lru_cache(maxsize=1)
def _producer_result_validator() -> Draft202012Validator:
    """Build a cached validator for the ProducerResult ``$def``.

    Every installed types/operation/manifest schema is registered under its
    absolute ``$id`` so sibling ``$ref`` values resolve locally. The validator's
    own schema is a one-line ``$ref`` into the ProducerResult subschema.
    """
    resources: list[tuple[str, Resource[dict[str, Any]]]] = []
    types_id: str | None = None
    for path in sorted(_SCHEMA_DIR.glob("*.schema.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        resources.append(
            (data["$id"], Resource.from_contents(data, default_specification=DRAFT202012))
        )
        if path.name == _TYPES_SCHEMA:
            types_id = data["$id"]
    if types_id is None:  # pragma: no cover - install layout invariant
        raise ContractValidationError(
            f"installed schema {_TYPES_SCHEMA!r} not found under {_SCHEMA_DIR}"
        )
    registry = Registry().with_resources(resources)
    return Draft202012Validator(
        {"$ref": f"{types_id}{_PRODUCER_RESULT_POINTER}"}, registry=registry
    )


def validate_producer_result_dict(data: object) -> None:
    """Raise :class:`ContractValidationError` if *data* is not a ProducerResult.

    Error messages are path-sorted and stable so a schema violation reads the
    same across runs and machines.
    """
    validator = _producer_result_validator()
    errors = sorted(validator.iter_errors(data), key=lambda err: list(err.absolute_path))
    if errors:
        rendered = "; ".join(
            f"{'/'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}"
            for err in errors
        )
        raise ContractValidationError(
            f"ProducerResult schema validation failed: {rendered}"
        )


def validate_producer_result(result: ProducerResult) -> ProducerResult:
    """Validate a :class:`ProducerResult` instance and return it unchanged.

    Serializes through the canonical ``to_dict`` wire form so the check exercises
    exactly what ri-07 would persist.
    """
    validate_producer_result_dict(result.to_dict())
    return result


def schema_dir() -> Path:
    """Return the installed schema directory (for tests and diagnostics)."""
    return _SCHEMA_DIR
