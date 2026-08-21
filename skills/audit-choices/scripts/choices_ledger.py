#!/usr/bin/env python3
"""Ledger writer and renderer for the audit-choices skill.

`choices.json` is the source of truth; `choices.md` is rendered from it by
the pure-Python renderer in this module. No LLM SDK calls anywhere in this
file — the module only validates and persists candidate entries an
independent sub-agent already produced (see
`skills/tests/autopilot-roadmap/test_host_assisted_invariant.py` for the
pattern this follows: reasoning happens through the orchestrating agent or
deterministic code, never a direct vendor SDK call from skill Python).

Design decisions (openspec/changes/add-decision-choices-ledger/design.md):
    D2 — choices.json is the source of truth; choices.md is a pure-Python
         rendering of it, so the ranking invariant and header requirements
         are unit-testable and re-rendering is idempotent.
    D3 — stable_id is content-derived: a hash of (normalized choice
         headline + primary file set + gap text). Re-auditing an unchanged
         decision reproduces the same id; a changed gap or file set does not.
    D4 — the six-field artifact header field set is copied verbatim from
         skills/prioritize-proposals/scripts/artifact_header.py, with
         generator "audit-choices@1.0" and event_kind "choices-ledger".
    D7 — this module is the "SCRIPT" side of the auditor contract: it
         validates and drops hallucinated entries (see
         `filter_valid_provenance`) and persists only what survives
         validation. The sub-agent itself never writes files.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCHEMA_VERSION = 1
GENERATOR = "audit-choices@1.0"
EVENT_KIND = "choices-ledger"

_THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = _THIS_DIR.parents[2]  # scripts -> audit-choices -> skills -> repo root
SCHEMA_PATH = REPO_ROOT / "openspec" / "schemas" / "decision-choices.schema.json"

# Rendering / ranking invariant (skill-workflow spec, Requirement: Least-
# confident-first ranking): ascending confidence, then needs-user before
# unsound before sound within equal confidence.
CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}
VERDICT_RANK = {"needs-user": 0, "unsound": 1, "sound": 2}


# ─────────────────────────────────────────────────────────────────────────
# Artifact header (D4)
# ─────────────────────────────────────────────────────────────────────────


def make_header(*, now: datetime, git_sha: str, run_id: str) -> dict[str, Any]:
    """Construct the six-field mandatory header for an event artifact.

    Field set and semantics copied verbatim from
    skills/prioritize-proposals/scripts/artifact_header.py (D4); only
    GENERATOR and EVENT_KIND differ. `now` must be UTC-aware; `git_sha`
    must be the full 40-char hash.
    """
    if now.tzinfo is None or now.utcoffset() != timezone.utc.utcoffset(None):
        raise ValueError("now must be a UTC-aware datetime")
    if len(git_sha) != 40:
        raise ValueError(f"git_sha must be the full 40-char hash, got length {len(git_sha)}")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_sha": git_sha,
        "generator": GENERATOR,
        "run_id": run_id,
        "event_kind": EVENT_KIND,
    }


# ─────────────────────────────────────────────────────────────────────────
# stable_id (D3)
# ─────────────────────────────────────────────────────────────────────────

_WS_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WS_RE.sub(" ", text.strip().lower())


def compute_stable_id(*, choice: str, files: list[str], gap: str) -> str:
    """Content-derived stable_id: hash of (normalized choice headline +
    primary file set + gap text).

    Re-auditing an unchanged decision (same choice headline, same touched
    files, same gap text) MUST produce the same id; a changed gap, a
    changed choice headline, or a changed file set MUST produce a
    different one. File order and casing of the choice/gap text do not
    matter — only their normalized content does.
    """
    norm_choice = _normalize(choice)
    norm_files = ",".join(sorted({f.strip() for f in files if f and f.strip()}))
    norm_gap = _normalize(gap)
    payload = "\x1f".join([norm_choice, norm_files, norm_gap])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────────────────
# Entry dataclasses
# ─────────────────────────────────────────────────────────────────────────


@dataclass
class Provenance:
    commits: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)


@dataclass
class Entry:
    choice: str
    scenario: str
    gap: str
    reach: str
    verdict: str
    verdict_rationale: str
    confidence: str
    provenance: Provenance
    self_reported: bool
    stable_id: str | None = None
    session_log_ref: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.provenance, dict):
            self.provenance = Provenance(
                commits=list(self.provenance.get("commits", [])),
                files=list(self.provenance.get("files", [])),
            )
        if self.stable_id is None:
            self.stable_id = compute_stable_id(
                choice=self.choice, files=self.provenance.files, gap=self.gap
            )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "stable_id": self.stable_id,
            "choice": self.choice,
            "scenario": self.scenario,
            "gap": self.gap,
            "reach": self.reach,
            "verdict": self.verdict,
            "verdict_rationale": self.verdict_rationale,
            "confidence": self.confidence,
            "provenance": {
                "commits": list(self.provenance.commits),
                "files": list(self.provenance.files),
            },
            "self_reported": self.self_reported,
        }
        if self.session_log_ref:
            out["session_log_ref"] = self.session_log_ref
        return out

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Entry":
        prov = d.get("provenance", {})
        return cls(
            choice=d["choice"],
            scenario=d["scenario"],
            gap=d["gap"],
            reach=d["reach"],
            verdict=d["verdict"],
            verdict_rationale=d["verdict_rationale"],
            confidence=d["confidence"],
            provenance=Provenance(
                commits=list(prov.get("commits", [])), files=list(prov.get("files", []))
            ),
            self_reported=d["self_reported"],
            stable_id=d.get("stable_id"),
            session_log_ref=d.get("session_log_ref"),
        )


# ─────────────────────────────────────────────────────────────────────────
# Ranking (skill-workflow spec: Least-confident-first ranking)
# ─────────────────────────────────────────────────────────────────────────


def _rank_key(entry: dict[str, Any]) -> tuple[int, int]:
    return (
        CONFIDENCE_RANK.get(entry.get("confidence", ""), 99),
        VERDICT_RANK.get(entry.get("verdict", ""), 99),
    )


def rank_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return entries sorted ascending by confidence (low, medium, high);
    within equal confidence, needs-user before unsound before sound."""
    return sorted(entries, key=_rank_key)


# ─────────────────────────────────────────────────────────────────────────
# Hallucination guard (D7)
# ─────────────────────────────────────────────────────────────────────────


def _commit_known(candidate_commit: str, known_full_shas: set[str]) -> bool:
    if not candidate_commit:
        return False
    if candidate_commit in known_full_shas:
        return True
    if len(candidate_commit) < 7:
        return False
    return any(full_sha.startswith(candidate_commit) for full_sha in known_full_shas)


def filter_valid_provenance(
    candidates: list[dict[str, Any]],
    *,
    known_commits: set[str],
    known_files: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split candidate entries into (kept, dropped) by whether every cited
    commit and file actually exists in the audited range.

    This is the hallucination guard from D7 / design.md Risks: an entry
    whose provenance cites a commit or file absent from the range is
    dropped, not persisted, regardless of how plausible its verdict reads.
    """
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for candidate in candidates:
        provenance = candidate.get("provenance") or {}
        commits = provenance.get("commits") or []
        files = provenance.get("files") or []
        commits_ok = bool(commits) and all(_commit_known(c, known_commits) for c in commits)
        files_ok = bool(files) and all(f in known_files for f in files)
        if commits_ok and files_ok:
            kept.append(candidate)
        else:
            dropped.append(candidate)
    return kept, dropped


def _entry_schema(schema_path: Path = SCHEMA_PATH) -> dict[str, Any]:
    schema = json.loads(schema_path.read_text())
    entry_schema = dict(schema["$defs"]["entry"])
    # Embed the $defs so a validator built from this sub-schema alone can
    # still resolve any internal $ref (none today, but this keeps the
    # sub-schema self-contained if the entry shape grows a $ref later).
    entry_schema["$defs"] = schema.get("$defs", {})
    return entry_schema


def split_schema_valid(
    entries: list[dict[str, Any]], *, schema_path: Path = SCHEMA_PATH
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split entries into (valid, invalid) against the ledger entry schema.

    Run this after stable_id / self_reported have been filled in — entries
    missing a required field or carrying a bad enum value are invalid and
    must not be persisted (D7: the script validates, not the sub-agent).
    """
    validator = Draft202012Validator(_entry_schema(schema_path))
    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for entry in entries:
        if validator.is_valid(entry):
            valid.append(entry)
        else:
            invalid.append(entry)
    return valid, invalid


# ─────────────────────────────────────────────────────────────────────────
# Document assembly, validation, idempotent write
# ─────────────────────────────────────────────────────────────────────────


def build_document(
    *,
    header: dict[str, Any],
    change_id: str,
    audited_range: dict[str, str],
    entries: list[dict[str, Any]],
    auditor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "header": header,
        "change_id": change_id,
        "audited_range": audited_range,
        "entries": rank_entries(entries),
    }
    if auditor:
        doc["auditor"] = auditor
    return doc


def validate_document(doc: dict[str, Any], *, schema_path: Path = SCHEMA_PATH) -> None:
    schema = json.loads(schema_path.read_text())
    Draft202012Validator(schema).validate(doc)


def merge_entries(
    existing: list[dict[str, Any]], new: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge `new` entries into `existing`, keyed by `stable_id`.

    Re-running the audit over an unchanged decision produces the same
    stable_id, so it updates that entry's slot in place rather than
    duplicating it (skill-workflow spec: Re-audit is idempotent). A
    genuinely new stable_id is appended.
    """
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for entry in existing:
        sid = entry["stable_id"]
        if sid not in by_id:
            order.append(sid)
        by_id[sid] = entry
    for entry in new:
        sid = entry["stable_id"]
        if sid not in by_id:
            order.append(sid)
        by_id[sid] = entry
    return [by_id[sid] for sid in order]


def write_ledger(
    ledger_path: Path,
    *,
    header: dict[str, Any],
    change_id: str,
    audited_range: dict[str, str],
    entries: list[dict[str, Any]],
    auditor: dict[str, Any] | None = None,
    schema_path: Path = SCHEMA_PATH,
) -> dict[str, Any]:
    """Write choices.json, merging with any existing ledger at `ledger_path`
    so re-runs are idempotent. Validates the full document against the
    schema before writing; raises on validation failure (callers that must
    never raise should use `run_audit.run_audit`, which catches this)."""
    existing_entries: list[dict[str, Any]] = []
    if ledger_path.exists():
        try:
            existing_doc = json.loads(ledger_path.read_text())
            existing_entries = existing_doc.get("entries", [])
        except (json.JSONDecodeError, OSError):
            existing_entries = []

    merged = merge_entries(existing_entries, entries)
    doc = build_document(
        header=header,
        change_id=change_id,
        audited_range=audited_range,
        entries=merged,
        auditor=auditor,
    )
    validate_document(doc, schema_path=schema_path)

    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(doc, indent=2) + "\n")
    return doc


# ─────────────────────────────────────────────────────────────────────────
# choices.md renderer (D2) — pure function, no I/O beyond the return value
# ─────────────────────────────────────────────────────────────────────────


def _fmt_list(items: list[str]) -> str:
    return ", ".join(f"`{item}`" for item in items) if items else "(none)"


def render_markdown(doc: dict[str, Any]) -> str:
    """Render choices.md from a choices.json document. Pure function: same
    input always produces the same output. Structure follows
    openspec/schemas/feature-workflow/templates/choices.md."""
    header = doc["header"]
    change_id = doc["change_id"]
    audited_range = doc["audited_range"]
    entries = doc.get("entries", [])

    lines: list[str] = [f"# Choices Ledger: {change_id}", ""]
    lines.append(
        "<!-- GENERATED from choices.json by the audit-choices skill. Do not hand-edit —\n"
        "     edits made here are discarded the next time the ledger is rendered.\n"
        "     choices.json is the source of truth; this file is a rendering of it.\n"
        "     Produced by an independent, read-only auditor pass — never hand-authored\n"
        "     during planning or implementation. -->"
    )
    lines.append("")
    lines.append(f"**Generated**: {header.get('generated_at', '')}")
    lines.append(
        f"**Audited range**: {audited_range.get('base_sha', '')}..{audited_range.get('head_sha', '')}"
    )
    lines.append("")
    lines.append(
        "<!-- Entries are ordered least-confident first (low, then medium, then high);\n"
        "     within equal confidence, needs-user before unsound before sound. This is\n"
        "     a rendering invariant enforced by the renderer, not editable here. -->"
    )
    lines.append("")
    lines.append("## Entries")
    lines.append("")

    ranked = rank_entries(entries)
    if not ranked:
        lines.append("_No entries recorded for this audit run._")
        return "\n".join(lines).rstrip() + "\n"

    for entry in ranked:
        lines.append(f"### {entry['choice']}")
        lines.append("")
        lines.append(f"**Confidence**: {entry['confidence']} · **Verdict**: {entry['verdict']}")
        lines.append("")
        lines.append("#### The choice")
        lines.append("")
        lines.append(entry["choice"])
        lines.append("")
        lines.append("#### Scenario")
        lines.append("")
        lines.append(entry["scenario"])
        lines.append("")
        lines.append("#### The gap")
        lines.append("")
        lines.append(entry["gap"])
        lines.append("")
        lines.append("#### The reach")
        lines.append("")
        lines.append(entry["reach"])
        lines.append("")
        lines.append("#### Verdict")
        lines.append("")
        lines.append(f"{entry['verdict']} — {entry['verdict_rationale']}")
        lines.append("")
        lines.append("#### Confidence")
        lines.append("")
        lines.append(entry["confidence"])
        lines.append("")
        lines.append("#### Provenance")
        lines.append("")
        provenance = entry.get("provenance", {})
        lines.append(f"- **Commits**: {_fmt_list(provenance.get('commits', []))}")
        lines.append(f"- **Files**: {_fmt_list(provenance.get('files', []))}")
        lines.append("")
        lines.append("#### Self-reported")
        lines.append("")
        if entry.get("self_reported"):
            lines.append(entry.get("session_log_ref") or "(self-reported, but no ref recorded)")
        else:
            lines.append(
                "Not self-reported — the auditor found this decision without a matching "
                "`Decisions` entry in `session-log.md`."
            )
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_ledger_pair(
    change_dir: Path,
    *,
    header: dict[str, Any],
    change_id: str,
    audited_range: dict[str, str],
    entries: list[dict[str, Any]],
    auditor: dict[str, Any] | None = None,
    schema_path: Path = SCHEMA_PATH,
) -> tuple[Path, Path]:
    """Write choices.json (source of truth) then render choices.md from it.
    The only two files this function touches are the ledger pair."""
    json_path = change_dir / "choices.json"
    md_path = change_dir / "choices.md"
    doc = write_ledger(
        json_path,
        header=header,
        change_id=change_id,
        audited_range=audited_range,
        entries=entries,
        auditor=auditor,
        schema_path=schema_path,
    )
    md_path.write_text(render_markdown(doc))
    return json_path, md_path
