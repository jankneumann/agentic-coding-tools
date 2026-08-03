"""Check mode is read-only for every registered producer (ri-10 task 2.3, D8).

ri-09's design D3 recorded the gap this module closes:

    ``registry.run_producer`` does not *structurally* prevent a ``check``-mode
    adapter from writing … ri-10 in particular should assert read-only-ness
    rather than assume it.

A runtime filesystem guard inside ``registry.run_producer`` was considered and
rejected (D8): it would change the seam both existing entry points depend on for
a property no current adapter violates. **This test is the enforcement
mechanism**, so it is written to be able to fail:

* it enumerates producers from ``registry.list_producers()`` at call time, never
  from a literal list, so a producer registered after this change is covered
  without editing anything here;
* it digests **every** path in the checkout — tracked, untracked, and ignored —
  so a scratch file written outside a producer's declared managed outputs is
  caught. ri-09's version compared only the tracked tree, which left that hole
  open;
* it runs against a deliberately **dirty** worktree, because a producer with
  nothing to reconcile is the one case where a writing adapter would not write;
* and ``TestTheAssertionCanFail`` registers adapters that write in check mode and
  requires the assertion to catch them, so a silently-vacuous version of this
  file fails its own suite.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from _runtime import (
    Fallback,
    FallbackKind,
    ProducerResult,
    ProducerStatus,
    Remediation,
)
from registry import Producer, ProducerSpec, list_producers, register, run_producer

# --------------------------------------------------------------------------- #
# Whole-checkout digesting
# --------------------------------------------------------------------------- #
#: ``.git/`` is excluded deliberately: it holds neither tracked nor untracked
#: repository content, and any read-only git invocation may refresh the index or
#: write a gc log, which would make the comparison flap for a reason that is not
#: a producer writing to the checkout. Repository state is instead pinned
#: separately through ``git status --porcelain`` (see ``_porcelain``).
_EXCLUDED_TOP = ".git"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _entry(repo: Path, path: Path) -> tuple[str, str]:
    """Digest one path: content for files, target for symlinks, marker for dirs."""
    rel = path.relative_to(repo).as_posix()
    if path.is_symlink():
        return rel, f"symlink:{path.readlink().as_posix()}"
    if path.is_dir():
        return rel, "dir"
    return rel, f"file:{_sha256(path)}"


def digest_checkout(repo: Path) -> dict[str, str]:
    """Digest every tracked, untracked, and ignored path under *repo*.

    Directories and symlinks are included as well as file bytes, so an empty
    directory or a re-pointed link is drift too.
    """
    return dict(
        _entry(repo, path)
        for path in sorted(repo.rglob("*"))
        if not path.relative_to(repo).as_posix().startswith(_EXCLUDED_TOP)
    )


def _porcelain(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def assert_check_mode_is_read_only(repo: Path, revision: str) -> list[str]:
    """Run every registered producer in check mode; return the ids exercised.

    Raises ``AssertionError`` naming the offending producer as soon as one
    changes the checkout, so a failure points at a producer rather than at a
    diff.
    """
    specs = list_producers()
    assert specs, "the registry exposed no producers; the assertion would be vacuous"

    exercised: list[str] = []
    for spec in specs:
        before = digest_checkout(repo)
        before_status = _porcelain(repo)

        run_producer(spec.producer_id, "check", repo, revision)
        exercised.append(spec.producer_id)

        after = digest_checkout(repo)
        if after != before:
            added = sorted(set(after) - set(before))
            removed = sorted(set(before) - set(after))
            changed = sorted(
                path for path in set(after) & set(before) if after[path] != before[path]
            )
            raise AssertionError(
                f"producer {spec.producer_id!r} modified the checkout in check mode: "
                f"added={added} removed={removed} changed={changed}"
            )
        after_status = _porcelain(repo)
        assert after_status == before_status, (
            f"producer {spec.producer_id!r} changed repository status in check mode:\n"
            f"before:\n{before_status}\nafter:\n{after_status}"
        )
    return exercised


# --------------------------------------------------------------------------- #
# Fixture: a committed checkout with real producer inputs, then made dirty
# --------------------------------------------------------------------------- #
def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _managed(title: str, block_id: str, body: str) -> str:
    """A marker-managed inventory file, matching ``inventory_file._skeleton``."""
    return (
        f"# {title}\n\n"
        "<!-- This file is generated by a project-context producer. Edit prose "
        "outside the generated markers only; content inside the markers is "
        "overwritten on regeneration. -->\n\n"
        f"<!-- GENERATED: begin {block_id} -->\n"
        f"{body}\n"
        f"<!-- GENERATED: end {block_id} -->\n"
    )


@pytest.fixture
def dirty_checkout(tmp_path: Path) -> tuple[Path, str]:
    """A committed checkout carrying every producer's inputs, then dirtied.

    Every producer must find real work to do: inputs it can render, a committed
    managed output to compare against, an active change with a spec delta, and an
    archived change with a session log. A producer that bailed out early would
    make the read-only assertion prove nothing.
    """
    repo = tmp_path / "checkout"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    for key, value in (("user.email", "t@example.com"), ("user.name", "T")):
        _git(repo, "config", key, value)

    # documentation.inventory inputs + its committed managed output.
    _write(
        repo / "skills" / "alpha" / "SKILL.md",
        "---\nname: alpha\nuser_invocable: true\ndescription: First skill\n---\n\nBody\n",
    )
    _write(
        repo / "skills" / "beta" / "SKILL.md",
        "---\nname: beta\nuser_invocable: false\ndescription: Second skill\n---\n\nBody\n",
    )
    _write(
        repo / "docs" / "architecture-analysis" / "skills-inventory.md",
        _managed("Skills inventory", "skills-inventory", "_stale body_"),
    )

    # api.contracts inputs + its committed managed output.
    _write(
        repo / "openspec" / "contracts" / "cap" / "schemas" / "thing.schema.json",
        '{\n  "$id": "thing.schema.json",\n  "title": "Thing",\n  "type": "object"\n}\n',
    )
    _write(
        repo / "docs" / "architecture-analysis" / "contracts-inventory.md",
        _managed("Contracts inventory", "contracts-inventory", "_stale body_"),
    )

    # openspec.projection: a canonical spec plus an active change delta over it.
    _write(
        repo / "openspec" / "specs" / "cap" / "spec.md",
        "# cap\n\n## Requirements\n\n### Requirement: Existing\n\nThe system SHALL exist.\n",
    )
    _write(
        repo / "openspec" / "changes" / "live-change" / "specs" / "cap" / "spec.md",
        "## ADDED Requirements\n\n### Requirement: New\n\nThe system SHALL be new.\n",
    )
    _write(repo / "openspec" / "changes" / "live-change" / "proposal.md", "# live-change\n")

    # decisions.timeline: an archived change with a session log, plus a committed index.
    archive = repo / "openspec" / "changes" / "archive" / "2026-01-01-old-change"
    _write(
        archive / "session-log.md",
        "# Session Log — old-change\n\n## Decision: Something was decided\n\nBecause.\n",
    )
    _write(archive / "proposal.md", "# old-change\n\n## Why\n\nBecause.\n")
    _write(repo / "docs" / "decisions" / "README.md", "# Decisions\n")

    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    head = _git(repo, "rev-parse", "HEAD")

    # Deliberately dirty: a modified tracked input, a new untracked input, and an
    # untracked scratch file that no producer owns.
    _write(
        repo / "skills" / "alpha" / "SKILL.md",
        "---\nname: alpha\nuser_invocable: true\ndescription: Edited uncommitted\n---\n",
    )
    _write(
        repo / "skills" / "gamma" / "SKILL.md",
        "---\nname: gamma\nuser_invocable: true\ndescription: Untracked skill\n---\n",
    )
    _write(repo / "scratch.local", "not owned by any producer\n")
    return repo, head


# --------------------------------------------------------------------------- #
# The assertion itself
# --------------------------------------------------------------------------- #
class TestCheckModeIsReadOnly:
    def test_the_fixture_is_actually_dirty(
        self, dirty_checkout: tuple[Path, str]
    ) -> None:
        """A clean tree would make the assertion prove nothing."""
        repo, _head = dirty_checkout
        status = _porcelain(repo)
        assert " M skills/alpha/SKILL.md" in status
        assert "?? skills/gamma/SKILL.md" in status
        assert "?? scratch.local" in status

    def test_every_registered_producer_leaves_the_checkout_byte_identical(
        self, dirty_checkout: tuple[Path, str]
    ) -> None:
        repo, head = dirty_checkout
        before = digest_checkout(repo)

        exercised = assert_check_mode_is_read_only(repo, head)

        assert exercised == [spec.producer_id for spec in list_producers()]
        assert digest_checkout(repo) == before

    def test_the_producers_did_real_work_rather_than_bailing_out(
        self, dirty_checkout: tuple[Path, str]
    ) -> None:
        """Read-only-ness proven by a producer that never ran is not evidence."""
        repo, head = dirty_checkout
        results = [
            run_producer(spec.producer_id, "check", repo, head)
            for spec in list_producers()
        ]
        assert results
        assert all(r.status is not ProducerStatus.FAILED for r in results), [
            (r.producer_id, r.error.summary if r.error else None) for r in results
        ]
        assert any(v for r in results for v in r.validations), (
            "no producer recorded a validation, so none compared anything"
        )
        # The two marker-managed inventories were committed stale on purpose, so
        # at least one producer must be reporting drift it declined to fix.
        assert any(r.status is ProducerStatus.DEGRADED for r in results)

    def test_the_untracked_scratch_file_is_covered_by_the_digest(
        self, dirty_checkout: tuple[Path, str]
    ) -> None:
        """The specific hole ri-09's tracked-only comparison left open."""
        repo, _head = dirty_checkout
        digests = digest_checkout(repo)
        assert "scratch.local" in digests
        assert "skills/gamma/SKILL.md" in digests

    def test_directories_and_symlinks_are_part_of_the_digest(
        self, dirty_checkout: tuple[Path, str]
    ) -> None:
        repo, _head = dirty_checkout
        digests = digest_checkout(repo)
        assert digests["skills/alpha"] == "dir"

        link = repo / "link-to-docs"
        link.symlink_to(repo / "docs")
        assert digest_checkout(repo)["link-to-docs"].startswith("symlink:")

    def test_git_internals_are_excluded_but_repository_status_is_pinned(
        self, dirty_checkout: tuple[Path, str]
    ) -> None:
        repo, _head = dirty_checkout
        assert not any(k.startswith(".git/") for k in digest_checkout(repo))
        assert _porcelain(repo)  # the status snapshot is non-empty, so it can differ


# --------------------------------------------------------------------------- #
# Mutation proof: the assertion must be able to fail
# --------------------------------------------------------------------------- #
class _WritingProducer(Producer):
    """A producer that violates the check-mode contract on purpose."""

    def __init__(self, producer_id: str, target_rel: str, *, delete: bool = False):
        self.spec = ProducerSpec(
            producer_id=producer_id,
            producer_version="1",
            owner="mutation-fixture",
            inputs=(),
            outputs=(target_rel,),
            optional=False,
        )
        self._target_rel = target_rel
        self._delete = delete

    def run(self, mode, repository, source_revision):  # noqa: ANN001
        target = Path(repository) / self._target_rel
        if self._delete:
            target.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("written in check mode\n", encoding="utf-8")
        return ProducerResult(
            producer_id=self.spec.producer_id,
            producer_version=self.spec.producer_version,
            status=ProducerStatus.FRESH,
        )


class _ReadOnlyProducer(Producer):
    def __init__(self, producer_id: str):
        self.spec = ProducerSpec(
            producer_id=producer_id,
            producer_version="1",
            owner="mutation-fixture",
            inputs=(),
            outputs=(),
        )
        self.calls = 0

    def run(self, mode, repository, source_revision):  # noqa: ANN001
        self.calls += 1
        return ProducerResult(
            producer_id=self.spec.producer_id,
            producer_version=self.spec.producer_version,
            status=ProducerStatus.FRESH,
        )


class TestTheAssertionCanFail:
    def test_a_producer_that_writes_a_tracked_file_is_caught_and_named(
        self, dirty_checkout: tuple[Path, str]
    ) -> None:
        repo, head = dirty_checkout
        register(_WritingProducer("zz.writes-tracked", "docs/decisions/README.md"))

        with pytest.raises(AssertionError) as excinfo:
            assert_check_mode_is_read_only(repo, head)

        message = str(excinfo.value)
        assert "zz.writes-tracked" in message
        assert "docs/decisions/README.md" in message

    def test_a_producer_that_writes_an_untracked_scratch_file_is_caught(
        self, dirty_checkout: tuple[Path, str]
    ) -> None:
        """Strictly stronger than a tracked-tree comparison, which misses this."""
        repo, head = dirty_checkout
        register(_WritingProducer("zz.writes-scratch", ".cache/producer-scratch.tmp"))

        with pytest.raises(AssertionError) as excinfo:
            assert_check_mode_is_read_only(repo, head)

        assert "zz.writes-scratch" in str(excinfo.value)
        assert ".cache/producer-scratch.tmp" in str(excinfo.value)

    def test_a_producer_that_deletes_a_file_is_caught(
        self, dirty_checkout: tuple[Path, str]
    ) -> None:
        repo, head = dirty_checkout
        register(
            _WritingProducer("zz.deletes", "docs/decisions/README.md", delete=True)
        )

        with pytest.raises(AssertionError) as excinfo:
            assert_check_mode_is_read_only(repo, head)

        assert "zz.deletes" in str(excinfo.value)
        assert "removed=['docs/decisions/README.md']" in str(excinfo.value)

    def test_a_newly_registered_producer_is_covered_without_editing_the_assertion(
        self, dirty_checkout: tuple[Path, str]
    ) -> None:
        repo, head = dirty_checkout
        baseline = assert_check_mode_is_read_only(repo, head)

        extra = _ReadOnlyProducer("zz.registered-later")
        register(extra)
        exercised = assert_check_mode_is_read_only(repo, head)

        assert "zz.registered-later" in exercised
        assert len(exercised) == len(baseline) + 1
        assert extra.calls == 1

    def test_the_enumeration_is_the_registry_not_a_captured_snapshot(
        self, dirty_checkout: tuple[Path, str]
    ) -> None:
        repo, head = dirty_checkout
        register(_ReadOnlyProducer("zz.late-a"))
        register(_ReadOnlyProducer("zz.late-b"))

        exercised = assert_check_mode_is_read_only(repo, head)

        assert set(exercised) == {spec.producer_id for spec in list_producers()}
        assert {"zz.late-a", "zz.late-b"} <= set(exercised)


# --------------------------------------------------------------------------- #
# The deliberate absence of a runtime guard (D8)
# --------------------------------------------------------------------------- #
class TestNoRuntimeGuard:
    def test_run_producer_does_not_block_a_check_mode_write(
        self, dirty_checkout: tuple[Path, str]
    ) -> None:
        """The absence of a filesystem guard is a decision, not an omission.

        D8 rejected a runtime guard in ``registry.run_producer`` because it would
        change the seam both existing entry points depend on. This pins that
        choice: the write goes through, and the *test above* is what catches it.
        Should a guard ever be added deliberately, this test is the one to delete.
        """
        repo, head = dirty_checkout
        scratch = repo / "guard-probe.tmp"
        register(_WritingProducer("zz.probes-guard", "guard-probe.tmp"))

        result = run_producer("zz.probes-guard", "check", repo, head)

        assert result.status is ProducerStatus.FRESH
        assert scratch.is_file(), (
            "registry.run_producer appears to have gained a filesystem guard; "
            "D8 rejected one, so either the design changed or this is a regression"
        )

    def test_the_registry_exposes_no_guard_hook(self) -> None:
        import registry as registry_mod

        assert not hasattr(registry_mod, "_enforce_read_only")
        assert not hasattr(registry_mod, "READ_ONLY_MODES")


# --------------------------------------------------------------------------- #
# Result-shape sanity for the fixtures above
# --------------------------------------------------------------------------- #
def test_writing_fixture_results_satisfy_the_ri06_invariants() -> None:
    """Guards against the mutation fixtures failing for the wrong reason."""
    result = ProducerResult(
        producer_id="zz.fixture",
        producer_version="1",
        status=ProducerStatus.DEGRADED,
        remediation=(Remediation(summary="fixture"),),
        fallback=Fallback(kind=FallbackKind.CUSTOM, reason="fixture"),
    )
    assert result.status is ProducerStatus.DEGRADED
