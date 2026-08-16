"""Shared axis/severity vocabulary for the structural architecture linters.

`review-findings.schema.json` marks both `axis` and `severity` as required on
every finding, so each linter must emit them. The mapping below is mechanical
and derived from behavior that already exists: `run_architecture_linters.py`
exits non-zero on `critical`/`high` criticality, so those are exactly the
findings that block — they map to the `critical` severity prefix. The
non-blocking criticalities (`medium`/`low`) map to `nit` ("should fix but does
not block. Quality, naming, minor structure").
"""

from __future__ import annotations

# criticality (review-findings `criticality` enum) -> severity (5-severity prefix)
_SEVERITY_BY_CRITICALITY: dict[str, str] = {
    "critical": "critical",
    "high": "critical",
    "medium": "nit",
    "low": "nit",
}

_DEFAULT_SEVERITY = "fyi"


def severity_for_criticality(criticality: str) -> str:
    """Map a linter's criticality onto the 5-value `severity` enum.

    Unknown criticalities fall back to `fyi` (informational) rather than
    raising — a linter must never fail the pipeline over its own labelling.
    """
    return _SEVERITY_BY_CRITICALITY.get(criticality, _DEFAULT_SEVERITY)
