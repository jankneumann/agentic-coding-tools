"""Findings ledger: dataclass, builder, contract-delete guard, and writer.

The ledger contract is ``install_assets/openspec/schemas/skill-audit-findings.schema.json``
(design D5). The guard here is the first line of defence: it raises before a
byte is written; the schema ``if/then`` is the second.

Ledgers are written with sorted keys and a trailing newline so two runs over
the same inputs are byte-identical (NFR "Determinism").
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parents[1]
SCHEMA_PATH = SKILL_DIR / "install_assets" / "openspec" / "schemas" / "skill-audit-findings.schema.json"

LAYERS = ("contract", "constraint", "procedure", "teaching", "unclassified")
KINDS = (
    "teaching_inferable",
    "procedure_without_probe",
    "constraint_without_reason",
    "contract_unpinned",
    "missing_deviation_protocol",
    "tier_concentrated_failure",
    "convention_drift",
)
REMEDIATIONS = ("keep", "move_to_reference", "extract_to_script", "add_probe", "add_reason", "delete")


class ContractDeleteError(ValueError):
    """A ``contract`` section was assigned ``remediation: delete``."""


class LedgerValidationError(ValueError):
    """The assembled ledger does not satisfy the findings schema."""


@dataclass
class Finding:
    kind: str
    layer: str
    section_id: str
    remediation: str
    rationale: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    id: str = ""

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown finding kind: {self.kind!r}")
        if self.layer not in LAYERS:
            raise ValueError(f"unknown layer: {self.layer!r}")
        if self.remediation not in REMEDIATIONS:
            raise ValueError(f"unknown remediation: {self.remediation!r}")

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "layer": self.layer,
            "section_id": self.section_id,
            "remediation": self.remediation,
            "evidence": dict(self.evidence),
        }
        if self.rationale:
            out["rationale"] = self.rationale
        return out


def guard_findings(findings: list[Finding]) -> None:
    """Raise ``ContractDeleteError`` if any contract finding says ``delete``.

    Called by ``build_ledger`` and again by ``write_ledger`` so a ledger dict
    assembled by hand cannot bypass it.
    """
    for f in findings:
        if f.layer == "contract" and f.remediation == "delete":
            raise ContractDeleteError(
                f"finding {f.id or '?'} ({f.kind}) on contract section {f.section_id!r} "
                "carries remediation=delete; contract sections are never deleted"
            )


def _guard_dicts(findings: list[dict[str, Any]]) -> None:
    for f in findings:
        if f.get("layer") == "contract" and f.get("remediation") == "delete":
            raise ContractDeleteError(
                f"finding {f.get('id', '?')} on contract section {f.get('section_id')!r} "
                "carries remediation=delete; contract sections are never deleted"
            )


def assign_ids(findings: list[Finding]) -> list[Finding]:
    """Give every finding a stable ``F###`` id in list order."""
    for index, f in enumerate(findings, 1):
        f.id = f"F{index:03d}"
    return findings


def build_ledger(
    *,
    skill: str,
    convention: str,
    generated_at: str,
    freshness: dict[str, Any],
    layers: list[dict[str, Any]],
    dispatch_profile: list[dict[str, Any]],
    evidence: dict[str, Any],
    findings: list[Finding],
) -> dict[str, Any]:
    """Assemble the ledger dict; runs the contract-delete guard first."""
    assign_ids(findings)
    guard_findings(findings)
    return {
        "schema_version": 1,
        "skill": skill,
        "generated_at": generated_at,
        "convention": convention,
        "freshness": {
            "archetypes_sha256": freshness["archetypes_sha256"],
            "reviewed_dates": list(freshness.get("reviewed_dates", [])),
            "evidence_window_days": int(freshness["evidence_window_days"]),
        },
        "layers": layers,
        "dispatch_profile": dispatch_profile,
        "evidence": evidence,
        "findings": [f.to_dict() for f in findings],
    }


def load_schema(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or SCHEMA_PATH).read_text(encoding="utf-8"))


def validate_ledger(ledger: dict[str, Any], *, schema: dict[str, Any] | None = None) -> None:
    """Validate against the shipped schema when jsonschema is importable."""
    try:
        import jsonschema
    except ImportError:  # pragma: no cover - consumer without the dependency
        return
    validator = jsonschema.Draft202012Validator(schema or load_schema())
    errors = sorted(validator.iter_errors(ledger), key=lambda e: list(e.absolute_path))
    if errors:
        joined = "\n  - ".join(
            f"$.{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors
        )
        raise LedgerValidationError(f"ledger failed schema validation:\n  - {joined}")


def ledger_bytes(ledger: dict[str, Any]) -> bytes:
    return (json.dumps(ledger, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def write_ledger(ledger: dict[str, Any], path: Path) -> Path:
    """Guard, validate, then write. Nothing touches disk if either step fails."""
    _guard_dicts(list(ledger.get("findings", [])))
    validate_ledger(ledger)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ledger_bytes(ledger))
    return path


__all__ = [
    "KINDS",
    "LAYERS",
    "REMEDIATIONS",
    "SCHEMA_PATH",
    "ContractDeleteError",
    "Finding",
    "LedgerValidationError",
    "assign_ids",
    "build_ledger",
    "guard_findings",
    "ledger_bytes",
    "load_schema",
    "validate_ledger",
    "write_ledger",
]
