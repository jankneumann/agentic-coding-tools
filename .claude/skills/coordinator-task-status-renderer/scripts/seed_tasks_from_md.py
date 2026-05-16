#!/usr/bin/env python3
"""Seed coordinator issues from openspec/changes/<id>/tasks.md.

Reads hand-authored task lines, builds a dependency DAG from
``**Dependencies**:`` annotations, topologically sorts task keys, and POSTs each
new task via ``coordination_bridge.try_issue_create`` with labels
``["change:<id>", "task:<key>"]``. Idempotent on the
``(change:<id>, task:<key>)`` label pair.

Contract: openspec/changes/add-coordinator-task-status-renderer/contracts/README.md
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# Allow importing coordination_bridge regardless of cwd.
_SKILL_ROOT = Path(__file__).resolve().parents[2]
_BRIDGE_DIR = _SKILL_ROOT / "coordination-bridge" / "scripts"
if str(_BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(_BRIDGE_DIR))

import coordination_bridge  # noqa: E402

# Match the renderer's marker name exactly.
_GEN_BEGIN = "<!-- GENERATED: begin coordinator:tasks-status -->"
_GEN_END = "<!-- GENERATED: end coordinator:tasks-status -->"
_GEN_BEGIN_RE = re.compile(re.escape(_GEN_BEGIN))
_GEN_END_RE = re.compile(re.escape(_GEN_END))

# Task-line shape: optional leading whitespace, then "- [ ]" or "- [x]", then a
# token (digits or letters) optionally with dots and trailing letters, then a
# separator and title.
_TASK_LINE_RE = re.compile(
    r"^\s*-\s+\[[ xX]\]\s+(?P<key>[A-Za-z0-9][A-Za-z0-9.]*)[\s\.:]+(?P<title>.+?)\s*$"
)
_DEPS_LINE_RE = re.compile(
    r"^\s*\*\*Dependencies\*\*\s*:\s*(?P<deps>.+?)\s*$", re.IGNORECASE
)

_PAGE_CAP = 100

# Reject change-ids that could escape openspec/changes/<id>/ via path
# traversal or absolute paths.
_CHANGE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def _sanitize_change_id(change_id: str) -> str:
    if not _CHANGE_ID_RE.match(change_id or ""):
        raise ValueError(
            f"invalid change-id {change_id!r}: must match {_CHANGE_ID_RE.pattern}"
        )
    return change_id


def _strip_managed_block(md: str) -> str:
    """Remove the renderer's managed block (markers and content) from md."""
    lines = md.split("\n")
    out: list[str] = []
    inside = False
    for line in lines:
        if _GEN_BEGIN_RE.search(line):
            inside = True
            continue
        if _GEN_END_RE.search(line):
            inside = False
            continue
        if inside:
            continue
        out.append(line)
    return "\n".join(out)


def _parse_tasks(
    md: str,
) -> tuple[list[tuple[str, str]], dict[str, list[str]]]:
    """Return (tasks_in_order, deps_map) parsed from hand-authored regions.

    ``tasks_in_order`` is a list of (key, title) tuples in file order.
    ``deps_map`` maps task_key -> list of upstream task_keys (verbatim).
    """
    cleaned = _strip_managed_block(md)
    tasks: list[tuple[str, str]] = []
    deps: dict[str, list[str]] = {}
    seen_keys: set[str] = set()
    current_key: str | None = None
    for raw in cleaned.split("\n"):
        m = _TASK_LINE_RE.match(raw)
        if m:
            key = m.group("key")
            title = m.group("title").strip()
            # Skip "Phase 1 — ..." style or other non-task patterns: require key
            # to start with digit or single uppercase letter+digit.
            if not _is_plausible_task_key(key):
                current_key = None
                continue
            if key in seen_keys:
                # Duplicate definition in hand-authored region: keep the first.
                current_key = key
                continue
            seen_keys.add(key)
            tasks.append((key, title))
            deps[key] = []
            current_key = key
            continue
        d = _DEPS_LINE_RE.match(raw)
        if d and current_key:
            raw_deps = d.group("deps").strip()
            if raw_deps.lower() in ("none", "n/a", "-"):
                continue
            parts = [p.strip().rstrip(".,") for p in raw_deps.split(",")]
            deps[current_key] = [p for p in parts if p]
    return tasks, deps


def _is_plausible_task_key(key: str) -> bool:
    if not key:
        return False
    if key[0].isdigit():
        return True
    # Letter prefix accepted only if followed by a digit (e.g. T1).
    return key[0].isalpha() and any(c.isdigit() for c in key)


def _detect_cycles(
    deps: dict[str, list[str]], known_keys: set[str]
) -> list[list[str]]:
    """Detect cycles. Forward refs (deps not in known_keys) are dropped."""
    graph: dict[str, list[str]] = {k: [] for k in known_keys}
    for k, upstreams in deps.items():
        if k not in known_keys:
            continue
        for u in upstreams:
            if u in known_keys:
                graph[k].append(u)
    WHITE, GRAY, BLACK = 0, 1, 2
    color = dict.fromkeys(graph, WHITE)
    parent: dict[str, str | None] = dict.fromkeys(graph, None)
    cycles: list[list[str]] = []

    def _walk(node: str) -> None:
        stack: list[tuple[str, int]] = [(node, 0)]
        color[node] = GRAY
        while stack:
            cur, idx = stack[-1]
            neighbors = graph[cur]
            if idx >= len(neighbors):
                color[cur] = BLACK
                stack.pop()
                continue
            stack[-1] = (cur, idx + 1)
            nxt = neighbors[idx]
            if color[nxt] == WHITE:
                parent[nxt] = cur
                color[nxt] = GRAY
                stack.append((nxt, 0))
            elif color[nxt] == GRAY:
                # Reconstruct cycle nxt -> ... -> cur -> nxt
                cyc = [nxt, cur]
                p = parent[cur]
                while p is not None and p != nxt:
                    cyc.append(p)
                    p = parent[p]
                if p == nxt:
                    cyc.append(nxt)
                cycles.append(cyc[::-1])

    for n in graph:
        if color[n] == WHITE:
            _walk(n)
    return cycles


def _topological_order(
    tasks: list[tuple[str, str]], deps: dict[str, list[str]]
) -> list[str]:
    """Kahn's algorithm. Preserves file-order tiebreak."""
    keys = [k for k, _ in tasks]
    indeg = dict.fromkeys(keys, 0)
    children: dict[str, list[str]] = {k: [] for k in keys}
    key_set = set(keys)
    for k in keys:
        for u in deps.get(k, []):
            if u in key_set:
                indeg[k] += 1
                children[u].append(k)
    queue = [k for k in keys if indeg[k] == 0]
    result: list[str] = []
    while queue:
        node = queue.pop(0)
        result.append(node)
        for child in children[node]:
            indeg[child] -= 1
            if indeg[child] == 0:
                queue.append(child)
    return result


def _resolve_repo_root(arg: str | None) -> Path:
    if arg:
        return Path(arg).resolve()
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd()


def _existing_issues_by_task_key(
    change_id: str,
) -> tuple[dict[str, str], str]:
    """Returns (task_key -> uuid, status).

    status is one of:
      - "ok"          — listing succeeded; the mapping is complete.
      - "unreachable" — coordinator did not respond ok; caller should
                        degrade gracefully (skip seeding, exit 0).
      - "truncated"   — coordinator returned the page cap; the mapping
                        may be incomplete and seeding could produce
                        duplicates. Caller MUST treat as a hard error.
    """
    result = coordination_bridge.try_issue_list(
        labels=[f"change:{change_id}"], limit=_PAGE_CAP
    )
    status = result.get("status", "skipped")
    if status not in ("ok", "success"):
        return {}, "unreachable"
    issues = result.get("data", {}).get("issues") or result.get("issues") or []
    if isinstance(issues, list) and len(issues) >= _PAGE_CAP:
        print(
            "ERROR: coordinator returned page cap ("
            f"{_PAGE_CAP}) for change {change_id!r}; refusing to seed "
            "(silent truncation risk).",
            file=sys.stderr,
        )
        return {}, "truncated"
    out: dict[str, str] = {}
    for iss in issues:
        labels = iss.get("labels") or []
        for lbl in labels:
            if isinstance(lbl, str) and lbl.startswith("task:"):
                k = lbl[len("task:") :]
                uid = iss.get("id") or iss.get("issue_id")
                if uid:
                    out[k] = str(uid)
                break
    return out, "ok"


def seed(
    change_id: str,
    repo_root: Path,
    *,
    dry_run: bool = False,
) -> int:
    try:
        change_id = _sanitize_change_id(change_id)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    tasks_path = repo_root / "openspec" / "changes" / change_id / "tasks.md"
    try:
        md = tasks_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"ERROR: tasks.md not found at {tasks_path}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"ERROR: cannot read {tasks_path}: {e}", file=sys.stderr)
        return 1

    tasks, deps = _parse_tasks(md)
    if not tasks:
        print(f"WARN: no tasks parsed from {tasks_path}", file=sys.stderr)
        print(f"seeded {change_id} created=0 existing=0", file=sys.stdout)
        return 0

    known = {k for k, _ in tasks}
    cycles = _detect_cycles(deps, known)
    if cycles:
        for cyc in cycles:
            print(
                f"ERROR: dependency cycle detected: {' -> '.join(cyc)}",
                file=sys.stderr,
            )
        return 1

    order = _topological_order(tasks, deps)
    titles = dict(tasks)

    if dry_run:
        for k in order:
            up_keys = [u for u in deps.get(k, []) if u in known]
            print(
                f"would-create {k} title={titles[k]!r} depends_on={up_keys}",
                file=sys.stdout,
            )
        print(f"seeded {change_id} created=0 existing=0 (dry-run)", file=sys.stdout)
        return 0

    existing, list_status = _existing_issues_by_task_key(change_id)
    if list_status == "truncated":
        # Page cap hit — the existing-issues map may be incomplete, so
        # idempotency cannot be guaranteed. Refuse to seed.
        print(
            f"seeded {change_id} created=0 existing=0 (aborted: truncated)",
            file=sys.stdout,
        )
        return 1
    if list_status == "unreachable":
        print(
            f"WARN: coordinator unreachable; cannot seed {change_id}",
            file=sys.stderr,
        )
        print(f"seeded {change_id} created=0 existing=0 (skipped)", file=sys.stdout)
        return 0

    created = 0
    skipped_existing = 0
    key_to_uuid: dict[str, str] = dict(existing)
    for k in order:
        if k in existing:
            skipped_existing += 1
            print(f"exists {k} {existing[k]}", file=sys.stdout)
            continue
        upstream_keys = [u for u in deps.get(k, []) if u in known]
        upstream_uuids: list[str] = []
        for u in upstream_keys:
            if u in key_to_uuid:
                upstream_uuids.append(key_to_uuid[u])
            else:
                # Forward ref impossible because we walk in topo order, but
                # guard anyway.
                print(
                    f"WARN: upstream {u} for {k} has no uuid yet; dropping",
                    file=sys.stderr,
                )
        payload: dict[str, Any] = {
            "title": titles[k],
            "issue_type": "task",
            "labels": [f"change:{change_id}", f"task:{k}"],
        }
        if upstream_uuids:
            payload["depends_on"] = upstream_uuids
        result = coordination_bridge.try_issue_create(**payload)
        status = result.get("status", "skipped")
        if status not in ("ok", "success"):
            print(
                f"WARN: coordinator unreachable mid-seed for {k}; "
                f"created={created} remaining={len(order) - (created + skipped_existing) - 1}",
                file=sys.stderr,
            )
            print(
                f"seeded {change_id} created={created} existing={skipped_existing} (partial)",
                file=sys.stdout,
            )
            return 0
        data = result.get("data") or result.get("issue") or {}
        uid = data.get("id") or data.get("issue_id") or ""
        if uid:
            key_to_uuid[k] = str(uid)
        created += 1
        print(f"created {k} {uid}", file=sys.stdout)

    print(
        f"seeded {change_id} created={created} existing={skipped_existing}",
        file=sys.stdout,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("change_id")
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    repo_root = _resolve_repo_root(args.repo_root)
    return seed(args.change_id, repo_root, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
