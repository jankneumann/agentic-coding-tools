#!/usr/bin/env python3
"""Collect one repository's pending gates and push them to the coordinator.

A repository records a gate that is waiting for a person in two places:

* ``openspec/roadmaps/<id>/checkpoint.json`` — a dispatch attempt whose
  ``status`` is ``parked``;
* ``openspec/changes/<id>/loop-state.json`` — a ``pending_gate`` marker.

``collect`` reads both and builds the snapshot ``POST /gates/projection``
accepts. ``push`` sends it. Neither writes to the repository: the files stay
the record, the coordinator holds a copy that is replaced on every push.

Usage::

    gate_projection.py --repo-root . collect --project owner/name
    gate_projection.py --repo-root . push --project owner/name

``push`` needs ``COORDINATION_API_URL``, ``COORDINATION_API_KEY`` and, for a
host that is not local, ``COORDINATION_ALLOWED_HOSTS``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SKILLS_ROOT = Path(__file__).resolve().parents[2]
if str(_SKILLS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILLS_ROOT))

from shared.trust_posture import (  # noqa: E402
    PostureValidationError,
    TrustPosture,
    load_posture,
)

PROJECT_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MAX_GATES = 500
MAX_SOURCE_ERRORS = 100
POSTURE_FILE = "TRUST_POSTURE.md"
SKILLS_DIR_PLACEHOLDER = "<skills-dir>"

# Longest value the coordinator accepts for each text field.
_MAX_LENGTH = {
    "gate": 64,
    "subject": 300,
    "prompt": 4000,
    "requested_at": 64,
    "deadline": 64,
    "default_action": 64,
    "disposition": 64,
    "approval_id": 64,
    "answer_hint": 1000,
    "phase": 64,
    "roadmap_id": 200,
    "change_id": 200,
    "item_id": 200,
    "dispatch_id": 300,
}
_ERROR_LENGTH = 500

# A park that names no gate is listed under its kind, except this one, which
# the supervisor answers through the escalate_resume gate.
_KIND_GATE = {"policy_pause": "escalate_resume"}


def _skills_dir(repo_root: Path) -> str:
    """Where the skills this collector belongs to sit, relative to ``repo_root``.

    The collector runs from the canonical tree or from an installed copy, so the
    commands it suggests name whichever one it is running from. A collector that
    reads some other repository cannot know that repository's layout and leaves
    a placeholder for the reader to fill in.
    """
    try:
        return _SKILLS_ROOT.relative_to(repo_root).as_posix()
    except ValueError:
        return SKILLS_DIR_PLACEHOLDER


def _text(value: Any) -> str | None:
    """Return ``value`` when it is a non-empty string, else None."""
    if isinstance(value, str) and value.strip():
        return value
    return None


def _gate_id(project: str, source: str, *parts: str | None) -> str:
    key = "\x1f".join([project, source, *[part or "" for part in parts]])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _finish(gate: dict[str, Any]) -> dict[str, Any]:
    """Drop empty fields and cut text to what the coordinator accepts."""
    finished: dict[str, Any] = {}
    for key, value in gate.items():
        if value is None:
            continue
        limit = _MAX_LENGTH.get(key)
        if limit is not None and isinstance(value, str):
            value = value[:limit]
        finished[key] = value
    return finished


class _Dispositions:
    """Looks up each gate's disposition in the repository's trust posture."""

    def __init__(self, repo_root: Path, errors: list[dict[str, str]]) -> None:
        self._posture: TrustPosture | None = None
        try:
            self._posture = load_posture(repo_root)
        except (PostureValidationError, OSError) as exc:
            errors.append({"path": POSTURE_FILE, "error": str(exc)[:_ERROR_LENGTH]})

    def known(self, gate: str) -> bool:
        return self._lookup(gate) is not None

    def fields(self, gate: str) -> dict[str, Any]:
        found = self._lookup(gate) if self._posture is not None else None
        if found is None:
            return {"disposition": "block"}
        return {
            "disposition": found.disposition.value,
            "timeout_seconds": found.timeout_seconds,
            "default_action": found.default_action.value if found.default_action else None,
        }

    def _lookup(self, gate: str) -> Any:
        posture = self._posture if self._posture is not None else TrustPosture(gates={})
        try:
            return posture.disposition_for(gate)
        except ValueError:  # not one of the posture's gates
            return None


def _read_object(path: Path, repo_root: Path, errors: list[dict[str, str]]) -> dict[str, Any] | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("expected a JSON object")
    except (OSError, ValueError) as exc:
        errors.append(
            {
                "path": path.relative_to(repo_root).as_posix()[:_ERROR_LENGTH],
                "error": str(exc)[:_ERROR_LENGTH],
            }
        )
        return None
    return loaded


def _approval_for(decisions: Any, gate: str, dispatch_id: str | None, item_id: str | None) -> str | None:
    """Approval request of the latest decision recorded for this parked gate."""
    if not isinstance(decisions, list):
        return None
    for key, wanted in (("dispatch_id", dispatch_id), ("item_id", item_id)):
        if not wanted:
            continue
        matching = [
            d for d in decisions if isinstance(d, dict) and d.get("gate") == gate and d.get(key) == wanted
        ]
        if matching:
            return _text(matching[-1].get("approval_id"))
    return None


def _checkpoint_gates(
    checkpoint: dict[str, Any],
    fallback_roadmap: str,
    project: str,
    dispositions: _Dispositions,
    skills_dir: str,
) -> list[dict[str, Any]]:
    roadmap_id = _text(checkpoint.get("roadmap_id")) or fallback_roadmap
    attempts = checkpoint.get("dispatch_attempts")
    gates: list[dict[str, Any]] = []
    for attempt in attempts if isinstance(attempts, list) else []:
        if not isinstance(attempt, dict) or attempt.get("status") != "parked":
            continue
        parked = attempt.get("parked")
        if not isinstance(parked, dict):
            continue
        kind = _text(parked.get("kind"))
        gate = _text(parked.get("gate")) or _KIND_GATE.get(kind or "") or kind
        if gate is None:
            continue
        item_id = _text(attempt.get("item_id"))
        change_id = _text(attempt.get("change_id"))
        dispatch_id = _text(attempt.get("dispatch_id"))
        if dispositions.known(gate):
            hint: str | None = (
                f"python3 {skills_dir}/supervise/scripts/cycle_state.py --repo-root . gate-answer"
                f" --roadmap {roadmap_id} --gate {gate} --decision <approved|rejected>"
            )
            if dispatch_id:
                hint = f"{hint} --dispatch-id {dispatch_id}"
        else:
            hint = _text(parked.get("resume_hint"))
        gates.append(
            _finish(
                {
                    "gate_id": _gate_id(
                        project, "checkpoint", roadmap_id, item_id, change_id, gate, dispatch_id
                    ),
                    "gate": gate,
                    "source": "checkpoint",
                    "subject": " ".join(p for p in (item_id, change_id) if p) or roadmap_id,
                    "prompt": _text(parked.get("reason")),
                    "deadline": _text(parked.get("deadline")),
                    **dispositions.fields(gate),
                    "approval_id": _approval_for(
                        checkpoint.get("gate_decisions"), gate, dispatch_id, item_id
                    ),
                    "answer_hint": hint,
                    "phase": _text(attempt.get("phase")),
                    "roadmap_id": roadmap_id,
                    "change_id": change_id,
                    "item_id": item_id,
                    "dispatch_id": dispatch_id,
                }
            )
        )
    return gates


def _loop_state_gate(
    state: dict[str, Any],
    fallback_change: str,
    project: str,
    dispositions: _Dispositions,
    skills_dir: str,
) -> dict[str, Any] | None:
    pending = state.get("pending_gate")
    if not isinstance(pending, dict):
        return None
    gate = _text(pending.get("gate"))
    if gate is None:
        return None
    change_id = _text(pending.get("change_id")) or _text(state.get("change_id")) or fallback_change
    return _finish(
        {
            "gate_id": _gate_id(project, "loop_state", None, None, change_id, gate, None),
            "gate": gate,
            "source": "loop_state",
            "subject": change_id,
            "prompt": _text(pending.get("prompt")),
            "requested_at": _text(pending.get("requested_at")),
            **dispositions.fields(gate),
            "approval_id": _text(pending.get("approval_id")),
            "answer_hint": (
                f"python3 {skills_dir}/autopilot/scripts/runner.py"
                f" gate-answer {change_id} --gate {gate} --decision <approved|rejected>"
            ),
            "phase": _text(pending.get("phase")),
            "change_id": change_id,
        }
    )


def collect(repo_root: Path | str, project: str, now: datetime | None = None) -> dict[str, Any]:
    """Build the pending-gate snapshot for ``project`` from ``repo_root``.

    Read-only. A source that cannot be read is listed in ``source_errors`` and
    the rest of the repository is still collected.
    """
    root = Path(repo_root).resolve()
    errors: list[dict[str, str]] = []
    dispositions = _Dispositions(root, errors)
    skills_dir = _skills_dir(root)
    gates: list[dict[str, Any]] = []

    for path in sorted(root.glob("openspec/roadmaps/*/checkpoint.json")):
        checkpoint = _read_object(path, root, errors)
        if checkpoint is not None:
            gates.extend(
                _checkpoint_gates(checkpoint, path.parent.name, project, dispositions, skills_dir)
            )

    for path in sorted(root.glob("openspec/changes/*/loop-state.json")):
        state = _read_object(path, root, errors)
        if state is not None:
            gate = _loop_state_gate(state, path.parent.name, project, dispositions, skills_dir)
            if gate is not None:
                gates.append(gate)

    if len(gates) > MAX_GATES:
        errors.insert(
            0,
            {
                "path": "openspec",
                "error": f"{len(gates)} pending gates found; only the first {MAX_GATES} are sent",
            },
        )
        gates = gates[:MAX_GATES]

    collected_at = now if now is not None else datetime.now(timezone.utc)
    return {
        "project": project,
        "collected_at": collected_at.isoformat(),
        "gates": gates,
        "source_errors": errors[:MAX_SOURCE_ERRORS],
    }


def _coordinator_client() -> Any:
    """Return the coordinator HTTP client; ValueError when none is configured."""
    bridge = _SKILLS_ROOT / "coordination-bridge" / "scripts"
    if str(bridge) not in sys.path:
        sys.path.insert(0, str(bridge))
    import coordination_bridge

    return coordination_bridge.CoordinatorHttpClient()


def _push(snapshot: dict[str, Any]) -> int:
    try:
        client = _coordinator_client()
    except ValueError as exc:
        print(f"push failed: {exc}", file=sys.stderr)
        return 1
    response = client.request("POST", "/gates/projection", snapshot)
    status = response.get("status_code")
    if status is None or not 200 <= status < 300:
        detail = response.get("error") or response.get("data")
        print(f"push failed: coordinator answered {status}: {detail}", file=sys.stderr)
        return 1
    print(json.dumps(response.get("data"), indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--repo-root", default=".", help="repository to read (default: .)")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, text in (
        ("collect", "print the pending-gate snapshot as JSON"),
        ("push", "send the snapshot to the coordinator"),
    ):
        command = commands.add_parser(name, help=text)
        command.add_argument("--project", required=True, help="owner/name of this repository")
    args = parser.parse_args(argv)

    if not PROJECT_PATTERN.match(args.project):
        print(f"--project must be owner/name, got {args.project!r}", file=sys.stderr)
        return 2

    snapshot = collect(Path(args.repo_root), args.project)
    if args.command == "collect":
        print(json.dumps(snapshot, indent=2, sort_keys=True))
        return 0
    return _push(snapshot)


if __name__ == "__main__":
    sys.exit(main())
