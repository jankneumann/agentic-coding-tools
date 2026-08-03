"""Orphaned-capability-file detection (task 4.1, design D9).

`validate-decision-index` regenerated `docs/decisions/` in place and ran
`git diff --exit-code`. `software-factory-tooling`'s "Per-Capability Decision
Index Emitter" requirement records the blind spot that motivates these tests: an
**orphaned** `docs/decisions/<capability>.md` — a file for a capability that no
longer has any tagged decisions — has *unchanged content*. It is the file's
**presence** that is stale, and a content comparison structurally cannot see it.
The emitter compensates by deleting such files before the diff is taken.

The `decisions.timeline` producer renders into a **tempdir**, so the emitter's
compensating deletion never touches the committed tree — the tempdir starts
empty and its stale-file sweep finds nothing to unlink. Detection therefore has
to come from `tree_diff.diff_trees`' `deleted` bucket (`committed - rendered`).

These tests pin that. Retiring the old job without proving the replacement
covers its blind spot would be a silent regression.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from _runtime import ChangeKind, ProducerStatus
from contract import validate_producer_result
from producer_decisions import DecisionsTimelineProducer, _render_index
from tree_diff import diff_trees

FULL_SHA = "d" * 40

ORPHAN_ARTIFACT = "docs/decisions/gadgets.md"


def _seed_capability(repo: Path, capability: str) -> None:
    spec_dir = repo / "openspec/specs" / capability
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "spec.md").write_text(f"# {capability} Specification\n", encoding="utf-8")


def _seed_change_with_decision(repo: Path, change_id: str, capability: str, text: str) -> None:
    change = repo / "openspec/changes" / change_id
    change.mkdir(parents=True, exist_ok=True)
    (change / "session-log.md").write_text(
        "# Session Log\n\n"
        "## Phase: Build (2026-01-15)\n\n"
        "### Decisions\n\n"
        f"1. **Chose an approach** `architectural: {capability}` — {text}\n",
        encoding="utf-8",
    )


def _decisions_dir(repo: Path) -> Path:
    return repo / "docs/decisions"


@pytest.fixture
def orphaned_repo(tmp_path: Path) -> tuple[Path, bytes]:
    """A repo whose committed index holds an orphaned `gadgets.md`.

    `widgets` keeps its tagged decision; `gadgets`' only source of tagged
    decisions is removed *after* the index is generated, so `gadgets.md` stays
    on disk byte-for-byte as emitted while nothing in the repo justifies it any
    more. The capability spec is deliberately left in place: what makes the file
    an orphan is the absence of tagged *decisions*, not the absence of a spec.
    """
    _seed_capability(tmp_path, "widgets")
    _seed_capability(tmp_path, "gadgets")
    _seed_change_with_decision(tmp_path, "add-widgets", "widgets", "chose a registry")
    _seed_change_with_decision(tmp_path, "add-gadgets", "gadgets", "chose a factory")

    DecisionsTimelineProducer().run("generate", tmp_path, FULL_SHA)
    orphan = _decisions_dir(tmp_path) / "gadgets.md"
    assert orphan.exists(), "fixture precondition: gadgets.md was emitted"
    emitted_bytes = orphan.read_bytes()

    # Remove the only source of gadgets' tagged decisions. The committed
    # gadgets.md is now an orphan; its bytes on disk are untouched.
    (tmp_path / "openspec/changes/add-gadgets/session-log.md").unlink()

    assert orphan.read_bytes() == emitted_bytes, (
        "fixture precondition: the orphan's content must be unchanged — that is "
        "the whole reason a content comparison cannot see it"
    )
    return tmp_path, emitted_bytes


def _content_only_drift(repo: Path) -> set[str]:
    """Files a *content* comparison would flag — the retired job's semantics.

    `git diff` after an in-place regeneration can only speak about files that
    exist in both the before and after trees (plus whatever the emitter itself
    deleted). This models the "compare the bytes of files present in both trees"
    half, which is precisely the half that is blind to an orphan.
    """
    with tempfile.TemporaryDirectory(prefix="orphan-content-only-") as tmp:
        rendered_root = Path(tmp)
        _render_index(repo, rendered_root)
        committed_root = _decisions_dir(repo)
        changed: set[str] = set()
        for rendered in sorted(rendered_root.rglob("*.md")):
            rel = rendered.relative_to(rendered_root).as_posix()
            committed = committed_root / rel
            if not committed.is_file():
                continue  # not present in both trees — outside content comparison
            if committed.read_bytes() != rendered.read_bytes():
                changed.add(f"docs/decisions/{rel}")
        return changed


def test_orphaned_capability_file_is_reported_as_drift(orphaned_repo):
    """pcro — The gate is the single freshness authority / Orphaned capability file is detected."""
    repo, _ = orphaned_repo

    result = DecisionsTimelineProducer().run("check", repo, FULL_SHA)
    validate_producer_result(result)

    assert result.status is ProducerStatus.DEGRADED
    assert ORPHAN_ARTIFACT in {a.path for a in result.artifacts}


def test_orphan_is_reported_through_the_deleted_bucket(orphaned_repo):
    """The orphan is drift because it is *absent* from the render, not because its bytes moved."""
    repo, _ = orphaned_repo

    result = DecisionsTimelineProducer().run("check", repo, FULL_SHA)
    orphan_artifacts = [a for a in result.artifacts if a.path == ORPHAN_ARTIFACT]

    assert len(orphan_artifacts) == 1
    artifact = orphan_artifacts[0]
    assert artifact.change is ChangeKind.DELETED
    # A deleted artifact carries no digest: there is no rendered content to hash.
    assert artifact.sha256 is None


def test_content_comparison_alone_misses_the_orphan(orphaned_repo):
    """Non-vacuity: the retired job's comparison is blind to exactly this file.

    If `diff_trees` had no `deleted` bucket, the producer's report would be this
    set — which does not mention the orphan. The test above would then fail, so
    it is asserting something the surrounding machinery genuinely provides.
    """
    repo, emitted_bytes = orphaned_repo

    content_drift = _content_only_drift(repo)

    assert ORPHAN_ARTIFACT not in content_drift, (
        "the orphan must be invisible to a content-only comparison; if this "
        "starts failing the fixture no longer models the blind spot"
    )
    # And the bytes really are untouched, so there is nothing for a content
    # comparison to notice.
    assert (_decisions_dir(repo) / "gadgets.md").read_bytes() == emitted_bytes


def test_diff_trees_deleted_bucket_is_the_detection_path(orphaned_repo):
    """The emitter's own stale-file sweep cannot help: the render target is empty.

    Rendering into a fresh tempdir means `emit_decision_index`'s `existing.unlink()`
    loop finds nothing to delete. `gadgets.md` is simply never rendered, and only
    `committed - rendered` surfaces it.
    """
    repo, _ = orphaned_repo

    with tempfile.TemporaryDirectory(prefix="orphan-render-") as tmp:
        rendered_root = Path(tmp)
        _render_index(repo, rendered_root)

        assert not (rendered_root / "gadgets.md").exists(), "orphan must not be re-rendered"
        assert (rendered_root / "widgets.md").exists(), "live capability must still render"

        artifacts = diff_trees(
            _decisions_dir(repo),
            rendered_root,
            path_prefix="docs/decisions",
            patterns=("*.md",),
        )

    deleted = {a.path for a in artifacts if a.change is ChangeKind.DELETED}
    assert deleted == {ORPHAN_ARTIFACT}


def test_check_does_not_delete_the_orphan(orphaned_repo):
    """`check` reports the orphan; it does not remediate it. Read-only stays read-only."""
    repo, emitted_bytes = orphaned_repo

    DecisionsTimelineProducer().run("check", repo, FULL_SHA)

    orphan = _decisions_dir(repo) / "gadgets.md"
    assert orphan.exists()
    assert orphan.read_bytes() == emitted_bytes


def test_generate_removes_the_orphan(orphaned_repo):
    """The remediation path closes it: `generate` syncs the deletion onto the tree."""
    repo, _ = orphaned_repo

    result = DecisionsTimelineProducer().run("generate", repo, FULL_SHA)
    validate_producer_result(result)

    assert not (_decisions_dir(repo) / "gadgets.md").exists()
    assert DecisionsTimelineProducer().run("check", repo, FULL_SHA).status is ProducerStatus.FRESH
