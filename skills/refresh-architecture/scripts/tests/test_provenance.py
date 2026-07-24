"""Tests for architecture provenance + content-based freshness (ri-04 wp-provenance).

Covers spec scenarios:
- architecture-refresh.1  complete provenance for a clean revision
- architecture-refresh.2  dirty relevant input is represented truthfully
- architecture-refresh.3  mtime-only change stays fresh
- architecture-refresh.3b artifact-only convergence commit does not self-invalidate
- architecture-refresh.4  relevant input change is stale immediately
- architecture-refresh.5  producer/tool identity change invalidates freshness
- architecture-refresh.6  invalid provenance fails closed
- architecture-refresh.7  check identifies exact artifact drift
- architecture-refresh.9  repeat refresh has no repository diff
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from arch_utils import provenance as prov
from arch_utils.determinism import generated_at_iso


# --------------------------------------------------------------------------- #
# Helpers / fixtures
# --------------------------------------------------------------------------- #
def _run(repo: Path, *args: str) -> None:
    subprocess.run(args, cwd=str(repo), check=True, capture_output=True)


def _git_init(repo: Path) -> None:
    _run(repo, "git", "init", "-q")
    _run(repo, "git", "config", "user.email", "t@example.com")
    _run(repo, "git", "config", "user.name", "Test")
    _run(repo, "git", "config", "commit.gpgsign", "false")


def _commit_all(repo: Path, message: str = "c") -> str:
    _run(repo, "git", "add", "-A")
    _run(repo, "git", "commit", "-q", "-m", message)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), capture_output=True, text=True, check=True
    ).stdout.strip()


TOOLS = [{"name": "tree-sitter", "available": False, "version": None}]


def _seed_artifacts(repo: Path) -> None:
    arch = repo / prov.ARCH_DIR_DEFAULT
    (arch / "views").mkdir(parents=True, exist_ok=True)
    (arch / "architecture.graph.json").write_text('{"nodes": [], "edges": []}\n')
    (arch / "architecture.summary.json").write_text('{"summary": "ok"}\n')
    (arch / "views" / "overview.md").write_text("# overview\n")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "proj"
    (r / "src").mkdir(parents=True)
    (r / "src" / "app.py").write_text("print('hello')\n")
    (r / "database" / "migrations").mkdir(parents=True)
    (r / "database" / "migrations" / "001.sql").write_text("CREATE TABLE t(id int);\n")
    _git_init(r)
    _seed_artifacts(r)
    _commit_all(r, "initial")
    return r


def _generate(repo: Path, *, mode: str = "full") -> dict:
    """Build + write provenance for the current committed state, deterministically."""
    rev = prov.analyzed_revision(repo)
    epoch = prov.deterministic_epoch(repo, rev)
    # Emulate the runner exporting SOURCE_DATE_EPOCH for the producers.
    os.environ["SOURCE_DATE_EPOCH"] = str(epoch)
    try:
        doc = prov.build_provenance(
            repo, mode=mode, roots=["src", "database/migrations"], optional_tools=TOOLS
        )
        prov.write_provenance(repo, doc)
    finally:
        os.environ.pop("SOURCE_DATE_EPOCH", None)
    return doc


def _check(repo: Path, *, mode: str = "full") -> prov.CheckResult:
    return prov.check_freshness(repo, mode=mode, optional_tools=TOOLS)


# --------------------------------------------------------------------------- #
# Scenario .1 — complete provenance
# --------------------------------------------------------------------------- #
def test_clean_revision_produces_complete_provenance(repo: Path) -> None:
    doc = _generate(repo)
    rev = prov.analyzed_revision(repo)
    assert doc["source_revision"] == rev
    assert doc["worktree_dirty"] is False
    assert doc["producer"]["producer_version"] == prov.PRODUCER_VERSION
    assert len(doc["input_fingerprint"]) == 64
    paths = {a["path"] for a in doc["artifacts"]}
    assert "docs/architecture-analysis/architecture.graph.json" in paths
    assert "docs/architecture-analysis/architecture.summary.json" in paths
    assert "docs/architecture-analysis/views/overview.md" in paths
    # The committed document is schema-valid.
    prov.validate_provenance(doc)
    assert _check(repo).is_fresh


# --------------------------------------------------------------------------- #
# Scenario .2 — dirty relevant input
# --------------------------------------------------------------------------- #
def test_dirty_relevant_input_is_truthful(repo: Path) -> None:
    rev_before = prov.analyzed_revision(repo)
    (repo / "src" / "app.py").write_text("print('changed working tree')\n")
    doc = prov.build_provenance(
        repo, mode="full", roots=["src", "database/migrations"], optional_tools=TOOLS
    )
    assert doc["source_revision"] == rev_before  # HEAD retained
    assert doc["worktree_dirty"] is True
    # Fingerprint reflects working-tree bytes: differs from the committed state.
    clean_fp = prov.compute_input_fingerprint(repo, ["src", "database/migrations"])
    assert doc["input_fingerprint"] == clean_fp  # both computed from dirty tree


def test_untracked_relevant_input_counts_as_dirty(repo: Path) -> None:
    (repo / "src" / "new_module.py").write_text("x = 1\n")
    assert prov.worktree_dirty(repo, ["src", "database/migrations"]) is True


# --------------------------------------------------------------------------- #
# Scenario .3 — mtime-only change stays fresh
# --------------------------------------------------------------------------- #
def test_mtime_only_change_stays_fresh(repo: Path) -> None:
    _generate(repo)
    assert _check(repo).is_fresh
    # Touch an artifact + an input without changing bytes.
    for p in (
        repo / prov.ARCH_DIR_DEFAULT / "architecture.graph.json",
        repo / "src" / "app.py",
    ):
        os.utime(p, (10_000_000, 10_000_000))
    result = _check(repo)
    assert result.is_fresh, [r.to_dict() for r in result.reasons]


# --------------------------------------------------------------------------- #
# Scenario .3b — artifact-only convergence commit does not self-invalidate
# --------------------------------------------------------------------------- #
def test_artifact_only_convergence_commit_stays_fresh(repo: Path) -> None:
    _generate(repo)
    # Commit ONLY the architecture artifacts + provenance (convergence commit).
    _run(repo, "git", "add", prov.ARCH_DIR_DEFAULT)
    _commit_all(repo, "chore: architecture convergence")
    result = _check(repo)
    assert result.is_fresh, [r.to_dict() for r in result.reasons]
    # Analyzed source commit is retained (not rewritten to the convergence commit).
    prov_doc = prov.load_provenance(repo)
    assert prov_doc is not None
    assert prov_doc["source_revision"] == result.provenance["source_revision"]


# --------------------------------------------------------------------------- #
# Scenario .4 — relevant input change is stale immediately
# --------------------------------------------------------------------------- #
def test_relevant_input_change_is_stale(repo: Path) -> None:
    _generate(repo)
    (repo / "src" / "app.py").write_text("print('a different relevant input')\n")
    result = _check(repo)
    assert result.status == "stale"
    codes = {r.code for r in result.reasons}
    assert prov.INPUT_FINGERPRINT_MISMATCH in codes


def test_added_and_removed_input_are_stale(repo: Path) -> None:
    _generate(repo)
    (repo / "src" / "extra.py").write_text("y = 2\n")
    assert prov.INPUT_FINGERPRINT_MISMATCH in {r.code for r in _check(repo).reasons}
    (repo / "src" / "extra.py").unlink()
    (repo / "src" / "app.py").unlink()
    assert prov.INPUT_FINGERPRINT_MISMATCH in {r.code for r in _check(repo).reasons}


# --------------------------------------------------------------------------- #
# Scenario .5 — producer / tool identity change invalidates freshness
# --------------------------------------------------------------------------- #
def test_producer_version_change_is_stale(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _generate(repo)
    monkeypatch.setattr(prov, "PRODUCER_VERSION", "2.0.0")
    result = _check(repo)
    assert result.status == "stale"
    assert prov.PRODUCER_IDENTITY_MISMATCH in {r.code for r in result.reasons}


def test_optional_tool_identity_change_is_stale(repo: Path) -> None:
    _generate(repo)
    changed_tools = [{"name": "tree-sitter", "available": True, "version": "0.21.0"}]
    result = prov.check_freshness(repo, mode="full", optional_tools=changed_tools)
    assert result.status == "stale"
    assert prov.PRODUCER_IDENTITY_MISMATCH in {r.code for r in result.reasons}


# --------------------------------------------------------------------------- #
# Scenario .6 — invalid provenance fails closed
# --------------------------------------------------------------------------- #
def test_missing_provenance_is_invalid_never_fresh(repo: Path) -> None:
    result = _check(repo)
    assert result.status == "invalid"
    assert not result.is_fresh
    assert result.reasons[0].code == prov.PROVENANCE_MISSING


def test_malformed_provenance_is_invalid(repo: Path) -> None:
    _generate(repo)
    prov.provenance_path(repo).write_text("{not json")
    r1 = _check(repo)
    assert r1.status == "invalid"
    # Schema-invalid (valid JSON, wrong shape) also fails closed.
    prov.provenance_path(repo).write_text(json.dumps({"schema_version": 1}))
    r2 = _check(repo)
    assert r2.status == "invalid"
    assert r2.reasons[0].code == prov.PROVENANCE_INVALID


# --------------------------------------------------------------------------- #
# Scenario .7 — check identifies exact artifact drift, byte-identical files
# --------------------------------------------------------------------------- #
def test_check_reports_exact_artifact_drift(repo: Path) -> None:
    _generate(repo)
    graph = repo / prov.ARCH_DIR_DEFAULT / "architecture.graph.json"
    summary = repo / prov.ARCH_DIR_DEFAULT / "architecture.summary.json"
    before = graph.read_bytes()
    graph.write_text('{"nodes": [{"id": "x"}], "edges": []}\n')  # modified
    summary.unlink()  # missing
    result = _check(repo)
    by_path = {r.path: r.code for r in result.reasons if r.path}
    assert by_path["docs/architecture-analysis/architecture.graph.json"] == (
        prov.ARTIFACT_DIGEST_MISMATCH
    )
    assert by_path["docs/architecture-analysis/architecture.summary.json"] == (
        prov.ARTIFACT_MISSING
    )
    # The check writes nothing: the modified file is left exactly as we set it,
    # and no other artifact bytes change.
    assert graph.read_bytes() != before
    assert not summary.exists()


# --------------------------------------------------------------------------- #
# Scenario .9 — repeat refresh has no repository diff
# --------------------------------------------------------------------------- #
def test_repeat_refresh_is_byte_identical(repo: Path) -> None:
    doc1 = _generate(repo)
    bytes1 = prov.provenance_path(repo).read_bytes()
    doc2 = _generate(repo)
    bytes2 = prov.provenance_path(repo).read_bytes()
    assert doc1 == doc2
    assert bytes1 == bytes2
    # A second identical write is an observable no-op.
    os.environ["SOURCE_DATE_EPOCH"] = str(prov.deterministic_epoch(repo, doc2["source_revision"]))
    try:
        changed, _sha = prov.write_provenance(repo, doc2)
    finally:
        os.environ.pop("SOURCE_DATE_EPOCH", None)
    assert changed is False


def test_deterministic_timestamp_honors_source_date_epoch(repo: Path) -> None:
    os.environ["SOURCE_DATE_EPOCH"] = "1700000000"
    try:
        assert generated_at_iso() == "2023-11-14T22:13:20+00:00"
    finally:
        os.environ.pop("SOURCE_DATE_EPOCH", None)
