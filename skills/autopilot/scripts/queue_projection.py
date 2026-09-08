"""One-way projection of durable Autopilot phase state into the work queue."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_THIS_DIR = Path(__file__).resolve().parent
_BRIDGE_DIR = _THIS_DIR.parent.parent / "coordination-bridge" / "scripts"
if str(_BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_DIR))

import coordination_bridge as bridge  # type: ignore[import-not-found]  # noqa: E402

_CHANGE_ID_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,127}\Z")
_OWNED_PROJECTION_LABEL = "projection:autopilot-phase"
_MAX_CLEANUP_ROWS = 100
_MAX_REASON = 200


def _bounded_reason(value: object, default: str) -> str:
    text = str(value or default).replace("\n", " ").strip()
    return text[:_MAX_REASON] or default


def _degraded(envelope: object, default: str = "projection_failed") -> dict[str, str]:
    if isinstance(envelope, dict):
        reason = envelope.get("reason") or envelope.get("error")
        if reason is None and isinstance(envelope.get("response"), dict):
            reason = envelope["response"].get("detail")
        return {"status": "degraded", "reason": _bounded_reason(reason, default)}
    return {"status": "degraded", "reason": default}


def _response(envelope: dict[str, Any]) -> dict[str, Any]:
    value = envelope.get("response")
    return value if isinstance(value, dict) else {}


@dataclass(frozen=True)
class QueueProjectionAdapter:
    """Project a LoopState without ever feeding queue data back into it."""

    http_url: str
    api_key: str | None = None
    change_path: str | None = None
    execution_tier: str = "coordinated"
    projection_provenance: str = "autopilot-loop-state"

    def __call__(self, state: Any, *, mode: str = "submit") -> dict[str, Any]:
        change_id = getattr(state, "change_id", None)
        if not isinstance(change_id, str) or _CHANGE_ID_RE.fullmatch(change_id) is None:
            return {"status": "degraded", "reason": "invalid_change_id"}
        if mode not in {"submit", "reconcile"}:
            return {"status": "degraded", "reason": "invalid_projection_mode"}

        coordination_state = bridge.detect_coordination(
            http_url=self.http_url, api_key=self.api_key
        )
        key = {
            "change_id": change_id,
            "phase": str(state.current_phase),
            "transition_sequence": int(state.total_iterations),
        }
        input_data: dict[str, str] = {
            "execution_tier": self.execution_tier[:64],
            "projection_provenance": self.projection_provenance[:128],
        }
        if self.change_path:
            input_data["change_path"] = self.change_path[:512]
        call = {
            "projection_key": key,
            "task_type": "issue",
            "task_description": f"Autopilot phase {state.current_phase}"[:500],
            "input_data": input_data,
            "priority": 1,
            "http_url": self.http_url,
            "api_key": self.api_key,
            "_coordination_state": coordination_state,
        }

        if mode == "reconcile":
            envelope = bridge.try_reconcile_work_projection(**call)
        else:
            envelope = bridge.try_submit_work(**call)
            if self._requires_reconciliation(envelope):
                envelope = bridge.try_reconcile_work_projection(**call)

        if not isinstance(envelope, dict) or envelope.get("status") != "ok":
            return _degraded(envelope)
        response = _response(envelope)
        task_id = response.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            return {"status": "degraded", "reason": "canonical_task_id_missing"}

        labels = [f"change:{change_id}", _OWNED_PROJECTION_LABEL]
        labelled = bridge.try_projection_issue_update(
            issue_id=task_id,
            labels=labels,
            http_url=self.http_url,
            api_key=self.api_key,
            _coordination_state=coordination_state,
        )
        if labelled.get("status") != "ok":
            return _degraded(labelled, "canonical_label_update_failed")

        stale_ids = {
            value
            for value in response.get("cancelled_task_ids", [])
            if isinstance(value, str) and value != task_id
        }
        if mode == "reconcile":
            listed = bridge.try_projection_issue_list(
                labels=labels,
                limit=_MAX_CLEANUP_ROWS,
                http_url=self.http_url,
                api_key=self.api_key,
                _coordination_state=coordination_state,
            )
            if listed.get("status") != "ok":
                return _degraded(listed, "stale_label_list_failed")
            payload = listed.get("response")
            issues = payload.get("issues", []) if isinstance(payload, dict) else []
            stale_ids.update(
                str(issue["id"])
                for issue in issues[:_MAX_CLEANUP_ROWS]
                if isinstance(issue, dict)
                and issue.get("id")
                and str(issue["id"]) != task_id
            )

        for stale_id in sorted(stale_ids):
            cleared = bridge.try_projection_issue_update(
                issue_id=stale_id,
                labels=[],
                http_url=self.http_url,
                api_key=self.api_key,
                _coordination_state=coordination_state,
            )
            if cleared.get("status") != "ok":
                return _degraded(cleared, "stale_label_cleanup_failed")

        return {"status": "ok", "task_id": task_id, "cleaned": len(stale_ids)}

    @staticmethod
    def _requires_reconciliation(envelope: object) -> bool:
        if not isinstance(envelope, dict):
            return False
        response = envelope.get("response")
        return (
            envelope.get("status") == "error"
            and envelope.get("status_code") == 409
            and isinstance(response, dict)
            and response.get("detail") == "reconciliation_required"
        )
