"""Emits review-findings-conformant findings-gen-eval.json from gen-eval results.

This module implements the "Behavioral Findings Schema Conformance" requirement
from openspec/changes/factory-missions-architecture-alignment/specs/gen-eval-framework/spec.md
and the "Behavioral Findings in Consensus Surface" requirement from the
evaluation-framework spec delta.

Each failing scenario produces one finding with ``type: behavioral_failure``. When
the failing scenario was generated under an OpenSpec scenario constraint
(``Scenario.source.openspec_scenario`` is set, in the form ``<file>:<start>-<end>``),
the emitted finding's location points back to the originating spec file/lines so
operators can trace failures to requirements rather than to gen-eval's internal
scenario YAML.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger(__name__)


def _load_review_findings_schema() -> dict[str, Any] | None:
    """Best-effort load of openspec/schemas/review-findings.schema.json.

    Walks parent directories from this module looking for an `openspec/schemas/`
    directory. Returns None if the schema can't be located — producer-side
    validation is defense-in-depth; the consumer (consensus_synthesizer) also
    validates, so a missing schema here degrades gracefully.
    """
    here = Path(__file__).resolve()
    for ancestor in (here, *here.parents):
        candidate = ancestor / "openspec" / "schemas" / "review-findings.schema.json"
        if candidate.is_file():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("failed to load schema for producer-side validation: %s", exc)
                return None
    return None


def _atomic_write_json(output_path: Path, document: dict[str, Any]) -> None:
    """Write JSON atomically: tempfile in the same dir, fsync, then rename.

    Prevents partially-written files from being read by downstream consumers
    if the process crashes or runs out of disk mid-write.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=output_path.name + ".",
        suffix=".tmp",
        dir=str(output_path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(document, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, output_path)
    except Exception:
        # Cleanup tempfile on any failure to avoid orphans.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

# ---------------------------------------------------------------------------
# Source-location parsing
# ---------------------------------------------------------------------------

# openspec_scenario format: "<file>:<start>-<end>"
# E.g. "openspec/changes/foo/specs/api/spec.md:42-50"
_SOURCE_REF = re.compile(r"^(?P<file>.+):(?P<start>\d+)-(?P<end>\d+)$")


def parse_openspec_source(
    ref: str | None,
) -> tuple[str | None, int | None, int | None]:
    """Parse an ``openspec_scenario`` ref into (file, line_start, line_end).

    Returns (None, None, None) when ``ref`` is falsy or unparseable.
    """
    if not ref:
        return None, None, None
    match = _SOURCE_REF.match(ref.strip())
    if not match:
        return None, None, None
    try:
        return match["file"], int(match["start"]), int(match["end"])
    except (ValueError, KeyError):
        return None, None, None


# ---------------------------------------------------------------------------
# Finding data model
# ---------------------------------------------------------------------------

# review-findings.schema.json criticality enum
VALID_CRITICALITY = ("low", "medium", "high", "critical")
# review-findings.schema.json disposition enum
VALID_DISPOSITION = ("fix", "regenerate", "accept", "escalate")


@dataclass
class BehavioralFinding:
    """A single behavioral_failure finding ready for serialization.

    Conforms to the per-finding object shape required by
    ``openspec/schemas/review-findings.schema.json``.
    """

    id: int
    description: str
    criticality: str = "high"
    disposition: str = "fix"
    type: str = "behavioral_failure"
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a schema-conformant dict.

        Only emits keys whose values are populated (so a scenario without an
        OpenSpec source doesn't produce an empty ``line_range``).
        """
        out: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "criticality": self.criticality,
            "description": self.description,
            "disposition": self.disposition,
        }
        if self.file_path:
            out["file_path"] = self.file_path
        if self.line_start is not None and self.line_end is not None:
            out["line_range"] = {
                "start": self.line_start,
                "end": self.line_end,
            }
        return out


# ---------------------------------------------------------------------------
# Emitter
# ---------------------------------------------------------------------------


def _scenario_failed(scenario: Any) -> bool:
    """Return True when the scenario object represents a failure.

    Accepts either:
      * a ``Scenario`` paired with a status attr (``.status`` in
        {"fail","error"}) — used by tests that pass a small wrapper, or
      * a ``ScenarioVerdict`` whose ``.status`` is ``fail``/``error``.
    Falls back to ``True`` (treat as failed) when no status is present so that
    callers passing a pre-filtered list of failures still get findings.
    """
    status = getattr(scenario, "status", None)
    if status is None:
        return True
    return status in ("fail", "error")


def _resolve_location(scenario: Any) -> tuple[str | None, int | None, int | None]:
    """Resolve (file_path, line_start, line_end) for a failing scenario.

    Precedence:
      1. ``scenario.source.openspec_scenario`` — points at the originating spec.
      2. ``scenario.source.template_path`` — the gen-eval scenario YAML.
      3. ``"unknown"`` fallback.
    """
    source = getattr(scenario, "source", None)
    if source is not None:
        ref = getattr(source, "openspec_scenario", None)
        file_path, start, end = parse_openspec_source(ref)
        if file_path:
            return file_path, start, end
        template_path = getattr(source, "template_path", None)
        if template_path:
            return template_path, None, None
    return "unknown", None, None


def _scenario_description(scenario: Any) -> str:
    """Build a human-readable description for a behavioral failure."""
    name = (
        getattr(scenario, "scenario_name", None)
        or getattr(scenario, "name", None)
        or getattr(scenario, "scenario_id", None)
        or getattr(scenario, "id", None)
        or "unknown scenario"
    )
    failure_summary = getattr(scenario, "failure_summary", None)
    if failure_summary:
        return f"Behavioral failure in scenario '{name}': {failure_summary}"
    return f"Behavioral failure in scenario '{name}'"


def _scenario_metadata(scenario: Any) -> dict[str, Any]:
    """Collect optional metadata fields per findings-vendor-source contract."""
    meta: dict[str, Any] = {}
    scenario_id = getattr(scenario, "scenario_id", None) or getattr(
        scenario, "id", None
    )
    if scenario_id:
        meta["scenario_id"] = scenario_id
    return meta


def build_findings(
    failed_scenarios: Sequence[Any],
) -> list[BehavioralFinding]:
    """Build BehavioralFinding instances for the supplied failing scenarios.

    Caller is responsible for filtering to failed scenarios (by status or other
    means) when passing a heterogeneous list. As a safety net, this function
    will additionally skip any item that exposes a ``status`` of ``pass``/``skip``.
    """
    findings: list[BehavioralFinding] = []
    next_id = 1
    for scenario in failed_scenarios:
        if not _scenario_failed(scenario):
            continue
        file_path, start, end = _resolve_location(scenario)
        findings.append(
            BehavioralFinding(
                id=next_id,
                description=_scenario_description(scenario),
                criticality="high",
                disposition="fix",
                file_path=file_path,
                line_start=start,
                line_end=end,
                metadata=_scenario_metadata(scenario),
            )
        )
        next_id += 1
    return findings


def emit_findings(
    *,
    failed_scenarios: Sequence[Any],
    output_path: Path,
    target: str,
    reviewer_vendor: str = "gen-eval",
    review_type: str = "implementation",
) -> Path:
    """Build a review-findings.schema.json-conformant document and write it.

    Args:
        failed_scenarios: Scenario or ScenarioVerdict objects representing
            failures. Items without a ``status`` attribute are treated as
            failures (allowing pre-filtered lists).
        output_path: File path to write (typically
            ``<output-dir>/findings-gen-eval.json`` per
            ``contracts/findings-vendor-source.md``).
        target: change-id or feature-id this findings file relates to.
        reviewer_vendor: name to record in the ``reviewer_vendor`` field.
            Defaults to ``"gen-eval"`` per the vendor-source contract.
        review_type: one of ``"plan"`` or ``"implementation"`` per schema.
            Defaults to ``"implementation"`` since behavioral findings are
            evidence of deployed-system behavior.

    Returns:
        The path written.
    """
    findings = build_findings(failed_scenarios)
    document = {
        "review_type": review_type,
        "target": target,
        "reviewer_vendor": reviewer_vendor,
        "findings": [f.to_dict() for f in findings],
    }

    # Producer-side schema validation (defense in depth — consumer also validates).
    schema = _load_review_findings_schema()
    if schema is not None:
        try:
            import jsonschema  # type: ignore[import-untyped]

            jsonschema.validate(instance=document, schema=schema)
        except ImportError:
            logger.debug("jsonschema not installed; skipping producer-side validation")
        except jsonschema.ValidationError as exc:
            raise ValueError(
                f"refusing to emit findings: schema validation failed at "
                f"{'/'.join(str(p) for p in exc.absolute_path)}: {exc.message}"
            ) from exc

    output_path = Path(output_path)
    _atomic_write_json(output_path, document)
    return output_path


__all__ = [
    "BehavioralFinding",
    "build_findings",
    "emit_findings",
    "parse_openspec_source",
]
