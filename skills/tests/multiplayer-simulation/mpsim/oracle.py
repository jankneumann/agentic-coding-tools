"""Ground-truth collision oracle (design D4).

A plain string comparison over files the fixture wrote: two spec deltas collide when
they name the same ``### Requirement:`` heading of the same capability. It reads no git
history and does no live scanning. It is not a detector and is never registered as a
probe; it exists so a broken fixture cannot make "not detected" trivially true.
"""

from __future__ import annotations

import re
from pathlib import Path

_HEADING = re.compile(r"^###\s+Requirement:\s*(.+?)\s*$", re.MULTILINE)


def delta_requirements(change_dir: Path) -> set[tuple[str, str]]:
    """(capability, requirement heading) pairs named by ``<change_dir>/specs/*/spec.md``."""
    found: set[tuple[str, str]] = set()
    for spec in sorted(Path(change_dir).glob("specs/*/spec.md")):
        capability = spec.parent.name
        for heading in _HEADING.findall(spec.read_text()):
            found.add((capability, heading))
    return found


def collision_present(first_change_dir: Path, second_change_dir: Path) -> bool:
    return bool(delta_requirements(first_change_dir) & delta_requirements(second_change_dir))
