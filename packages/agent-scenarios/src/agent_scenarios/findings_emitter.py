"""Emit review-findings.schema.json-conformant findings from parity results.

Two finding sources, both conforming to
``openspec/schemas/review-findings.schema.json``:

1. **Deterministic goal-gate failures** — each failed/errored gate becomes one
   ``behavioral_failure`` finding (axis ``correctness``, severity ``critical``).
2. **LLM-judge trajectory findings** — additive quality observations mapped to
   the nearest schema ``type``: ``inefficiency`` -> ``performance``,
   ``wrong_but_passed`` -> ``behavioral_failure``, everything else ->
   ``behavioral_failure``. These are lower severity so they never mask a
   deterministic failure.

Mirrors the gen-eval ``findings_emitter`` contract: producer-side schema
validation (defense in depth) and atomic write.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from .models import ParityMatrix, TrajectoryFinding, VendorRunVerdict

logger = logging.getLogger(__name__)

# Map judge finding kinds to review-findings.schema.json `type` enum values.
_JUDGE_TYPE = {
    "inefficiency": "performance",
    "unnecessary_action": "performance",
    "wrong_but_passed": "behavioral_failure",
    "other": "behavioral_failure",
}
_JUDGE_AXIS = {
    "inefficiency": "performance",
    "unnecessary_action": "performance",
    "wrong_but_passed": "correctness",
    "other": "correctness",
}
# review-findings severity enum: critical|nit|optional|fyi|none
_JUDGE_SEVERITY = {"high": "critical", "medium": "optional", "low": "fyi"}


def _load_schema() -> dict[str, Any] | None:
    here = Path(__file__).resolve()
    for ancestor in (here, *here.parents):
        candidate = ancestor / "openspec" / "schemas" / "review-findings.schema.json"
        if candidate.is_file():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("failed to load review-findings schema: %s", exc)
                return None
    return None


def _atomic_write_json(output_path: Path, document: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=output_path.name + ".", suffix=".tmp", dir=str(output_path.parent)
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


def _gate_finding(
    finding_id: int,
    result: VendorRunVerdict,
    gate_detail: str,
    gate_id: str,
    source_path: str | None,
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "id": finding_id,
        "type": "behavioral_failure",
        "criticality": "high",
        "description": (
            f"[{result.vendor}] scenario '{result.scenario_id}' goal gate "
            f"'{gate_id}' failed: {gate_detail}"
        ),
        "disposition": "fix",
        "axis": "correctness",
        "severity": "critical",
    }
    if source_path:
        finding["file_path"] = source_path
    return finding


def _judge_finding(
    finding_id: int,
    result: VendorRunVerdict,
    tf: TrajectoryFinding,
    source_path: str | None,
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "id": finding_id,
        "type": _JUDGE_TYPE.get(tf.kind, "behavioral_failure"),
        "criticality": "medium" if tf.severity == "high" else "low",
        "description": (
            f"[{result.vendor}] scenario '{result.scenario_id}' trajectory "
            f"{tf.kind}: {tf.description}"
        ),
        "disposition": "accept",
        "axis": _JUDGE_AXIS.get(tf.kind, "correctness"),
        "severity": _JUDGE_SEVERITY.get(tf.severity, "optional"),
    }
    if source_path:
        finding["file_path"] = source_path
    return finding


def build_findings(
    matrices: list[ParityMatrix],
    *,
    source_paths: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Build schema-conformant finding dicts from parity matrices.

    Args:
        matrices: results from the runner.
        source_paths: optional map scenario_id -> scenario file path, used to
            set ``file_path`` so findings trace back to the scenario.
    """
    source_paths = source_paths or {}
    findings: list[dict[str, Any]] = []
    next_id = 1
    for matrix in matrices:
        src = source_paths.get(matrix.scenario_id)
        for result in matrix.results:
            for gate in result.failed_gates:
                findings.append(_gate_finding(next_id, result, gate.detail, gate.gate_id, src))
                next_id += 1
            # Judge findings are additive — emitted even when gates pass.
            for tf in result.trajectory.findings:
                findings.append(_judge_finding(next_id, result, tf, src))
                next_id += 1
    return findings


def emit_findings(
    *,
    matrices: list[ParityMatrix],
    output_path: str | Path,
    target: str,
    reviewer_vendor: str = "agent-scenarios",
    source_paths: dict[str, str] | None = None,
) -> Path:
    """Build and atomically write a review-findings.schema.json document.

    ``review_type`` is fixed to ``"implementation"`` since a trajectory failure
    is evidence about how the agent behaved on a concrete task.
    """
    findings = build_findings(matrices, source_paths=source_paths)
    document = {
        "review_type": "implementation",
        "target": target,
        "reviewer_vendor": reviewer_vendor,
        "findings": findings,
    }

    schema = _load_schema()
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

    out = Path(output_path)
    _atomic_write_json(out, document)
    return out


__all__ = ["build_findings", "emit_findings"]
