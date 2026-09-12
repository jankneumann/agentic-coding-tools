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


# ---------------------------------------------------------------------------
# Prompt contract + coercion + timeout budget (harden-review-dispatch)
# ---------------------------------------------------------------------------

COERCION_FILENAME = "finding-coercion.json"
TIMEOUT_BUDGET_FILENAME = "dispatch-timeout-budget.json"

JUDGMENT = "judgment"
DETERMINISTIC = "deterministic"


def _find_sidecar_json(filename: str, start: Path | None = None) -> Path | None:
    """Locate a runtime JSON sidecar (coercion table or timeout budget).

    Looks beside this module, then ``openspec/schemas/``, then the
    skill-local ``install_assets`` copy. Does not bind to an OpenSpec
    change directory — those move on archive.
    """
    here = (start or Path(__file__)).resolve()
    candidates = [here.parent / filename]
    for base in [here, *here.parents]:
        candidates.append(base / "openspec" / "schemas" / filename)
        candidates.append(
            base / "install_assets" / "openspec" / "schemas" / filename
        )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


@lru_cache(maxsize=4)
def load_coercion_table() -> dict[str, Any]:
    path = _find_sidecar_json(COERCION_FILENAME)
    if path is None:
        raise SchemaNotFoundError(
            f"could not locate {COERCION_FILENAME} next to "
            f"{Path(__file__).name} or in openspec/schemas"
        )
    return json.loads(path.read_text())


@lru_cache(maxsize=4)
def load_timeout_budget() -> dict[str, Any]:
    path = _find_sidecar_json(TIMEOUT_BUDGET_FILENAME)
    if path is None:
        return {
            "schema_version": 1,
            "default_seconds": 300,
            "empty_findings_min_seconds": 15,
            "vendors": {},
        }
    return json.loads(path.read_text())


def timeout_for_vendor(vendor: str, override: int | None = None) -> int:
    """Return the subprocess timeout for *vendor*.

    An explicit *override* (CLI ``--timeout``) wins. Otherwise the versioned
    budget table is used, then ``default_seconds``.
    """
    if override is not None:
        return int(override)
    budget = load_timeout_budget()
    vendors = budget.get("vendors") or {}
    row = vendors.get(vendor) or {}
    return int(row.get("timeout_seconds") or budget.get("default_seconds") or 300)


def empty_findings_min_seconds() -> int:
    return int(load_timeout_budget().get("empty_findings_min_seconds") or 15)


def prompt_contract() -> tuple[tuple[str, ...], dict[str, tuple[str, ...]]]:
    """Return ``(required_fields, enums)`` for one finding, from the schema.

    This is the only field list review prompts may use. Hand-copied lists
    drift from the canonical file (2026-08-24 defect).
    """
    item = finding_item_schema()
    required = tuple(item.get("required") or ())
    enums = {
        name: tuple(spec["enum"])
        for name, spec in (item.get("properties") or {}).items()
        if isinstance(spec, dict) and spec.get("enum")
    }
    return required, enums


def prompt_contract_block() -> str:
    """Prose block listing required fields and enum vocabularies for a prompt."""
    required, enums = prompt_contract()
    required_list = ", ".join(required)
    lines = [
        f"REQUIRED on every finding — output is REJECTED if any is missing: {required_list}",
        "These fields use DIFFERENT vocabularies. Do not reuse one value for another:",
    ]
    if "criticality" in enums:
        lines.append(
            "  criticality: " + "|".join(enums["criticality"]) + " — how much it matters"
        )
    if "severity" in enums:
        lines.append(
            "  severity: " + "|".join(enums["severity"])
            + " — review-gate grading (NOT the same scale as criticality)"
        )
    if "axis" in enums:
        lines.append("  axis: " + "|".join(enums["axis"]))
    if "type" in enums:
        lines.append("  type: " + "|".join(enums["type"]))
    if "disposition" in enums:
        lines.append("  disposition: " + "|".join(enums["disposition"]))
    lines.append("Use exactly one value from each listed set; do not invent values.")
    lines.append("Output ONLY a JSON object with a top-level `findings` array.")
    return "\n".join(lines)


def coerce_findings_payload(
    payload: dict[str, Any],
    table: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Apply the alias table to *payload* before schema validation.

    Does not invent findings. Unknown enums are left unchanged so validation
    still fails closed. Returns ``(payload, coercion_notes)``.
    """
    table = table if table is not None else load_coercion_table()
    type_aliases: dict[str, str] = table.get("type_aliases") or {}
    axis_aliases: dict[str, str] = table.get("axis_aliases") or {}
    sev_from_crit: dict[str, str] = table.get("severity_from_criticality") or {}
    crit_from_sev: dict[str, str] = table.get("criticality_from_severity") or {}

    notes: list[str] = []
    findings = payload.get("findings")
    if not isinstance(findings, list):
        return payload, notes

    for finding in findings:
        if not isinstance(finding, dict):
            continue
        raw_type = finding.get("type")
        if isinstance(raw_type, str) and raw_type in type_aliases:
            finding["type"] = type_aliases[raw_type]
            notes.append(f"type:{raw_type}->{finding['type']}")
        if not finding.get("axis") and isinstance(raw_type, str) and raw_type in axis_aliases:
            finding["axis"] = axis_aliases[raw_type]
            notes.append(f"axis:{raw_type}->{finding['axis']}")
        elif isinstance(finding.get("axis"), str) and finding["axis"] in axis_aliases:
            old = finding["axis"]
            finding["axis"] = axis_aliases[old]
            notes.append(f"axis:{old}->{finding['axis']}")
        if not finding.get("severity") and isinstance(finding.get("criticality"), str):
            mapped = sev_from_crit.get(finding["criticality"])
            if mapped:
                finding["severity"] = mapped
                notes.append(f"severity:from-criticality:{finding['criticality']}")
        if not finding.get("criticality") and isinstance(finding.get("severity"), str):
            mapped = crit_from_sev.get(finding["severity"])
            if mapped:
                finding["criticality"] = mapped
                notes.append(f"criticality:from-severity:{finding['severity']}")
    return payload, notes


def stamp_judgment_ingest(
    payload: dict[str, Any],
    *,
    caller_declared_deterministic: bool = False,
) -> dict[str, Any]:
    """Stamp model-review findings as judgment unless the caller declared otherwise.

    A payload cannot promote itself to deterministic.
    """
    if caller_declared_deterministic:
        return payload
    findings = payload.get("findings")
    if not isinstance(findings, list):
        return payload
    for finding in findings:
        if isinstance(finding, dict):
            finding["evidence_class"] = JUDGMENT
    return payload

