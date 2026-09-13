"""Packed review input: diff, spec excerpts, prompt contract, ledger.

Shared by ``converge()`` and the review dispatcher so both send the same
markdown packet plus sidecar metadata instead of asking a coding agent to
walk the repo. Does not depend on ``SEMANTIC_CONTEXT_INJECTION``.
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

logger = logging.getLogger(__name__)

BUDGET_CHARS = 320_000
SPEC_EXCERPT_CHARS = 12_000
SCHEMA_VERSION = 1
PACKET_BODY_NAME = "review-packet.md"
PACKET_META_NAME = "review-packet.meta.json"
EMPTY_DIFF_MARKER = "(empty-diff)"
DEFAULT_BASE_REF = "main"
DEFAULT_HEAD_REF = "HEAD"

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
) -> tuple[Path, dict[str, Any]]:
    """Write a review packet body and schema-matching sidecar metadata.

    Returns ``(body_path, metadata)``.
    """
    artifacts_dir = Path(artifacts_dir)
    worktree_path = Path(worktree_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    contract = prompt_contract_block()
    diff_text, diff_kind = _select_diff(
        round_num=round_num,
        last_fix_diff=last_fix_diff,
        worktree_path=worktree_path,
        base_ref=base_ref,
        head_ref=head_ref,
    )
    spec_entries = _spec_entries(artifacts_dir)
    includes_ledger, open_items = _open_ledger_items(artifacts_dir, ledger)

    body, tools_overflow = _fit_to_budget(
        round_num=round_num,
        contract=contract,
        diff_text=diff_text,
        spec_entries=spec_entries,
        open_items=open_items if includes_ledger else None,
    )
    if not (diff_text or "").strip():
        diff_kind = "empty"

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
    }
    meta_path = output_dir / PACKET_META_NAME
    meta_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return body_path, metadata


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
    spec_entries: list[tuple[str, str]],
    open_items: list[dict[str, Any]] | None,
) -> tuple[str, bool]:
    body = _render(
        round_num=round_num,
        contract=contract,
        diff_text=diff_text,
        spec_entries=list(spec_entries),
        open_items=open_items,
        overflow=False,
    )
    if len(body) <= BUDGET_CHARS:
        return body, False

    dropped: list[tuple[str, str | None]] = [(rel, None) for rel, _ in spec_entries]
    body = _render(
        round_num=round_num,
        contract=contract,
        diff_text=diff_text,
        spec_entries=dropped,
        open_items=open_items,
        overflow=True,
    )
    if len(body) <= BUDGET_CHARS:
        return body, True

    placeholder = "\x00DIFF\x00"
    probe = _render(
        round_num=round_num,
        contract=contract,
        diff_text=placeholder,
        spec_entries=dropped,
        open_items=open_items,
        overflow=True,
    )
    overhead = len(probe) - len(placeholder)
    room = BUDGET_CHARS - overhead - len(DIFF_TRUNCATION_NOTE)
    if room < 1:
        truncated = EMPTY_DIFF_MARKER + DIFF_TRUNCATION_NOTE
    else:
        truncated = diff_text[:room] + DIFF_TRUNCATION_NOTE
    body = _render(
        round_num=round_num,
        contract=contract,
        diff_text=truncated,
        spec_entries=dropped,
        open_items=open_items,
        overflow=True,
    )
    if len(body) > BUDGET_CHARS:
        body = body[:BUDGET_CHARS]
    return body, True


def _render(
    *,
    round_num: int,
    contract: str,
    diff_text: str,
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
