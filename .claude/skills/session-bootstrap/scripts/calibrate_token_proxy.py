#!/usr/bin/env python3
"""Calibrate CHAR_PER_TOKEN against real Claude Code transcripts.

Compares the proxy estimator in check_compact.py against the authoritative
Anthropic SDK ``messages.count_tokens`` for one or more transcripts, and
prints a recommended CHAR_PER_TOKEN value to use as the proxy divisor.

Why this matters: the Stop hook's threshold detection runs the proxy on
every Stop event when ANTHROPIC_API_KEY is unset (or when the SDK cache
has not refreshed). If CHAR_PER_TOKEN is mistuned, the threshold trip
misfires — too low and we compact prematurely; too high and we run out
of context before compacting.

Usage:
    # Calibrate against the most recently modified transcript in
    # ~/.claude/projects/<project-hash>/.
    ANTHROPIC_API_KEY=sk-... python3 calibrate_token_proxy.py

    # Calibrate against an explicit list of transcripts.
    python3 calibrate_token_proxy.py /path/to/session-a.jsonl /path/to/session-b.jsonl

    # Override the model (default claude-opus-4-7).
    ANTHROPIC_MODEL=claude-sonnet-4-6 python3 calibrate_token_proxy.py

Output example:
    transcript=session-a.jsonl
      messages   : 318
      total chars: 254,910
      proxy /4   : 63,727 tokens
      sdk        : 71,420 tokens
      ratio      : 3.57 chars/token  (proxy is under by 10.8%)

    Recommendation: CHAR_PER_TOKEN = 3.5  (averaged 3.57 over 1 transcript)

Caveats:
  * The SDK count includes the system prompt and tool definitions which
    are NOT in the transcript file. Expect the proxy to be systematically
    low by ~3000-8000 tokens regardless of CHAR_PER_TOKEN tuning.
  * Char counts vary by content type (code vs. prose). Calibrate against
    a representative mix.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from statistics import mean
from typing import Any

# Make the hook module importable so we reuse its proxy logic verbatim.
_HOOKS_DIR = Path(__file__).resolve().parent / "hooks"
sys.path.insert(0, str(_HOOKS_DIR))
import check_compact  # noqa: E402  type: ignore


def _discover_newest_transcript() -> Path | None:
    base = Path.home() / ".claude" / "projects"
    if not base.exists():
        return None
    candidates = list(base.glob("*/*.jsonl"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _load_messages(transcript: Path) -> list[dict[str, Any]]:
    return check_compact._transcript_messages(transcript)


def _total_chars(messages: list[dict[str, Any]]) -> int:
    """Same accounting as _proxy_estimate but without the //4."""
    total = 0
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total += check_compact._extract_block_chars(block)
    return total


def _sdk_count(
    messages: list[dict[str, Any]], model: str,
) -> int:
    import anthropic  # type: ignore

    client = anthropic.Anthropic()
    response = client.messages.count_tokens(model=model, messages=messages)
    return int(response.input_tokens)


def _calibrate_one(transcript: Path, model: str) -> dict[str, Any] | None:
    if not transcript.exists():
        print(f"skip {transcript}: not found", file=sys.stderr)
        return None
    messages = _load_messages(transcript)
    if not messages:
        print(f"skip {transcript}: no messages", file=sys.stderr)
        return None
    total_chars = _total_chars(messages)
    proxy_tokens = total_chars // check_compact.CHAR_PER_TOKEN

    try:
        sdk_tokens = _sdk_count(messages, model)
    except Exception as exc:  # noqa: BLE001
        print(f"skip {transcript}: SDK call failed ({exc})", file=sys.stderr)
        return None

    ratio = total_chars / sdk_tokens if sdk_tokens else 0.0
    proxy_drift_pct = (
        (proxy_tokens - sdk_tokens) * 100 / sdk_tokens if sdk_tokens else 0.0
    )

    return {
        "transcript": transcript.name,
        "messages": len(messages),
        "total_chars": total_chars,
        "proxy_tokens": proxy_tokens,
        "sdk_tokens": sdk_tokens,
        "ratio": ratio,
        "proxy_drift_pct": proxy_drift_pct,
    }


def _print_result(r: dict[str, Any]) -> None:
    print(f"transcript={r['transcript']}")
    print(f"  messages   : {r['messages']}")
    print(f"  total chars: {r['total_chars']:,}")
    print(f"  proxy /{check_compact.CHAR_PER_TOKEN}   : "
          f"{r['proxy_tokens']:,} tokens")
    print(f"  sdk        : {r['sdk_tokens']:,} tokens")
    direction = "under" if r["proxy_drift_pct"] < 0 else "over"
    print(f"  ratio      : {r['ratio']:.2f} chars/token  "
          f"(proxy is {direction} by {abs(r['proxy_drift_pct']):.1f}%)")
    print()


def _recommend(results: list[dict[str, Any]]) -> None:
    if not results:
        print("No usable results. Cannot recommend.", file=sys.stderr)
        return
    avg_ratio = mean(r["ratio"] for r in results)
    rounded = round(avg_ratio * 2) / 2  # nearest 0.5
    print(
        f"Recommendation: CHAR_PER_TOKEN = {rounded}  "
        f"(averaged {avg_ratio:.2f} over {len(results)} transcript"
        f"{'s' if len(results) != 1 else ''})"
    )
    if rounded != check_compact.CHAR_PER_TOKEN:
        print(
            f"\nCurrent value in check_compact.py is "
            f"{check_compact.CHAR_PER_TOKEN}. To apply the recommendation, "
            f"edit CHAR_PER_TOKEN at the top of:"
        )
        print(f"  {Path(check_compact.__file__).resolve()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "transcripts", nargs="*", type=Path,
        help="Transcript JSONL paths (default: newest in ~/.claude/projects)",
    )
    parser.add_argument(
        "--model", default=os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7"),
        help="Model passed to count_tokens (default: claude-opus-4-7)",
    )
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ANTHROPIC_API_KEY is not set. The SDK call requires a valid key.",
            file=sys.stderr,
        )
        return 2

    transcripts: list[Path] = list(args.transcripts)
    if not transcripts:
        newest = _discover_newest_transcript()
        if newest is None:
            print("No transcripts found in ~/.claude/projects.",
                  file=sys.stderr)
            return 2
        transcripts = [newest]
        print(f"Auto-discovered: {newest}\n")

    results: list[dict[str, Any]] = []
    for t in transcripts:
        r = _calibrate_one(t, args.model)
        if r:
            _print_result(r)
            results.append(r)

    _recommend(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
