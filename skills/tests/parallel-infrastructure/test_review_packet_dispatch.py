"""Packet-plus-concurrency: ledger-absent packet still dispatches in parallel.

Hermetic: stub vendor CLIs only. No live vendor APIs.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from openspec_paths import change_dir, repo_root_from

REPO_ROOT = repo_root_from(__file__, 3)
SCRIPTS = REPO_ROOT / "skills" / "parallel-infrastructure" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from review_dispatcher import (  # noqa: E402
    CliConfig,
    CliVendorAdapter,
    ModeConfig,
    ReviewOrchestrator,
)
from review_findings_schema import prompt_contract, prompt_contract_block  # noqa: E402
from review_packet import build_review_packet  # noqa: E402

CONTRACTS = change_dir(REPO_ROOT, "pack-and-parallelize-vendor-review") / "contracts"
PACKET_SCHEMA = json.loads((CONTRACTS / "review-packet.schema.json").read_text())

SPEC_TOKEN = "PACKET_PLUS_CONCURRENCY_SPEC_TOKEN"
DIFF_TOKEN = "PACKET_PLUS_CONCURRENCY_DIFF_TOKEN"
_STUB_SLEEP_SECONDS = 2.0
_CONCURRENT_WALL_LIMIT_SECONDS = 3.0

VALID_FINDINGS_JSON = json.dumps({
    "review_type": "plan",
    "target": "test-feature",
    "reviewer_vendor": "test",
    "findings": [
        {
            "id": 1,
            "type": "security",
            "criticality": "high",
            "description": "test",
            "disposition": "fix",
            "axis": "security",
            "severity": "critical",
        },
    ],
})


@dataclass(frozen=True)
class PacketPlusConcurrency:
    cwd: Path
    body_path: Path
    meta: dict
    body: str
    orch: ReviewOrchestrator
    stamp_codex: Path
    stamp_grok: Path


def _artifacts(tmp_path: Path) -> Path:
    artifacts = tmp_path / "change"
    spec_dir = artifacts / "specs" / "skill-workflow"
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text(
        f"# Spec\n\nA requirement about {SPEC_TOKEN}.\n",
        encoding="utf-8",
    )
    return artifacts


def _adapter(agent_id: str, vendor: str, command: str) -> CliVendorAdapter:
    return CliVendorAdapter(
        agent_id=agent_id,
        vendor=vendor,
        cli_config=CliConfig(
            command=command,
            dispatch_modes={
                "review": ModeConfig(args=["exec", "-s", "read-only"]),
            },
            model_flag="-m",
        ),
    )


def _write_sleep_stub(path: Path, stamp_path: Path, sleep_seconds: float) -> None:
    """Fake vendor CLI: record start/end/prompt, sleep, print valid findings."""
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys, time\n"
        "from pathlib import Path\n"
        f"stamp = Path({str(stamp_path)!r})\n"
        "prompt = sys.argv[-1] if len(sys.argv) > 1 else (sys.stdin.read() or '')\n"
        "stamp.write_text(json.dumps({\n"
        '    "start": time.time(),\n'
        '    "cwd": os.getcwd(),\n'
        '    "pid": os.getpid(),\n'
        '    "prompt": prompt,\n'
        "}))\n"
        f"time.sleep({sleep_seconds!r})\n"
        "data = json.loads(stamp.read_text())\n"
        'data["end"] = time.time()\n'
        "stamp.write_text(json.dumps(data))\n"
        f"print({VALID_FINDINGS_JSON!r})\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _intervals_overlap(a: dict[str, float], b: dict[str, float]) -> bool:
    return a["start"] < b["end"] and b["start"] < a["end"]


@pytest.fixture
def packet_plus_concurrency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> PacketPlusConcurrency:
    """Ledger-absent packet plus two 2s stub vendor CLIs on PATH."""
    artifacts = _artifacts(tmp_path)
    assert not (artifacts / ".review-ledger").exists()
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    output_dir = tmp_path / "round-1"
    last_fix = (
        "diff --git a/src.py b/src.py\n"
        "@@ -1,1 +1,2 @@\n"
        " hello\n"
        f"+{DIFF_TOKEN}\n"
    )
    body_path, meta = build_review_packet(
        change_id="demo-change",
        round_num=2,
        artifacts_dir=artifacts,
        worktree_path=worktree,
        output_dir=output_dir,
        last_fix_diff=last_fix,
    )
    body = body_path.read_text(encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stamp_codex = tmp_path / "codex-stamp.json"
    stamp_grok = tmp_path / "grok-stamp.json"
    _write_sleep_stub(bin_dir / "review-stub-codex", stamp_codex, _STUB_SLEEP_SECONDS)
    _write_sleep_stub(bin_dir / "review-stub-grok", stamp_grok, _STUB_SLEEP_SECONDS)
    monkeypatch.setenv(
        "PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
    )

    orch = ReviewOrchestrator({
        "codex-local": _adapter("codex-local", "codex", "review-stub-codex"),
        "grok-local": _adapter("grok-local", "grok", "review-stub-grok"),
    })
    return PacketPlusConcurrency(
        cwd=tmp_path,
        body_path=body_path,
        meta=meta,
        body=body,
        orch=orch,
        stamp_codex=stamp_codex,
        stamp_grok=stamp_grok,
    )


def test_missing_ledger_packet_still_builds_and_dispatch_proceeds(
    packet_plus_concurrency: PacketPlusConcurrency,
) -> None:
    env = packet_plus_concurrency
    assert env.body_path.exists()
    assert env.meta["includes_ledger"] is False
    assert "Open ledger" not in env.body
    has_hunk = "diff --git" in env.body or "@@" in env.body
    has_empty = "empty-diff" in env.body.lower()
    assert has_hunk or has_empty
    assert DIFF_TOKEN in env.body
    assert SPEC_TOKEN in env.body
    assert "specs/skill-workflow/spec.md" in env.body
    contract = prompt_contract_block()
    assert contract in env.body
    required, _enums = prompt_contract()
    for field in required:
        assert field in env.body
    Draft202012Validator(PACKET_SCHEMA).validate(env.meta)

    started = time.monotonic()
    results = env.orch.dispatch_and_wait(
        review_type="plan",
        dispatch_mode="review",
        prompt=env.body,
        cwd=env.cwd,
        timeout_seconds=15,
        packet_path=env.body_path,
    )
    elapsed = time.monotonic() - started

    assert elapsed < _CONCURRENT_WALL_LIMIT_SECONDS, (
        f"concurrent dispatch took {elapsed:.2f}s; sequential 2s stubs "
        "would take >=4s, overlap must finish in <3s"
    )
    assert elapsed < 4.0
    assert len(results) == 2
    assert all(r.success for r in results)

    a = json.loads(env.stamp_codex.read_text(encoding="utf-8"))
    b = json.loads(env.stamp_grok.read_text(encoding="utf-8"))
    assert _intervals_overlap(a, b), (
        f"subprocess lifetimes did not overlap: codex={a} grok={b}"
    )
    assert a["cwd"] == str(env.cwd)
    assert b["cwd"] == str(env.cwd)
    assert a["prompt"] == env.body
    assert b["prompt"] == env.body
    assert SPEC_TOKEN in a["prompt"]
    assert DIFF_TOKEN in a["prompt"]
