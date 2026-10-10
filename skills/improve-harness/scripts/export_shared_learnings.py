#!/usr/bin/env python3
"""Export capability-gap learnings to a tracked, repository-scoped JSONL file.

Opt-in only: ``<repo-root>/.agentic-toolkit/config.json`` must contain
``{"schema_version": 1, "shared_learnings": {"enabled": true}}``.  The export is
a one-way, allowlisted projection of the coordinator's episodic memory into
``<repo-root>/.agentic-toolkit/learnings.jsonl``; it is not a second store.

Privacy rules (defence in depth, in order of strength):

1. Allowlist: only ``event_type``, ``summary``, ``outcome``, ``lessons``,
   ``tags`` and ``created_at`` survive; ``details``, ``agent_id`` and
   ``session_id`` are dropped.
2. Tag namespace filter: only ``failure_type:``, ``capability_gap:``,
   ``affected_skill:``, ``severity:`` and ``source:`` tags survive.
3. Entries tagged ``source:transcript-mined`` are excluded outright.
4. Every exported string is passed through the ``session-log`` sanitizer.

Exit codes:
  0 — exported
  2 — refused: config absent, unreadable or sharing not enabled (nothing written)
  3 — memory returned no entries (coordinator down or empty); file left unchanged
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

TOOLKIT_DIR = ".agentic-toolkit"
CONFIG_NAME = "config.json"
LEARNINGS_NAME = "learnings.jsonl"

ALLOWED_FIELDS = ("event_type", "summary", "outcome", "lessons", "tags", "created_at")
ALLOWED_TAG_PREFIXES = (
    "failure_type:",
    "capability_gap:",
    "affected_skill:",
    "severity:",
    "source:",
)
EXCLUDED_SOURCE_TAG = "source:transcript-mined"


def sharing_enabled(repo_root: Path | str) -> tuple[bool, str]:
    """Return ``(enabled, reason)`` for the repository's opt-in config."""
    config = Path(repo_root) / TOOLKIT_DIR / CONFIG_NAME
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return False, f"{config} is absent"
    except (OSError, ValueError) as exc:
        return False, f"{config} is unreadable: {exc}"
    if not isinstance(data, dict):
        return False, f"{config} is not a JSON object"
    version = data.get("schema_version")
    if isinstance(version, bool) or version != 1:
        # Same rule as the stamp reader: an unknown schema is not an opt-in.
        return False, f"unsupported schema_version {version!r} in {config} (expected 1)"
    section = data.get("shared_learnings")
    if not isinstance(section, dict) or section.get("enabled") is not True:
        return False, f"shared_learnings.enabled is not true in {config}"
    return True, ""


def load_sanitizer() -> Callable[[str], tuple[str, list[dict[str, str]]]]:
    """Load ``sanitize()`` from the co-installed session-log skill.

    Resolved relative to this script (``<skill-base-dir>/../session-log``), so it
    works both in the toolkit source tree and in an installed agent mirror.
    """
    path = SCRIPT_DIR.parent.parent / "session-log" / "scripts" / "sanitize_session_log.py"
    spec = importlib.util.spec_from_file_location("_shared_learnings_sanitizer", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load sanitizer from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.sanitize  # type: ignore[no-any-return]


def _is_excluded_source(tag: str) -> bool:
    """True for ``source:transcript-mined`` tags, tolerant of case, padding and suffixes.

    Fail closed: a differently-cased or suffixed variant must not leak a
    transcript-derived entry into a tracked file.
    """
    return tag.strip().lower().startswith(EXCLUDED_SOURCE_TAG)


def _tag_value(tags: list[str], prefix: str) -> str:
    for tag in tags:
        if tag.startswith(prefix):
            return tag[len(prefix):]
    return "unknown"


def _sanitize_value(value: Any, sanitize: Callable[[str], tuple[str, Any]]) -> Any:
    if isinstance(value, str):
        return sanitize(value)[0]
    if isinstance(value, list):
        return [_sanitize_value(item, sanitize) for item in value]
    if isinstance(value, dict):
        return {k: _sanitize_value(v, sanitize) for k, v in value.items()}
    return value


def project_entries(
    entries: list[dict[str, Any]],
    sanitize: Callable[[str], tuple[str, Any]],
) -> list[dict[str, Any]]:
    """Project raw memory entries to sorted, deduplicated export records."""
    records: list[dict[str, Any]] = []
    for entry in entries:
        raw_tags = [t for t in entry.get("tags") or [] if isinstance(t, str)]
        if any(_is_excluded_source(t) for t in raw_tags):
            continue
        record: dict[str, Any] = {k: entry[k] for k in ALLOWED_FIELDS if k in entry}
        record["tags"] = sorted(t for t in raw_tags if t.startswith(ALLOWED_TAG_PREFIXES))
        records.append(_sanitize_value(record, sanitize))

    records.sort(key=lambda r: (str(r.get("created_at") or ""), str(r.get("summary") or "")))

    seen: set[tuple[str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for record in records:
        tags = record["tags"]
        key = (
            _tag_value(tags, "capability_gap:"),
            _tag_value(tags, "affected_skill:"),
            str(record.get("summary") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique


def render_jsonl(records: list[dict[str, Any]]) -> str:
    return "".join(
        json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
        for r in records
    )


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".learnings.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def export(
    repo_root: Path | str,
    *,
    time_window_days: int = 30,
    limit: int = 500,
) -> int:
    """Run the export; return the process exit code."""
    root = Path(repo_root)
    enabled, reason = sharing_enabled(root)
    if not enabled:
        print(f"export_shared_learnings: refusing to export: {reason}", file=sys.stderr)
        return 2

    import analyze_failures  # sibling script; same query path as the analysis

    entries = analyze_failures.query_memory(time_window_days=time_window_days, limit=limit)
    if not entries:
        print(
            "export_shared_learnings: memory returned no entries; "
            f"{TOOLKIT_DIR}/{LEARNINGS_NAME} left unchanged",
            file=sys.stderr,
        )
        return 3

    records = project_entries(entries, load_sanitizer())
    target = root / TOOLKIT_DIR / LEARNINGS_NAME
    _write_atomic(target, render_jsonl(records))
    print(f"Exported {len(records)} learning(s) to {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export capability-gap learnings to .agentic-toolkit/learnings.jsonl"
    )
    parser.add_argument("--repo-root", default=None, help="Repository root (default: cwd)")
    parser.add_argument("--time-window", type=int, default=30, help="Window in days (default: 30)")
    parser.add_argument("--limit", type=int, default=500, help="Maximum entries (default: 500)")
    args = parser.parse_args(argv)
    return export(
        args.repo_root or os.getcwd(),
        time_window_days=args.time_window,
        limit=args.limit,
    )


if __name__ == "__main__":
    sys.exit(main())
