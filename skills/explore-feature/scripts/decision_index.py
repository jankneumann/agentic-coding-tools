"""Per-capability decision-index extractor and emitter.

Reads `architectural:` tagged Decision bullets from session-log Phase Entries
and emits reverse-chronological markdown files at `docs/decisions/<capability>.md`.

Design: see ../../../openspec/changes/add-decision-index/design.md

Pipeline:
    session-log.md  →  extract_decisions()  →  list[TaggedDecision]
                                                    │
                                                    ▼
                               emit_decision_index()  →  docs/decisions/<cap>.md
"""

from __future__ import annotations

import logging
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Patterns ────────────────────────────────────────────────────────


_CAPABILITY = r"[a-z0-9](?:[a-z0-9-]{0,50}[a-z0-9])?"
"""Kebab-case capability identifier, 2-52 chars — matches sanitizer allowlist."""

_DECISION_RE = re.compile(
    r"^(?P<bullet>\d+)\.\s+\*\*(?P<title>[^*]+)\*\*\s+"
    r"`architectural:\s+(?P<capability>" + _CAPABILITY + r")`"
    r".*?"
    r"(?:`supersedes:\s+(?P<supersedes>[^`]+)`.*?)?"
    r"—\s*(?P<rationale>.+)$",
    re.MULTILINE,
)
"""Anchored extraction regex for tagged Decision bullets.

Captures the 1-indexed bullet position so `decision_index_in_phase` matches
the natural-read convention documented in SKILL.md (`#D<n>` = bullet number
within the phase entry, counting all Decision bullets including untagged).

The permissive `.*?` between the capability tag and the em-dash handles benign
extras (whitespace, the optional `supersedes:` span, even a second `architectural:`
span which is ignored by first-match semantics)."""

_PHASE_RE = re.compile(
    r"^##\s+Phase:\s+(?P<name>[^(]+?)\s+\((?P<date>\d{4}-\d{2}-\d{2})\)\s*$",
    re.MULTILINE,
)

# Supersedes-reference syntax comes in two forms:
#
#   <change-id>#<phase-slug>/D<n>   — preferred, unambiguous when a change has
#                                      multiple phases that both carry a D<n>
#                                      at the same bullet position.
#   <change-id>#D<n>                — legacy bare form. Accepted when the
#                                      target change has only ONE phase with a
#                                      D<n> at that position; otherwise the
#                                      emitter warns and skips the link to
#                                      avoid silently marking multiple phases
#                                      as superseded.
_SUPERSEDES_REF_PHASED = re.compile(
    r"^(?P<change_id>[A-Za-z0-9][A-Za-z0-9._-]*?)"
    r"#(?P<phase_slug>[a-z0-9][a-z0-9-]*)"
    r"/D(?P<index>\d+)$"
)
_SUPERSEDES_REF_LEGACY = re.compile(
    r"^(?P<change_id>[A-Za-z0-9][A-Za-z0-9._-]*?)#D(?P<index>\d+)$"
)


def _phase_slug(phase_name: str) -> str:
    """Convert a human-readable phase name to a URL-safe slug.

    Examples:
        "Plan" -> "plan"
        "Plan Iteration 2" -> "plan-iteration-2"
        "Implementation" -> "implementation"
    """
    return phase_name.strip().lower().replace(" ", "-")


# ── Data model ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class TaggedDecision:
    """A single Decision bullet carrying an `architectural:` tag."""

    capability: str
    change_id: str
    phase_name: str
    phase_date: date
    title: str
    rationale: str
    supersedes: str | None
    source_offset: int
    decision_index_in_phase: int = 1
    source_relpath: str = ""


# ── Extraction ──────────────────────────────────────────────────────


def extract_decisions(session_log_path: Path) -> list[TaggedDecision]:
    """Extract tagged Decisions from a single session-log.md.

    Returns [] when the file does not exist — per design open question #3,
    pre-session-log changes are silently skipped rather than warned.
    """
    if not session_log_path.is_file():
        return []

    content = session_log_path.read_text()
    change_id = session_log_path.parent.name

    phase_matches = list(_PHASE_RE.finditer(content))
    if not phase_matches:
        return []

    decisions: list[TaggedDecision] = []

    for i, phase_match in enumerate(phase_matches):
        phase_name = phase_match.group("name").strip()
        try:
            phase_date = date.fromisoformat(phase_match.group("date"))
        except ValueError:
            logger.warning(
                "Unparseable phase date %r in %s — skipping phase",
                phase_match.group("date"),
                session_log_path,
            )
            continue

        block_start = phase_match.end()
        block_end = (
            phase_matches[i + 1].start()
            if i + 1 < len(phase_matches)
            else len(content)
        )
        block = content[block_start:block_end]

        for dec_match in _DECISION_RE.finditer(block):
            supersedes = dec_match.group("supersedes")
            decisions.append(
                TaggedDecision(
                    capability=dec_match.group("capability"),
                    change_id=change_id,
                    phase_name=phase_name,
                    phase_date=phase_date,
                    title=dec_match.group("title").strip(),
                    rationale=dec_match.group("rationale").strip(),
                    supersedes=supersedes.strip() if supersedes else None,
                    source_offset=block_start + dec_match.start(),
                    decision_index_in_phase=int(dec_match.group("bullet")),
                    source_relpath=str(session_log_path),
                )
            )

    return decisions


# ── Emission ────────────────────────────────────────────────────────


def emit_decision_index(
    decisions: list[TaggedDecision],
    output_dir: Path,
    capabilities_root: Path,
    *,
    strict: bool,
) -> None:
    """Write per-capability decision markdown files under `output_dir`.

    - Groups decisions by capability
    - Skips decisions with unknown capabilities (warn in non-strict, SystemExit in strict)
    - Sorts each capability's decisions newest-first, deterministically
    - Resolves `supersedes:` markers into bidirectional Supersedes/Superseded by links
    - Writes one file per capability that has at least one valid decision
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    valid_caps: set[str] = (
        {p.name for p in capabilities_root.iterdir() if p.is_dir()}
        if capabilities_root.is_dir()
        else set()
    )

    by_cap: dict[str, list[TaggedDecision]] = defaultdict(list)
    for d in decisions:
        if d.capability not in valid_caps:
            msg = (
                f"Unknown capability {d.capability!r} in {d.change_id} "
                f"phase {d.phase_name!r}"
            )
            logger.warning(msg)
            if strict:
                sys.exit(f"Strict mode: {msg}")
            continue
        by_cap[d.capability].append(d)

    for ds in by_cap.values():
        ds.sort(
            key=lambda d: (
                -d.phase_date.toordinal(),
                d.change_id,
                d.decision_index_in_phase,
                d.source_offset,
            )
        )

    superseded_by_map = _build_supersession_map(by_cap)

    # Delete stale capability files — any previously-emitted <cap>.md for a
    # capability that no longer has any valid tagged decisions in the current
    # run. Without this, removing tags leaves orphan files that CI's
    # `git diff --exit-code` gate cannot detect (the file content is unchanged
    # — it's the presence that's stale). README is regenerated so it listed
    # only current capabilities, meaning README and capability files would
    # otherwise drift apart.
    will_emit = set(by_cap.keys())
    for existing in output_dir.glob("*.md"):
        if existing.name == "README.md":
            continue
        if existing.stem not in will_emit:
            existing.unlink()

    for cap, ds in sorted(by_cap.items()):
        file_path = output_dir / f"{cap}.md"
        file_path.write_text(_render_capability_file(cap, ds, superseded_by_map))

    known_caps_with_files = sorted(by_cap.keys())
    emit_readme(output_dir, known_caps_with_files)


def _build_supersession_map(
    by_cap: dict[str, list[TaggedDecision]],
) -> dict[tuple[str, str, int], TaggedDecision]:
    """Map `(superseded_change_id, phase_slug, decision_index)` → the later
    decision that supersedes it.

    Keyed by phase slug to disambiguate multi-phase changes where two phases
    both carry a D<n> at the same bullet position. Legacy bare `#D<n>` refs
    are accepted only when the target change has exactly one phase matching
    that bullet index; otherwise a warning is emitted and the ref is skipped
    (silently marking multiple phases as superseded would be wrong-but-quiet).
    """
    all_tagged = [d for ds in by_cap.values() for d in ds]

    # Count how many phases of each (change_id, bullet_index) exist, so a
    # legacy bare ref can be accepted only when unambiguous.
    legacy_candidates: dict[tuple[str, int], list[TaggedDecision]] = defaultdict(list)
    for d in all_tagged:
        legacy_candidates[(d.change_id, d.decision_index_in_phase)].append(d)

    mapping: dict[tuple[str, str, int], TaggedDecision] = {}
    for ds in by_cap.values():
        for d in ds:
            if not d.supersedes:
                continue
            ref = d.supersedes.strip()

            phased = _SUPERSEDES_REF_PHASED.match(ref)
            if phased:
                key = (
                    phased.group("change_id"),
                    phased.group("phase_slug"),
                    int(phased.group("index")),
                )
                mapping[key] = d
                continue

            legacy = _SUPERSEDES_REF_LEGACY.match(ref)
            if legacy:
                c_id = legacy.group("change_id")
                idx = int(legacy.group("index"))
                matches = legacy_candidates.get((c_id, idx), [])
                if len(matches) > 1:
                    logger.warning(
                        "Ambiguous supersedes ref %r on %s — change %s has "
                        "%d phases carrying D%d; use "
                        "'<change-id>#<phase-slug>/D<n>' to disambiguate. "
                        "Skipping the link.",
                        ref, d.change_id, c_id, len(matches), idx,
                    )
                    continue
                if len(matches) == 1:
                    target = matches[0]
                    mapping[(c_id, _phase_slug(target.phase_name), idx)] = d
                # len(matches) == 0 is silent — the target change may simply
                # have no session-log in the corpus (e.g., pre-convention
                # archive); nothing to link.
                continue

            logger.warning(
                "Unparseable supersedes ref %r on %s — expected "
                "'<change-id>#D<n>' or '<change-id>#<phase-slug>/D<n>'",
                ref, d.change_id,
            )
    return mapping


def _render_capability_file(
    capability: str,
    decisions: list[TaggedDecision],
    superseded_by_map: dict[tuple[str, str, int], TaggedDecision],
) -> str:
    lines: list[str] = [
        f"# Architectural Decisions — {capability}",
        "",
        f"> Reverse-chronological timeline of decisions tagged "
        f"`architectural: {capability}` in session-log Phase Entries.",
        "> Generated by `make decisions` — do not edit manually.",
        "",
    ]

    for d in decisions:
        lines.extend(_render_decision(d, superseded_by_map))

    return "\n".join(lines).rstrip() + "\n"


def _render_decision(
    d: TaggedDecision,
    superseded_by_map: dict[tuple[str, str, int], TaggedDecision],
) -> list[str]:
    superseded_by = superseded_by_map.get(
        (d.change_id, _phase_slug(d.phase_name), d.decision_index_in_phase)
    )
    status = "superseded" if superseded_by else "active"
    # Prefer the concrete path captured at extraction time. Fall back to a
    # descriptive placeholder for decisions constructed in tests that omit it.
    if d.source_relpath:
        source_line = f"- Source: [{d.source_relpath}](/{d.source_relpath}) (D{d.decision_index_in_phase})"
    else:
        source_line = f"- Source: `{d.change_id}/session-log.md` (D{d.decision_index_in_phase})"

    lines = [
        "---",
        "",
        f"## {d.phase_date.isoformat()} — {d.change_id}",
        "",
        f"### Phase: {d.phase_name}",
        "",
        f"**{d.title}** — {d.rationale}",
        "",
        f"- Status: `{status}`",
        source_line,
    ]

    if d.supersedes:
        lines.append(f"- **Supersedes**: `{d.supersedes}`")

    if superseded_by:
        lines.append(
            f"- **Superseded by**: `{superseded_by.change_id}` "
            f"(D{superseded_by.decision_index_in_phase})"
        )

    lines.append("")
    return lines


def emit_readme(output_dir: Path, capabilities: list[str]) -> None:
    """Generate `docs/decisions/README.md` — meta file explaining the index."""
    output_dir.mkdir(parents=True, exist_ok=True)
    caps = sorted(set(capabilities))

    lines = [
        "# Architectural Decisions Index",
        "",
        "This directory is **generated** by `make decisions` from "
        "`architectural:` tagged Decision bullets in session-log Phase Entries. "
        "Do not edit these files by hand.",
        "",
        "## What belongs in this index",
        "",
        "A Decision is *architectural* when it shapes how a capability behaves "
        "across multiple changes — patterns, constraints, or interfaces that "
        "later work either builds on or reverses. Tag such decisions with "
        "`` `architectural: <capability>` `` in the Decision bullet of the "
        "session-log Phase Entry where the call was made.",
        "",
        "Routine engineering choices that do not outlive the change that "
        "introduced them SHOULD remain untagged — they clutter the index "
        "without adding archaeological value.",
        "",
        "## How to read a capability timeline",
        "",
        "Each `<capability>.md` file is reverse-chronological (newest first). "
        "Every entry carries a status (`active` or `superseded`), a back-reference "
        "to the originating session-log phase entry, and — when a later decision "
        "explicitly reverses an earlier one via `` `supersedes:` `` — bidirectional "
        "`Supersedes` / `Superseded by` links.",
        "",
        "## Generation",
        "",
        "```",
        "make decisions",
        "```",
        "",
        "CI verifies the index is fresh by re-running `make decisions` and failing "
        "on any `git diff docs/decisions/`.",
        "",
        "## Active capabilities in this index",
        "",
    ]

    if caps:
        for cap in caps:
            lines.append(f"- [{cap}](./{cap}.md)")
    else:
        lines.append("_(none yet — add `architectural:` tags to session-log Decisions)_")

    (output_dir / "README.md").write_text("\n".join(lines).rstrip() + "\n")


# ── CLI ─────────────────────────────────────────────────────────────


def _cli_main(argv: list[str] | None = None) -> int:
    """CLI entry point — wired up in Phase 4 via `make decisions`."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Emit per-capability decision index from session-log tags."
    )
    parser.add_argument(
        "--archive-root",
        type=Path,
        default=Path("openspec/changes"),
        help="Root dir to walk for session-log.md files (default: openspec/changes)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/decisions"),
        help="Output dir for per-capability markdown (default: docs/decisions)",
    )
    parser.add_argument(
        "--capabilities-root",
        type=Path,
        default=Path("openspec/specs"),
        help="Dir containing capability subdirs (default: openspec/specs)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on unknown-capability tags (CI mode).",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable INFO logging."
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    all_decisions: list[TaggedDecision] = []
    for session_log in sorted(args.archive_root.rglob("session-log.md")):
        all_decisions.extend(extract_decisions(session_log))

    logger.info("Extracted %d tagged decisions", len(all_decisions))

    emit_decision_index(
        all_decisions,
        output_dir=args.output_dir,
        capabilities_root=args.capabilities_root,
        strict=args.strict,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
