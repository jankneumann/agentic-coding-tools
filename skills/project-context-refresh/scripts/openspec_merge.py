"""Offline requirement-block merge for OpenSpec delta projection (D6).

The OpenSpec archiver merges a change's ``## ADDED/MODIFIED/REMOVED
Requirements`` deltas into ``openspec/specs/<capability>/spec.md``. This module
computes that same projection *in memory*, at requirement-block granularity, so
the ``openspec.projection`` producer can report what canonical specs would
become without ever mutating them, archiving a change, or invoking the npm CLI
(keeping the check offline and deterministic).

It edits only the requirement blocks a delta names; every other byte of the
canonical spec is spliced through verbatim, so a capability touched by an
unrelated delta is not spuriously reported as changed.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

_REQUIREMENT_RE = re.compile(r"(?m)^### Requirement:[ \t]*(?P<name>.+?)[ \t]*$")
_SECTION_RE = re.compile(
    r"(?m)^## (?P<op>ADDED|MODIFIED|REMOVED|RENAMED) Requirements[ \t]*$"
)


def split_requirements(spec_text: str) -> tuple[str, list[tuple[str, str]]]:
    """Split *spec_text* into ``(head, [(name, block_text), ...])``.

    ``head`` is everything before the first ``### Requirement:`` (including the
    ``## Requirements`` header). Each ``block_text`` runs from its
    ``### Requirement:`` line to just before the next requirement header (or EOF),
    preserving all interior formatting and trailing blank lines.
    """
    matches = list(_REQUIREMENT_RE.finditer(spec_text))
    if not matches:
        return spec_text, []
    head = spec_text[: matches[0].start()]
    blocks: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(spec_text)
        blocks.append((match["name"], spec_text[start:end]))
    return head, blocks


def parse_delta(delta_text: str) -> dict[str, list[tuple[str, str]]]:
    """Parse a change delta into ``{op: [(name, block_text), ...]}``.

    ``op`` is one of ``ADDED``/``MODIFIED``/``REMOVED``/``RENAMED``. Blocks inside
    each ``## <op> Requirements`` section are split on ``### Requirement:`` the
    same way as canonical specs.
    """
    out: dict[str, list[tuple[str, str]]] = {}
    sections = list(_SECTION_RE.finditer(delta_text))
    for i, section in enumerate(sections):
        op = section["op"]
        body_start = section.end()
        body_end = sections[i + 1].start() if i + 1 < len(sections) else len(delta_text)
        _, blocks = split_requirements(delta_text[body_start:body_end])
        out.setdefault(op, []).extend(blocks)
    return out


def _normalize_trailing(block_text: str) -> str:
    """Ensure a block ends with exactly one blank line for stable concatenation."""
    return block_text.rstrip("\n") + "\n\n"


def project_capability(
    canonical_text: str, deltas: Iterable[dict[str, list[tuple[str, str]]]]
) -> str:
    """Return the canonical spec with every delta's requirement edits applied.

    ADDED/MODIFIED insert or replace a named block; REMOVED drops it. Unknown
    names in MODIFIED are treated as additions (the archiver's forgiving
    behavior). RENAMED is conservatively ignored here — it is rare and the
    projection stays a superset-safe approximation the sync-point owner refines.
    """
    head, blocks = split_requirements(canonical_text)
    order = [name for name, _ in blocks]
    body: dict[str, str] = {name: text for name, text in blocks}

    for delta in deltas:
        for name, _ in delta.get("REMOVED", []):
            body.pop(name, None)
            order = [n for n in order if n != name]
        for name, text in delta.get("MODIFIED", []):
            if name not in body:
                order.append(name)
            body[name] = text
        for name, text in delta.get("ADDED", []):
            if name not in body:
                order.append(name)
            body[name] = text

    if not order:
        return head
    merged_head = head if head.endswith("\n") or not head else head + "\n"
    return merged_head + "".join(_normalize_trailing(body[name]) for name in order)


def active_change_deltas(changes_root, specs_subdir: str = "specs"):
    """Yield ``(capability, delta_dict)`` for every active change delta spec.

    ``changes_root`` is ``openspec/changes``; the ``archive`` subtree is skipped.
    Import-light so the producer can call it without pulling the whole module
    graph.
    """
    from pathlib import Path

    root = Path(changes_root)
    if not root.is_dir():
        return
    for change_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        if change_dir.name == "archive":
            continue
        specs_dir = change_dir / specs_subdir
        if not specs_dir.is_dir():
            continue
        for spec_file in sorted(specs_dir.rglob("spec.md")):
            capability = spec_file.parent.name
            yield capability, parse_delta(spec_file.read_text(encoding="utf-8"))
