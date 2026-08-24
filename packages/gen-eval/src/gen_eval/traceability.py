"""Requirement traceability: stable identifiers, resolution, and citations.

Implements the first edge of the four-edge chain ``requirement -> contract ->
descriptor -> declared surface`` (design: `trace-requirements-to-contracts`).
This module owns two things that later phases build on:

- **Requirement identifiers** (D2): a requirement id is
  ``<capability>.<slug-of-heading>``, derived from the heading text under
  ``### Requirement:`` in ``openspec/specs/<capability>/spec.md``. Two
  headings deriving the same slug fail closed, naming both.
- **The effective requirement set** (D11): the archived spec, shadowed by
  the active change's own spec delta. ``ADDED``/``MODIFIED`` requirements
  from the delta appear or replace their archived version; ``REMOVED``
  requirements disappear; ``RENAMED`` requirements resolve under the new
  identifier only. Requirements belonging to *other* in-flight changes are
  never read — the resolver is handed one ``change_id`` at a time and reads
  only that change's delta, never scanning ``openspec/changes/*``.

``specs_root`` and ``changes_root`` are constructor parameters, never
hardcoded repo-relative hops: this package is installed standalone by
downstream consumers where ``openspec/`` does not exist (see
``findings_emitter.py``'s ancestor-search precedent for the same concern
solved a different way — this module takes the roots as input instead,
because a gate script always has a natural place to resolve real defaults,
per task 1.2's note).

No OpenSpec CLI dependency at runtime: everything here reads the same
markdown ``openspec`` itself renders, via ``re``, never by shelling out.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# D2 — the normative slug algorithm
# ---------------------------------------------------------------------------

_REQUIREMENT_HEADING_RE = re.compile(r"(?m)^### Requirement:[ \t]*(?P<name>.+?)[ \t]*$")
_SCENARIO_RE = re.compile(r"(?m)^#### Scenario:")
_DELTA_SECTION_RE = re.compile(
    r"(?m)^## (?P<op>ADDED|MODIFIED|REMOVED|RENAMED) Requirements[ \t]*$"
)
# OpenSpec's own RENAMED shape (skill-templates.js): "- FROM: `### Requirement: X`"
# and "- TO: `### Requirement: Y`", the backticks and leading "- " optional.
_RENAME_FROM_RE = re.compile(r"^\s*-?\s*FROM:\s*`?###\s*Requirement:\s*(?P<name>.+?)`?\s*$")
_RENAME_TO_RE = re.compile(r"^\s*-?\s*TO:\s*`?###\s*Requirement:\s*(?P<name>.+?)`?\s*$")

#: D2's consequence: bound the candidate list so a capability-wide rename
#: (skill-workflow has 208 requirement headings) does not print failures
#: times headings.
_MAX_CANDIDATES = 5


def slugify(heading: str) -> str:
    """The D2 normative slug algorithm.

    NFKD normalize and drop non-ASCII marks, lowercase, replace each run of
    characters outside ``[a-z0-9]`` with a single ``-``, collapse, strip
    leading and trailing ``-``. Written down because real headings in this
    repository start with backticks and contain em-dashes; a naive rule
    turns those into ids the citation schema's pattern rejects.
    """
    text = unicodedata.normalize("NFKD", heading)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def requirement_id(capability: str, heading: str) -> str:
    """The full ``<capability>.<slug>`` identifier for one heading."""
    return f"{capability}.{slugify(heading)}"


# ---------------------------------------------------------------------------
# Fail-closed errors
# ---------------------------------------------------------------------------


class TraceabilityError(Exception):
    """Base for every fail-closed error this module raises (D1/D2/D11)."""


class RequirementCollisionError(TraceabilityError):
    """Two or more headings in one capability derive the same slug (D2).

    An undetected collision is worse than a broken citation: a citation to
    the shared id marks *both* requirements cited, and one becomes invisible
    to reverse completeness with no signal. Fails closed naming every
    colliding heading rather than picking one silently.
    """

    def __init__(self, capability: str, slug: str, headings: list[str]) -> None:
        self.capability = capability
        self.slug = slug
        self.headings = list(headings)
        named = ", ".join(repr(h) for h in self.headings)
        super().__init__(
            f"{capability}: {len(self.headings)} requirement headings derive the "
            f"same identifier {capability}.{slug}: {named}. Reword one heading "
            f"so each requirement has a distinct id."
        )


class UnresolvedRequirementError(TraceabilityError):
    """``requirement_id`` resolves to nothing in the effective requirement set (D2).

    Names the id and up to :data:`_MAX_CANDIDATES` nearest candidate
    headings by edit distance, ranked for a human to scan — display only,
    never a rebind (D1's inference is forbidden even here).
    """

    def __init__(self, req_id: str, candidates: list[str]) -> None:
        self.requirement_id = req_id
        self.candidates = list(candidates)
        message = (
            f"{req_id!r} is not in the effective requirement set: no requirement "
            f"derives this identifier."
        )
        if self.candidates:
            listed = ", ".join(repr(c) for c in self.candidates)
            message += f" Nearest candidate headings: {listed}."
        super().__init__(message)


class MalformedDeltaError(TraceabilityError):
    """A change's spec delta disagrees with the archive it shadows.

    Mirrors the real OpenSpec archiver's own validation (RENAMED source not
    found / target exists, REMOVED not found, MODIFIED not found, ADDED
    already exists) so this resolver never silently accepts a delta the
    archiver would reject. Deliberately fail-closed rather than a silent
    best-effort merge (D2's philosophy applied to delta application).
    """


# ---------------------------------------------------------------------------
# Spec / delta parsing (no OpenSpec CLI; markdown only)
# ---------------------------------------------------------------------------


def parse_requirement_headings(spec_text: str) -> list[str]:
    """Ordered ``### Requirement:`` heading texts, verbatim."""
    return [m["name"] for m in _REQUIREMENT_HEADING_RE.finditer(spec_text)]


def _split_blocks(spec_text: str) -> list[tuple[str, str]]:
    """``(heading, body_text)`` pairs; body runs to the next heading or EOF."""
    matches = list(_REQUIREMENT_HEADING_RE.finditer(spec_text))
    blocks: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(spec_text)
        blocks.append((match["name"], spec_text[start:end].strip()))
    return blocks


def requirement_body_text(block_text: str) -> str:
    """The requirement's own prose, excluding its ``#### Scenario:`` blocks."""
    match = _SCENARIO_RE.search(block_text)
    body = block_text[: match.start()] if match else block_text
    return body.strip()


@dataclass(frozen=True)
class ParsedDelta:
    """One change's spec delta for one capability, split by operation."""

    added: tuple[tuple[str, str], ...]
    modified: tuple[tuple[str, str], ...]
    removed: tuple[str, ...]
    renamed: tuple[tuple[str, str], ...]


def _parse_renames(section_body: str) -> list[tuple[str, str]]:
    renames: list[tuple[str, str]] = []
    pending_from: str | None = None
    for line in section_body.splitlines():
        from_match = _RENAME_FROM_RE.match(line)
        if from_match:
            pending_from = from_match["name"].strip()
            continue
        to_match = _RENAME_TO_RE.match(line)
        if to_match and pending_from is not None:
            renames.append((pending_from, to_match["name"].strip()))
            pending_from = None
    return renames


def parse_delta(delta_text: str) -> ParsedDelta:
    """Parse one ``## ADDED/MODIFIED/REMOVED/RENAMED Requirements`` delta.

    Reads the same markdown ``openspec`` renders and validates; this is not
    a second parser drifting from the CLI's, it is the same grammar reread
    (D11's stated risk mitigation).
    """
    added: list[tuple[str, str]] = []
    modified: list[tuple[str, str]] = []
    removed: list[str] = []
    renamed: list[tuple[str, str]] = []

    sections = list(_DELTA_SECTION_RE.finditer(delta_text))
    for i, section in enumerate(sections):
        op = section["op"]
        body_start = section.end()
        body_end = sections[i + 1].start() if i + 1 < len(sections) else len(delta_text)
        body = delta_text[body_start:body_end]
        if op == "RENAMED":
            renamed.extend(_parse_renames(body))
            continue
        blocks = _split_blocks(body)
        if op == "ADDED":
            added.extend(blocks)
        elif op == "MODIFIED":
            modified.extend(blocks)
        elif op == "REMOVED":
            removed.extend(name for name, _ in blocks)

    return ParsedDelta(
        added=tuple(added), modified=tuple(modified), removed=tuple(removed), renamed=tuple(renamed)
    )


def _nearest_headings(slug: str, headings: list[str], limit: int = _MAX_CANDIDATES) -> list[str]:
    by_slug = {slugify(h): h for h in headings}
    matches = difflib.get_close_matches(slug, list(by_slug), n=limit, cutoff=0.0)
    return [by_slug[m] for m in matches]


def _collision_check(capability: str, headings: list[str]) -> dict[str, str]:
    """``slug -> heading``, raising :class:`RequirementCollisionError` on a dup."""
    by_slug: dict[str, list[str]] = {}
    for heading in headings:
        by_slug.setdefault(slugify(heading), []).append(heading)
    for slug, names in sorted(by_slug.items()):
        if len(names) > 1:
            raise RequirementCollisionError(capability, slug, names)
    return {slug: names[0] for slug, names in by_slug.items()}


# ---------------------------------------------------------------------------
# The resolver (D2, D11)
# ---------------------------------------------------------------------------


class RequirementResolver:
    """Resolves requirement identifiers against the repository's own specs.

    ``specs_root`` (``openspec/specs``) and ``changes_root``
    (``openspec/changes``) are parameters — never a hardcoded
    ``Path(__file__).parent...`` hop — so tests can inject ``tmp_path`` roots
    and a downstream consumer can point this at a repository that has no
    ``openspec/`` at all (``scripts/check_traceability.py`` resolves the real
    repo-relative defaults; this class never does).

    A resolver is handed one ``change_id`` at a time (or none). It reads
    only ``changes_root/<change_id>/specs/<capability>/spec.md`` — never
    ``changes_root/*`` — so another in-flight change's requirements are
    structurally invisible (D11): there is no code path that could read them.
    """

    def __init__(self, specs_root: Path, changes_root: Path) -> None:
        self.specs_root = Path(specs_root)
        self.changes_root = Path(changes_root)

    def archived_headings(self, capability: str) -> list[str]:
        """Ordered headings from the archived spec.

        Empty for a capability with no ``spec.md`` — the schemas-only case
        (D6): a capability may hold only contract schemas and no spec.
        """
        spec_path = self.specs_root / capability / "spec.md"
        if not spec_path.is_file():
            return []
        return parse_requirement_headings(spec_path.read_text(encoding="utf-8"))

    def _delta(self, capability: str, change_id: str) -> ParsedDelta | None:
        delta_path = self.changes_root / change_id / "specs" / capability / "spec.md"
        if not delta_path.is_file():
            return None
        return parse_delta(delta_path.read_text(encoding="utf-8"))

    def effective_headings(self, capability: str, change_id: str | None = None) -> dict[str, str]:
        """``slug -> heading`` for the effective requirement set.

        The archive, shadowed by ``change_id``'s delta if given. Operation
        order mirrors OpenSpec's own archiver exactly (RENAMED -> REMOVED ->
        MODIFIED -> ADDED) so this resolver never accepts a delta shape the
        real archiver would reject, and every operation is validated the
        same way: RENAMED requires an existing source and an unused target;
        REMOVED and MODIFIED require an existing target; ADDED requires an
        unused name. A MODIFIED block naming a heading absent from the
        current set is therefore a :class:`MalformedDeltaError`, not a
        silent add — the only "the old id stops, the new one starts" path is
        an explicit RENAMED entry.
        """
        names = list(self.archived_headings(capability))
        name_set = set(names)

        if change_id is not None:
            delta = self._delta(capability, change_id)
            if delta is not None:
                for old, new in delta.renamed:
                    if old not in name_set:
                        raise MalformedDeltaError(
                            f"{capability}: RENAMED names {old!r} as FROM, but no "
                            f"requirement by that name is in the effective set."
                        )
                    if new in name_set:
                        raise MalformedDeltaError(
                            f"{capability}: RENAMED TO {new!r} already exists in "
                            f"the effective set."
                        )
                    names = [new if n == old else n for n in names]
                    name_set.discard(old)
                    name_set.add(new)

                for name in delta.removed:
                    if name not in name_set:
                        raise MalformedDeltaError(
                            f"{capability}: REMOVED names {name!r}, which is not in "
                            f"the effective set."
                        )
                    names = [n for n in names if n != name]
                    name_set.discard(name)

                for name, _ in delta.modified:
                    if name not in name_set:
                        raise MalformedDeltaError(
                            f"{capability}: MODIFIED names {name!r}, which is not in "
                            f"the effective set — a MODIFIED block replaces an "
                            f"existing requirement's body, it cannot rename one; "
                            f"use RENAMED to change a heading."
                        )
                    # Body changes don't affect the id; name stays in place.

                for name, _ in delta.added:
                    if name in name_set:
                        raise MalformedDeltaError(
                            f"{capability}: ADDED names {name!r}, which already "
                            f"exists in the effective set."
                        )
                    names.append(name)
                    name_set.add(name)

        return _collision_check(capability, names)

    def resolve(self, req_id: str, *, change_id: str | None = None) -> str:
        """Return the heading ``req_id`` names, or raise (fail closed, D2).

        ``req_id`` must be a well-formed ``<capability>.<slug>`` citation; a
        malformed one (no ``.``) fails with no candidates rather than being
        treated as a capability with an empty slug.
        """
        capability, sep, slug = req_id.partition(".")
        if not sep or not capability or not slug:
            raise UnresolvedRequirementError(req_id, [])
        by_slug = self.effective_headings(capability, change_id=change_id)
        heading = by_slug.get(slug)
        if heading is not None:
            return heading
        raise UnresolvedRequirementError(req_id, _nearest_headings(slug, list(by_slug.values())))

    def resolves(self, req_id: str, *, change_id: str | None = None) -> bool:
        """``True`` iff :meth:`resolve` would not raise."""
        try:
            self.resolve(req_id, change_id=change_id)
        except UnresolvedRequirementError:
            return False
        return True


# ---------------------------------------------------------------------------
# The traceability block model (D1) — parsed only, never inferred
# ---------------------------------------------------------------------------


class TraceabilityExclusion(BaseModel):
    """``excluded`` on an operation-side traceability block (D4).

    Mirrors ``traceability.schema.json``'s ``excluded`` object: a non-blank
    reason is the only requirement pydantic enforces here. Whether the
    reason is a *good* reason is a review question, not a parse question.
    """

    reason: str = Field(min_length=1)


class TraceabilityBlock(BaseModel):
    """One contracted operation's traceability (D1): citations, or an exclusion.

    Carried as ``x-traceability`` on an OpenAPI operation and as
    ``traceability`` on a CLI contract flag, positional, or command — one
    model, two surface spellings, matching ``contracts/traceability.schema.json``
    exactly (including its ``oneOf``: an operation that both cites and
    excludes is stating that it has a purpose and that it has none).

    Parsing only. Nothing on this class or its callers infers a citation
    from a name, a path, or prose similarity — every ``requirements`` entry
    is copied verbatim from the contract as written (D1). Resolving those
    entries against the effective requirement set is a separate step
    (:func:`resolve_citations`), and evaluating completeness is Phase 3's.
    """

    requirements: list[str] | None = None
    excluded: TraceabilityExclusion | None = None

    @model_validator(mode="after")
    def _exactly_one_of_requirements_or_excluded(self) -> TraceabilityBlock:
        has_requirements = self.requirements is not None
        has_excluded = self.excluded is not None
        if has_requirements == has_excluded:
            raise ValueError(
                "a traceability block must set exactly one of `requirements` or "
                "`excluded` — citing a requirement and excluding the operation "
                "at once states both that it has a purpose and that it has none"
            )
        if has_requirements and not self.requirements:
            raise ValueError(
                "`requirements` must not be empty — an empty list is an "
                "exclusion written without a reason, spelled differently"
            )
        return self


def resolve_citations(
    block: TraceabilityBlock,
    resolver: RequirementResolver,
    *,
    change_id: str | None = None,
) -> list[str]:
    """Resolve every id in ``block.requirements`` to its heading, fail closed.

    Returns ``[]`` for an excluded block (nothing to resolve) and the
    resolved headings, in citation order, otherwise. The first unresolved id
    raises :class:`UnresolvedRequirementError` immediately, naming the id and
    its nearest candidates (D2) — resolution is a precondition for
    completeness evaluation; reporting every failure across a whole run is
    Phase 3's job, not this function's.
    """
    if block.requirements is None:
        return []
    return [resolver.resolve(req_id, change_id=change_id) for req_id in block.requirements]


__all__ = [
    "MalformedDeltaError",
    "ParsedDelta",
    "RequirementCollisionError",
    "RequirementResolver",
    "TraceabilityBlock",
    "TraceabilityError",
    "TraceabilityExclusion",
    "UnresolvedRequirementError",
    "parse_delta",
    "parse_requirement_headings",
    "requirement_body_text",
    "requirement_id",
    "resolve_citations",
    "slugify",
]
