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
- architecture-refresh.16 every recorded artifact declares its tier
- architecture-refresh.17 absent local-cache artifact is not drift
- architecture-refresh.18 present local-cache artifact is still digest-verified
- architecture-refresh.19 provenance from an earlier schema version fails closed
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
    clean_fp, _enumeration = prov.compute_input_fingerprint(repo, ["src", "database/migrations"])
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


def test_pre_grammar_record_mismatches_once_then_regenerates(repo: Path) -> None:
    """The one-time cost of per-grammar optional-tool identity (D6).

    A record written before the upgrade carries one `tree-sitter` entry and the
    previous producer version. The check must say PRODUCER_IDENTITY_MISMATCH
    rather than report the artifacts as drifted, and one regeneration must
    settle it — that is why the first post-upgrade run reporting stale is
    expected rather than a regression.
    """
    roots = ["src", "database/migrations"]
    rev = prov.analyzed_revision(repo)
    os.environ["SOURCE_DATE_EPOCH"] = str(prov.deterministic_epoch(repo, rev))
    try:
        pre_upgrade = prov.build_provenance(
            repo,
            mode="full",
            roots=roots,
            optional_tools=[
                {"name": "tree-sitter", "available": True, "version": "0.25.2"}
            ],
        )
        pre_upgrade["producer"]["producer_version"] = "1.2.0"
        prov.write_provenance(repo, pre_upgrade)

        stale = prov.check_freshness(repo, mode="full")
        assert stale.status == "stale"
        assert prov.PRODUCER_IDENTITY_MISMATCH in {r.code for r in stale.reasons}
        assert prov.ARTIFACT_DIGEST_MISMATCH not in {r.code for r in stale.reasons}

        prov.write_provenance(
            repo, prov.build_provenance(repo, mode="full", roots=roots)
        )
    finally:
        os.environ.pop("SOURCE_DATE_EPOCH", None)

    assert prov.check_freshness(repo, mode="full").is_fresh


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
    # Schema-invalid (valid JSON, current version, wrong shape) also fails closed.
    # The version is deliberately the current one: a *stale* version is its own
    # reason code (PROVENANCE_SCHEMA_VERSION_MISMATCH), and this case is about
    # the generic "does not match the published shape" path.
    prov.provenance_path(repo).write_text(json.dumps({"schema_version": prov.PROVENANCE_SCHEMA_VERSION}))
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


# --------------------------------------------------------------------------- #
# Portable input identity — the fingerprint describes the repository, not the
# machine that happens to be holding it.
#
# The defect these pin: `_iter_root_files` walked the working tree excluding a
# fixed list of directory *names*, with no notion of `.gitignore`. Any ignored
# file sitting under an input root was hashed into the committed fingerprint, so
# provenance generated on a developer machine could never match a clean CI
# checkout, and no amount of regeneration could reconcile the two. The gate that
# consumes this reported the resulting drift as an apparatus failure naming no
# artifact, which is why it went unfixed.
# --------------------------------------------------------------------------- #
ROOTS = ["src", "database/migrations"]


def _fingerprint(repo: Path) -> str:
    fp, _enumeration = prov.compute_input_fingerprint(repo, ROOTS)
    return fp


def _discovered_paths(repo: Path) -> set[str]:
    entries, _missing = prov.discover_relevant_inputs(repo, ROOTS)
    return {e["path"] for e in entries}


def test_gitignored_file_under_an_input_root_is_not_an_input(repo: Path) -> None:
    """The regression, asserted through the signature-stable entry list.

    Deliberately not phrased over ``compute_input_fingerprint``: this test must
    fail on the unfixed producer by *naming the offending path*, not incidentally
    on a changed return type, or it proves nothing about the defect.
    """
    (repo / ".gitignore").write_text("*.local\n.env\n")
    _commit_all(repo, "ignore rules")
    before = _discovered_paths(repo)

    (repo / "src" / "secrets.local").write_text("API_KEY=hunter2\n")
    (repo / "src" / ".env").write_text("TOKEN=abc\n")

    leaked = _discovered_paths(repo) - before
    assert not leaked, f"ignored files were fingerprinted as inputs: {sorted(leaked)}"
    assert _fingerprint(repo) == _fingerprint(repo)  # and the hash over them is stable


def test_untracked_but_unignored_file_is_still_an_input(repo: Path) -> None:
    """The fix must not go too far: a new source file is a real input.

    ``--exclude-standard`` removes ignored files only. A file the developer has
    not yet ``git add``-ed is still something a clean clone would get once
    committed, and it genuinely feeds the analyzers.
    """
    before = _fingerprint(repo)
    (repo / "src" / "new_module.py").write_text("x = 1\n")
    assert _fingerprint(repo) != before


def test_dirty_tracked_input_still_changes_the_fingerprint(repo: Path) -> None:
    """Scenario architecture-refresh.2 must survive the enumeration change.

    Git decides *which* files are inputs; the working tree decides what they
    contain. Uncommitted edits to a tracked file must still register.
    """
    before = _fingerprint(repo)
    (repo / "src" / "app.py").write_text("print('edited, not committed')\n")
    assert _fingerprint(repo) != before


def test_fingerprint_matches_a_clean_clone_of_the_same_revision(repo: Path, tmp_path: Path) -> None:
    """The end-to-end property the gate depends on: dev tree == CI checkout."""
    (repo / ".gitignore").write_text("*.local\n")
    _commit_all(repo, "ignore rules")
    (repo / "src" / "developer.local").write_text("machine-specific junk\n")

    clone = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", "-q", str(repo), str(clone)], check=True, capture_output=True
    )

    assert _fingerprint(clone) == _fingerprint(repo)


def test_input_mode_records_only_the_git_visible_bit(repo: Path) -> None:
    """Permission bits below the executable bit belong to the umask, not the repo."""
    target = repo / "src" / "app.py"
    entries, _missing = prov.discover_relevant_inputs(repo, ROOTS)
    modes = {e["mode"] for e in entries}
    assert modes <= {"100644", "100755"}

    before = _fingerprint(repo)
    target.chmod(0o664)  # a umask-002 checkout of the very same file
    assert _fingerprint(repo) == before

    target.chmod(0o755)  # a genuinely executable file is a real difference
    assert _fingerprint(repo) != before


def test_enumeration_strategy_is_recorded(repo: Path) -> None:
    doc = _generate(repo)
    assert doc["input_enumeration"] == prov.INPUT_ENUMERATION_GIT
    prov.validate_provenance(doc)


def test_absent_enumeration_is_an_identity_mismatch_not_input_drift(repo: Path) -> None:
    """Provenance predating this field must say what to do about it.

    A recorded document with no ``input_enumeration`` was produced by the walk
    strategy. Reporting that as INPUT_FINGERPRINT_MISMATCH would tell a reader
    the source inputs changed, sending them to look for a source edit that never
    happened. It is an identity change, and the identity code is what carries
    "regenerate" as the remediation.
    """
    doc = _generate(repo)
    doc.pop("input_enumeration")
    prov.provenance_path(repo).write_text(json.dumps(doc))

    result = _check(repo)
    assert not result.is_fresh
    codes = {r.code for r in result.reasons}
    assert prov.PRODUCER_IDENTITY_MISMATCH in codes
    assert prov.INPUT_FINGERPRINT_MISMATCH not in codes


# --------------------------------------------------------------------------- #
# Issue #382 — the record distinguishes "generated now" from "left over"
# --------------------------------------------------------------------------- #
def test_owned_artifacts_without_a_generated_set_claims_nothing(repo: Path) -> None:
    """An ad-hoc build cannot know what a run produced, so it must not say.

    ``carried_over`` absent means "unknown", which is the honest answer when
    provenance is assembled outside a staged run (and the shape every document
    written before this field existed already has).
    """
    artifacts = prov.owned_artifacts(repo)
    assert artifacts
    assert all("carried_over" not in a for a in artifacts)


def test_owned_artifacts_flags_files_this_run_did_not_write(repo: Path) -> None:
    arch = repo / prov.ARCH_DIR_DEFAULT
    (arch / "treesitter_enrichment.json").write_text('{"from": "an older revision"}\n')
    (arch / "views" / ".gitkeep").write_text("")

    artifacts = prov.owned_artifacts(
        repo,
        generated={"architecture.graph.json", "architecture.summary.json", "views/overview.md"},
    )
    flags = {a["path"]: a["carried_over"] for a in artifacts}

    assert flags["docs/architecture-analysis/architecture.graph.json"] is False
    assert flags["docs/architecture-analysis/architecture.summary.json"] is False
    assert flags["docs/architecture-analysis/views/overview.md"] is False
    # Never staged by this run: an optional producer that did not run, and the
    # committed placeholder that only ever exists in the output directory.
    assert flags["docs/architecture-analysis/treesitter_enrichment.json"] is True
    assert flags["docs/architecture-analysis/views/.gitkeep"] is True
    # Flagged, not dropped: the digest still pins the committed bytes.
    carried = next(
        a for a in artifacts
        if a["path"] == "docs/architecture-analysis/treesitter_enrichment.json"
    )
    assert carried["sha256"] == prov.hash_file(arch / "treesitter_enrichment.json")[0]


def test_flagged_provenance_is_schema_valid_and_still_fresh(repo: Path) -> None:
    """Carrying an artifact over is a soft skip, not drift.

    The optional stages fail soft on purpose, so a partial refresh must not make
    the freshness check fail — it must make the *record* tell the truth.
    """
    (repo / prov.ARCH_DIR_DEFAULT / "treesitter_enrichment.json").write_text("{}\n")
    doc = prov.build_provenance(
        repo,
        mode="full",
        roots=["src", "database/migrations"],
        optional_tools=TOOLS,
        generated={"architecture.graph.json", "architecture.summary.json", "views/overview.md"},
    )
    prov.validate_provenance(doc)
    prov.write_provenance(repo, doc)

    result = _check(repo)
    assert result.is_fresh, [r.to_dict() for r in result.reasons]
    # The check surfaces what it did not vouch for without failing on it.
    assert result.to_dict()["carried_over"] == [
        "docs/architecture-analysis/treesitter_enrichment.json"
    ]


# --------------------------------------------------------------------------- #
# Artifact tiers — what an artifact's absence is allowed to mean
#
# The defect these pin: the artifact loop in ``check_freshness`` reported
# ARTIFACT_MISSING for every recorded artifact not on disk, and the ``required``
# flag did not gate it (that flag only governs generation and promotion). So an
# artifact the repository deliberately does not track turned the drift gate red
# in every clean clone, and there was no vocabulary for saying "this one is
# expected to be absent". ``tier`` is that vocabulary.
# --------------------------------------------------------------------------- #
_LOCAL_CACHE_NAMES = (
    "treesitter_enrichment.json",
    "python_analysis.json",
    "parallel_zones.json",
)


def _seed_local_cache(repo: Path) -> None:
    arch = repo / prov.ARCH_DIR_DEFAULT
    for name in _LOCAL_CACHE_NAMES:
        (arch / name).write_text('{"cache": "generated but not tracked"}\n')


def _tiers(doc: dict) -> dict[str, str]:
    return {a["path"]: a["tier"] for a in doc["artifacts"]}


# Scenario .16 — every recorded artifact declares its tier
def test_every_recorded_artifact_declares_a_tier(repo: Path) -> None:
    _seed_local_cache(repo)
    (repo / prov.ARCH_DIR_DEFAULT / "views" / ".gitkeep").write_text("")
    doc = _generate(repo)
    tiers = _tiers(doc)

    assert tiers
    assert set(tiers.values()) <= {prov.TIER_COMMITTED, prov.TIER_LOCAL_CACHE}
    for name in _LOCAL_CACHE_NAMES:
        assert tiers[f"{prov.ARCH_DIR_DEFAULT}/{name}"] == prov.TIER_LOCAL_CACHE
    assert tiers[f"{prov.ARCH_DIR_DEFAULT}/architecture.graph.json"] == prov.TIER_COMMITTED
    assert tiers[f"{prov.ARCH_DIR_DEFAULT}/architecture.summary.json"] == prov.TIER_COMMITTED
    # The recursive views/ walk records through the same helper, so those files
    # carry a tier too — they are tracked in git, so absence there is drift.
    assert tiers[f"{prov.ARCH_DIR_DEFAULT}/views/overview.md"] == prov.TIER_COMMITTED
    assert tiers[f"{prov.ARCH_DIR_DEFAULT}/views/.gitkeep"] == prov.TIER_COMMITTED
    prov.validate_provenance(doc)


# Scenario .17 — absent local-cache artifact is not drift
def test_absent_local_cache_artifact_is_not_drift(repo: Path) -> None:
    """A clean checkout has every committed artifact and none of the caches."""
    _seed_local_cache(repo)
    _generate(repo)
    for name in _LOCAL_CACHE_NAMES:
        (repo / prov.ARCH_DIR_DEFAULT / name).unlink()

    result = _check(repo)

    assert result.is_fresh, [r.to_dict() for r in result.reasons]
    assert not [r for r in result.reasons if r.code == prov.ARTIFACT_MISSING]


# Scenario .18 — a present local-cache artifact is still digest-verified
def test_present_local_cache_artifact_is_still_digest_verified(repo: Path) -> None:
    """Presence is judged identically for both tiers: a stale cache is reported."""
    _seed_local_cache(repo)
    _generate(repo)
    cache = repo / prov.ARCH_DIR_DEFAULT / "treesitter_enrichment.json"
    cache.write_text('{"cache": "bytes from an older revision"}\n')

    result = _check(repo)

    assert result.status == "stale"
    by_path = {r.path: r.code for r in result.reasons if r.path}
    assert by_path[f"{prov.ARCH_DIR_DEFAULT}/treesitter_enrichment.json"] == (
        prov.ARTIFACT_DIGEST_MISMATCH
    )


# Scenario .19 — provenance from an earlier schema version fails closed
def test_earlier_schema_version_is_stale_and_names_the_version(repo: Path) -> None:
    """The remediation is "regenerate the record", not "regenerate a file".

    Reporting a shape change as artifact drift sends the reader looking for the
    file that changed, when nothing about any file changed.
    """
    doc = _generate(repo)
    doc["schema_version"] = 1
    for artifact in doc["artifacts"]:
        artifact.pop("tier")
    prov.provenance_path(repo).write_text(json.dumps(doc))

    result = _check(repo)

    assert result.status == "stale"
    assert not result.is_fresh
    codes = {r.code for r in result.reasons}
    assert prov.PROVENANCE_SCHEMA_VERSION_MISMATCH in codes
    assert prov.ARTIFACT_MISSING not in codes
    assert prov.ARTIFACT_DIGEST_MISMATCH not in codes
    detail = next(
        r.detail for r in result.reasons if r.code == prov.PROVENANCE_SCHEMA_VERSION_MISMATCH
    )
    assert "1" in detail and str(prov.PROVENANCE_SCHEMA_VERSION) in detail


def test_schema_version_mismatch_is_detected_before_artifact_state(repo: Path) -> None:
    """A v1 record must not be re-read through v2 rules, whatever is on disk."""
    doc = _generate(repo)
    doc["schema_version"] = 1
    prov.provenance_path(repo).write_text(json.dumps(doc))
    (repo / prov.ARCH_DIR_DEFAULT / "architecture.summary.json").unlink()

    result = _check(repo)

    assert not result.is_fresh
    assert result.reasons[0].code == prov.PROVENANCE_SCHEMA_VERSION_MISMATCH
    assert prov.ARTIFACT_MISSING not in {r.code for r in result.reasons}
