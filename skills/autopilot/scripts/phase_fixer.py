"""Phase-specific fix application for the review convergence loop.

PLAN_FIX / IMPL_FIX / VAL_FIX run as ``converge()``'s ``fix_callback``,
not as an outer cold-review bounce. Callers may inject ``dispatch_fn``
(tests) or rely on vendor CLI dispatch (targeted) / conductor-equivalent
dispatch (inline).
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_PARALLEL_INFRA_DIR = str(
    Path(__file__).resolve().parent.parent.parent
    / "parallel-infrastructure"
    / "scripts"
)
if _PARALLEL_INFRA_DIR not in sys.path:
    sys.path.insert(0, _PARALLEL_INFRA_DIR)

DispatchFn = Callable[..., Any]


class FixDispatchError(RuntimeError):
    """Raised when a phase fixer cannot dispatch or apply scoped edits."""


def build_scoped_fix_prompt(
    blocking: list[dict[str, Any]],
    *,
    fix_mode: str,
) -> str:
    """Prompt that forbids out-of-scope edits and new architecture."""
    lines = [
        f"Apply scoped {fix_mode} fixes for the following blocking review findings.",
        "Edit ONLY the allowed_paths listed on each item.",
        "Do not add architecture, expand scope, or modify unrelated files.",
        "",
    ]
    for item in blocking:
        lines.append(f"## Finding {item.get('id')}")
        lines.append(
            f"type: {item.get('type') or item.get('agreed_type')}"
        )
        lines.append(
            "criticality: "
            f"{item.get('criticality') or item.get('agreed_criticality')}"
        )
        lines.append(f"allowed_paths: {item.get('allowed_paths')}")
        lines.append(str(item.get("description") or ""))
        lines.append("")
    return "\n".join(lines)


def apply_phase_fixes(
    blocking: list[dict[str, Any]],
    worktree_path: Path,
    *,
    fix_mode: str = "inline",
    change_dir: Path | None = None,
    package_authors: dict[str, str] | None = None,
    dispatch_fn: DispatchFn | None = None,
) -> None:
    """Apply scoped PLAN/IMPL/VAL fixes for the current blocking set.

    Always persists the payload under ``.review-ledger/pending-fixes.json``
    when ``change_dir`` is set, then dispatches via ``dispatch_fn`` or the
    vendor CLI adapter. A missing dispatcher is an error — never a silent
    no-op that would let the loop mark findings addressed.
    """
    if change_dir is not None:
        ledger_dir = Path(change_dir) / ".review-ledger"
        ledger_dir.mkdir(parents=True, exist_ok=True)
        (ledger_dir / "pending-fixes.json").write_text(
            json.dumps(
                {"fix_mode": fix_mode, "items": blocking},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    prompt = build_scoped_fix_prompt(blocking, fix_mode=fix_mode)
    authors = package_authors or {}
    if dispatch_fn is not None:
        dispatch_fn(
            blocking,
            worktree_path,
            prompt=prompt,
            fix_mode=fix_mode,
            package_authors=authors,
        )
        return
    _dispatch_vendor_fix(
        blocking,
        worktree_path,
        prompt=prompt,
        fix_mode=fix_mode,
        package_authors=authors,
    )


def _pick_fix_mode(adapter: Any) -> str | None:
    """Prefer a write-capable dispatch mode over read-only review."""
    can_dispatch = getattr(adapter, "can_dispatch", None)
    if not callable(can_dispatch):
        return None
    for mode in ("alternative", "quick", "review"):
        try:
            if can_dispatch(mode):
                return mode
        except Exception:  # noqa: BLE001 — adapter availability is best-effort
            continue
    return None


def _dispatch_vendor_fix(
    blocking: list[dict[str, Any]],
    worktree_path: Path,
    *,
    prompt: str,
    fix_mode: str,
    package_authors: dict[str, str],
) -> None:
    """Send the scoped fix prompt to a vendor CLI adapter."""
    try:
        from review_dispatcher import ReviewOrchestrator
    except ImportError as exc:
        raise FixDispatchError(
            "review_dispatcher unavailable; pass dispatch_fn or a real "
            "fix_callback"
        ) from exc
    try:
        orch = ReviewOrchestrator.from_coordinator()
    except Exception as exc:
        raise FixDispatchError(
            f"could not build review orchestrator: {exc}"
        ) from exc

    adapters = getattr(orch, "adapters", None) or {}
    lead: str | None = None
    if fix_mode == "targeted" and package_authors:
        lead = next(iter(package_authors.values()), None)

    chosen = None
    if lead:
        for adapter in adapters.values():
            if getattr(adapter, "vendor", None) == lead:
                chosen = adapter
                break
    if chosen is None:
        for adapter in adapters.values():
            if _pick_fix_mode(adapter) is not None:
                chosen = adapter
                break
    if chosen is None:
        raise FixDispatchError(
            "no vendor adapter available for scoped phase fixes"
        )

    mode = _pick_fix_mode(chosen)
    if mode is None:
        raise FixDispatchError(
            f"adapter {getattr(chosen, 'vendor', chosen)!r} has no "
            "write-capable dispatch mode"
        )
    result = chosen.dispatch(mode, prompt, cwd=worktree_path)
    success = bool(getattr(result, "success", False))
    if not success:
        error = getattr(result, "error", None) or "vendor fix dispatch failed"
        raise FixDispatchError(str(error))
    logger.info(
        "Dispatched %s fix via %s (%d items)",
        fix_mode,
        getattr(chosen, "vendor", "?"),
        len(blocking),
    )
