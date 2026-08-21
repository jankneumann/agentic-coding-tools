#!/usr/bin/env python3
"""Evidence collector and session-log cross-reference resolver for the
audit-choices skill.

Read-only: every function in this module only reads the repository (git
subprocess calls, file reads) or does pure computation. Nothing here ever
writes a file — the only writer in this skill is
`choices_ledger.write_ledger_pair`, called from `run_audit.py`.

Design decisions (openspec/changes/add-decision-choices-ledger/design.md):
    D5 — cross-reference-only linkage to self-reported decisions: this
         module resolves session-log.md `Decisions` bullets to
         `<change-id>#D<n>` refs (or phase-qualified
         `<change-id>#<phase-slug>/D<n>` refs when the log has more than
         one phase entry with decisions); unmatched candidates are simply
         left unresolved (`self_reported: False`). This module never
         writes to session-log.md or docs/decisions/.
    D7 — the evidence bundle assembled here is the read-only input handed
         to the independent auditor sub-agent; commits/files collected
         here also become the allow-list `run_audit.py` uses to drop
         hallucinated provenance.
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = _THIS_DIR.parents[2]  # scripts -> audit-choices -> skills -> repo root
_PHASE_RECORD_PATH = REPO_ROOT / "skills" / "session-log" / "scripts" / "phase_record.py"

_EXCERPT_CHARS = 4000
_SESSION_LOG_CHARS = 20000


def _load_phase_record() -> Any:
    """Load session-log's phase_record module by path (script-style layout,
    not a package) so we reuse `parse_markdown` / `Decision` rather than
    writing a second session-log parser (task 2.6)."""
    module_name = "_phase_record_for_audit_choices"
    spec = importlib.util.spec_from_file_location(module_name, _PHASE_RECORD_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"Could not load {_PHASE_RECORD_PATH}")
    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules before exec: phase_record.py uses
    # `from __future__ import annotations` (string annotations), and its
    # dataclasses resolve annotations via sys.modules[cls.__module__] at
    # class-definition time. Without this, dataclass() raises AttributeError.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# ─────────────────────────────────────────────────────────────────────────
# Evidence bundle
# ─────────────────────────────────────────────────────────────────────────


@dataclass
class EvidenceBundle:
    """Read-only evidence handed to the independent auditor sub-agent."""

    change_id: str
    base_sha: str
    head_sha: str
    commits: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    diff_stat: str = ""
    proposal_excerpt: str = ""
    design_excerpt: str = ""
    spec_delta_excerpts: dict[str, str] = field(default_factory=dict)
    session_log_excerpt: str = ""
    impl_findings_excerpt: str = ""
    known_decisions: list[dict[str, str]] = field(default_factory=list)

    @property
    def known_commits(self) -> set[str]:
        return set(self.commits)

    @property
    def known_files(self) -> set[str]:
        return set(self.files)

    def to_prompt_dict(self) -> dict[str, Any]:
        """Shape suitable for handing to the auditor sub-agent as its
        read-only evidence bundle (e.g. serialized to JSON in the dispatch
        prompt)."""
        return {
            "change_id": self.change_id,
            "audited_range": {"base_sha": self.base_sha, "head_sha": self.head_sha},
            "commits": list(self.commits),
            "files": list(self.files),
            "diff_stat": self.diff_stat,
            "proposal_excerpt": self.proposal_excerpt,
            "design_excerpt": self.design_excerpt,
            "spec_delta_excerpts": dict(self.spec_delta_excerpts),
            "session_log_excerpt": self.session_log_excerpt,
            "impl_findings_excerpt": self.impl_findings_excerpt,
            "known_decisions": list(self.known_decisions),
        }


# ─────────────────────────────────────────────────────────────────────────
# Git collection (read-only subprocess calls)
# ─────────────────────────────────────────────────────────────────────────


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def collect_commits(repo_root: Path, base_sha: str, head_sha: str) -> list[str]:
    """Full 40-char commit shas in (base_sha, head_sha]."""
    out = _git(repo_root, "log", "--format=%H", f"{base_sha}..{head_sha}")
    return [line.strip() for line in out.splitlines() if line.strip()]


def collect_touched_files(repo_root: Path, base_sha: str, head_sha: str) -> list[str]:
    out = _git(repo_root, "diff", "--name-only", f"{base_sha}..{head_sha}")
    return [line.strip() for line in out.splitlines() if line.strip()]


def collect_diff_stat(repo_root: Path, base_sha: str, head_sha: str) -> str:
    return _git(repo_root, "diff", "--stat", f"{base_sha}..{head_sha}")


# ─────────────────────────────────────────────────────────────────────────
# Artifact excerpts (read-only file reads, bounded length)
# ─────────────────────────────────────────────────────────────────────────


def _read_excerpt(path: Path, limit: int = _EXCERPT_CHARS) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... (truncated)"


def collect_spec_delta_excerpts(change_dir: Path, limit: int = _EXCERPT_CHARS) -> dict[str, str]:
    specs_dir = change_dir / "specs"
    out: dict[str, str] = {}
    if not specs_dir.is_dir():
        return out
    for spec_path in sorted(specs_dir.rglob("spec.md")):
        rel = str(spec_path.relative_to(change_dir))
        out[rel] = _read_excerpt(spec_path, limit)
    return out


# ─────────────────────────────────────────────────────────────────────────
# Session-log cross-reference resolver (D5, task 2.6)
# ─────────────────────────────────────────────────────────────────────────

_PHASE_BLOCK_SPLIT_RE = re.compile(r"(?=^## Phase:)", re.MULTILINE)


def parse_session_log_decisions(
    session_log_text: str, *, change_id: str
) -> list[dict[str, str]]:
    """Parse every phase entry's Decisions bullets into a flat list of
    ``{"title", "rationale", "ref"}`` dicts, reusing
    ``phase_record.parse_markdown`` (task 2.6) instead of writing a second
    session-log parser.

    ``ref`` is the bare ``<change_id>#D<n>`` form when the log has exactly
    one phase entry carrying decisions, and the phase-qualified
    ``<change_id>#<phase-slug>/D<n>`` form when more than one phase entry
    does — a bare ``#D<n>`` would otherwise be ambiguous across phases
    (see ``skills/session-log/SKILL.md``, "`#D<n>` is the decision's
    1-indexed position within its phase entry").

    Returns an empty list for empty/absent text or text with no `## Phase:`
    headers — never raises, so a missing or malformed session-log.md
    degrades to "everything unmatched" rather than crashing the audit.
    """
    if not session_log_text or not session_log_text.strip():
        return []

    blocks = [
        block
        for block in _PHASE_BLOCK_SPLIT_RE.split(session_log_text)
        if block.strip().startswith("## Phase:")
    ]
    if not blocks:
        return []

    phase_record = _load_phase_record()

    parsed_phases: list[tuple[str, Any]] = []
    for block in blocks:
        try:
            record = phase_record.parse_markdown(block, change_id=change_id)
        except ValueError:
            continue
        if record.decisions:
            slug = record.phase_name.lower().replace(" ", "-")
            parsed_phases.append((slug, record))

    multi_phase = len(parsed_phases) > 1
    out: list[dict[str, str]] = []
    for slug, record in parsed_phases:
        for n, decision in enumerate(record.decisions, start=1):
            ref = f"{change_id}#{slug}/D{n}" if multi_phase else f"{change_id}#D{n}"
            out.append({"title": decision.title, "rationale": decision.rationale, "ref": ref})
    return out


_WORD_RE = re.compile(r"[a-z0-9]+")


def _keywords(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if len(w) > 3}


def resolve_self_reported(
    candidate_choice: str,
    known_decisions: list[dict[str, str]],
    *,
    min_overlap: float = 0.4,
) -> tuple[bool, str | None]:
    """Match a candidate entry's choice headline against session-log
    `Decisions` bullets by keyword overlap. Returns
    ``(self_reported, session_log_ref)``.

    A candidate with no matching bullet (or an empty/absent
    `known_decisions`, e.g. no session-log.md at all) resolves to
    ``(False, None)`` — the auditor's "unreported decision" signal.
    """
    if not known_decisions:
        return False, None
    candidate_keywords = _keywords(candidate_choice)
    if not candidate_keywords:
        return False, None

    best_ref: str | None = None
    best_score = 0.0
    for decision in known_decisions:
        decision_keywords = _keywords(decision["title"] + " " + decision.get("rationale", ""))
        if not decision_keywords:
            continue
        overlap = len(candidate_keywords & decision_keywords) / len(candidate_keywords)
        if overlap > best_score:
            best_score = overlap
            best_ref = decision["ref"]

    if best_score >= min_overlap:
        return True, best_ref
    return False, None


# ─────────────────────────────────────────────────────────────────────────
# Bundle assembly
# ─────────────────────────────────────────────────────────────────────────


def collect_evidence(
    repo_root: Path, *, change_id: str, base_sha: str, head_sha: str
) -> EvidenceBundle:
    """Assemble the read-only evidence bundle for a change-id or commit
    range. Never writes anything; a missing session-log.md (or any other
    missing artifact) degrades gracefully to an empty excerpt rather than
    raising."""
    change_dir = repo_root / "openspec" / "changes" / change_id

    commits = collect_commits(repo_root, base_sha, head_sha)
    files = collect_touched_files(repo_root, base_sha, head_sha)
    diff_stat = collect_diff_stat(repo_root, base_sha, head_sha)

    session_log_text = _read_excerpt(change_dir / "session-log.md", limit=_SESSION_LOG_CHARS)
    known_decisions = (
        parse_session_log_decisions(session_log_text, change_id=change_id)
        if session_log_text
        else []
    )

    return EvidenceBundle(
        change_id=change_id,
        base_sha=base_sha,
        head_sha=head_sha,
        commits=commits,
        files=files,
        diff_stat=diff_stat,
        proposal_excerpt=_read_excerpt(change_dir / "proposal.md"),
        design_excerpt=_read_excerpt(change_dir / "design.md"),
        spec_delta_excerpts=collect_spec_delta_excerpts(change_dir),
        session_log_excerpt=session_log_text,
        impl_findings_excerpt=_read_excerpt(change_dir / "impl-findings.md"),
        known_decisions=known_decisions,
    )


def _cli() -> int:
    """Print the evidence bundle as JSON — the SKILL.md dispatch step uses
    this to build the auditor sub-agent's prompt."""
    import argparse
    import json

    p = argparse.ArgumentParser(description="Assemble the audit-choices evidence bundle")
    p.add_argument("--change-id", required=True)
    p.add_argument("--base-sha", required=True)
    p.add_argument("--head-sha", required=True)
    p.add_argument("--repo-root", default=".")
    args = p.parse_args()

    bundle = collect_evidence(
        Path(args.repo_root).resolve(),
        change_id=args.change_id,
        base_sha=args.base_sha,
        head_sha=args.head_sha,
    )
    print(json.dumps(bundle.to_prompt_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
