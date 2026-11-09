"""The status applier: the simulated supervisor step (design D5, operator decision A1).

``roadmap.yaml`` has exactly one authoritative copy, the one on the shared remote's
``main``. Principals never edit it. This module is part of the ``mpsim`` package but is
*not* a principal: it operates on its own clone of the shared remote and commits as
``sim-supervisor``, mirroring the real split where workers report results and only the
supervisor writes roadmap state.

The applier holds no transition logic. It writes exactly the status a fixture declared,
for the item of the principal that reported it.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import yaml

from mpsim.errors import ScenarioError
from mpsim.model import StatusTransition
from mpsim.world import SUPERVISOR_IDENTITY, World

ROADMAP_FILE = "roadmap.yaml"


class StatusApplier:
    def __init__(self, world: World, root: Path) -> None:
        self._world = world
        self._clone = world.clone_for(Path(root) / "supervisor" / "clone", SUPERVISOR_IDENTITY)

    def apply(self, transitions: Sequence[StatusTransition], tick: int) -> None:
        """Commit each transition to ``main`` in order, then push once."""
        if not transitions:
            return
        self._world.run_git(self._clone, "pull", "-q", "--ff-only", "origin", "main")
        path = self._clone / ROADMAP_FILE
        for t in transitions:
            data = yaml.safe_load(path.read_text())
            item = next((i for i in data.get("items", []) if i.get("item_id") == t.item_id), None)
            if item is None:
                raise ScenarioError(f"roadmap has no item {t.item_id!r} reported by {t.principal}")
            item["status"] = t.status
            path.write_text(yaml.safe_dump(data, sort_keys=False))
            self._world.commit_as(
                self._clone,
                f"chore(roadmap): {t.item_id} -> {t.status} ({t.principal} {t.step} {t.when})",
                SUPERVISOR_IDENTITY,
                tick,
            )
        self._world.run_git(self._clone, "push", "-q", "origin", "HEAD:refs/heads/main")
