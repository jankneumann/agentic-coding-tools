"""Collision probe seam (design D4).

Plan-time collision detectors attach only through :class:`CollisionProbe`. The registry
is empty by default: no plan-time requirement-collision detector exists yet, so the
baseline honestly records "not detected".

Adding a probe means adding one import line below (``ri-06`` does this); scenario
definitions stay untouched. A probe that raises or runs past its timeout is recorded
with ``status: error`` and the scenario still completes, mirroring the roadmap rule that
advisory signals fail open.
"""

from __future__ import annotations

import os
import subprocess
import threading
from collections.abc import Sequence
from pathlib import Path
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from mpsim.errors import UsageError
from mpsim.world import PrincipalView

# Default per-probe timeout in seconds. Read at call time so tests can lower it.
PER_PROBE_TIMEOUT = 10.0


@dataclass(frozen=True)
class Collision:
    level: str  # intent | requirement | contract | file
    other_change: str
    requirement: str | None


@dataclass(frozen=True)
class ProbeResult:
    probe_id: str
    status: str  # ok | error
    collisions: list[Collision] = field(default_factory=list)
    error: str | None = None


@runtime_checkable
class CollisionProbe(Protocol):
    probe_id: str

    def detect(self, view: PrincipalView, change_id: str) -> ProbeResult: ...


REGISTRY: dict[str, CollisionProbe] = {}


def register(probe: CollisionProbe) -> None:
    if probe.probe_id in REGISTRY:
        raise ValueError(f"probe {probe.probe_id!r} is already registered")
    REGISTRY[probe.probe_id] = probe


def select(probe_ids: Sequence[str] | None) -> list[CollisionProbe]:
    """Registered probes in registration order, or the named subset (unknown id -> UsageError)."""
    if not probe_ids:
        return list(REGISTRY.values())
    unknown = [pid for pid in probe_ids if pid not in REGISTRY]
    if unknown:
        raise UsageError(f"unknown probe id: {', '.join(unknown)}")
    wanted = set(probe_ids)
    return [p for pid, p in REGISTRY.items() if pid in wanted]


def run_probe(probe: CollisionProbe, view: PrincipalView, change_id: str) -> ProbeResult:
    """Run one probe in a daemon thread; abandon it at the timeout instead of joining."""
    timeout = PER_PROBE_TIMEOUT
    box: list[ProbeResult | BaseException] = []

    def target() -> None:
        try:
            box.append(probe.detect(view, change_id))
        except BaseException as exc:  # noqa: BLE001 - any probe failure is recorded, never raised
            box.append(exc)

    thread = threading.Thread(target=target, name=f"probe-{probe.probe_id}", daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        return ProbeResult(probe.probe_id, "error", [], f"probe timeout after {timeout:g}s")
    outcome = box[0]
    if isinstance(outcome, BaseException):
        return ProbeResult(probe.probe_id, "error", [], f"{type(outcome).__name__}: {outcome}")
    if not isinstance(outcome, ProbeResult) or outcome.status not in ("ok", "error"):
        return ProbeResult(probe.probe_id, "error", [], "probe returned an invalid result")
    return ProbeResult(probe.probe_id, outcome.status, list(outcome.collisions), outcome.error)


def _git(worktree: Path, *args: str) -> str:
    # Same isolation as the world (design D6): no global or system git config.
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    return subprocess.run(
        ["git", "-C", str(worktree), *args], env=env, check=True, capture_output=True, text=True
    ).stdout


def _worktree_state(worktree: Path) -> tuple[str, str]:
    return (
        _git(worktree, "rev-parse", "HEAD").strip(),
        _git(worktree, "status", "--porcelain", "--untracked-files=all"),
    )


def run_probes(
    probes: Sequence[CollisionProbe], view: PrincipalView, change_id: str
) -> list[ProbeResult]:
    """Run each probe, enforcing the read-only promise of :class:`PrincipalView`.

    The view hands probes a real path, so nothing stops a probe from writing. A probe
    that changes the worktree's HEAD or files is recorded as ``status: error`` and,
    when the worktree was clean before it ran, the worktree is restored so the rest of
    the scenario measures the world the fixture built.
    """
    results = []
    for probe in probes:
        before = _worktree_state(view.worktree)
        result = run_probe(probe, view, change_id)
        if _worktree_state(view.worktree) != before:
            result = ProbeResult(probe.probe_id, "error", [], "probe mutated the worktree")
            if not before[1]:
                _git(view.worktree, "reset", "-q", "--hard", before[0])
                _git(view.worktree, "clean", "-q", "-f", "-d", "-x")
        results.append(result)
    return results


def detected(results: Sequence[ProbeResult], other_change: str) -> bool:
    """True when an ``ok`` probe reported a requirement-level collision with ``other_change``."""
    return any(
        r.status == "ok"
        and any(c.level == "requirement" and c.other_change == other_change for c in r.collisions)
        for r in results
    )


def as_report_entry(result: ProbeResult) -> dict:
    return {
        "probe_id": result.probe_id,
        "status": result.status,
        "collisions": [
            {"level": c.level, "other_change": c.other_change, "requirement": c.requirement}
            for c in result.collisions
        ],
        "error": result.error,
    }


# Probe registrations go below this line, one import per probe. ri-06 adds its import here:
#
#     from mpsim.probes import requirement_collision  # noqa: F401  (registers itself)
