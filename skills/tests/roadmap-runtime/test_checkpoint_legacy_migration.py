"""Legacy checkpoint migration and the persisted attempt shape (dispatch-contract
Launch Token Digest, Host-Portable Attempt Isolation; design D6, D7).

The archived roadmap checkpoint carries raw launch tokens, so sources are copied
into ``tmp_path`` at test time and never committed as fixtures. The live checkpoint
may already be digest-only; re-saving it must leave every digest unchanged.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Iterator

import pytest

from checkpoint import CheckpointManager
from models import LEGACY_UNKNOWN_HOST, load_checkpoint, migrate_legacy_attempt

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "skills"))

_ARCHIVED = (
    _REPO_ROOT
    / "openspec/roadmaps/archive/2026-09-26-roadmap-supervisor-orchestration/checkpoint.json"
)
_LIVE = _REPO_ROOT / "openspec/roadmaps/multiplayer-collaboration/checkpoint.json"
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def _strings(value: Any) -> Iterator[str]:
    """Every persisted string except host handles, which are opaque identifiers
    the host assigns (one archived handle is a host-local path), not isolation."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            if key != "handle":
                yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def _assert_portable(attempts: list[dict[str, Any]]) -> None:
    for attempt in attempts:
        assert "launch_token" not in attempt
        assert _DIGEST.fullmatch(attempt["launch_digest"])
        assert set(attempt["isolation"]) == {"mode", "worktree_ref", "branch", "host_id"}
        for text in _strings(attempt):
            assert not text.startswith("/"), text
            assert not re.match(r"^[A-Za-z]:[\\/]", text), text


@pytest.mark.parametrize("source", [_ARCHIVED, _LIVE], ids=["archived", "live"])
def test_legacy_checkpoint_loads_and_the_next_save_drops_raw_tokens(
    source: Path, tmp_path: Path
) -> None:
    if not source.is_file():
        pytest.skip(f"{source.relative_to(_REPO_ROOT)} is not present on this branch")
    raw = json.loads(source.read_text())
    source_attempts = raw.get("dispatch_attempts", [])
    tokens = {
        attempt["dispatch_id"]: attempt["launch_token"]
        for attempt in source_attempts
        if "launch_token" in attempt
    }
    # An already-migrated source carries digests only; they must survive unchanged.
    digests = {
        attempt["dispatch_id"]: attempt["launch_digest"]
        for attempt in source_attempts
        if "launch_digest" in attempt and "launch_token" not in attempt
    }
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    shutil.copy2(source, workspace / "checkpoint.json")

    manager = CheckpointManager(workspace, _REPO_ROOT)
    checkpoint = manager.load()
    manager.save(checkpoint)

    saved = json.loads((workspace / "checkpoint.json").read_text())
    text = (workspace / "checkpoint.json").read_text()
    assert "launch_token" not in text
    for token in tokens.values():
        assert token not in text
    for attempt in saved["dispatch_attempts"]:
        dispatch_id = attempt["dispatch_id"]
        if dispatch_id in tokens:
            expected = "sha256:" + hashlib.sha256(tokens[dispatch_id].encode()).hexdigest()
        else:
            expected = digests[dispatch_id]
        assert attempt["launch_digest"] == expected
    _assert_portable(saved["dispatch_attempts"])
    # The saved file reloads against the published schema.
    assert len(load_checkpoint(workspace / "checkpoint.json", _REPO_ROOT).dispatch_attempts) == len(
        source_attempts
    )


def test_source_checkpoints_are_not_modified(tmp_path: Path) -> None:
    for source in (_ARCHIVED, _LIVE):
        if source.is_file():
            before = source.read_bytes()
            workspace = tmp_path / source.parent.name
            workspace.mkdir()
            shutil.copy2(source, workspace / "checkpoint.json")
            CheckpointManager(workspace, _REPO_ROOT).load()
            assert source.read_bytes() == before


def _legacy_attempt(worktree: str) -> dict[str, Any]:
    return {
        "dispatch_id": "batch-0123456789abcdef01234567:ri-01:attempt-1",
        "item_id": "ri-01",
        "change_id": "change-alpha",
        "phase": "autopilot",
        "attempt": 1,
        "status": "prepared",
        "prepared_at": "2026-09-01T00:00:00+00:00",
        "launch_token": "legacy-launch-token-0001",
        "launch_marker_path": ".supervised-dispatch/change-alpha/ri-01-attempt-1.marker",
        "lease_generation": 1,
        "launch_history": [],
        "scope": {"proof": "serial_indeterminate", "write_allow": [], "lock_keys": []},
        "isolation": {"mode": "managed_worktree", "worktree_path": worktree, "branch": "openspec/change-alpha"},
        "context": {},
    }


def test_inside_the_managed_root_becomes_a_relative_ref(tmp_path: Path) -> None:
    managed = tmp_path / ".git-worktrees"
    migrated = migrate_legacy_attempt(
        _legacy_attempt(str(managed / "change-alpha")),
        repo_root=tmp_path,
        managed_root=managed,
        host_id="host-a",
    )
    assert migrated["isolation"] == {
        "mode": "managed_worktree",
        "worktree_ref": "change-alpha",
        "branch": "openspec/change-alpha",
        "host_id": "host-a",
    }
    assert "needs_rebind" not in migrated
    assert migrated["launch_digest"] == (
        "sha256:" + hashlib.sha256(b"legacy-launch-token-0001").hexdigest()
    )


def test_outside_every_root_marks_needs_rebind(tmp_path: Path) -> None:
    migrated = migrate_legacy_attempt(
        _legacy_attempt("/elsewhere/change-alpha"),
        repo_root=tmp_path,
        managed_root=tmp_path / ".git-worktrees",
        host_id="host-a",
    )
    assert migrated["needs_rebind"] is True
    assert migrated["isolation"]["worktree_ref"] is None
    assert migrated["isolation"]["host_id"] == LEGACY_UNKNOWN_HOST


def test_prepared_batch_persists_no_raw_token_and_no_absolute_path(tmp_path: Path) -> None:
    import yaml
    from models import Effort, ItemStatus, Roadmap, RoadmapItem
    # Appended (not prepended) so the roadmap-runtime modules keep precedence.
    sys.path.append(str(_REPO_ROOT / "skills" / "autopilot-roadmap" / "scripts"))
    from orchestrator import prepare_delegated_batch
    from shared import dispatch_contract

    repo = tmp_path / "repo"
    schemas = repo / "openspec" / "schemas"
    schemas.mkdir(parents=True)
    for name in ("roadmap.schema.json", "checkpoint.schema.json"):
        shutil.copy2(_REPO_ROOT / "openspec" / "schemas" / name, schemas / name)
    workspace = repo / "roadmap"
    workspace.mkdir()
    roadmap = Roadmap(
        schema_version=1,
        roadmap_id="roadmap-legacy",
        source_proposal="proposal.md",
        items=[RoadmapItem("ri-01", "Alpha", ItemStatus.APPROVED, 1, Effort.S, change_id="change-alpha")],
    )
    (workspace / "roadmap.yaml").write_text(yaml.safe_dump(roadmap.to_dict(), sort_keys=False))
    managed = repo / ".git-worktrees"
    prepared = prepare_delegated_batch(
        workspace,
        repo_root=repo,
        isolation_resolver=lambda item: {
            "mode": "managed_worktree",
            "worktree_path": str(managed / item.change_id),
            "branch": f"openspec/{item.change_id}",
        },
        managed_root=managed,
        host_id="host-a",
    )
    assert prepared["requests"]
    saved = json.loads((workspace / "checkpoint.json").read_text())
    _assert_portable(saved["dispatch_attempts"])
    digests = {a["dispatch_id"]: a["launch_digest"] for a in saved["dispatch_attempts"]}
    for request in prepared["requests"]:
        assert dispatch_contract.verify_launch_token(
            request["launch_token"], digests[request["dispatch_id"]]
        )
