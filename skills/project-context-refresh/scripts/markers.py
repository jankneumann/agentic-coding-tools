"""Generated-marker engine absorbed from ``add-update-documentation-skill`` (D5).

Generated content lives between HTML-comment markers:

    <!-- GENERATED: begin <block-id> -->
    ...generated lines...
    <!-- GENERATED: end <block-id> -->

Everything outside a matched marker pair is hand-authored prose and is preserved
byte-for-byte. The engine is *fail-closed*: an unbalanced, duplicated, nested, or
mis-ordered marker raises :class:`MarkerError` and no caller writes a file
(design "Failure Behavior"; spec ``preserve-prose``). This is the safety
property that lets ``generate`` own the mechanical block while humans own the
surrounding narrative.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

_BEGIN_RE = re.compile(r"^[ \t]*<!--[ \t]*GENERATED:[ \t]*begin[ \t]+(?P<id>[^\s>]+)[ \t]*-->[ \t]*$")
_END_RE = re.compile(r"^[ \t]*<!--[ \t]*GENERATED:[ \t]*end[ \t]+(?P<id>[^\s>]+)[ \t]*-->[ \t]*$")


class MarkerError(Exception):
    """A marker structure is malformed; the file must not be written."""


@dataclass(frozen=True, slots=True)
class Block:
    """One matched marker pair and the generated body it encloses.

    Line indices are 0-based into the file's line list. ``body_start`` and
    ``body_end`` bound the *inner* lines (exclusive of the marker lines); an
    empty body has ``body_start == body_end``.
    """

    block_id: str
    begin_line: int
    end_line: int
    body_start: int
    body_end: int


def find_blocks(text: str) -> tuple[Block, ...]:
    """Parse *text* into ordered generated blocks, failing closed on any defect.

    Raises :class:`MarkerError` on: an ``end`` without a matching open ``begin``,
    a nested ``begin`` inside an open block, a duplicate block id, or an unclosed
    ``begin`` at end of file.
    """
    lines = text.splitlines()
    blocks: list[Block] = []
    seen: set[str] = set()
    open_id: str | None = None
    open_begin = -1
    for index, line in enumerate(lines):
        begin_match = _BEGIN_RE.match(line)
        end_match = _END_RE.match(line)
        if begin_match:
            if open_id is not None:
                raise MarkerError(
                    f"nested generated begin {begin_match['id']!r} inside open "
                    f"block {open_id!r} at line {index + 1}"
                )
            block_id = begin_match["id"]
            if block_id in seen:
                raise MarkerError(f"duplicate generated block id {block_id!r}")
            open_id = block_id
            open_begin = index
        elif end_match:
            block_id = end_match["id"]
            if open_id is None:
                raise MarkerError(
                    f"generated end {block_id!r} with no open begin at line {index + 1}"
                )
            if block_id != open_id:
                raise MarkerError(
                    f"generated end {block_id!r} does not match open begin "
                    f"{open_id!r} at line {index + 1}"
                )
            blocks.append(
                Block(
                    block_id=block_id,
                    begin_line=open_begin,
                    end_line=index,
                    body_start=open_begin + 1,
                    body_end=index,
                )
            )
            seen.add(block_id)
            open_id = None
            open_begin = -1
    if open_id is not None:
        raise MarkerError(f"unclosed generated begin {open_id!r}")
    return tuple(blocks)


def block_ids(text: str) -> tuple[str, ...]:
    """Return the ordered ids of every matched generated block in *text*."""
    return tuple(block.block_id for block in find_blocks(text))


def _splitlines_keepends(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def render(text: str, bodies: Mapping[str, str]) -> str:
    """Return *text* with each named block's body replaced by *bodies[id]*.

    Only the inner lines of a matched block change; the marker lines and every
    byte outside a block are preserved exactly. A body id absent from *text*
    raises :class:`MarkerError` (fail closed rather than silently drop content).
    A block present in *text* but absent from *bodies* is left unchanged.
    """
    blocks = find_blocks(text)
    by_id = {block.block_id: block for block in blocks}
    for block_id in bodies:
        if block_id not in by_id:
            raise MarkerError(f"no generated block {block_id!r} to render in target")

    keep = _splitlines_keepends(text)
    # Repo markdown is LF-only; injected generated lines use "\n". Bytes outside
    # generated bodies keep their original terminators via ``keepends`` slicing.
    newline = "\n"

    out: list[str] = []
    cursor = 0
    for block in blocks:
        # Emit untouched lines up to and including the begin marker line.
        out.extend(keep[cursor : block.begin_line + 1])
        if block.block_id in bodies:
            body = bodies[block.block_id]
            if body:
                for body_line in body.split("\n"):
                    out.append(body_line + newline)
        else:
            out.extend(keep[block.body_start : block.body_end])
        # Emit the end marker line; the next iteration/segment resumes after it.
        out.append(keep[block.end_line])
        cursor = block.end_line + 1
    out.extend(keep[cursor:])
    return "".join(out)
