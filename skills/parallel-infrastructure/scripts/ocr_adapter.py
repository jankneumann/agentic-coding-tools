#!/usr/bin/env python3
"""OCR (alibaba/open-code-review) reviewer vendor adapter.

Runs ``ocr review`` over the current worktree's diff and rewrites its
``comments[]`` into a review-findings payload on stdout. See
``openspec/changes/add-deterministic-review-preprocessing/contracts/
ocr-adapter.md`` for the full command and output-rewrite contract.

Discovered as an optional Tier-1 reviewer vendor only when the ``ocr``
binary is on PATH and an LLM endpoint is configured — see
:func:`can_dispatch`. Absent either, the adapter exits 2 and dispatch treats
the vendor as unavailable, the standard Tier-3 skip; nothing else about
dispatch changes.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def ocr_configured() -> bool:
    """True when ``ocr`` has an LLM endpoint configured (env or config file)."""
    if os.environ.get("OCR_LLM_URL") or os.environ.get("OCR_LLM_TOKEN"):
        return True
    config_path = Path.home() / ".opencodereview" / "config.json"
    return config_path.is_file()


def can_dispatch() -> bool:
    """True when the ``ocr`` binary is on PATH and it is configured."""
    return shutil.which("ocr") is not None and ocr_configured()


def _rewrite_comment(comment: dict[str, Any], index: int) -> dict[str, Any]:
    """Rewrite one OCR comment into a review-findings finding fragment.

    ``category`` becomes both ``type`` and ``axis`` (coercion maps the same
    source string through separate alias tables). ``severity`` becomes
    ``criticality`` directly — OCR's four severities are spelled identically
    to our ``criticality`` enum — and the finding's own ``severity`` is left
    absent so the standard criticality-to-severity coercion fills it.
    """
    category = comment.get("category") or "other"
    finding: dict[str, Any] = {
        "id": index,
        "type": category,
        "criticality": comment.get("severity") or "low",
        "description": comment.get("content") or "",
        "disposition": "fix",
        "axis": category,
        "file_path": comment.get("path"),
    }
    existing_code = comment.get("existing_code")
    if existing_code:
        finding["existing_code"] = existing_code
    start = comment.get("start_line") or 0
    end = comment.get("end_line") or 0
    if start and end:
        finding["line_range"] = {"start": start, "end": end}
    suggestion = comment.get("suggestion_code")
    if suggestion:
        finding["resolution"] = f"Suggested change:\n{suggestion}"
    return finding


def rewrite_output(
    ocr_result: dict[str, Any], *, change_id: str, review_type: str,
) -> dict[str, Any]:
    """Rewrite a parsed ``ocr review --format json`` document into our schema."""
    comments = ocr_result.get("comments") or []
    findings = [_rewrite_comment(c, i + 1) for i, c in enumerate(comments)]
    return {
        "review_type": review_type,
        "target": change_id,
        "reviewer_vendor": "ocr",
        "findings": findings,
    }


class OcrRunError(RuntimeError):
    """Raised when ``ocr review`` fails to produce a readable result."""


def run_ocr(cwd: Path, *, timeout_seconds: int = 900) -> dict[str, Any]:
    """Run ``ocr review`` over *cwd* and return its parsed JSON result.

    Workspace mode by default (matches the diff every other vendor reviews
    from the packet, since OCR runs in the same worktree before any round's
    fix commit). ``REVIEW_BASE_REF``/``REVIEW_HEAD_REF`` env vars switch to
    range mode when both are set.
    """
    # A directory, not mkstemp: mkstemp pre-creates the file itself, which
    # would defeat the "ocr never wrote it" check below (the file would
    # already exist, just empty, on every failure path).
    tmp_dir = tempfile.mkdtemp(prefix="ocr-review-")
    output_path = Path(tmp_dir) / "result.json"
    try:
        cmd = [
            "ocr", "review", "--format", "json", "--audience", "agent",
            "--output", str(output_path),
        ]
        from_ref = os.environ.get("REVIEW_BASE_REF")
        to_ref = os.environ.get("REVIEW_HEAD_REF")
        if from_ref and to_ref:
            cmd.extend(["--from", from_ref, "--to", to_ref])
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_seconds,
            cwd=str(cwd),
        )
        if result.returncode != 0 and not output_path.exists():
            raise OcrRunError(
                f"ocr review exited {result.returncode}: {result.stderr[:500]}"
            )
        text = output_path.read_text(encoding="utf-8")
        if not text.strip():
            raise OcrRunError("ocr review produced an empty output file")
        return json.loads(text)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--change-id", default=os.environ.get("OCR_CHANGE_ID", "unknown"),
    )
    parser.add_argument(
        "--review-type", default=os.environ.get("OCR_REVIEW_TYPE", "implementation"),
    )
    parser.add_argument("--repo", default=".")
    args = parser.parse_args(argv)

    # Consume and discard stdin (the review packet body): OCR reads the diff
    # itself and does not need a pre-built packet.
    if not sys.stdin.isatty():
        try:
            sys.stdin.read()
        except (OSError, ValueError):
            pass

    if shutil.which("ocr") is None:
        print("ocr: binary not found on PATH", file=sys.stderr)
        return 2
    if not ocr_configured():
        print(
            "ocr: no LLM endpoint configured "
            "(OCR_LLM_URL/OCR_LLM_TOKEN unset, no ~/.opencodereview/config.json)",
            file=sys.stderr,
        )
        return 2

    try:
        ocr_result = run_ocr(Path(args.repo))
    except (subprocess.TimeoutExpired, OcrRunError, json.JSONDecodeError, OSError) as exc:
        print(f"ocr: review failed: {exc}", file=sys.stderr)
        return 1

    payload = rewrite_output(
        ocr_result, change_id=args.change_id, review_type=args.review_type,
    )
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
