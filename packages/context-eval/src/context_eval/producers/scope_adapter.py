"""Resolve the shared scope-normalization dependency, or say that it did not.

ri-12's ``_normalize_read_scope`` (``semantic_context.py:919``) normalizes a
package's declared globs through ri-09's ``ReadScope``, which resolves deny
precedence on the value and rejects a scope whose deny list cancels every glob
it allows. That function is **not injectable**: it mutates ``sys.path`` and
imports ``semantic_adapter`` directly, and when the import fails it returns the
raw, unnormalized globs (``:934-938``) with nothing recorded anywhere.

That silent fallback is the hazard this module exists to make visible. A
compliance number computed under unnormalized glob semantics is not a weaker
version of the same measurement — it is a measurement of something else, wearing
the same name. So the harness records ``scope_adapter: "resolved" | "degraded"``
and treats ``degraded`` as an ``apparatus_failure`` fail reason rather than a
result (design D8).

This module and ``producers/semantic_runtime.py`` are the only two places in
``packages/`` that know ``skills/`` exists, and both obey the same rule: the
location is **supplied by configuration**, never derived from ``__file__``.
Resolution is attempted exactly the way ri-12 attempts it — same directory, same
module name, same ``sys.path`` insertion — so a ``resolved`` verdict here is
evidence about the import ri-12 will perform, not about a lookalike.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RESOLVED = "resolved"
DEGRADED = "degraded"

#: The two states the report's ``environment.scope_adapter`` may carry.
SCOPE_ADAPTER_STATES: tuple[str, ...] = (RESOLVED, DEGRADED)

#: The module ri-12 imports, and the attribute it needs from it.
ADAPTER_MODULE = "semantic_adapter"
ADAPTER_ATTRIBUTE = "ReadScope"

#: ``skills/project-context-refresh/scripts`` relative to a repository root.
#: A default *location within a supplied root*, not a derived root: the caller
#: still has to say which checkout, which is the property D1 is about.
DEFAULT_ADAPTER_SUBPATH = Path("skills") / "project-context-refresh" / "scripts"


class ScopeSelfCancellingError(ValueError):
    """The declared scope denies every glob it allows (ri-09's own rule)."""


@dataclass(frozen=True)
class ScopeAdapter:
    """A resolved-or-not normalizer for declared read scopes."""

    status: str
    #: ``ReadScope`` when resolved, ``None`` when degraded. Untyped because the
    #: class is loaded from a path this package must not import statically.
    read_scope: Any = field(default=None, repr=False, compare=False)
    detail: str | None = None

    @property
    def resolved(self) -> bool:
        return self.status == RESOLVED

    def normalize(
        self, read_allow: Sequence[str], deny: Sequence[str]
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Normalize a declared scope exactly as ri-12 would.

        The degraded branch returns the globs untouched — deliberately identical
        to ``semantic_context.py:934-938``, so a caller that ignores ``status``
        gets ri-12's real degraded behaviour rather than a sanitized imitation of
        it. Ignoring ``status`` is what the gate forbids; hiding the consequence
        would make the forbidding pointless.
        """
        if not self.resolved:
            return (tuple(read_allow), tuple(deny))
        try:
            normalized = self.read_scope(read_allow=tuple(read_allow), deny=tuple(deny))
        except ValueError as error:
            raise ScopeSelfCancellingError(str(error)) from error
        return (tuple(normalized.read_allow), tuple(normalized.deny))


def resolve_scope_adapter(adapter_dir: Path | str | None) -> ScopeAdapter:
    """Load ri-09's ``ReadScope`` from *adapter_dir*, or report a degraded adapter.

    ``None`` is a legitimate input meaning "no location was configured", and it
    degrades rather than raising: the run continues far enough to write a report
    that says why it cannot be trusted, which is the whole shape of a fail-closed
    harness.
    """
    if adapter_dir is None:
        return ScopeAdapter(status=DEGRADED, detail="no scope adapter location was configured")

    directory = Path(adapter_dir)
    if not (directory / f"{ADAPTER_MODULE}.py").is_file():
        return ScopeAdapter(
            status=DEGRADED, detail=f"{ADAPTER_MODULE}.py is not present in {directory}"
        )

    # Same insertion ri-12 performs. Importing by name rather than by file
    # location is required, not incidental: the adapter imports two siblings
    # from its own directory, so a location-loaded module would fail on them.
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

    # Drop a cached module loaded from somewhere else first. Without this a
    # second call against a broken location would be answered by the first
    # call's module and report `resolved` — the exact silent success this whole
    # module exists to prevent, arriving through the import system instead of
    # through ri-12.
    cached = sys.modules.get(ADAPTER_MODULE)
    if cached is not None and not _loaded_from(cached, directory):
        del sys.modules[ADAPTER_MODULE]

    try:
        module = __import__(ADAPTER_MODULE)
        read_scope = getattr(module, ADAPTER_ATTRIBUTE)
    # Every way loading can fail is one fact — "the shared normalization rules
    # are not available here" — and each must produce `degraded` rather than
    # propagate. `SystemExit` is named explicitly because the sibling skills
    # call `sys.exit` on a missing dependency and that is not an `Exception`.
    except (Exception, SystemExit) as error:  # noqa: BLE001
        return ScopeAdapter(status=DEGRADED, detail=f"{ADAPTER_MODULE} did not import: {error!r}")

    if not _loaded_from(module, directory):
        return ScopeAdapter(
            status=DEGRADED,
            detail=f"{ADAPTER_MODULE} resolved to {getattr(module, '__file__', None)}",
        )
    return ScopeAdapter(status=RESOLVED, read_scope=read_scope)


def _loaded_from(module: Any, directory: Path) -> bool:
    """Is *module* the one that lives in *directory*?

    Identity by location, not by name. Two checkouts on one machine — a
    worktree and its shared repository — hold two ``semantic_adapter`` modules
    with the same name and possibly different normalization rules, and the one
    the report claims to have used has to be the one it used.
    """
    origin = getattr(module, "__file__", None)
    if origin is None:
        return False
    return Path(origin).resolve().parent == directory.resolve()


def adapter_dir_for(repository_root: Path) -> Path:
    """Where ``semantic_adapter`` lives inside a supplied checkout."""
    return Path(repository_root) / DEFAULT_ADAPTER_SUBPATH
