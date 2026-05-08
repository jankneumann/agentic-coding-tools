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
import re
from dataclasses import dataclass, field
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
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return output_path


__all__ = [
    "BehavioralFinding",
    "build_findings",
    "emit_playwright_findings",
    "parse_source_ref",
]
