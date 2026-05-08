"""Convert Playwright run results into a review-findings.schema.json document.

Per ``contracts/findings-vendor-source.md`` and design D8, the Playwright
validator emits ``findings-playwright.json`` (NOT shared with gen-eval's
``findings-gen-eval.json``). Each finding uses ``type: behavioral_failure``
and references the originating OpenSpec scenario when one exists.

Filename routing rule (from the gen-eval-framework spec delta):
the playwright validator's location MUST point at the spec.md, not at the
generated ``.spec.ts`` file -- so consumers of consensus findings see
"Login flow scenario at openspec/.../spec.md:30-45 failed" rather than
"generated TypeScript file at <hash>.spec.ts failed".

This module deliberately defines its own minimal :class:`BehavioralFinding`
dataclass rather than importing from ``agent-coordinator/evaluation/gen_eval``
because the playwright skill should be packageable independently (see D2).
The shape MUST match the gen-eval emitter so consensus_synthesizer treats
both files identically.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def _load_review_findings_schema():
    """Best-effort load of openspec/schemas/review-findings.schema.json.

    Walks parent directories from this module looking for an ``openspec/schemas/``
    directory. Returns None if the schema can't be located — producer-side
    validation is defense-in-depth; the consumer (consensus_synthesizer) also
    validates, so a missing schema here degrades gracefully.
    """
    from pathlib import Path as _P
    here = _P(__file__).resolve()
    for ancestor in (here, *here.parents):
        candidate = ancestor / "openspec" / "schemas" / "review-findings.schema.json"
        if candidate.is_file():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(
                    "failed to load schema for producer-side validation: %s", exc
                )
                return None
    return None


def _atomic_write_json(output_path, document):
    """Atomic write: tempfile in same dir, fsync, then rename."""
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
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


# ---------------------------------------------------------------------------
# Source-ref parsing (mirrors agent-coordinator's parse_openspec_source)
# ---------------------------------------------------------------------------


_SOURCE_REF = re.compile(r"^(?P<file>.+):(?P<start>\d+)-(?P<end>\d+)$")


def parse_source_ref(
    ref: str | None,
) -> tuple[str | None, int | None, int | None]:
    """Parse ``"<file>:<start>-<end>"`` into (file, start, end) ints."""
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


@dataclass
class BehavioralFinding:
    """A single behavioral_failure finding ready for serialization.

    Mirrors :class:`agent_coordinator.evaluation.gen_eval.findings_emitter.BehavioralFinding`
    so a consumer reading the resulting ``findings-playwright.json`` cannot
    tell whether it came from gen-eval or Playwright by shape alone. The
    discriminator is the filename + ``reviewer_vendor`` field.
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
        if self.metadata:
            # ``metadata`` is not a top-level schema field, but the schema
            # is open for additional properties on findings; keeping it
            # makes downstream filtering (by browser, scenario_id) trivial.
            out["metadata"] = dict(self.metadata)
        return out


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def _scenario_lookup(
    scenarios: Sequence[Any],
) -> dict[str, Any]:
    """Index translated scenarios by their test name so failures can be matched."""
    return {
        getattr(s, "name", None) or getattr(s, "test_name", "unknown"): s
        for s in scenarios
    }


def build_findings(
    failures: Iterable[Any],
    scenarios: Sequence[Any],
) -> list[BehavioralFinding]:
    """Build one BehavioralFinding per failure.

    Args:
        failures: Iterable of objects with ``test_name``, ``browser``,
            ``error_message`` -- e.g. :class:`PlaywrightFailure` from
            :mod:`runner`.
        scenarios: List of :class:`TranslatedScenario` (or any duck-typed
            object exposing ``name``, ``source_ref``). Used to map a failure
            back to its originating OpenSpec scenario for the
            ``location.file:line_range`` field.
    """
    by_name = _scenario_lookup(scenarios)
    findings: list[BehavioralFinding] = []
    next_id = 1
    for failure in failures:
        test_name = getattr(failure, "test_name", "unknown")
        browser = getattr(failure, "browser", "unknown")
        message = getattr(failure, "error_message", "")

        scenario = by_name.get(test_name)
        file_path: str | None = None
        line_start: int | None = None
        line_end: int | None = None
        scenario_id = test_name
        if scenario is not None:
            source_ref = getattr(scenario, "source_ref", "") or ""
            f, s, e = parse_source_ref(source_ref)
            if f:
                file_path, line_start, line_end = f, s, e
            scenario_id = getattr(scenario, "name", scenario_id)
        else:
            # Couldn't match — fall back to the .spec.ts file from the
            # Playwright reporter. Better than "unknown".
            file_path = getattr(failure, "file", None) or "unknown"

        description = (
            f"Behavioral failure in scenario '{scenario_id}' "
            f"(browser={browser}): {message}"
            if message
            else f"Behavioral failure in scenario '{scenario_id}' (browser={browser})"
        )

        findings.append(
            BehavioralFinding(
                id=next_id,
                description=description,
                criticality="high",
                disposition="fix",
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                metadata={
                    "browser": browser,
                    "scenario_id": scenario_id,
                },
            )
        )
        next_id += 1
    return findings


def emit_playwright_findings(
    *,
    failures: Iterable[Any],
    scenarios: Sequence[Any],
    output_path: Path,
    target: str,
    reviewer_vendor: str = "playwright",
    review_type: str = "implementation",
) -> Path:
    """Write a review-findings.schema.json-conformant document.

    Args:
        failures: :class:`PlaywrightFailure` objects from the runner.
        scenarios: :class:`TranslatedScenario` objects (for back-reference).
        output_path: Typically ``openspec/changes/<id>/findings-playwright.json``.
        target: Change-id or feature-id this findings file relates to.
        reviewer_vendor: The vendor name; defaults to ``"playwright"`` per
            the findings-vendor-source contract.
        review_type: ``"plan"`` or ``"implementation"`` per schema.

    Returns:
        The path written.
    """
    findings = build_findings(failures, scenarios)
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
            logger.debug(
                "jsonschema not installed; skipping producer-side validation"
            )
        except jsonschema.ValidationError as exc:
            raise ValueError(
                f"refusing to emit playwright findings: schema validation "
                f"failed at {'/'.join(str(p) for p in exc.absolute_path)}: "
                f"{exc.message}"
            ) from exc

    output_path = Path(output_path)
    _atomic_write_json(output_path, document)
    return output_path


__all__ = [
    "BehavioralFinding",
    "build_findings",
    "emit_playwright_findings",
    "parse_source_ref",
]
