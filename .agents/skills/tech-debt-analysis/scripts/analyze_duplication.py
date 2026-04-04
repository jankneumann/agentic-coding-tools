#!/usr/bin/env python3
"""Analyzer: duplicate / near-duplicate code blocks.

Detects Fowler's *Duplicated Code* smell using a lightweight structural
fingerprinting approach:

1. Normalize each Python source file (strip comments, collapse whitespace).
2. Extract sliding windows of N consecutive normalized lines.
3. Hash each window and group by hash to find exact structural duplicates.

This avoids heavyweight token-level comparison while still catching the most
impactful cases: copy-pasted blocks of logic across files.
"""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

from models import AnalyzerResult, TechDebtFinding

ANALYZER = "duplication"

SKIP_DIRS = {
    ".venv", "node_modules", "__pycache__", ".git", ".tox", "dist", "build",
    ".agents", ".claude", ".codex", ".gemini",  # runtime skill copies
}

# ── Configurable thresholds ───────────────────────────────────────────
WINDOW_SIZE = 6  # consecutive lines to form a fingerprint
MIN_DUPLICATE_GROUPS = 1  # report if at least this many duplicate groups found
MIN_LINE_LENGTH = 3  # skip trivially short normalized lines


def _normalize_line(line: str) -> str:
    """Normalize a line for structural comparison.

    - Strip leading/trailing whitespace
    - Remove inline comments
    - Collapse multiple spaces
    - Replace string literals with a placeholder
    """
    # Remove inline comments (but not inside strings — good-enough heuristic)
    line = re.sub(r"#.*$", "", line)
    # Replace string literals with placeholder
    line = re.sub(r'""".*?"""', '"S"', line)
    line = re.sub(r"'''.*?'''", '"S"', line)
    line = re.sub(r'"[^"]*"', '"S"', line)
    line = re.sub(r"'[^']*'", '"S"', line)
    # Replace numeric literals with placeholder
    line = re.sub(r"\b\d+\.?\d*\b", "N", line)
    # Collapse whitespace
    line = re.sub(r"\s+", " ", line).strip()
    return line


def _should_skip(path: Path) -> bool:
    return bool(SKIP_DIRS.intersection(path.parts))


def _is_trivial(lines: list[str]) -> bool:
    """Return True if the window is trivially common (e.g. all blank/import)."""
    non_trivial = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip lines that are just common boilerplate
        if stripped.startswith(("import ", "from ", "return", "pass", ")", "]", "}")):
            continue
        non_trivial += 1
    return non_trivial < 3


def _fingerprint_file(
    source: str,
) -> list[tuple[str, int, list[str]]]:
    """Return (hash, start_line, normalized_lines) for each window in source."""
    raw_lines = source.splitlines()
    normalized: list[tuple[int, str]] = []

    for i, raw_line in enumerate(raw_lines, start=1):
        n = _normalize_line(raw_line)
        if len(n) >= MIN_LINE_LENGTH:
            normalized.append((i, n))

    windows: list[tuple[str, int, list[str]]] = []
    for idx in range(len(normalized) - WINDOW_SIZE + 1):
        chunk = normalized[idx : idx + WINDOW_SIZE]
        norm_lines = [c[1] for c in chunk]

        if _is_trivial(norm_lines):
            continue

        combined = "\n".join(norm_lines)
        h = hashlib.md5(combined.encode(), usedforsecurity=False).hexdigest()
        start_line = chunk[0][0]
        windows.append((h, start_line, norm_lines))

    return windows


def analyze(project_dir: str) -> AnalyzerResult:
    """Scan Python files for duplicated code blocks.

    Parameters
    ----------
    project_dir:
        Path to the project root.

    Returns
    -------
    AnalyzerResult
    """
    start = time.monotonic()
    root = Path(project_dir).resolve()

    # hash -> list of (rel_path, start_line)
    hash_locations: dict[str, list[tuple[str, int]]] = {}

    try:
        py_files = sorted(root.glob("**/*.py"))
        for py_file in py_files:
            rel = py_file.relative_to(root)
            if _should_skip(rel):
                continue

            try:
                source = py_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            for h, line_no, _norm in _fingerprint_file(source):
                locations = hash_locations.setdefault(h, [])
                # Avoid reporting overlapping windows in the same file
                if locations and locations[-1][0] == str(rel):
                    prev_line = locations[-1][1]
                    if abs(line_no - prev_line) < WINDOW_SIZE:
                        continue
                locations.append((str(rel), line_no))

    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return AnalyzerResult(
            analyzer=ANALYZER,
            status="error",
            duration_ms=elapsed,
            messages=[f"Unexpected error: {exc}"],
        )

    # ── Build findings from duplicate groups ──────────────────────
    findings: list[TechDebtFinding] = []
    dup_groups = {
        h: locs for h, locs in hash_locations.items() if len(locs) >= 2
    }

    # Deduplicate: if two groups share a location, keep the one with more hits
    seen_locations: set[tuple[str, int]] = set()

    for group_idx, (h, locations) in enumerate(
        sorted(dup_groups.items(), key=lambda x: -len(x[1]))
    ):
        # Skip if we've already reported all these locations
        new_locations = [
            loc for loc in locations if loc not in seen_locations
        ]
        if len(new_locations) < 2 and len(locations) < 3:
            continue

        for loc in locations:
            seen_locations.add(loc)

        # Determine severity by number of copies
        copies = len(locations)
        if copies >= 5:
            severity = "high"
        elif copies >= 3:
            severity = "medium"
        else:
            severity = "low"

        # Cross-file vs same-file duplication
        unique_files = {loc[0] for loc in locations}
        if len(unique_files) > 1:
            scope = "cross-file"
        else:
            scope = "same-file"

        location_strs = [f"{f}:{l}" for f, l in locations[:5]]
        if len(locations) > 5:
            location_strs.append(f"...and {len(locations) - 5} more")

        # Use the first location as the primary
        primary_file, primary_line = locations[0]

        findings.append(
            TechDebtFinding(
                id=f"td-dup-{group_idx}-{h[:8]}",
                analyzer=ANALYZER,
                severity=severity,  # type: ignore[arg-type]
                category="duplicate-code",  # type: ignore[arg-type]
                title=f"Duplicated code block ({copies} copies, {scope})",
                detail=(
                    f"A {WINDOW_SIZE}-line code block appears {copies} times "
                    f"({scope}). Locations: {', '.join(location_strs)}"
                ),
                file_path=primary_file,
                line=primary_line,
                metric_name="duplicate_copies",
                metric_value=copies,
                threshold=2,
                smell="Duplicated Code",
                recommendation=(
                    "Extract Method or Extract Class to share the common logic. "
                    "If cross-file, consider a shared utility module."
                ),
            ),
        )

    elapsed = int((time.monotonic() - start) * 1000)
    return AnalyzerResult(
        analyzer=ANALYZER,
        status="ok",
        findings=findings,
        duration_ms=elapsed,
    )
