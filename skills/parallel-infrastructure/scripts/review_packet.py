"""Packed review input: selection, diff, rule groups, spec excerpts, ledger.

Shared by ``converge()`` and the review dispatcher so both send the same
markdown packet plus sidecar metadata instead of asking a coding agent to
walk the repo. Does not depend on ``SEMANTIC_CONTEXT_INJECTION``.

Deterministic file selection (:mod:`file_selection`) and path-glob rule
groups (:mod:`review_rules`) run before rendering — ported from alibaba/
open-code-review's engineering split (Apache-2.0 License,
https://github.com/alibaba/open-code-review, read 2026-09-14). Selection
decisions and rule groups are recorded in the packet metadata (schema
version 2) so a reviewer, or an auditor of the round, can see exactly which
files were excluded and why, without spending a token.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from review_findings_schema import prompt_contract_block  # noqa: E402
import file_selection  # noqa: E402
import review_rules  # noqa: E402

logger = logging.getLogger(__name__)

BUDGET_CHARS = 320_000
SPEC_EXCERPT_CHARS = 12_000
SCHEMA_VERSION = 2
PACKET_BODY_NAME = "review-packet.md"
PACKET_META_NAME = "review-packet.meta.json"
EMPTY_DIFF_MARKER = "(empty-diff)"
DEFAULT_BASE_REF = "main"
DEFAULT_HEAD_REF = "HEAD"

# 80% of the packet's token-equivalent budget (BUDGET_CHARS / 4 chars-per-
# token), matching the same 80% ceiling the dispatcher's own prompt-budget
# guard uses elsewhere. A single file cannot eat more than this on its own —
# see file_selection.py's REASON_TOO_LARGE gate.
PER_FILE_TOKEN_CEILING = int(0.8 * BUDGET_CHARS / 4)

COMPLETE_INSTRUCTION = (
    "The packet is complete; do not explore the repo for missing artifacts."
)
OVERFLOW_INSTRUCTION = (
    "This packet exceeds the size budget and was truncated. "
    "You MAY use Read/Grep to recover truncated context."
)
DIFF_TRUNCATION_NOTE = (
    "\n\n[diff truncated to fit packet budget; use Read/Grep for the remainder]\n"
)
SPEC_DROPPED_NOTE = (
    "(excerpt dropped — over packet budget; Read this path if needed)"
)


def build_review_packet(
    *,
    change_id: str,
    round_num: int,
    artifacts_dir: Path,
    worktree_path: Path,
    output_dir: Path,
    last_fix_diff: str | None = None,
    base_ref: str = DEFAULT_BASE_REF,
    head_ref: str = DEFAULT_HEAD_REF,
    ledger: dict[str, Any] | None = None,
    rule_config: review_rules.RuleConfig | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Write a review packet body and schema-matching sidecar metadata.

    Returns ``(body_path, metadata)``.
    """
    artifacts_dir = Path(artifacts_dir)
    worktree_path = Path(worktree_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    contract = prompt_contract_block()
    raw_diff_text, diff_kind = _select_diff(
        round_num=round_num,
        last_fix_diff=last_fix_diff,
        worktree_path=worktree_path,
        base_ref=base_ref,
        head_ref=head_ref,
    )
    rule_config = rule_config if rule_config is not None else review_rules.load_config(
        worktree_path
    )
    sel = select_and_group(raw_diff_text, rule_config)

    spec_entries = _spec_entries(artifacts_dir)
    includes_ledger, open_items = _open_ledger_items(artifacts_dir, ledger)

    body, tools_overflow, diff_chars_kept = _fit_to_budget(
        round_num=round_num,
        contract=contract,
        diff_text=sel.diff_text,
        rule_groups_md=sel.rule_groups_md,
        spec_entries=spec_entries,
        open_items=open_items if includes_ledger else None,
    )
    if not (raw_diff_text or "").strip():
        diff_kind = "empty"

    truncated_paths = _truncated_paths(sel.offsets, diff_chars_kept)

    body_path = output_dir / PACKET_BODY_NAME
    body_path.write_text(body, encoding="utf-8")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    metadata: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "change_id": change_id,
        "round": int(round_num),
        "body_path": PACKET_BODY_NAME,
        "sha256": digest,
        "char_length": len(body),
        "budget_chars": BUDGET_CHARS,
        "tools_overflow": tools_overflow,
        "includes_ledger": includes_ledger,
        "diff_kind": diff_kind,
        "selection": {
            "per_file_token_ceiling": PER_FILE_TOKEN_CEILING,
            "selected": [d.to_dict() for d in sel.decisions if d.selected],
            "excluded": [d.to_dict() for d in sel.decisions if not d.selected],
            "truncated": truncated_paths,
        },
        "rule_groups": [g.to_dict() for g in sel.rule_groups],
    }
    meta_path = output_dir / PACKET_META_NAME
    meta_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return body_path, metadata


class SelectionResult:
    """Everything :func:`select_and_group` derives from a raw diff blob."""

    __slots__ = (
        "decisions", "diff_text", "offsets", "rule_groups", "rule_groups_md",
    )

    def __init__(
        self,
        decisions: list[file_selection.FileDecision],
        diff_text: str,
        offsets: list[tuple[str, int, int]],
        rule_groups: list[review_rules.RuleGroup],
        rule_groups_md: str,
    ) -> None:
        self.decisions = decisions
        self.diff_text = diff_text
        self.offsets = offsets
        self.rule_groups = rule_groups
        self.rule_groups_md = rule_groups_md


def select_and_group(
    raw_diff_text: str, rule_config: review_rules.RuleConfig,
) -> SelectionResult:
    """Run selection and rule grouping over a raw diff blob.

    This is the ONE function both :func:`build_review_packet` and
    :func:`preview` call — the shared selection path that keeps the two
    from drifting (see the module docstring).
    """
    files = file_selection.parse_diff_files(raw_diff_text)
    decisions = file_selection.select_files(
        files,
        include=rule_config.include,
        exclude=rule_config.exclude,
        generated_paths=rule_config.generated_paths,
        per_file_token_ceiling=PER_FILE_TOKEN_CEILING,
    )
    selected = [d for d in decisions if d.selected and d.file is not None]

    parts: list[str] = []
    offsets: list[tuple[str, int, int]] = []
    pos = 0
    for d in selected:
        assert d.file is not None  # narrowed by the filter above
        parts.append(d.file.body)
        start = pos
        pos += len(d.file.body) + 1  # +1 for the join separator
        offsets.append((d.path, start, pos - 1))
    diff_text = "\n".join(parts)

    rule_groups = review_rules.group_files_by_rule(
        [d.path for d in selected], rule_config
    )
    rule_groups_md = _render_rule_groups(rule_groups)
    return SelectionResult(decisions, diff_text, offsets, rule_groups, rule_groups_md)


def preview(
    *,
    artifacts_dir: Path,
    worktree_path: Path,
    round_num: int = 1,
    last_fix_diff: str | None = None,
    base_ref: str = DEFAULT_BASE_REF,
    head_ref: str = DEFAULT_HEAD_REF,
    rule_config: review_rules.RuleConfig | None = None,
) -> list[file_selection.FileDecision]:
    """Return selection decisions without rendering, writing, or dispatching.

    Calls the exact same :func:`select_and_group` a real build calls, so
    preview and build cannot diverge — see the "Preview Parity" requirement.
    """
    worktree_path = Path(worktree_path)
    raw_diff_text, _diff_kind = _select_diff(
        round_num=round_num,
        last_fix_diff=last_fix_diff,
        worktree_path=worktree_path,
        base_ref=base_ref,
        head_ref=head_ref,
    )
    rule_config = rule_config if rule_config is not None else review_rules.load_config(
        worktree_path
    )
    return select_and_group(raw_diff_text, rule_config).decisions


def _truncated_paths(
    offsets: list[tuple[str, int, int]], diff_chars_kept: int | None,
) -> list[str]:
    if diff_chars_kept is None:
        return []
    return [path for path, _start, end in offsets if end > diff_chars_kept]


def _render_rule_groups(groups: list[review_rules.RuleGroup]) -> str:
    if not groups:
        return ""
    parts = ["### Rule groups", ""]
    for g in groups:
        parts.append(f"#### Group {g.group_id} ({g.source}: `{g.pattern}`)")
        parts.append("Applies to:")
        for f in g.files:
            parts.append(f"- {f}")
        parts.append("")
        parts.append(g.text)
        parts.append("")
    return "\n".join(parts)


def _select_diff(
    *,
    round_num: int,
    last_fix_diff: str | None,
    worktree_path: Path,
    base_ref: str,
    head_ref: str,
) -> tuple[str, str]:
    if round_num > 1 and last_fix_diff is not None:
        text = last_fix_diff
        kind = "last_fix" if text.strip() else "empty"
        return text, kind
    text = _git_diff(worktree_path, base_ref, head_ref)
    kind = "full" if text.strip() else "empty"
    return text, kind


def _git_diff(worktree_path: Path, base_ref: str, head_ref: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "diff", f"{base_ref}...{head_ref}"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if proc.returncode != 0:
        logger.warning(
            "git diff %s...%s failed: %s",
            base_ref,
            head_ref,
            (proc.stderr or "").strip(),
        )
        return ""
    return proc.stdout or ""


def _spec_entries(artifacts_dir: Path) -> list[tuple[str, str]]:
    specs_root = artifacts_dir / "specs"
    if not specs_root.is_dir():
        return []
    entries: list[tuple[str, str]] = []
    for path in sorted(specs_root.glob("**/spec.md")):
        rel = path.relative_to(artifacts_dir).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("failed to read spec excerpt %s: %s", path, exc)
            continue
        if len(text) > SPEC_EXCERPT_CHARS:
            text = text[:SPEC_EXCERPT_CHARS] + "\n\n[spec excerpt truncated]\n"
        entries.append((rel, text))
    return entries


def _open_ledger_items(
    artifacts_dir: Path,
    ledger: dict[str, Any] | None,
) -> tuple[bool, list[dict[str, Any]]]:
    data = ledger
    if data is None:
        path = artifacts_dir / ".review-ledger" / "ledger.json"
        if not path.is_file():
            return False, []
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("failed to read review ledger %s: %s", path, exc)
            return False, []
        if not isinstance(loaded, dict):
            return False, []
        data = loaded
    items = [
        item
        for item in (data.get("items") or [])
        if isinstance(item, dict) and item.get("status") == "open"
    ]
    return True, items


def _fit_to_budget(
    *,
    round_num: int,
    contract: str,
    diff_text: str,
    rule_groups_md: str,
    spec_entries: list[tuple[str, str]],
    open_items: list[dict[str, Any]] | None,
) -> tuple[str, bool, int | None]:
    """Fit the packet to :data:`BUDGET_CHARS`.

    Returns ``(body, tools_overflow, diff_chars_kept)``. ``diff_chars_kept``
    is ``None`` when the diff text was not itself truncated (the common
    case, and also the case when only spec excerpts were dropped); it is
    the number of leading characters of the (already file-selected) diff
    text that survived, used by ``_truncated_paths`` to report which
    selected files lost content to the character-budget ladder.
    """
    body = _render(
        round_num=round_num,
        contract=contract,
        diff_text=diff_text,
        rule_groups_md=rule_groups_md,
        spec_entries=list(spec_entries),
        open_items=open_items,
        overflow=False,
    )
    if len(body) <= BUDGET_CHARS:
        return body, False, None

    dropped: list[tuple[str, str | None]] = [(rel, None) for rel, _ in spec_entries]
    body = _render(
        round_num=round_num,
        contract=contract,
        diff_text=diff_text,
        rule_groups_md=rule_groups_md,
        spec_entries=dropped,
        open_items=open_items,
        overflow=True,
    )
    if len(body) <= BUDGET_CHARS:
        return body, True, None

    placeholder = "\x00DIFF\x00"
    probe = _render(
        round_num=round_num,
        contract=contract,
        diff_text=placeholder,
        rule_groups_md=rule_groups_md,
        spec_entries=dropped,
        open_items=open_items,
        overflow=True,
    )
    overhead = len(probe) - len(placeholder)
    room = BUDGET_CHARS - overhead - len(DIFF_TRUNCATION_NOTE)
    if room < 1:
        truncated = EMPTY_DIFF_MARKER + DIFF_TRUNCATION_NOTE
        kept_chars = 0
    else:
        truncated = diff_text[:room] + DIFF_TRUNCATION_NOTE
        kept_chars = min(room, len(diff_text))
    body = _render(
        round_num=round_num,
        contract=contract,
        diff_text=truncated,
        rule_groups_md=rule_groups_md,
        spec_entries=dropped,
        open_items=open_items,
        overflow=True,
    )
    if len(body) > BUDGET_CHARS:
        body = body[:BUDGET_CHARS]
    return body, True, kept_chars


def _render(
    *,
    round_num: int,
    contract: str,
    diff_text: str,
    rule_groups_md: str,
    spec_entries: list[tuple[str, str | None]] | list[tuple[str, str]],
    open_items: list[dict[str, Any]] | None,
    overflow: bool,
) -> str:
    displayed_diff = diff_text if (diff_text or "").strip() else EMPTY_DIFF_MARKER
    parts: list[str] = [
        f"## Review Round {round_num}",
        "",
        OVERFLOW_INSTRUCTION if overflow else COMPLETE_INSTRUCTION,
        "",
        "Review the attached artifacts for correctness, completeness, "
        "and adherence to project standards.",
        "",
        "### Prompt contract",
        contract,
        "",
        "### Diff",
        "```diff",
        displayed_diff,
        "```",
        "",
    ]
    if rule_groups_md:
        parts.append(rule_groups_md)
    if spec_entries:
        parts.append("### Spec excerpts")
        for rel, excerpt in spec_entries:
            parts.append(f"#### {rel}")
            if excerpt is None:
                parts.append(SPEC_DROPPED_NOTE)
            else:
                parts.append(excerpt)
            parts.append("")
    if open_items:
        parts.append("### Open ledger items")
        for item in open_items:
            parts.append(f"- [{item.get('id')}] {item.get('description', '')}")
        parts.append("")
        parts.append(
            "Do not emit findings for issues already in the ledger "
            "except to re-verify the open items listed above."
        )
        parts.append("")
    if round_num > 1:
        parts.append(
            "Hunt only in the attached last-fix diff. Re-verify open "
            "ledger items. Do not re-open retired or parked items."
        )
        parts.append("")
    parts.extend(
        [
            "### Instructions",
            "Return findings as JSON with a top-level `findings` array.",
            "",
            f"This is round {round_num}. Focus on remaining issues.",
        ]
    )
    return "\n".join(parts)
