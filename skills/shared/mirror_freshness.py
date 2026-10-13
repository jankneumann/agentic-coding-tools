"""Detect a runtime skill mirror that has drifted from the canonical source.

Agents execute skills from ``.claude/skills/`` or ``.agents/skills/``, which
``skills/install.sh`` rsyncs from ``skills/`` once and never refreshes.  A
long-lived checkout keeps running that snapshot after toolkit fixes merge to
``skills/``: the openrouter-review-lane PLAN_REVIEW ran a ``review_ledger``
mirror that predated ``fix_touched_file`` and re-opened ten fixed findings.

``stale_mirror`` answers one question for the script that calls it: is it
running from a mirror whose payload no longer matches the ``skills/`` tree of
the same repository?  It never syncs; the caller decides how loudly to warn.

Dependency-free (standard library only) so it installs in the consumer layout.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shared.payload_hash import MANIFEST_NAME, hash_payload, payload_names

MIRROR_PARENTS = frozenset({".claude", ".agents"})
SYNC_COMMAND = "bash skills/install.sh --mode rsync --deps none --python-tools none"


@dataclass(frozen=True)
class MirrorDrift:
    mirror: Path
    canonical: Path
    mirror_hash: str
    canonical_hash: str

    def message(self) -> str:
        return (
            f"runtime skill mirror {self.mirror} differs from {self.canonical} "
            f"({self.mirror_hash[:19]} != {self.canonical_hash[:19]}); this run "
            f"executes stale toolkit code. Resync from the repository root: "
            f"{SYNC_COMMAND}"
        )


def _mirror_root(script_path: Path) -> Path | None:
    for parent in script_path.resolve().parents:
        if parent.name == "skills" and parent.parent.name in MIRROR_PARENTS:
            return parent
    return None


def stale_mirror(script_path: Path | str) -> MirrorDrift | None:
    """Return the drift when ``script_path`` runs from a stale mirror.

    Returns ``None`` when the script runs from the canonical tree, when the
    repository has no canonical ``skills/`` source (a consumer install), when
    the manifest is unreadable, or when the payloads match.
    """
    mirror = _mirror_root(Path(script_path))
    if mirror is None:
        return None
    canonical = mirror.parent.parent / "skills"
    manifest = canonical / MANIFEST_NAME
    if not (canonical / "install.sh").is_file() or not manifest.is_file():
        return None
    try:
        skills, libraries = payload_names(manifest)
    except (OSError, ValueError, KeyError):
        return None
    canonical_hash = hash_payload(canonical, skills, libraries)
    mirror_hash = hash_payload(mirror, skills, libraries)
    if canonical_hash == mirror_hash:
        return None
    return MirrorDrift(mirror, canonical, mirror_hash, canonical_hash)
