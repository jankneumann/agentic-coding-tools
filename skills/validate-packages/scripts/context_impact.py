"""Infer which derived context surfaces a work package affects (ri-08).

A work package may declare, in an optional ``context_impact`` block, which
project-context surfaces it can invalidate. That declaration is a *reviewable
hint* — a planner can simply omit it — so this module never treats it as
evidence of completeness. The authoritative signal is the package's changed
files, intersected with its declared write scope, run through a glob rule table.

The library layer is deliberately git-free: it takes changed files as a
sequence and never shells out. That keeps it unit-testable with no repository
present and lets ri-09 reuse it with a checkpoint's own file list instead of a
git range. ``validate_context_impact.py`` is the CLI that resolves a git range
into that sequence.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

try:
    import yaml
except ImportError:  # pragma: no cover - environment guard
    sys.exit("pyyaml is required: pip install pyyaml")


#: The canonical context surfaces. Must stay identical to the ``ContextSurface``
#: enum in ``work-packages.schema.json``; pinned by
#: ``test_surfaces_constant_matches_the_schema_enum``.
SURFACES: tuple[str, ...] = (
    "capabilities",
    "apis",
    "architecture",
    "decisions",
    "documentation",
    "semantic_code",
)

RULES_FILENAME = "context-impact-rules.yaml"

#: The work-package declaration file. Duplicated from ``gate.py`` rather than
#: imported, because the dependency runs the other way: ``gate.py`` imports this
#: module, and this module must stay importable with no gate present.
WORK_PACKAGES_FILENAME = "work-packages.yaml"

#: Write-scope globs that match every conceivable path. Such a glob does not
#: *declare* a scope, it declines to: it draws no boundary and so distinguishes
#: nothing. Mirrors ``BROAD_WRITE_SCOPES`` in
#: ``skills/autopilot/scripts/complexity_gate.py``, which already treats exactly
#: this set as a scope-safety concern rather than as a claim.
BOUNDLESS_WRITE_SCOPES = frozenset({"**", "**/*", "*", ".", "./"})


class ContextImpactRulesError(Exception):
    """The rule table is missing, malformed, or names an unknown surface."""


def _find_repo_root() -> Path:
    """Find the git repository root, mirroring ``validate_work_packages.py``."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        p = Path(__file__).resolve().parent
        while p != p.parent:
            if (p / ".git").exists() or (p / "openspec").exists():
                return p
            p = p.parent
        return Path(__file__).resolve().parent.parent


def default_rules_path() -> Path:
    """Where to look for the rule table.

    The installed location (``<repo>/openspec/schemas/``) wins, because that is
    where ``install.sh`` places the file in a consumer repository. The
    script-relative install asset is the fallback so the detector still works in
    this repository before ``install.sh`` has been re-run.
    """
    installed = _find_repo_root() / "openspec" / "schemas" / RULES_FILENAME
    if installed.is_file():
        return installed
    return (
        Path(__file__).resolve().parent.parent
        / "install_assets"
        / "openspec"
        / "schemas"
        / RULES_FILENAME
    )


@dataclass(frozen=True)
class ImpactRules:
    """Glob patterns per context surface."""

    surface_globs: Mapping[str, tuple[str, ...]]
    source: Path

    def surfaces(self) -> tuple[str, ...]:
        return tuple(self.surface_globs)

    def globs_for(self, surface: str) -> tuple[str, ...]:
        return self.surface_globs.get(surface, ())


def load_rules(path: Path | None = None) -> ImpactRules:
    """Load and validate the rule table.

    Fails loudly on a missing file rather than yielding an empty rule set: a
    detector that matches nothing would let every package pass the gate while
    appearing to work.
    """
    resolved = Path(path) if path is not None else default_rules_path()
    if not resolved.is_file():
        raise ContextImpactRulesError(f"context-impact rule table not found: {resolved}")

    try:
        document = yaml.safe_load(resolved.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ContextImpactRulesError(f"{resolved}: invalid YAML: {exc}") from exc

    raw_rules = document.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ContextImpactRulesError(f"{resolved}: 'rules' must be a non-empty list")

    surface_globs: dict[str, tuple[str, ...]] = {}
    for index, rule in enumerate(raw_rules):
        if not isinstance(rule, dict):
            raise ContextImpactRulesError(f"{resolved}: rule {index} is not a mapping")
        surface = rule.get("surface")
        if surface not in SURFACES:
            raise ContextImpactRulesError(
                f"{resolved}: rule {index} names unknown surface {surface!r}; "
                f"known surfaces: {', '.join(SURFACES)}"
            )
        globs = rule.get("globs")
        if not isinstance(globs, list) or not globs:
            raise ContextImpactRulesError(
                f"{resolved}: rule for surface {surface!r} has no globs"
            )
        merged = surface_globs.get(surface, ()) + tuple(str(g) for g in globs)
        surface_globs[surface] = merged

    return ImpactRules(surface_globs=surface_globs, source=resolved)


def matches(path: str, pattern: str) -> bool:
    """Match a repo-relative path against a glob.

    ``fnmatchcase`` rather than ``fnmatch`` so behavior does not vary with the
    host filesystem's case sensitivity. A ``**/`` prefix additionally matches at
    the repository root, so ``**/*.py`` covers both ``pkg/mod.py`` and
    ``setup.py`` — plain fnmatch would require the separator.
    """
    if fnmatchcase(path, pattern):
        return True
    if pattern.startswith("**/") and fnmatchcase(path, pattern[3:]):
        return True
    return False


def _matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(matches(path, pattern) for pattern in patterns)


@dataclass(frozen=True)
class IndexScopes:
    """A package's resolved read scope, for downstream context consumers.

    Resolves rather than duplicates: the globs live on ``scope``, and adding a
    parallel copy under ``context_impact`` would create two sources of truth.
    """

    read_allow: tuple[str, ...]
    deny: tuple[str, ...]

    def allows(self, path: str) -> bool:
        """Whether ``path`` is readable. ``deny`` takes precedence."""
        if _matches_any(path, self.deny):
            return False
        return _matches_any(path, self.read_allow)


def index_scopes(package: Mapping[str, Any]) -> IndexScopes:
    """Resolve a work package's read scope for indexing and context injection."""
    scope = package.get("scope") or {}
    return IndexScopes(
        read_allow=tuple(scope.get("read_allow") or ()),
        deny=tuple(scope.get("deny") or ()),
    )


def declared_surfaces(package: Mapping[str, Any]) -> frozenset[str] | None:
    """The surfaces a package declares, or ``None`` when it declares nothing.

    ``None`` and ``frozenset()`` are deliberately different: the first means the
    package predates the field (``unmigrated``), the second is an explicit
    "affects nothing" assertion that the gate checks strictly.
    """
    block = package.get("context_impact")
    if block is None:
        return None
    return frozenset(block.get("surfaces") or ())


def declared_rationale(package: Mapping[str, Any]) -> Mapping[str, Mapping[str, str]]:
    """Per-surface approved rationale, empty when absent."""
    block = package.get("context_impact") or {}
    return block.get("rationale") or {}


def carries_a_declaration(changed_files: Sequence[str]) -> bool:
    """Whether the changed-file list transports a work-package declaration.

    This is the shape the gate always evaluates — it selects a
    ``work-packages.yaml`` *because* the diff moved or edited it — and it is the
    shape in which co-presence is least likely to be authorship: a plan commit
    writes the declaration alongside nothing, and an archive commit moves it
    alongside whatever else that commit regenerated.
    """
    return any(
        PurePosixPath(path).name == WORK_PACKAGES_FILENAME for path in changed_files
    )


def attributing_globs(
    write_allow: Sequence[str], changed_files: Sequence[str]
) -> tuple[str, ...]:
    """The ``write_allow`` globs that may attribute a path in *changed_files*.

    D6: a changed path is attributed to a work package when that package's
    *declared* scope covers it. A boundless glob (see
    ``BOUNDLESS_WRITE_SCOPES``) declares nothing — it covers every path in the
    repository equally, so a match against it is not evidence about this package
    at all, only evidence that the path was in the diff. Attribution through it
    is attribution by co-presence, which is what this function removes.

    It is dropped only when the diff carries a work-package declaration, because
    that is exactly the case where a diff is known to be transporting
    declarations rather than reporting one package's own edits. Elsewhere —
    ri-09's uncommitted checkpoint file lists, and any caller using this module
    as a plain path classifier — a boundless glob keeps its historical
    "everything is mine" reading, since there is no other candidate author to
    confuse it with.
    """
    if not carries_a_declaration(changed_files):
        return tuple(write_allow)
    return tuple(glob for glob in write_allow if glob not in BOUNDLESS_WRITE_SCOPES)


def package_files(
    package: Mapping[str, Any], changed_files: Sequence[str]
) -> tuple[str, ...]:
    """Changed files this package is responsible for.

    A package can only invalidate context through files it is allowed to write,
    so files outside ``scope.write_allow`` — or inside ``scope.deny`` — are not
    its impact to declare. ``attributing_globs`` further drops a boundless
    ``write_allow`` when the diff transports work-package declarations: PR #423
    charged an archived change's ``wp-integration`` with ``decisions`` for five
    ``docs/decisions/*.md`` files the archive commit itself had regenerated,
    purely because that package declared ``write_allow: ['**']``.
    """
    scope = package.get("scope") or {}
    write_allow = attributing_globs(
        tuple(scope.get("write_allow") or ()), changed_files
    )
    deny = tuple(scope.get("deny") or ())
    return tuple(
        path
        for path in changed_files
        if _matches_any(path, write_allow) and not _matches_any(path, deny)
    )


def infer_surfaces(
    package: Mapping[str, Any],
    changed_files: Sequence[str],
    rules: ImpactRules,
    contract_files: Sequence[str] = (),
) -> dict[str, tuple[str, ...]]:
    """Map a package's changed files onto the surfaces they invalidate.

    Returns ``{surface: (files that implied it, ...)}``. A surface with no
    implying file is absent rather than present-and-empty, so ``not implied``
    reads as "this package invalidates nothing".
    """
    owned = package_files(package, changed_files)
    implied: dict[str, list[str]] = {}

    for path in owned:
        for surface in SURFACES:
            if _matches_any(path, rules.globs_for(surface)):
                implied.setdefault(surface, []).append(path)

    # A file the change declares as a contract implies `apis` regardless of
    # where it lives — a contract kept outside the usual directories is still a
    # contract.
    contract_set = set(contract_files)
    for path in owned:
        if path in contract_set and path not in implied.get("apis", []):
            implied.setdefault("apis", []).append(path)

    return {surface: tuple(paths) for surface, paths in implied.items()}


__all__ = [
    "SURFACES",
    "ContextImpactRulesError",
    "ImpactRules",
    "IndexScopes",
    "attributing_globs",
    "carries_a_declaration",
    "declared_rationale",
    "declared_surfaces",
    "default_rules_path",
    "index_scopes",
    "infer_surfaces",
    "load_rules",
    "matches",
    "package_files",
]
