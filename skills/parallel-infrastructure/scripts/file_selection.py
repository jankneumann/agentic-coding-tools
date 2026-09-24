"""Deterministic file selection for the review packet.

Ported from alibaba/open-code-review's five-gate selection algorithm
(internal/agent/selection.go, Apache-2.0 License,
https://github.com/alibaba/open-code-review, read 2026-09-14): binary,
user_exclude, user_include, generated_path, deleted, too_large — in that
order, first match wins.

Pure: given a parsed diff and rule config, returns one :class:`FileDecision`
per file, with no I/O. ``review_packet.build_review_packet`` and its
``preview`` entry point both call :func:`select_files`, so preview and a
real build cannot diverge — the failure mode this port exists to avoid
(OCR's own issue #782, where the two selection paths drifted).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Any

REASON_NONE = "none"
REASON_BINARY = "binary"
REASON_USER_EXCLUDE = "user_exclude"
REASON_GENERATED_PATH = "generated_path"
REASON_DELETED = "deleted"
REASON_TOO_LARGE = "too_large"

GATE_BINARY = "binary"
GATE_USER_EXCLUDE = "user_exclude"
GATE_USER_INCLUDE = "user_include"
GATE_GENERATED_PATH = "generated_path"
GATE_DELETED = "deleted"
GATE_TOO_LARGE = "too_large"
GATE_PASSED = "passed"


@dataclass
class FileDiff:
    """One file's slice of a unified diff, as parsed by :func:`parse_diff_files`."""

    path: str
    status: str  # "added" | "modified" | "deleted" | "renamed"
    body: str
    is_binary: bool = False
    old_path: str | None = None


@dataclass
class FileDecision:
    path: str
    status: str
    reason: str
    gate: str
    est_tokens: int
    file: FileDiff | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "status": self.status,
            "reason": self.reason,
            "gate": self.gate,
            "est_tokens": self.est_tokens,
        }

    @property
    def selected(self) -> bool:
        return self.reason == REASON_NONE


_DIFF_HEADER_RE = re.compile(r"^diff --git a/(.*) b/(.*)$")


def parse_diff_files(diff_text: str) -> list[FileDiff]:
    """Split a unified ``git diff`` blob into one :class:`FileDiff` per file.

    Tolerant, not exhaustive: covers the standard ``git diff`` header shapes
    (add/modify/delete/rename, binary markers). A block whose header does not
    parse is skipped rather than raising — a diff the caller cannot select
    files from is treated the same as an empty diff, not a hard failure.
    """
    if not (diff_text or "").strip():
        return []
    lines = diff_text.split("\n")
    blocks: list[list[str]] = []
    current: list[str] | None = None
    for line in lines:
        if line.startswith("diff --git "):
            if current is not None:
                blocks.append(current)
            current = [line]
        elif current is not None:
            current.append(line)
    if current is not None:
        blocks.append(current)

    files: list[FileDiff] = []
    for block in blocks:
        header = block[0]
        match = _DIFF_HEADER_RE.match(header)
        if not match:
            continue
        a_path, b_path = match.group(1), match.group(2)
        body = "\n".join(block)
        is_binary = (
            ("Binary files " in body and " differ" in body)
            or "GIT binary patch" in body
        )
        is_new = any(line.startswith("new file mode") for line in block)
        is_deleted = any(line.startswith("deleted file mode") for line in block)
        is_renamed = any(
            line.startswith("rename from ") for line in block
        ) or (a_path != b_path and not is_new and not is_deleted)

        if is_deleted:
            status, path = "deleted", a_path
        elif is_new:
            status, path = "added", b_path
        elif is_renamed:
            status, path = "renamed", b_path
        else:
            status, path = "modified", b_path

        files.append(
            FileDiff(
                path=path,
                status=status,
                body=body,
                is_binary=is_binary,
                old_path=a_path if a_path != b_path else None,
            )
        )
    return files


def estimate_tokens(text: str) -> int:
    """Rough floor: one token per four characters.

    Exact vendor tokenization would need a dependency and per-vendor tables;
    the gate only has to decide "this file cannot fit", and the number it
    used is reported in the packet metadata for anyone auditing the
    decision — see the design doc's rationale for why this is a documented
    floor rather than an exact count.
    """
    return math.ceil(len(text) / 4) if text else 0


def _match_any(path: str, patterns: list[str]) -> bool:
    """Case-insensitive glob match, with one gitignore-style convenience.

    Plain :func:`fnmatch.fnmatch` (this project's existing glob convention —
    see ``roadmap-runtime/scripts/scope_overlap.py``) requires a literal
    ``/`` before the filename for a leading ``**/`` to match; it does not
    special-case "at the repository root" the way gitignore/doublestar do.
    A missed generated-path exclusion defeats the point of that gate, so a
    ``**/`` prefix is also tried against the path with that prefix
    stripped — ``**/*.lock`` then matches a root-level ``foo.lock`` too.
    """
    lowered = path.lower()
    for pattern in patterns:
        p = pattern.lower()
        if fnmatch(lowered, p):
            return True
        if p.startswith("**/") and fnmatch(lowered, p[3:]):
            return True
    return False


def select_files(
    files: list[FileDiff],
    *,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    generated_paths: list[str] | None = None,
    per_file_token_ceiling: int,
) -> list[FileDecision]:
    """Apply the five gates to every file, in input order, first match wins.

    Gate order: ``binary``, ``user_exclude``, ``user_include`` (keeps the
    file and skips every remaining gate), ``generated_path``, ``deleted``,
    ``too_large``. A file surviving every gate gets ``reason="none"``,
    ``gate="passed"``.
    """
    include = include or []
    exclude = exclude or []
    generated_paths = generated_paths or []
    decisions: list[FileDecision] = []
    for f in files:
        tokens = estimate_tokens(f.body)
        if f.is_binary:
            decisions.append(
                FileDecision(f.path, f.status, REASON_BINARY, GATE_BINARY, tokens, f)
            )
            continue
        if exclude and _match_any(f.path, exclude):
            decisions.append(
                FileDecision(
                    f.path, f.status, REASON_USER_EXCLUDE, GATE_USER_EXCLUDE, tokens, f,
                )
            )
            continue
        if include and _match_any(f.path, include):
            decisions.append(
                FileDecision(f.path, f.status, REASON_NONE, GATE_USER_INCLUDE, tokens, f)
            )
            continue
        if generated_paths and _match_any(f.path, generated_paths):
            decisions.append(
                FileDecision(
                    f.path, f.status, REASON_GENERATED_PATH, GATE_GENERATED_PATH,
                    tokens, f,
                )
            )
            continue
        if f.status == "deleted":
            decisions.append(
                FileDecision(f.path, f.status, REASON_DELETED, GATE_DELETED, tokens, f)
            )
            continue
        if per_file_token_ceiling > 0 and tokens > per_file_token_ceiling:
            decisions.append(
                FileDecision(
                    f.path, f.status, REASON_TOO_LARGE, GATE_TOO_LARGE, tokens, f,
                )
            )
            continue
        decisions.append(
            FileDecision(f.path, f.status, REASON_NONE, GATE_PASSED, tokens, f)
        )
    return decisions
