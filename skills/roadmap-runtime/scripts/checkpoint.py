"""Checkpoint manager for roadmap execution state.

Provides save/restore/advance operations with idempotent resume semantics.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from models import (  # type: ignore[import-untyped]
    Checkpoint,
    CheckpointPhase,
    FailedItem,
    ItemStatus,
    Roadmap,
    load_checkpoint,
    save_checkpoint,
)

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Manages checkpoint lifecycle for a roadmap execution."""

    def __init__(self, workspace: Path, repo_root: Path | None = None) -> None:
        self.workspace = workspace
        self.repo_root = repo_root
        self.checkpoint_path = workspace / "checkpoint.json"

    def exists(self) -> bool:
        return self.checkpoint_path.exists()

    def load(self) -> Checkpoint:
        if not self.checkpoint_path.exists():
            raise FileNotFoundError(f"No checkpoint at {self.checkpoint_path}")
        checkpoint = load_checkpoint(self.checkpoint_path, self.repo_root)
        # `gate_decisions` is carried as a sidecar (see `record_gate_decision`),
        # so re-attach it on load — otherwise a resumed run would silently drop
        # the audit trail of every gate the previous run evaluated.
        raw = json.loads(self.checkpoint_path.read_text())
        checkpoint.gate_decisions = list(raw.get("gate_decisions", []))
        return checkpoint

    def save(self, checkpoint: Checkpoint) -> None:
        save_checkpoint(checkpoint, self.checkpoint_path)
        self._write_gate_decisions(checkpoint)
        logger.info(
            "Checkpoint saved: item=%s phase=%s",
            checkpoint.current_item_id,
            checkpoint.phase.value,
        )

    def create(self, roadmap: Roadmap) -> Checkpoint:
        """Create initial checkpoint for a roadmap."""
        ready = roadmap.ready_items()
        if not ready:
            first_id = roadmap.items[0].item_id if roadmap.items else "none"
        else:
            first_id = ready[0].item_id
        checkpoint = Checkpoint.create(roadmap.roadmap_id, first_id)
        self.save(checkpoint)
        return checkpoint

    def advance_phase(self, checkpoint: Checkpoint, new_phase: CheckpointPhase) -> None:
        """Advance to next phase within the current item."""
        checkpoint.phase = new_phase
        self.save(checkpoint)

    def complete_item(self, checkpoint: Checkpoint, item_id: str) -> None:
        """Mark an item as completed and advance to next ready item."""
        if item_id not in checkpoint.completed_items:
            checkpoint.completed_items.append(item_id)
        checkpoint.phase = CheckpointPhase.COMPLETED
        self.save(checkpoint)

    def record_gate_decision(self, checkpoint: Checkpoint, record: dict[str, Any]) -> None:
        """Append one gate-decision record (``gate-decision.schema.json``) to the
        checkpoint's append-only ``gate_decisions`` audit trail.

        The list is a *sidecar*: ``Checkpoint`` in ``models.py`` has no field for
        it, so the record is attached to the in-memory dataclass (which has no
        ``__slots__``) and merged into ``checkpoint.json`` on write. Keeping the
        write here rather than adding a model field means an existing checkpoint
        deserialises unchanged and ``checkpoint.schema.json`` — which does not set
        ``additionalProperties: false`` — still accepts the file. Dropping the
        record instead was the alternative, and it would leave a blocked gate with
        no evidence that a human decision ever happened.
        """
        decisions = list(getattr(checkpoint, "gate_decisions", None) or [])
        decisions.append(dict(record))
        checkpoint.gate_decisions = decisions  # type: ignore[attr-defined]
        self.save(checkpoint)

    def _write_gate_decisions(self, checkpoint: Checkpoint) -> None:
        """Merge the sidecar into the JSON ``save_checkpoint`` just wrote."""
        decisions = getattr(checkpoint, "gate_decisions", None)
        if not decisions:
            return
        data = json.loads(self.checkpoint_path.read_text())
        data["gate_decisions"] = list(decisions)
        self.checkpoint_path.write_text(json.dumps(data, indent=2) + "\n")

    def fail_item(
        self,
        checkpoint: Checkpoint,
        item_id: str,
        reason: str,
        roadmap: Roadmap,
        *,
        replan: bool = False,
    ) -> None:
        """Record item failure and propagate to dependents.

        ``replan`` is the explicit signal from the failing item's outcome payload
        (``{"replan": true}``): when set, dependents are parked in
        ``replan_required`` instead of ``blocked``, which tells the orchestrator to
        evaluate ``Gate.REPLAN_REQUIRED`` and, on proceed, ask the host to
        re-decompose that subgraph. It is keyword-only and defaults to ``False`` so
        every existing caller keeps today's exact behaviour: nothing here tries to
        infer "hard failure" from "workaround-able failure" out of the reason text —
        that classification stays with the agent that saw the failure.
        """
        now = datetime.now(timezone.utc).isoformat()
        existing = next((f for f in checkpoint.failed_items if f.item_id == item_id), None)
        if existing:
            existing.retry_count += 1
            existing.reason = reason
            existing.failed_at = now
        else:
            checkpoint.failed_items.append(
                FailedItem(item_id=item_id, reason=reason, failed_at=now)
            )
        checkpoint.phase = CheckpointPhase.FAILED

        # Propagate to dependents in roadmap
        item = roadmap.get_item(item_id)
        if item:
            item.status = ItemStatus.FAILED
            item.failure_reason = reason

        dependent_status = (
            ItemStatus.REPLAN_REQUIRED if replan else ItemStatus.BLOCKED
        )
        for other in roadmap.items:
            if item_id in other.depends_on and other.status in (
                ItemStatus.APPROVED,
                ItemStatus.CANDIDATE,
            ):
                other.status = dependent_status
                other.blocked_by = list(set(other.blocked_by) | {item_id})

        self.save(checkpoint)

    def advance_to_next(self, checkpoint: Checkpoint, roadmap: Roadmap) -> str | None:
        """Move to next ready item. Returns new item_id or None if roadmap is done/blocked.

        The new item enters at ``PLANNING``, not ``IMPLEMENTING``. Its change
        directory holds only the preliminary scaffold that ``plan-roadmap`` wrote
        when the roadmap was created, so it needs a refinement pass
        (``/plan-feature`` or ``/iterate-on-plan``) informed by what was learned
        implementing its dependencies — which is the whole reason roadmap items are
        planned one at a time rather than all at once up front.

        Entering at ``IMPLEMENTING`` also made ``should_skip_phase`` report planning
        as already complete for the freshly advanced item, because ``PLANNING``
        sorts before ``IMPLEMENTING`` in the phase order. The refinement pass was
        therefore skipped silently rather than deliberately.
        """
        ready = roadmap.ready_items()
        if not ready:
            return None
        next_item = ready[0]
        checkpoint.current_item_id = next_item.item_id
        checkpoint.phase = CheckpointPhase.PLANNING
        self.save(checkpoint)
        return next_item.item_id

    def is_resumable(self, checkpoint: Checkpoint) -> bool:
        """Check if execution can resume from this checkpoint."""
        return checkpoint.phase not in (CheckpointPhase.COMPLETED, CheckpointPhase.BLOCKED)

    def should_skip_phase(self, checkpoint: Checkpoint, item_id: str, phase: CheckpointPhase) -> bool:
        """Check if a phase should be skipped (already completed for this item)."""
        if checkpoint.current_item_id != item_id:
            return False
        phase_order = [
            CheckpointPhase.PLANNING,
            CheckpointPhase.IMPLEMENTING,
            CheckpointPhase.REVIEWING,
            CheckpointPhase.VALIDATING,
            CheckpointPhase.COMPLETED,
        ]
        if checkpoint.phase in phase_order and phase in phase_order:
            return phase_order.index(phase) < phase_order.index(checkpoint.phase)
        return False
