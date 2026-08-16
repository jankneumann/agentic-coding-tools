#!/usr/bin/env python3
"""Deterministic state for the supervise cycle (supervisor roadmap ri-02).

Everything here answers a question with exactly one right answer — what is ready,
what did a previous cycle already surface, has anything changed, is this write
allowed. Sensing, ranking and sizing are model work performed by the *session*;
this module never calls an LLM and never reaches the network, mirroring the
host-assisted invariant enforced for ``autopilot-roadmap``.

The two idempotency mechanisms live here, because a scheduled cycle fires on
whatever tree it finds — including an unchanged one:

* **Cycle fingerprint** — a digest over the tracked tree content (excluding this
  skill's own ledger surface, so recording a cycle never changes the fingerprint),
  the active change-ids, and every ``(roadmap_id, item_id, status, change_id)``
  tuple. No wall clock and no mtime, so the same tree always fingerprints the
  same and a re-run is detectable.
* **Stub keys** — a stable identity per candidate-work stub, so a stub already
  surfaced by an earlier cycle (or already tracked as a change or roadmap item) is
  suppressed instead of re-proposed.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import posixpath
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

_RUNTIME = Path(__file__).resolve().parents[2] / "roadmap-runtime" / "scripts"


def _load_runtime_models():
    """Load roadmap-runtime's models under a collision-proof module name.

    Several skill trees ship a module literally named ``models`` and load it via
    ``sys.path`` insertion; whichever test collects first wins ``sys.modules``
    and every later bare ``import models`` silently gets the wrong file. Loading
    by explicit path under a unique name makes this module independent of
    collection order. models.py is self-contained (stdlib + yaml), so file-based
    loading is safe.
    """
    name = "supervise_roadmap_runtime_models"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _RUNTIME / "models.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_models = _load_runtime_models()
ItemStatus = _models.ItemStatus
Roadmap = _models.Roadmap
completed_external_refs = _models.completed_external_refs
load_all_roadmaps = _models.load_all_roadmaps

#: Tracked so a rehydrated session on another machine inherits what has already
#: been surfaced. The supervisor is a rehydratable role, not a resident process.
LEDGER_PATH = "openspec/supervise/cycle-ledger.json"

LEDGER_SCHEMA_VERSION = 1

#: Statuses in which an item no longer owns its change_id (mirrors decomposer's
#: ceded-status rule): a stub naming such a change is NOT considered a duplicate.
_CEDED = frozenset({ItemStatus.SKIPPED, ItemStatus.SUPERSEDED})

#: Path prefixes a supervise run may write. Everything else is implementation and
#: belongs to a dispatched write-capable worker.
_ALLOWED_WRITE_PREFIXES = (
    "openspec/roadmaps/",
    "openspec/changes/",
    "openspec/priorities/",
    "openspec/supervise/",
    "docs/proposals/",
)

#: Never writable by the supervisor even though they sit under an allowed prefix
#: — spec deltas and implementation live behind a worker's review, not a digest.
_FORBIDDEN_WRITE_SUFFIXES = ("/specs/",)


# --------------------------------------------------------------------------- #
# Git / repository facts
# --------------------------------------------------------------------------- #
def _tree_listing(repo_root: Path) -> str:
    """Blob digest + path for every tracked file at HEAD, minus this skill's own
    ledger surface, or "" when this is not a git checkout with commits.

    Deliberately NOT the HEAD commit sha. The ledger under ``openspec/supervise/``
    is tracked, so recording a cycle and committing it advances HEAD; a fingerprint
    over the commit sha would therefore differ on every cycle-after-a-cycle and the
    unchanged-tree early exit could never fire once a recorded ledger was pushed.
    Hashing the tree *content* excluding ``openspec/supervise/`` makes a
    ledger-only commit invisible to the fingerprint while any real change — source,
    roadmap, change directory — still lands in it.
    """
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "ls-tree", "-r", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return ""
    lines = [
        line
        for line in completed.stdout.splitlines()
        # ls-tree format: "<mode> <type> <object>\t<path>"
        if "\t" in line and not line.split("\t", 1)[1].startswith("openspec/supervise/")
    ]
    return "\n".join(sorted(lines))


def active_change_ids(repo_root: Path) -> set[str]:
    """Change-ids with a directory under ``openspec/changes/`` (excluding archive)."""
    changes = repo_root / "openspec" / "changes"
    if not changes.is_dir():
        return set()
    return {
        d.name for d in changes.iterdir() if d.is_dir() and d.name != "archive"
    }


def claimed_change_ids(roadmaps: dict[str, Roadmap]) -> set[str]:
    """Change-ids claimed by a roadmap item that has not ceded ownership."""
    return {
        item.change_id
        for roadmap in roadmaps.values()
        for item in roadmap.items
        if item.change_id and item.status not in _CEDED
    }


# --------------------------------------------------------------------------- #
# Cycle fingerprint
# --------------------------------------------------------------------------- #
def compute_fingerprint(repo_root: Path) -> str:
    """Digest of the repository state a discovery cycle would reason over.

    Deterministic by construction: every component is sorted, and none of them is
    a timestamp. Two cycles over an unchanged tree therefore produce the same
    fingerprint, which is what lets a scheduled re-run detect that it has nothing
    new to do rather than re-proposing the same work.

    The ledger surface is excluded from the tree component (see
    :func:`_tree_listing`), so the record-commit-push of cycle N does not make
    cycle N+1 look like a changed tree.
    """
    roadmaps = load_all_roadmaps(repo_root)
    tree = _tree_listing(repo_root)
    parts: list[str] = [f"tree:{hashlib.sha256(tree.encode('utf-8')).hexdigest()}"]
    parts += [f"change:{cid}" for cid in sorted(active_change_ids(repo_root))]
    parts += [
        f"item:{roadmap_id}:{item.item_id}:{item.status.value}:{item.change_id or ''}"
        for roadmap_id, roadmap in sorted(roadmaps.items())
        for item in sorted(roadmap.items, key=lambda i: i.item_id)
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Candidate-work stub identity
# --------------------------------------------------------------------------- #
def stub_key(stub: dict[str, Any]) -> str:
    """Stable identity for a candidate-work stub.

    Prefers ``suggested_change_id`` — two generators proposing the same change are
    proposing the same work, whatever their wording. Falls back to a digest of the
    provenance (source artifact + sorted finding ids), so a stub without a suggested
    id is still deduplicable against its own re-discovery.
    """
    suggested = (stub.get("suggested_change_id") or "").strip()
    if suggested:
        return f"change:{suggested}"
    provenance = stub.get("provenance") or {}
    source = str(provenance.get("source_artifact", "")).strip()
    findings = sorted(str(f) for f in provenance.get("finding_ids", []) or [])
    payload = json.dumps({"source": source, "findings": findings}, sort_keys=True)
    return "prov:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


@dataclass(frozen=True)
class DedupeResult:
    """Outcome of suppressing already-tracked or already-surfaced stubs."""

    fresh: list[dict[str, Any]] = field(default_factory=list)
    suppressed: list[tuple[dict[str, Any], str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fresh": self.fresh,
            "suppressed": [
                {"key": stub_key(stub), "reason": reason}
                for stub, reason in self.suppressed
            ],
            "fresh_count": len(self.fresh),
            "suppressed_count": len(self.suppressed),
        }


def dedupe_stubs(
    stubs: Sequence[dict[str, Any]],
    *,
    seen_keys: Iterable[str] = (),
    existing_change_ids: Iterable[str] = (),
    claimed_ids: Iterable[str] = (),
) -> DedupeResult:
    """Split *stubs* into genuinely new work and work already tracked.

    Four suppression reasons, in precedence order — the most specific first, so the
    digest can explain *why* something was dropped rather than silently shrinking:

    ``already-surfaced``  a previous cycle recorded this key
    ``change-exists``     a directory under openspec/changes/ already has this id
    ``roadmap-claimed``   a non-ceded roadmap item already owns this change_id
    ``duplicate-in-batch`` two generators produced the same key this cycle
    """
    seen = set(seen_keys)
    existing = set(existing_change_ids)
    claimed = set(claimed_ids)

    fresh: list[dict[str, Any]] = []
    suppressed: list[tuple[dict[str, Any], str]] = []
    batch_keys: set[str] = set()

    for stub in stubs:
        key = stub_key(stub)
        change_id = (stub.get("suggested_change_id") or "").strip()
        if key in seen:
            suppressed.append((stub, "already-surfaced"))
        elif change_id and change_id in existing:
            suppressed.append((stub, "change-exists"))
        elif change_id and change_id in claimed:
            suppressed.append((stub, "roadmap-claimed"))
        elif key in batch_keys:
            suppressed.append((stub, "duplicate-in-batch"))
        else:
            batch_keys.add(key)
            fresh.append(stub)
    return DedupeResult(fresh=fresh, suppressed=suppressed)


# --------------------------------------------------------------------------- #
# Ledger
# --------------------------------------------------------------------------- #
def load_ledger(repo_root: Path) -> dict[str, Any]:
    """Read the cycle ledger, returning an empty ledger when absent or malformed.

    A malformed ledger degrades to "nothing surfaced yet" rather than raising: the
    worst case is one cycle re-proposing work, which the operator sees and can
    dismiss. Failing the cycle outright would be the more damaging outcome.
    """
    empty = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "last_fingerprint": None,
        "seen_keys": [],
    }
    path = repo_root / LEDGER_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(empty)
    if not isinstance(data, dict):
        return dict(empty)
    # Shape-validate the fields this module consumes; a wrong-typed value is as
    # malformed as bad JSON. Without this, seen_keys="change:x" would be iterated
    # character-by-character by dedupe and permanently exploded into one-character
    # keys by record_cycle's set() merge — degradation to garbage, not to empty.
    keys = data.get("seen_keys")
    if not (isinstance(keys, list) and all(isinstance(k, str) for k in keys)):
        data["seen_keys"] = []
    fingerprint = data.get("last_fingerprint")
    if fingerprint is not None and not isinstance(fingerprint, str):
        data["last_fingerprint"] = None
    data.setdefault("schema_version", LEDGER_SCHEMA_VERSION)
    data.setdefault("last_fingerprint", None)
    data.setdefault("seen_keys", [])
    return data


def record_cycle(
    repo_root: Path, fingerprint: str, new_keys: Iterable[str]
) -> dict[str, Any]:
    """Merge *new_keys* into the ledger and stamp *fingerprint*.

    Keys are stored sorted and de-duplicated so a repeat run over an unchanged tree
    rewrites byte-identical content — no spurious repository diff.
    """
    ledger = load_ledger(repo_root)
    merged = sorted(set(ledger.get("seen_keys", [])) | set(new_keys))
    ledger.update(
        {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "last_fingerprint": fingerprint,
            "seen_keys": merged,
        }
    )
    path = repo_root / LEDGER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ledger


def is_unchanged(repo_root: Path, fingerprint: str | None = None) -> bool:
    """True when the tree has not changed since the last recorded cycle."""
    fp = fingerprint or compute_fingerprint(repo_root)
    return load_ledger(repo_root).get("last_fingerprint") == fp


# --------------------------------------------------------------------------- #
# Ready set across roadmaps
# --------------------------------------------------------------------------- #
def ready_across_roadmaps(repo_root: Path) -> dict[str, list[dict[str, Any]]]:
    """Ready items per roadmap, honoring in-roadmap deps and typed external edges.

    Mirrors the orchestrator's admission rule (approved / in_progress with every
    dependency completed) and adds ri-17's external resolution, so an item blocked
    only by another roadmap's prerequisite disappears from the ready set until that
    prerequisite completes — and reappears with no manual status edit.
    """
    roadmaps = load_all_roadmaps(repo_root)
    external_done = completed_external_refs(repo_root)
    out: dict[str, list[dict[str, Any]]] = {}
    for roadmap_id, roadmap in sorted(roadmaps.items()):
        # Delegate to the shared admission rule rather than hand-rolling a copy.
        # The first draft of this function WAS such a copy, and it had already
        # drifted: it admitted items carrying a superseded_by edge, which both
        # Roadmap.ready_items and the orchestrator exclude — the digest would
        # have listed work another roadmap's item owns as "Ready now".
        ready = roadmap.ready_items(external_done, include_in_progress=True)
        ready.sort(key=lambda i: (i.priority, i.item_id))
        out[roadmap_id] = [
            {
                "item_id": i.item_id,
                "title": i.title,
                "priority": i.priority,
                "effort": i.effort.value,
                "change_id": i.change_id,
            }
            for i in ready
        ]
    return out


# --------------------------------------------------------------------------- #
# Write-boundary audit
# --------------------------------------------------------------------------- #
def classify_write(path: str) -> str:
    """``allowed`` or ``forbidden`` for a repo-relative path a supervise run wrote.

    The supervisor archetype is ``write_capable: false``; this makes that structural
    rather than aspirational. Coordination artifacts are allowed; source code, specs,
    and everything outside the coordination surface are a worker's job.

    Paths are normalized before the prefix check, because the check is only as
    strong as its canonical form: the first draft used ``lstrip("./")`` (a
    character strip, not a prefix strip) and no ``..`` resolution, so both
    ``../openspec/roadmaps/x.yaml`` and
    ``openspec/roadmaps/../../agent-coordinator/src/x.py`` classified as allowed
    — a traversal that defeats the entire audit. Anything absolute, or escaping
    the repository root after normalization, is forbidden outright.
    """
    candidate = path.strip()
    if not candidate or candidate.startswith(("/", "\\")) or ":" in candidate.split("/", 1)[0]:
        return "forbidden"
    normalized = posixpath.normpath(candidate.replace("\\", "/"))
    if normalized == "." or normalized == ".." or normalized.startswith("../"):
        return "forbidden"
    if any(suffix in f"/{normalized}/" for suffix in _FORBIDDEN_WRITE_SUFFIXES):
        return "forbidden"
    return (
        "allowed"
        if normalized.startswith(_ALLOWED_WRITE_PREFIXES)
        else "forbidden"
    )


def audit_writes(paths: Iterable[str]) -> list[str]:
    """Repo-relative paths a supervise run must not have written (empty = clean)."""
    return sorted(p for p in paths if classify_write(p) == "forbidden")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _cmd_fingerprint(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    fp = compute_fingerprint(repo)
    print(json.dumps({"fingerprint": fp, "unchanged": is_unchanged(repo, fp)}, indent=2))
    return 0


def _cmd_ready(args: argparse.Namespace) -> int:
    print(json.dumps(ready_across_roadmaps(Path(args.repo_root).resolve()), indent=2))
    return 0


def _cmd_dedupe(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    raw = json.loads(Path(args.stubs).read_text(encoding="utf-8"))
    stubs = raw if isinstance(raw, list) else [raw]
    roadmaps = load_all_roadmaps(repo)
    result = dedupe_stubs(
        stubs,
        seen_keys=load_ledger(repo).get("seen_keys", []),
        existing_change_ids=active_change_ids(repo),
        claimed_ids=claimed_change_ids(roadmaps),
    )
    print(json.dumps(result.to_dict(), indent=2))
    return 0


def _cmd_record(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root).resolve()
    keys = json.loads(Path(args.keys).read_text(encoding="utf-8")) if args.keys else []
    ledger = record_cycle(repo, compute_fingerprint(repo), keys)
    print(json.dumps({"recorded": len(ledger["seen_keys"])}, indent=2))
    return 0


def _cmd_audit_writes(args: argparse.Namespace) -> int:
    violations = audit_writes(args.paths)
    print(json.dumps({"violations": violations}, indent=2))
    return 1 if violations else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic supervise-cycle state.")
    parser.add_argument("--repo-root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("fingerprint", help="Print the cycle fingerprint and whether it is unchanged.")
    sub.add_parser("ready", help="Print ready items per roadmap, resolving external edges.")

    p_dedupe = sub.add_parser("dedupe", help="Suppress already-tracked or already-surfaced stubs.")
    p_dedupe.add_argument("--stubs", required=True)

    p_record = sub.add_parser("record", help="Stamp the ledger with this cycle's fingerprint and keys.")
    p_record.add_argument("--keys", help="JSON file containing a list of stub keys.")

    p_audit = sub.add_parser("audit-writes", help="Fail if any path is outside the coordination surface.")
    p_audit.add_argument("paths", nargs="*")

    args = parser.parse_args(argv)
    return {
        "fingerprint": _cmd_fingerprint,
        "ready": _cmd_ready,
        "dedupe": _cmd_dedupe,
        "record": _cmd_record,
        "audit-writes": _cmd_audit_writes,
    }[args.command](args)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
