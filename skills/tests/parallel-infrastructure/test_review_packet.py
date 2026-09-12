"""Tests for review_packet.py: packed review input, checksum, overflow, ledger."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from openspec_paths import change_dir, repo_root_from

REPO_ROOT = repo_root_from(__file__, 3)
SCRIPTS = REPO_ROOT / "skills" / "parallel-infrastructure" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from review_findings_schema import prompt_contract, prompt_contract_block  # noqa: E402
from review_packet import BUDGET_CHARS, build_review_packet  # noqa: E402

CONTRACTS = change_dir(REPO_ROOT, "pack-and-parallelize-vendor-review") / "contracts"
PACKET_SCHEMA = json.loads((CONTRACTS / "review-packet.schema.json").read_text())


def _git(repo: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def _repo_with_committed_diff(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "--initial-branch=main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "src.py").write_text("hello\n", encoding="utf-8")
    _git(repo, "add", "src.py")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "checkout", "-qb", "feature")
    (repo / "src.py").write_text("hello\nworld\n", encoding="utf-8")
    _git(repo, "add", "src.py")
    _git(repo, "commit", "-qm", "change")
    return repo


def _artifacts(tmp_path: Path, *, spec_body: str | None = None) -> Path:
    artifacts = tmp_path / "change"
    artifacts.mkdir()
    spec_dir = artifacts / "specs" / "skill-workflow"
    spec_dir.mkdir(parents=True)
    (spec_dir / "spec.md").write_text(
        spec_body or "# Spec\n\nA requirement about widget assembly.\n",
        encoding="utf-8",
    )
    return artifacts


def _write_ledger(artifacts: Path, items: list[dict]) -> None:
    ledger_dir = artifacts / ".review-ledger"
    ledger_dir.mkdir()
    payload = {
        "schema_version": 1,
        "change_id": "demo-change",
        "items": items,
    }
    (ledger_dir / "ledger.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


def _build(
    tmp_path: Path,
    *,
    artifacts: Path | None = None,
    worktree: Path | None = None,
    round_num: int = 1,
    last_fix_diff: str | None = None,
    change_id: str = "demo-change",
) -> tuple[Path, dict, str]:
    artifacts = artifacts if artifacts is not None else _artifacts(tmp_path)
    worktree = worktree if worktree is not None else tmp_path / "empty-wt"
    worktree.mkdir(parents=True, exist_ok=True)
    output_dir = tmp_path / "round"
    output_dir.mkdir(exist_ok=True)
    body_path, meta = build_review_packet(
        change_id=change_id,
        round_num=round_num,
        artifacts_dir=artifacts,
        worktree_path=worktree,
        output_dir=output_dir,
        last_fix_diff=last_fix_diff,
    )
    body = body_path.read_text(encoding="utf-8")
    return body_path, meta, body


def test_packet_includes_diff_hunk_or_empty_marker(tmp_path: Path) -> None:
    repo = _repo_with_committed_diff(tmp_path)
    artifacts = _artifacts(tmp_path)
    _body_path, _meta, body = _build(tmp_path, artifacts=artifacts, worktree=repo)
    has_hunk = "diff --git" in body or "@@" in body
    has_empty = "empty-diff" in body.lower()
    assert has_hunk or has_empty


def test_packet_includes_prompt_contract_required_fields(tmp_path: Path) -> None:
    _body_path, _meta, body = _build(
        tmp_path,
        round_num=2,
        last_fix_diff="diff --git a/src.py b/src.py\n@@ -1,1 +1,2 @@\n hello\n+world\n",
    )
    required, _enums = prompt_contract()
    contract = prompt_contract_block()
    assert contract in body
    for field in required:
        assert field in body


def test_missing_ledger_still_builds(tmp_path: Path) -> None:
    artifacts = _artifacts(tmp_path)
    assert not (artifacts / ".review-ledger").exists()
    body_path, meta, body = _build(
        tmp_path,
        artifacts=artifacts,
        round_num=2,
        last_fix_diff="diff --git a/x b/x\n@@ -0,0 +1 @@\n+ok\n",
    )
    assert body_path.exists()
    assert meta["includes_ledger"] is False
    assert "Open ledger" not in body
    Draft202012Validator(PACKET_SCHEMA).validate(meta)


def test_open_ledger_items_appear(tmp_path: Path) -> None:
    artifacts = _artifacts(tmp_path)
    _write_ledger(
        artifacts,
        [
            {
                "id": 1,
                "status": "open",
                "description": "Missing null check in parse_line",
            },
            {
                "id": 2,
                "status": "retired",
                "description": "Already gone",
            },
        ],
    )
    _body_path, meta, body = _build(
        tmp_path,
        artifacts=artifacts,
        round_num=2,
        last_fix_diff="diff --git a/x b/x\n@@ -0,0 +1 @@\n+ok\n",
    )
    assert meta["includes_ledger"] is True
    assert "Missing null check in parse_line" in body
    assert "Already gone" not in body


def test_round_1_uses_full_git_diff(tmp_path: Path) -> None:
    repo = _repo_with_committed_diff(tmp_path)
    artifacts = _artifacts(tmp_path)
    _body_path, meta, body = _build(
        tmp_path,
        artifacts=artifacts,
        worktree=repo,
        round_num=1,
        last_fix_diff="THIS_SHOULD_NOT_APPEAR_IN_ROUND_1",
    )
    assert "THIS_SHOULD_NOT_APPEAR_IN_ROUND_1" not in body
    assert "world" in body
    assert "diff --git" in body or "@@" in body
    assert meta.get("diff_kind") == "full"


def test_round_n_uses_last_fix_diff_when_provided(tmp_path: Path) -> None:
    repo = _repo_with_committed_diff(tmp_path)
    artifacts = _artifacts(tmp_path)
    last_fix = (
        "diff --git a/fix.py b/fix.py\n"
        "@@ -1,1 +1,2 @@\n"
        " base\n"
        "+LAST_FIX_ONLY_TOKEN\n"
    )
    _body_path, meta, body = _build(
        tmp_path,
        artifacts=artifacts,
        worktree=repo,
        round_num=2,
        last_fix_diff=last_fix,
    )
    assert "LAST_FIX_ONLY_TOKEN" in body
    assert "world" not in body
    assert meta.get("diff_kind") == "last_fix"


def test_overflow_drops_spec_excerpts_first(tmp_path: Path) -> None:
    spec_token = "SPEC_EXCERPT_UNIQUE_TOKEN"
    artifacts = _artifacts(tmp_path, spec_body=spec_token * 800)
    huge_diff = (
        "diff --git a/big.py b/big.py\n@@ -1,1 +1,2 @@\n keep\n+"
        + ("D" * 310_000)
        + "\n"
    )
    _body_path, meta, body = _build(
        tmp_path,
        artifacts=artifacts,
        round_num=2,
        last_fix_diff=huge_diff,
    )
    assert meta["tools_overflow"] is True
    assert "specs/skill-workflow/spec.md" in body
    assert spec_token not in body
    assert "diff --git" in body
    assert "Read" in body or "Grep" in body
    assert len(body) <= BUDGET_CHARS


def test_overflow_truncates_diff_after_specs_dropped(tmp_path: Path) -> None:
    artifacts = _artifacts(tmp_path, spec_body="SPEC_BODY_" + ("x" * 8_000))
    huge_diff = (
        "diff --git a/huge.py b/huge.py\n@@ -1,1 +1,2 @@\n keep\n+"
        + ("Z" * 400_000)
        + "\n"
    )
    _body_path, meta, body = _build(
        tmp_path,
        artifacts=artifacts,
        round_num=2,
        last_fix_diff=huge_diff,
    )
    assert meta["tools_overflow"] is True
    assert "SPEC_BODY_" not in body
    assert "specs/skill-workflow/spec.md" in body
    assert "diff --git" in body or "@@" in body
    assert "truncated" in body.lower()
    assert len(body) <= BUDGET_CHARS
    assert body.count("Z") < 400_000


def test_sha256_sidecar_written_next_to_body(tmp_path: Path) -> None:
    body_path, meta, body = _build(
        tmp_path,
        round_num=2,
        last_fix_diff="diff --git a/x b/x\n@@ -0,0 +1 @@\n+ok\n",
    )
    sidecar = body_path.with_suffix(".meta.json")
    if not sidecar.exists():
        sidecar = body_path.parent / "review-packet.meta.json"
    assert sidecar.exists()
    on_disk = json.loads(sidecar.read_text(encoding="utf-8"))
    expected = hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert meta["sha256"] == expected
    assert on_disk["sha256"] == expected
    assert meta["char_length"] == len(body)
    assert meta["budget_chars"] == 320000
    assert meta["body_path"]
    Draft202012Validator(PACKET_SCHEMA).validate(on_disk)


def test_under_budget_prompt_says_complete_do_not_explore(tmp_path: Path) -> None:
    _body_path, meta, body = _build(
        tmp_path,
        round_num=2,
        last_fix_diff="diff --git a/x b/x\n@@ -0,0 +1 @@\n+ok\n",
    )
    assert meta["tools_overflow"] is False
    assert meta["char_length"] <= BUDGET_CHARS
    lowered = body.lower()
    assert "complete" in lowered
    assert "not to explore" in lowered or "do not explore" in lowered
