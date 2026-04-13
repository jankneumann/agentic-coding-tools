"""Checkpoint manager for roadmap execution state.

Provides save/restore/advance operations with idempotent resume semantics.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

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
        return load_checkpoint(self.checkpoint_path, self.repo_root)

    def save(self, checkpoint: Checkpoint) -> None:
        save_checkpoint(checkpoint, self.checkpoint_path)
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

    def fail_item(
        self,
        checkpoint: Checkpoint,
        item_id: str,
        reason: str,
        roadmap: Roadmap,
    ) -> None:
        """Record item failure and propagate to dependents."""
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

        for other in roadmap.items:
            if item_id in other.depends_on and other.status in (
                ItemStatus.APPROVED,
                ItemStatus.CANDIDATE,
            ):
                other.status = ItemStatus.BLOCKED
                other.blocked_by = list(set(other.blocked_by) | {item_id})

        self.save(checkpoint)

    def advance_to_next(self, checkpoint: Checkpoint, roadmap: Roadmap) -> str | None:
        """Move to next ready item. Returns new item_id or None if roadmap is done/blocked."""
        ready = roadmap.ready_items()
        if not ready:
            return None
        next_item = ready[0]
        checkpoint.current_item_id = next_item.item_id
        checkpoint.phase = CheckpointPhase.IMPLEMENTING
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
