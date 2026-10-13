"""A committed checkpoint with live attempts passes the default secret scan
(dispatch-contract Launch Token Digest, D6; acceptance outcome 6).

``fixtures/landable-checkpoint.json`` was produced by :func:`build_landable_checkpoint`
(``prepare`` + ``child_start`` + ``acknowledge`` through the real execution
adapter). Regenerate it with::

    skills/.venv/bin/python skills/tests/roadmap-runtime/test_landable_checkpoint.py

The CI gitleaks job scans it with ``.gitleaks.toml`` (default rules, no allowlist
entry for it). Locally, these tests apply the default ``generic-api-key`` rule
(keyword pre-filter, regex, Shannon entropy > 3.5) to its text, and
``gitleaks detect --no-git --source skills/tests/roadmap-runtime/fixtures`` is
run when the binary is installed.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterator

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURE = Path(__file__).parent / "fixtures" / "landable-checkpoint.json"

# gitleaks' default generic-api-key rule (config/gitleaks.toml), translated to
# Python `re`: the case-insensitive group is spelled out because Python has no
# scoped `(?-i:...)`.
_KEYWORDS = ("access", "auth", "api", "credential", "creds", "key", "passw", "secret", "token")
_GENERIC_API_KEY = re.compile(
    r"""[\w.-]{0,50}?(?:[Aa][Cc][Cc][Ee][Ss][Ss]|[Aa][Uu][Tt][Hh]|[Aa]pi|API|"""
    r"""[Cc][Rr][Ee][Dd][Ee][Nn][Tt][Ii][Aa][Ll]|[Cc][Rr][Ee][Dd][Ss]|[Kk][Ee][Yy]|"""
    r"""[Pp][Aa][Ss][Ss][Ww](?:[Oo][Rr])?[Dd]|[Ss][Ee][Cc][Rr][Ee][Tt]|[Tt][Oo][Kk][Ee][Nn])"""
    r"""(?:[ \t\w.-]{0,20})[\s'"]{0,3}(?:=|>|:{1,3}=|\|\||:|=>|\?=|,)[\x60'"\s=]{0,5}"""
    r"""([\w.=-]{10,150}|[a-z0-9][a-z0-9+/]{11,}={0,3})(?:[\x60'"\s;]|\\[nr]|$)"""
)
_ENTROPY = 3.5


def _shannon(value: str) -> float:
    counts = {c: value.count(c) for c in set(value)}
    return -sum(n / len(value) * math.log2(n / len(value)) for n in counts.values())


def generic_api_key_findings(text: str) -> list[str]:
    if not any(keyword in text.lower() for keyword in _KEYWORDS):
        return []
    return [m.group(1) for m in _GENERIC_API_KEY.finditer(text) if _shannon(m.group(1)) > _ENTROPY]


def _scalar_fields(value: Any, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(child, (dict, list)):
                yield from _scalar_fields(child, f"{path}/{key}")
            else:
                yield key, f"{path}/{key}"
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _scalar_fields(child, f"{path}/{index}")


def build_landable_checkpoint(tmp: Path) -> dict[str, Any]:
    """Prepare a two-item batch and launch both up to acknowledgement."""
    import yaml

    for sub in ("supervise/scripts", "roadmap-runtime/scripts", "autopilot-roadmap/scripts"):
        path = str(_REPO_ROOT / "skills" / sub)
        if path not in sys.path:
            sys.path.append(path)
    from datetime import datetime, timezone

    import gate_router
    from execution import ExecutionAdapter
    from models import Effort, ItemStatus, Roadmap, RoadmapItem
    from shared.trust_posture import Gate

    repo = tmp / "repo"
    schemas = repo / "openspec" / "schemas"
    schemas.mkdir(parents=True)
    for name in ("roadmap.schema.json", "checkpoint.schema.json",
                 "supervisor-record.schema.json", "supervisor-record-mirror.schema.json"):
        shutil.copy2(_REPO_ROOT / "openspec" / "schemas" / name, schemas / name)
    workspace = repo / "openspec" / "roadmaps" / "landable"
    workspace.mkdir(parents=True)
    items = [
        RoadmapItem("ri-01", "Alpha", ItemStatus.APPROVED, 1, Effort.S, change_id="landable-alpha"),
        RoadmapItem("ri-02", "Beta", ItemStatus.APPROVED, 1, Effort.S, change_id="landable-beta"),
    ]
    roadmap = Roadmap(schema_version=1, roadmap_id="landable", source_proposal="proposal.md", items=items)
    (workspace / "roadmap.yaml").write_text(yaml.safe_dump(roadmap.to_dict(), sort_keys=False))
    for change in ("landable-alpha", "landable-beta"):
        package = {
            "package_id": f"wp-{change}", "task_type": "implementation", "description": "fixture",
            "depends_on": [], "priority": 1, "locks": {"files": [], "keys": [f"feature:{change}"]},
            "scope": {"write_allow": [f"src/{change}/**"], "read_allow": ["**"]},
            "worktree": {"name": change}, "timeout_minutes": 10, "retry_budget": 0, "min_trust_level": 0,
            "verification": {"tier_required": "C", "steps": [{
                "name": "fixture", "kind": "command", "command": "true",
                "evidence": {"artifacts": [], "result_keys": ["fixture"]}}]},
            "outputs": {"result_keys": ["fixture"]},
        }
        document = {"schema_version": 1, "feature": {"id": change, "plan_revision": 1},
                    "contracts": {"revision": 1, "openapi": {"primary": "contracts/openapi.yaml",
                                                             "files": ["contracts/openapi.yaml"]}},
                    "packages": [package]}
        target = repo / "openspec" / "changes" / change / "work-packages.yaml"
        target.parent.mkdir(parents=True)
        target.write_text(yaml.safe_dump(document, sort_keys=False))
    managed = repo / ".git-worktrees"
    for change in ("landable-alpha", "landable-beta"):
        (managed / change / ".git").mkdir(parents=True)

    def probe(_repo: Path) -> tuple[int, str]:
        return 0, json.dumps({
            "modes": {m: {"verified": ["claude_code", "codex"], "unverified": []}
                      for m in ("review", "alternative", "quick")},
            "probe_command": "python3 <skill-base-dir>/../parallel-infrastructure/scripts/review_dispatcher.py --check-vendors --json",
            "quorum_policy": {"environment": "host", "min_quorum": {"PLAN_REVIEW": 2, "IMPL_REVIEW": 2, "VAL_REVIEW": 2},
                              "policy_id": None, "sunset": None},
        })

    adapter = ExecutionAdapter(
        managed_worktree_root=managed,
        repo_root=repo,
        host_id="host-fixture-a",
        clock=lambda: datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc),
        branch_resolver=lambda path: f"openspec/{path.name}",
        commit_resolver=lambda _path: "a" * 40,
        liveness_probe=lambda _handle: "live",
        host_entry=lambda *_a: "entered",
        profile_probe=probe,
    )
    approved = gate_router.answer(Gate.ROADMAP_APPROVAL, workspace=workspace, repo_root=repo, approved=True,
                                  note="landable fixture")
    prepared = adapter.prepare(
        workspace, repo_root=repo,
        isolation_resolver=lambda item: {"mode": "managed_worktree",
                                         "worktree_path": str(managed / item.change_id),
                                         "branch": f"openspec/{item.change_id}"},
        roadmap_approval_ref=f"gate-decision:{approved.record['decision_id']}",
    )
    for index, request in enumerate(prepared["requests"], start=1):
        adapter.child_start(workspace, dispatch_id=request["dispatch_id"], launch_token=request["launch_token"],
                            lease_generation=1, owner_nonce=f"owner-nonce-fixture-{index:04d}")
        adapter.acknowledge(workspace, dispatch_id=request["dispatch_id"], lease_generation=1,
                            handle=f"task-fixture-{index:04d}")
    return json.loads((workspace / "checkpoint.json").read_text())


def _fixture() -> dict[str, Any]:
    return json.loads(_FIXTURE.read_text())


def test_the_fixture_has_live_attempts_and_no_raw_token() -> None:
    fixture = _fixture()
    attempts = fixture["dispatch_attempts"]
    assert len(attempts) == 2
    assert {a["status"] for a in attempts} == {"acknowledged"}
    text = _FIXTURE.read_text()
    assert "launch_token" not in text
    for attempt in attempts:
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", attempt["launch_digest"])


def test_the_fixture_loads_against_the_published_schema() -> None:
    from models import load_checkpoint

    assert len(load_checkpoint(_FIXTURE, _REPO_ROOT).dispatch_attempts) == 2


def test_no_scalar_field_name_matches_the_generic_api_key_keywords() -> None:
    """The rule's attack surface is ``<keyword...>: <scalar value>``. Array-valued
    fields (``scope.lock_keys``) cannot match its value character class, which
    the regex scan below proves on the whole text."""
    fixture = _fixture()
    offending = [
        path for key, path in _scalar_fields(fixture)
        if any(keyword in key.lower() for keyword in _KEYWORDS)
    ]
    # The one pre-existing keyword field: gate-decision `authorizing_disposition`
    # (it contains "auth"). Its value is the closed Disposition enum, whose
    # longest member stays below the rule's entropy threshold, so it can never
    # be a finding; every dispatch-attempt field is keyword-free.
    exempt = [path for path in offending if path.endswith("/authorizing_disposition")]
    for path in exempt:
        index = int(path.split("/")[2])
        assert fixture["gate_decisions"][index]["authorizing_disposition"] in {
            "auto", "block", "notify_with_timeout",
        }
    assert all(_shannon(v) <= _ENTROPY for v in ("auto", "block", "notify_with_timeout"))
    assert [path for path in offending if path not in exempt] == []
    assert not [p for p in offending if p.startswith("/dispatch_attempts")]


def test_the_default_generic_api_key_rule_finds_nothing() -> None:
    assert generic_api_key_findings(_FIXTURE.read_text()) == []


def test_the_rule_port_catches_a_raw_launch_token() -> None:
    """Calibration: the pre-dispatch-contract shape is a finding."""
    leaked = '{"launch_token": "ri01-DXYx307mS6iZ1WYxAerNYR8eQk2"}'
    assert generic_api_key_findings(leaked)


def test_gitleaks_config_has_no_entry_for_the_fixture() -> None:
    config = (_REPO_ROOT / ".gitleaks.toml").read_text()
    assert "landable-checkpoint" not in config
    assert "launch_digest" not in config


@pytest.mark.skipif(shutil.which("gitleaks") is None, reason="gitleaks binary not installed")
def test_gitleaks_scan_of_the_fixture_directory_is_clean() -> None:
    completed = subprocess.run(
        ["gitleaks", "detect", "--no-git", "--source", str(_FIXTURE.parent),
         "--config", str(_REPO_ROOT / ".gitleaks.toml"), "--no-banner"],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_the_builder_reproduces_the_fixture_shape(tmp_path: Path) -> None:
    built = build_landable_checkpoint(tmp_path)

    def shape(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: shape(v) for k, v in sorted(value.items())}
        if isinstance(value, list):
            return [shape(v) for v in value]
        return type(value).__name__

    fixture = _fixture()
    assert shape(built["dispatch_attempts"]) == shape(fixture["dispatch_attempts"])
    assert generic_api_key_findings(json.dumps(built, indent=2)) == []


if __name__ == "__main__":  # pragma: no cover - fixture regeneration
    import tempfile

    sys.path.insert(0, str(_REPO_ROOT / "skills"))
    with tempfile.TemporaryDirectory() as scratch:
        data = build_landable_checkpoint(Path(scratch))
    _FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    _FIXTURE.write_text(json.dumps(data, indent=2) + "\n")
    print(f"wrote {_FIXTURE}")
