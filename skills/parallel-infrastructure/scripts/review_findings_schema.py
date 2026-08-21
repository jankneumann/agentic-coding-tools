"""Canonical review-findings schema access — single source of truth.

The review-findings JSON schema used to be duplicated in three places:

* inlined as a ``--json-schema`` string in ``agent-coordinator/agents.yaml``
  (grok's structured-output arg),
* implicitly assumed by ``review_dispatcher.py`` when it parsed vendor output,
* implicitly assumed by ``consensus_synthesizer.py`` when it merged findings.

Every copy could drift from ``openspec/schemas/review-findings.schema.json``.
This module makes all of them read the ONE canonical file:

* the dispatch adapter injects the schema into grok's ``--json-schema`` arg
  (``grok_schema_arg``) instead of carrying a hand-copied JSON blob in
  agents.yaml — agents.yaml only holds the :data:`GROK_SCHEMA_SENTINEL`
  placeholder, which the adapter replaces at build time,
* the dispatcher validates parsed findings against the schema
  (:func:`validate_findings_payload`),
* the synthesizer validates each per-vendor findings file against the schema
  (:func:`validate_findings_document`).

Validation is MANDATORY on the review path, not best-effort. ``jsonschema`` is
a declared dependency of both ``skills/pyproject.toml`` and
``agent-coordinator/pyproject.toml``, so its absence is a broken environment,
not a supported degraded mode. When it cannot be imported the validators raise
:class:`ValidationUnavailableError` instead of returning ``[]``.

That distinction is the whole point of the item. A validator that returns "no
errors" when it could not run is indistinguishable from one that checked and
found nothing — which is exactly how a drifted finding reaches consensus while
the logs claim enforcement. Every unenforceable condition on this path fails
loudly; none of them degrade to a pass.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

SCHEMA_FILENAME = "review-findings.schema.json"

# Placeholder that stands in agents.yaml where the grok ``--json-schema`` value
# used to be inlined. ``CliVendorAdapter.build_command`` replaces it with the
# schema derived from the canonical file so the two can never drift.
GROK_SCHEMA_SENTINEL = "@review-findings-schema"


class SchemaNotFoundError(FileNotFoundError):
    """Raised when the canonical review-findings schema cannot be located."""


def find_schema_path(start: Path | None = None) -> Path:
    """Locate ``review-findings.schema.json`` by walking up from *start*.

    Prefers a repo-root ``openspec/schemas/`` copy (the canonical, installed
    location) and falls back to a skill-local ``install_assets/openspec/
    schemas/`` copy so the dispatcher still resolves the schema when it runs
    from inside the skill's source tree before an install has projected it to
    the repo root.
    """
    here = (start or Path(__file__)).resolve()
    bases = [here, *here.parents]

    for base in bases:
        candidate = base / "openspec" / "schemas" / SCHEMA_FILENAME
        if candidate.is_file():
            return candidate
    for base in bases:
        candidate = (
            base / "install_assets" / "openspec" / "schemas" / SCHEMA_FILENAME
        )
        if candidate.is_file():
            return candidate

    raise SchemaNotFoundError(
        f"could not locate {SCHEMA_FILENAME} in openspec/schemas or "
        f"install_assets/openspec/schemas above {here}"
    )


@lru_cache(maxsize=8)
def _load_schema_text(path_str: str) -> str:
    return Path(path_str).read_text()


def load_schema(path: Path | None = None) -> dict[str, Any]:
    """Return the parsed canonical schema (fresh dict per call)."""
    schema_path = path or find_schema_path()
    return json.loads(_load_schema_text(str(schema_path)))


def finding_item_schema(schema: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the JSON-schema for a single finding object."""
    schema = schema if schema is not None else load_schema()
    return schema["properties"]["findings"]["items"]


def derive_output_schema(schema: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the grok ``--json-schema`` value from the canonical schema.

    Vendors are asked to emit only the ``{"findings": [...]}`` object (no
    ``review_type``/``target`` envelope — those are supplied by the dispatcher
    when it writes the per-vendor file), so wrap the canonical ``findings``
    array subschema. Deriving it here means the finding shape has exactly one
    definition: the canonical file.
    """
    schema = schema if schema is not None else load_schema()
    return {
        "type": "object",
        "required": ["findings"],
        "properties": {"findings": schema["properties"]["findings"]},
    }


def grok_schema_arg(schema: dict[str, Any] | None = None) -> str:
    """Return the compact JSON string for grok's ``--json-schema`` argument."""
    return json.dumps(derive_output_schema(schema), separators=(",", ":"))


class ValidationUnavailableError(RuntimeError):
    """Raised when the schema cannot be enforced because ``jsonschema`` is absent.

    Distinct from a validation *failure*: this says the check could not run at
    all. Callers on the review path must treat it as a hard error rather than
    as "no errors found" — see the module docstring.
    """


def _validate(data: Any, schema: dict[str, Any]) -> list[str]:
    """Validate *data* against *schema*; return human-readable error strings.

    Returns ``[]`` only when *data* is actually valid. When ``jsonschema`` is
    not importable this raises :class:`ValidationUnavailableError` rather than
    returning ``[]``: an empty error list is indistinguishable from "checked
    and clean", and returning it here is what let an unenforceable schema read
    as an enforced one.
    """
    try:
        import jsonschema  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ValidationUnavailableError(
            "the 'jsonschema' package is required to enforce "
            f"{SCHEMA_FILENAME} but is not importable"
        ) from exc

    validator = jsonschema.Draft202012Validator(schema)
    errors = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        location = "/".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"{location}: {err.message}")
    return errors


def validate_findings_payload(
    payload: dict[str, Any], schema: dict[str, Any] | None = None
) -> list[str]:
    """Validate a ``{"findings": [...]}`` payload (vendor output shape).

    Checks the findings array against the canonical finding shape without
    requiring the ``review_type``/``target`` envelope, which vendors do not
    emit. Returns a list of error strings ([] when valid or jsonschema absent).
    """
    output_schema = derive_output_schema(schema)
    return _validate(payload, output_schema)


def validate_findings_document(
    document: dict[str, Any], schema: dict[str, Any] | None = None
) -> list[str]:
    """Validate a full per-vendor findings document against the canonical schema.

    The document shape is ``{review_type, target, [reviewer_vendor,] findings}``
    as written by ``checkpoint_findings.write_vendor_findings``. Returns a list
    of error strings ([] when valid or jsonschema absent).
    """
    schema = schema if schema is not None else load_schema()
    return _validate(document, schema)
