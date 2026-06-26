"""Shared helpers for AXI-aligned, agent-ergonomic list output.

The coordinator exposes the same capabilities over multiple transports (MCP,
the HTTP API, and ``coordination-cli``). These helpers keep the agent-facing
list contract — definitive counts, explicit truncation, contextual next steps —
computed identically across the CLI and HTTP surfaces.

The two surfaces differ deliberately in *shape* (not in semantics):

- The CLI renames its array to ``items`` inside a fresh envelope, because a
  pre-flight trace found no consumer parsed its bare-array output.
- The HTTP API preserves its existing named array key (``features``,
  ``entries``, ``memories``, ``handoffs``) and adds the AXI signals as sibling
  fields, because it has live external consumers (the coordination bridge,
  skills, cloud agents) that read those keys.

See ``openspec/changes/axi-align-coordinator-output`` for the rationale.
"""

from __future__ import annotations

from typing import Any


def probe_truncation(rows: list[Any], limit: int) -> tuple[list[Any], bool]:
    """Detect truncation precisely via the limit+1 fetch pattern.

    Callers request ``limit + 1`` rows from the service layer; if more than
    ``limit`` come back, the result was truncated. Trimming the sentinel row
    here keeps the reported count honest while letting the response flag that
    more data exists. This avoids the off-by-one ambiguity of
    ``len(rows) == limit`` (which cannot tell "exactly limit rows exist" from
    "the first page of many").
    """
    truncated = len(rows) > limit
    return rows[:limit], truncated


def truncation_hint(limit: int) -> str:
    """Human-readable guidance for paging past a truncated result."""
    return f"showing first {limit}; re-run with a higher limit to see more"


def list_envelope(
    rows_key: str,
    rows: list[Any],
    *,
    limit: int | None = None,
    truncated: bool = False,
    next_steps: list[str] | None = None,
) -> dict[str, Any]:
    """Augment an HTTP list response with AXI-aligned agent signals.

    Preserves the existing named array key (``rows_key``) for backward
    compatibility and adds sibling metadata:

    - ``count``      definitive empty state (``count: 0``, never an ambiguous
                     bare ``[]``).
    - ``truncated``  ``true`` when a limit cut the result short.
    - ``hint``       present only when truncated: how to page for more.
    - ``next_steps`` optional suggested follow-up requests.
    """
    envelope: dict[str, Any] = {
        rows_key: rows,
        "count": len(rows),
        "truncated": truncated,
    }
    if truncated and limit is not None:
        envelope["hint"] = truncation_hint(limit)
    if next_steps:
        envelope["next_steps"] = next_steps
    return envelope
