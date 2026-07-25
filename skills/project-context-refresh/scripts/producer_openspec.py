"""``openspec.projection`` producer — non-mutating spec-delta projection (D6).

This producer projects how active change deltas would alter canonical capability
specs and reports the expected repository-artifact changes. It is *projection
only*: OpenSpec canonical updates are sync-point mutations owned by
cleanup-feature, so neither ``generate`` nor ``check`` ever writes
``openspec/specs/``, mutates active changes, archives, or bypasses the
active-agent guard. Both modes therefore behave identically — a truthful,
read-only comparison — and drift is reported as ``degraded`` because the pending
merge is a real, actionable state the sync-point owner must resolve.
"""

from __future__ import annotations

from pathlib import Path

import results as R
from _runtime import ChangeKind, Remediation, RepositoryArtifact, SafeError, sha256_hex
from openspec_merge import active_change_deltas, project_capability
from registry import OPENSPEC_PROJECTION, Mode, Producer, ProducerSpec

PRODUCER_ID = OPENSPEC_PROJECTION
PRODUCER_VERSION = "1.0.0"
OWNER = "cleanup-feature / openspec archive (canonical spec merge owner)"

_SPECS_ROOT = "openspec/specs"
_CHANGES_ROOT = "openspec/changes"


class OpenSpecProjectionProducer(Producer):
    """Report expected canonical spec changes from active deltas, writing nothing."""

    def __init__(self) -> None:
        self.spec = ProducerSpec(
            producer_id=PRODUCER_ID,
            producer_version=PRODUCER_VERSION,
            owner=OWNER,
            inputs=(f"{_CHANGES_ROOT}/*/specs/**/spec.md", f"{_SPECS_ROOT}/*/spec.md"),
            # Declared surface it reports on; it never writes these (sync-point owns it).
            outputs=(f"{_SPECS_ROOT}/",),
        )

    def run(self, mode: Mode, repository: Path, source_revision: str):
        try:
            deltas_by_cap: dict[str, list] = {}
            for capability, delta in active_change_deltas(repository / _CHANGES_ROOT):
                deltas_by_cap.setdefault(capability, []).append(delta)
        except Exception as exc:  # noqa: BLE001 - surfaced as a failed result
            return R.failed(
                PRODUCER_ID,
                PRODUCER_VERSION,
                error=SafeError(exc.__class__.__name__, str(exc)[:300]),
                remediation=[Remediation(summary="Inspect active change delta specs and re-run.")],
                validations=[R.failed_validation("openspec", "delta parse failed")],
            )

        artifacts: list[RepositoryArtifact] = []
        validations: list = []
        for capability in sorted(deltas_by_cap):
            canonical = repository / _SPECS_ROOT / capability / "spec.md"
            canonical_text = canonical.read_text(encoding="utf-8") if canonical.exists() else ""
            projected = project_capability(canonical_text, deltas_by_cap[capability])
            rel = f"{_SPECS_ROOT}/{capability}/spec.md"
            if not canonical.exists():
                artifacts.append(
                    RepositoryArtifact(rel, ChangeKind.ADDED, sha256_hex(projected.encode("utf-8")))
                )
                validations.append(R.failed_validation(R.vid("spec", capability), f"{rel} would be created"))
            elif projected != canonical_text:
                artifacts.append(
                    RepositoryArtifact(rel, ChangeKind.MODIFIED, sha256_hex(projected.encode("utf-8")))
                )
                validations.append(R.failed_validation(R.vid("spec", capability), f"{rel} has a pending merge"))
            else:
                validations.append(R.passed(R.vid("spec", capability), f"{rel} already reflects deltas"))

        artifacts_sorted = R.sort_artifacts(artifacts)
        if artifacts_sorted:
            return R.drift(
                PRODUCER_ID,
                PRODUCER_VERSION,
                artifacts=artifacts_sorted,
                validations=validations,
                remediation=[
                    Remediation(
                        summary=(
                            "Archive the active change(s) through cleanup-feature so the "
                            "canonical spec merge lands at the sync point."
                        ),
                        command="openspec archive <change-id>",
                    )
                ],
                reason=(
                    "Projection only: this producer never writes canonical specs; "
                    "the sync-point owner performs the merge."
                ),
            )
        return R.fresh(
            PRODUCER_ID,
            PRODUCER_VERSION,
            validations=validations
            or [R.passed("openspec", "no active spec deltas to project")],
        )
