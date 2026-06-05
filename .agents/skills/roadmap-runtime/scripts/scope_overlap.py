"""Scope overlap detection primitives.

Used by ``validate_work_packages.py`` (parallel package validation) for
deterministic scope-overlap checks between work units.

Provides pairwise overlap checks for write_allow globs, read_allow globs,
and lock keys.  All functions operate on plain lists/sets — they don't
know about ``RoadmapItem`` or ``WorkPackage`` dataclasses.
"""

from __future__ import annotations

from fnmatch import fnmatch


def glob_overlap(globs_a: list[str], globs_b: list[str]) -> list[tuple[str, str]]:
    """Check for pairwise overlap between two lists of file globs.

    Returns a list of ``(glob_a, glob_b)`` pairs that overlap.
    Overlap is approximate: ``fnmatch(a, b)`` OR ``fnmatch(b, a)``
    OR exact equality.  This catches cases like ``src/db/**`` vs
    ``src/db/migrations/*``.
    """
    overlaps: list[tuple[str, str]] = []
    for ga in globs_a:
        for gb in globs_b:
            if fnmatch(ga, gb) or fnmatch(gb, ga) or ga == gb:
                overlaps.append((ga, gb))
    return overlaps


def write_write_overlap(
    write_a: list[str],
    write_b: list[str],
) -> str:
    """Check for write-write scope overlap.

    Returns a rationale string if overlap exists, empty string otherwise.
    """
    pairs = glob_overlap(write_a, write_b)
    if pairs:
        descs = [f"'{a}' vs '{b}'" for a, b in pairs]
        return f"write_allow overlap: {', '.join(descs)}"
    return ""


def read_after_write_overlap(
    write_a: list[str],
    read_b: list[str],
) -> str:
    """Check if A writes to files that B reads (read-after-write).

    Returns a rationale string if overlap exists, empty string otherwise.
    """
    pairs = glob_overlap(write_a, read_b)
    if pairs:
        descs = [f"'{w}' written, '{r}' read" for w, r in pairs]
        return f"read-after-write: {', '.join(descs)}"
    return ""


def lock_key_overlap(keys_a: list[str], keys_b: list[str]) -> str:
    """Check for shared lock keys between two scopes.

    Returns a rationale string if overlap exists, empty string otherwise.
    Lock keys are canonicalized strings (e.g., ``db:schema:users``).
    """
    shared = set(keys_a) & set(keys_b)
    if shared:
        return f"shared lock_keys: {', '.join(sorted(shared))}"
    return ""


def check_scope_overlap(
    write_a: list[str],
    read_a: list[str],
    lock_a: list[str],
    write_b: list[str],
    read_b: list[str],
    lock_b: list[str],
) -> str:
    """Full scope overlap check between two items.

    Checks write-write, read-after-write (both directions), and
    lock key overlap.  Returns the first rationale found, or empty
    string if no overlap.
    """
    # Write-write
    rationale = write_write_overlap(write_a, write_b)
    if rationale:
        return rationale

    # Read-after-write: A writes, B reads
    rationale = read_after_write_overlap(write_a, read_b)
    if rationale:
        return rationale

    # Read-after-write: B writes, A reads
    rationale = read_after_write_overlap(write_b, read_a)
    if rationale:
        return rationale

    # Lock keys
    rationale = lock_key_overlap(lock_a, lock_b)
    if rationale:
        return rationale

    return ""
