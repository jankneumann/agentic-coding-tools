"""Tests for review_packet.py: selection, rule groups, checksum, overflow, ledger."""

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
from review_packet import (  # noqa: E402
    BUDGET_CHARS,
    PER_FILE_TOKEN_CEILING,
    build_review_packet,
    preview,
)
from review_rules import RuleConfig  # noqa: E402

CONTRACTS = change_dir(REPO_ROOT, "add-deterministic-review-preprocessing") / "contracts"
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


def _empty_rule_config() -> RuleConfig:
    """A rule config with no generated-path/include/exclude noise, so tests
    built around synthetic single-file diffs are not affected by this
    repo's own embedded default sidecar (e.g. its skills/**/*.py rule)."""
    return RuleConfig(default_rules=[("**/*", "Generic review checklist.")])


def _build(
    tmp_path: Path,
    *,
    artifacts: Path | None = None,
    worktree: Path | None = None,
    round_num: int = 1,
    last_fix_diff: str | None = None,
    change_id: str = "demo-change",
    rule_config: RuleConfig | None = None,
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
        rule_config=rule_config if rule_config is not None else _empty_rule_config(),
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


def _artifacts_with_many_specs(tmp_path: Path, *, count: int, token: str) -> Path:
    """Many spec.md files, each near the 12K per-file spec-excerpt cap (so
    none is truncated by _spec_entries itself), summing well over budget."""
    artifacts = tmp_path / "change"
    (artifacts / "specs" / "skill-workflow").mkdir(parents=True)
    (artifacts / "specs" / "skill-workflow" / "spec.md").write_text(
        "# Spec\n\nA requirement about widget assembly.\n", encoding="utf-8",
    )
    for i in range(count):
        d = artifacts / "specs" / f"cap-{i:03d}"
        d.mkdir(parents=True)
        (d / "spec.md").write_text(token * 400, encoding="utf-8")  # ~10.8K chars
    return artifacts


def test_overflow_drops_spec_excerpts_first(tmp_path: Path) -> None:
    """A diff well under the per-file ceiling, but enough spec files alone
    to push the packet over budget: specs drop first, diff survives
    untouched."""
    spec_token = "SPEC_EXCERPT_UNIQUE_TOKEN"
    artifacts = _artifacts_with_many_specs(tmp_path, count=40, token=spec_token)
    small_diff = "diff --git a/small.py b/small.py\n@@ -1,1 +1,2 @@\n keep\n+added\n"
    _body_path, meta, body = _build(
        tmp_path,
        artifacts=artifacts,
        round_num=2,
        last_fix_diff=small_diff,
    )
    assert meta["tools_overflow"] is True
    assert "specs/skill-workflow/spec.md" in body
    assert spec_token not in body
    assert "diff --git" in body
    assert "added" in body  # diff was NOT truncated
    assert "Read" in body or "Grep" in body
    assert len(body) <= BUDGET_CHARS
    assert meta["selection"]["truncated"] == []


def test_overflow_truncates_diff_after_specs_dropped(tmp_path: Path) -> None:
    """Three files, each individually under the per-file token ceiling, whose
    combined size still exceeds the packet budget after specs are dropped:
    exercises the character-level diff-truncation ladder, not the per-file
    too_large gate."""
    assert PER_FILE_TOKEN_CEILING * 4 > 150_000, "fixture assumes ceiling > 150K chars"
    artifacts = _artifacts(tmp_path, spec_body="SPEC_BODY_" + ("x" * 8_000))

    def _file_diff(name: str, marker: str) -> str:
        # Each file's own tokens (~50K) stay under PER_FILE_TOKEN_CEILING
        # (64K), so no file is excluded as too_large individually; three of
        # them combined (~600K chars) still exceeds BUDGET_CHARS (320K).
        return (
            f"diff --git a/{name} b/{name}\n@@ -1,1 +1,2 @@\n keep\n+"
            + (marker * 200_000)
            + "\n"
        )

    huge_diff = (
        _file_diff("huge1.py", "Z") + _file_diff("huge2.py", "Y") + _file_diff("huge3.py", "X")
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
    # Truncation is a hard char-boundary cut on the concatenated diff, so
    # the last file (huge3.py / "X") is the one guaranteed to lose content.
    assert body.count("X") < 200_000
    # Every selected file made it into the packet's selection.excluded/
    # selected accounting — none was too_large individually.
    assert {e["reason"] for e in meta["selection"]["excluded"]} <= {"none"}
    assert len(meta["selection"]["selected"]) == 3
    # At least one file lost content to the character-budget ladder.
    assert meta["selection"]["truncated"]


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


# ---------------------------------------------------------------------------
# Selection and rule groups in the packet
# ---------------------------------------------------------------------------


def test_generated_path_excluded_from_diff_body(tmp_path: Path) -> None:
    diff = (
        "diff --git a/src/keep.py b/src/keep.py\n@@ -1,1 +1,2 @@\n a\n+b\n"
        "diff --git a/apps/x/package-lock.json b/apps/x/package-lock.json\n"
        "@@ -1,1 +1,1 @@\n-old\n+new\n"
    )
    config = RuleConfig(
        generated_paths=["**/package-lock.json"],
        default_rules=[("**/*", "Generic rule.")],
    )
    _body_path, meta, body = _build(
        tmp_path, round_num=2, last_fix_diff=diff, rule_config=config,
    )
    assert "src/keep.py" in body
    assert "package-lock.json" not in body
    excluded = meta["selection"]["excluded"]
    assert len(excluded) == 1
    assert excluded[0]["path"] == "apps/x/package-lock.json"
    assert excluded[0]["reason"] == "generated_path"
    selected = meta["selection"]["selected"]
    assert len(selected) == 1
    assert selected[0]["path"] == "src/keep.py"


def test_no_file_is_dropped_without_a_reason(tmp_path: Path) -> None:
    diff = (
        "diff --git a/a.py b/a.py\n@@ -1,1 +1,2 @@\n x\n+y\n"
        "diff --git a/assets/logo.png b/assets/logo.png\n"
        "index e69de29..a1b2c3d 100644\n"
        "Binary files a/assets/logo.png and b/assets/logo.png differ\n"
    )
    _body_path, meta, _body = _build(tmp_path, round_num=2, last_fix_diff=diff)
    total = len(meta["selection"]["selected"]) + len(meta["selection"]["excluded"])
    assert total == 2
    for entry in meta["selection"]["excluded"]:
        assert entry["reason"]


def test_rule_groups_render_once_per_group(tmp_path: Path) -> None:
    diff = (
        "diff --git a/a.py b/a.py\n@@ -1,1 +1,2 @@\n x\n+y\n"
        "diff --git a/b.py b/b.py\n@@ -1,1 +1,2 @@\n x\n+z\n"
    )
    config = RuleConfig(default_rules=[("**/*.py", "UNIQUE_PY_RULE_TEXT")])
    _body_path, meta, body = _build(
        tmp_path, round_num=2, last_fix_diff=diff, rule_config=config,
    )
    assert body.count("UNIQUE_PY_RULE_TEXT") == 1
    assert len(meta["rule_groups"]) == 1
    assert set(meta["rule_groups"][0]["files"]) == {"a.py", "b.py"}
    assert meta["rule_groups"][0]["source"] == "default"


def test_project_rule_group_source_recorded(tmp_path: Path) -> None:
    diff = "diff --git a/special.py b/special.py\n@@ -1,1 +1,2 @@\n x\n+y\n"
    config = RuleConfig(
        project_rules=[("**/special.py", "Special rule.")],
        default_rules=[("**/*.py", "Default rule.")],
    )
    _body_path, meta, _body = _build(
        tmp_path, round_num=2, last_fix_diff=diff, rule_config=config,
    )
    assert meta["rule_groups"][0]["source"] == "project"


def test_no_rule_file_still_builds_from_embedded_default(tmp_path: Path) -> None:
    """rule_config=None falls through to review_rules.load_config, which
    always has the embedded default sidecar."""
    diff = "diff --git a/skills/foo/scripts/bar.py b/skills/foo/scripts/bar.py\n@@ -1,1 +1,2 @@\n x\n+y\n"
    artifacts = _artifacts(tmp_path)
    worktree = tmp_path / "wt"
    worktree.mkdir()
    output_dir = tmp_path / "round"
    output_dir.mkdir()
    body_path, meta = build_review_packet(
        change_id="demo",
        round_num=2,
        artifacts_dir=artifacts,
        worktree_path=worktree,
        output_dir=output_dir,
        last_fix_diff=diff,
    )
    assert body_path.exists()
    assert len(meta["rule_groups"]) >= 1


# ---------------------------------------------------------------------------
# Preview parity
# ---------------------------------------------------------------------------


def test_preview_matches_build_selection_decisions(tmp_path: Path) -> None:
    diff = (
        "diff --git a/src/keep.py b/src/keep.py\n@@ -1,1 +1,2 @@\n a\n+b\n"
        "diff --git a/vendor/lib.lock b/vendor/lib.lock\n@@ -1,1 +1,1 @@\n-o\n+n\n"
    )
    config = RuleConfig(
        generated_paths=["**/*.lock"], default_rules=[("**/*", "Generic rule.")],
    )
    artifacts = _artifacts(tmp_path)
    worktree = tmp_path / "wt"
    worktree.mkdir()

    preview_decisions = preview(
        artifacts_dir=artifacts, worktree_path=worktree, round_num=2,
        last_fix_diff=diff, rule_config=config,
    )

    output_dir = tmp_path / "round"
    output_dir.mkdir()
    _body_path, meta = build_review_packet(
        change_id="demo", round_num=2, artifacts_dir=artifacts,
        worktree_path=worktree, output_dir=output_dir, last_fix_diff=diff,
        rule_config=config,
    )

    preview_as_dicts = [d.to_dict() for d in preview_decisions]
    build_as_dicts = meta["selection"]["selected"] + meta["selection"]["excluded"]
    # Compare as sets of tuples since ordering conventions may differ
    # between preview's raw list and the packet's selected/excluded split.
    preview_set = {tuple(sorted(d.items())) for d in preview_as_dicts}
    build_set = {tuple(sorted(d.items())) for d in build_as_dicts}
    assert preview_set == build_set


def test_preview_creates_no_round_directory_files(tmp_path: Path) -> None:
    artifacts = _artifacts(tmp_path)
    worktree = tmp_path / "wt"
    worktree.mkdir()
    cache_dir = artifacts / ".review-cache"

    preview(
        artifacts_dir=artifacts, worktree_path=worktree, round_num=1,
        rule_config=_empty_rule_config(),
    )
    assert not cache_dir.exists()
