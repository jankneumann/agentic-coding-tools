#!/usr/bin/env python3
"""Read-only reader for open `needs-user` entries in a change's choices ledger.

Design F3 (openspec/changes/followup-add-decision-choices-ledger/design.md):
this is the one reader both `validate-feature` and `cleanup-feature` shell out
to, so the `needs-user` filter and the least-confident-first ordering live in
one tested place instead of two SKILL.md snippets.

Contract: print the open `needs-user` entries, nothing else, and exit 0.
The reader does not distinguish "no ledger" from "a ledger with nothing
open" — it is silent for both in text mode (and prints `[]` for both in
json mode), deliberately, so a caller can pipe it without branching. Callers
that need to tell the two cases apart do it themselves by testing for
`openspec/changes/<id>/choices.json` before invoking this script (F3).

Never raises. Opens no file for writing — the SKILL.md invariant "nothing
else in scripts/ opens a file for writing" holds for this module too.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import choices_ledger  # noqa: E402


def load_needs_user_entries(repo_root: Path, change_id: str) -> list[dict[str, Any]]:
    """Return the change's `needs-user` entries, least-confident-first.

    Returns `[]` when the ledger is absent, unreadable, or has no
    `needs-user` entries. Prints exactly one warning to stderr when the
    ledger file exists but is not valid JSON; never raises.
    """
    ledger_path = repo_root / "openspec" / "changes" / change_id / "choices.json"
    if not ledger_path.exists():
        return []

    try:
        doc = json.loads(ledger_path.read_text())
        entries = doc.get("entries") if isinstance(doc, dict) else None
        if not isinstance(entries, list):
            # Covers both a missing `entries` key and a present-but-null (or
            # otherwise non-list) one: `doc.get("entries", [])` only falls
            # back to `[]` when the key is *absent* — `{"entries": null}` has
            # the key, so `.get` returns `None` and a bare `for e in entries`
            # would raise `TypeError: 'NoneType' object is not iterable`.
            entries = []
        needs_user_entries = [
            e for e in entries if isinstance(e, dict) and e.get("verdict") == "needs-user"
        ]
        # rank_entries -> _rank_key looks up `entry.get("confidence", "")` in
        # a dict; a list- or dict-valued `confidence` field (malformed but
        # schema-adjacent input) makes that lookup raise
        # `TypeError: unhashable type`. The whole load path — parse, filter,
        # rank — must be total per F3, so it is wrapped as one unit below.
        return choices_ledger.rank_entries(needs_user_entries)
    except Exception as exc:  # noqa: BLE001 - F3: never raise, warn once, return [].
        print(f"needs_user: WARNING - could not read {ledger_path}: {exc}", file=sys.stderr)
        return []


def _format_text_line(entry: dict[str, Any]) -> str:
    stable_id = str(entry.get("stable_id") or "")[:12]
    confidence = entry.get("confidence", "")
    choice = entry.get("choice", "")
    return f"{stable_id}  {confidence}  {choice}"


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        description="List a change's open needs-user choices-ledger entries (read-only)."
    )
    p.add_argument("--change-id", required=True)
    p.add_argument("--repo-root", default=".")
    p.add_argument("--format", choices=["text", "json"], default="text")
    args = p.parse_args(argv)

    entries = load_needs_user_entries(Path(args.repo_root).resolve(), args.change_id)

    if args.format == "json":
        print(json.dumps(entries))
    else:
        for entry in entries:
            print(_format_text_line(entry))

    return 0  # Never blocks (F3 / D6 posture).


def _cli() -> int:
    return main()


if __name__ == "__main__":
    raise SystemExit(_cli())
