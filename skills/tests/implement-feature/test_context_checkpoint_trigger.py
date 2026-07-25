"""The per-package context-checkpoint trigger consumed by implement-feature (ri-09 4.1-4.2).

Spec scenarios (capability ``skill-workflow``):

* "A context-invalidating package produces a checkpoint"
* "A package with no context impact produces no checkpoint"
* "Checkpoint evaluation uses the package's changed-file list"
* "Missing declaration is reported as unmigrated"
* "Empty declaration is reported as an assertion"
* "Package scope is supplied to the checkpoint"

Design decisions: D2 (the trigger, and the ``unmigrated`` / "asserted no impact"
distinction), D5 (the read scope handed from the package to the checkpoint).

These tests pin the *machine-readable* half of the workflow contract:
``CheckpointDecision`` is what the workflow branches on, and ``to_dict()`` is
what a summary entry serializes, so asserting on those pins the behaviour the
spec scenarios describe. The prose in ``implement-feature/SKILL.md`` is checked
only for the things that are genuinely textual (task 4.3); nothing here asserts
against markdown.

An explicit :class:`ImpactRules` table is built in-process for every case, so
these tests describe checkpoint behaviour rather than the repository's live
``context-impact-rules.yaml``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_SKILLS_DIR = Path(__file__).resolve().parents[2]
for _scripts in (
    _SKILLS_DIR / "validate-packages" / "scripts",
    _SKILLS_DIR / "project-context-refresh" / "scripts",
):
    if str(_scripts) not in sys.path:
        sys.path.insert(0, str(_scripts))

import checkpoint  # noqa: E402
from context_impact import ImpactRules, IndexScopes, index_scopes  # noqa: E402
from semantic_adapter import ReadScope  # noqa: E402

#: A 40-char lowercase object id: the only revision shape the runtime accepts.
REVISION = "a" * 40
CHANGE_ID = "add-branch-local-context-checkpoints"
PACKAGE_ID = "wp-workflow"


def _rules() -> ImpactRules:
    return ImpactRules(
        surface_globs={
            "documentation": ("docs/**", "**/*.md"),
            "semantic_code": ("**/*.py",),
        },
        source=Path("test-rules.yaml"),
    )


def _package(**overrides: Any) -> dict[str, Any]:
    """A completed package that writes documentation and code, and declares it."""
    package: dict[str, Any] = {
        "package_id": PACKAGE_ID,
        "scope": {
            "read_allow": ["skills/**", "docs/**"],
            "write_allow": ["skills/**", "docs/**"],
            "deny": ["**/.venv/**"],
        },
        "context_impact": {"surfaces": ["documentation", "semantic_code"]},
    }
    package.update(overrides)
    return package


def _without_declaration() -> dict[str, Any]:
    package = _package()
    del package["context_impact"]
    return package


#: Files inside the package's write scope that invalidate documentation and code.
INVALIDATING_FILES = ("docs/guides/workflow.md", "skills/implement-feature/scripts/x.py")
#: Files inside the write scope that no rule maps to any surface.
INERT_FILES = ("skills/implement-feature/notes.txt",)


# --------------------------------------------------------------------------- #
# D2 — the trigger at the package-completion boundary
# --------------------------------------------------------------------------- #
class TestTriggerAtPackageCompletion:
    def test_a_context_invalidating_package_produces_a_checkpoint(self) -> None:
        decision = checkpoint.should_checkpoint(
            _package(), INVALIDATING_FILES, rules=_rules()
        )

        assert decision.should_run is True
        assert decision.status == "declared"
        assert decision.surfaces == ("documentation", "semantic_code")
        # The surfaces that trigger a checkpoint must be members of the named
        # invalidating set, not an ad-hoc list the workflow keeps of its own.
        assert set(decision.surfaces) <= checkpoint.CONTEXT_INVALIDATING_SURFACES

    def test_an_explicitly_empty_declaration_produces_no_checkpoint(self) -> None:
        decision = checkpoint.should_checkpoint(
            _package(context_impact={"surfaces": []}), INERT_FILES, rules=_rules()
        )

        assert decision.should_run is False
        assert decision.status == "declared"
        assert decision.surfaces == ()
        # An assertion of no impact, never an admission of not having looked.
        assert decision.is_unmigrated is False

    def test_a_missing_declaration_is_reported_as_unmigrated(self) -> None:
        decision = checkpoint.should_checkpoint(
            _without_declaration(), INVALIDATING_FILES, rules=_rules()
        )

        assert decision.should_run is False
        assert decision.status == checkpoint.UNMIGRATED
        assert decision.is_unmigrated is True
        # The surfaces its files DO imply are still reported, so the summary
        # carries the evidence needed to migrate the package.
        assert decision.surfaces == ("documentation", "semantic_code")

    def test_the_summary_entry_never_reports_unmigrated_as_impact_free(self) -> None:
        """``to_dict()`` is the summary payload; it must carry the status verbatim."""
        entry = checkpoint.should_checkpoint(
            _without_declaration(), INVALIDATING_FILES, rules=_rules()
        ).to_dict()

        assert entry["status"] == "unmigrated"
        assert entry["should_run"] is False
        # "no context impact" is a claim only an explicit empty declaration earns.
        assert entry["surfaces"] == ["documentation", "semantic_code"]

    def test_missing_and_empty_declarations_are_distinguishable(self) -> None:
        """The whole point of D2: both skip, and they must not read alike.

        Both decisions are taken from *identical* inputs, so a workflow that
        branched on ``should_run`` alone would be indistinguishable from one
        that had collapsed the two states. The status, the flag, the reason, and
        the serialized entry must all separate them.
        """
        missing = checkpoint.should_checkpoint(
            _without_declaration(), INERT_FILES, rules=_rules()
        )
        empty = checkpoint.should_checkpoint(
            _package(context_impact={"surfaces": []}), INERT_FILES, rules=_rules()
        )

        assert missing.should_run == empty.should_run is False  # would pass alone
        assert missing.status != empty.status
        assert missing.is_unmigrated is True
        assert empty.is_unmigrated is False
        assert missing.reason != empty.reason
        assert missing.to_dict() != empty.to_dict()

    def test_neither_skip_reason_is_a_blocking_status(self) -> None:
        """Skipping is not failing: the ri-08 gate owns the failing statuses."""
        for decision in (
            checkpoint.should_checkpoint(
                _without_declaration(), INERT_FILES, rules=_rules()
            ),
            checkpoint.should_checkpoint(
                _package(context_impact={"surfaces": []}), INERT_FILES, rules=_rules()
            ),
        ):
            assert decision.is_blocking is False


# --------------------------------------------------------------------------- #
# D2 — evaluation is git-free
# --------------------------------------------------------------------------- #
class TestChangedFileListIsSuppliedDirectly:
    def test_evaluation_shells_out_to_no_git_command(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """No git range, no commit, no repository.

        The detector is deliberately git-free so a checkpoint can be decided on
        an uncommitted worktree between package completion and commit. Running
        from a directory that is not a repository, with ``subprocess.run``
        booby-trapped, is what makes that claim testable rather than asserted.
        """

        def _boom(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError(f"the trigger must not shell out: {args!r}")

        monkeypatch.setattr(subprocess, "run", _boom)
        monkeypatch.chdir(tmp_path)
        assert not (tmp_path / ".git").exists()

        decision = checkpoint.should_checkpoint(
            _package(), INVALIDATING_FILES, rules=_rules()
        )

        assert decision.should_run is True
        assert decision.surfaces == ("documentation", "semantic_code")

    def test_files_that_exist_nowhere_on_disk_still_decide_the_trigger(
        self, tmp_path: Path
    ) -> None:
        """Uncommitted — and here, not even written — files still count."""
        never_written = "docs/guides/not-yet-created.md"
        assert not (tmp_path / never_written).exists()

        decision = checkpoint.should_checkpoint(
            _package(context_impact={"surfaces": ["documentation"]}),
            (never_written,),
            rules=_rules(),
        )

        assert decision.should_run is True
        assert decision.surfaces == ("documentation",)


# --------------------------------------------------------------------------- #
# D5 — the package's resolved read scope is handed to the checkpoint
# --------------------------------------------------------------------------- #
class _RecordingIndexerFactory:
    """Stands in for ``default_semantic_indexer`` and records how it was built."""

    def __init__(self) -> None:
        self.namespace: Any = None
        self.scope: ReadScope | None = None

    def __call__(self, *, namespace: Any, scope: ReadScope) -> None:
        self.namespace = namespace
        self.scope = scope
        return None  # unconfigured: the index degrades, the report still lands


class TestScopeHandoff:
    def test_resolved_scope_is_read_allow_minus_deny_with_deny_winning(self) -> None:
        package = _package(
            scope={
                "read_allow": ["skills/**", "docs/**"],
                "write_allow": ["skills/**"],
                "deny": ["docs/private/**", "**/.venv/**"],
            }
        )

        scopes = index_scopes(package)

        assert isinstance(scopes, IndexScopes)
        assert scopes.read_allow == ("skills/**", "docs/**")
        assert scopes.deny == ("docs/private/**", "**/.venv/**")
        assert scopes.allows("skills/implement-feature/SKILL.md") is True
        assert scopes.allows("docs/guides/workflow.md") is True
        # Deny wins over an overlapping read-allow glob...
        assert scopes.allows("docs/private/secret.md") is False
        assert scopes.allows("skills/.venv/lib/mod.py") is False
        # ...and anything outside read_allow was never permitted to begin with.
        assert scopes.allows("agent-coordinator/src/app.py") is False

    def test_the_workflow_supplies_that_scope_to_the_checkpoint(
        self, tmp_path: Path
    ) -> None:
        """The report and the indexer both carry the package's own globs."""
        package = _package(
            scope={
                "read_allow": ["skills/**", "docs/**"],
                "write_allow": ["skills/**", "docs/**"],
                "deny": ["docs/private/**"],
            }
        )
        factory = _RecordingIndexerFactory()

        result = checkpoint.run_checkpoint(
            tmp_path,
            change_id=CHANGE_ID,
            package_id=PACKAGE_ID,
            package=package,
            changed_files=INVALIDATING_FILES,
            revision=REVISION,
            rules=_rules(),
            producer_ids=(),
            architecture=lambda _repo, _base: checkpoint.ArchitectureFinding(
                freshness=checkpoint.FRESHNESS_UNKNOWN
            ),
            indexer_factory=factory,
            write=False,
        )

        assert result.report["scope"] == {
            "read_allow": ["skills/**", "docs/**"],
            "deny": ["docs/private/**"],
        }
        assert factory.scope == ReadScope(
            read_allow=("skills/**", "docs/**"), deny=("docs/private/**",)
        )
        # Branch-local namespace, never the canonical one (D4).
        assert factory.namespace.kind == "work_package"
        assert factory.namespace.key == f"{CHANGE_ID}--{PACKAGE_ID}"

    def test_a_denied_glob_is_never_offered_to_the_indexer_as_readable(
        self, tmp_path: Path
    ) -> None:
        """Deny beats an identical read-allow glob on the way into the indexer."""
        package = _package(
            scope={
                "read_allow": ["skills/**", "docs/**"],
                "write_allow": ["skills/**", "docs/**"],
                "deny": ["docs/**"],
            }
        )
        factory = _RecordingIndexerFactory()

        checkpoint.run_checkpoint(
            tmp_path,
            change_id=CHANGE_ID,
            package_id=PACKAGE_ID,
            package=package,
            changed_files=INVALIDATING_FILES,
            revision=REVISION,
            rules=_rules(),
            producer_ids=(),
            architecture=lambda _repo, _base: checkpoint.ArchitectureFinding(
                freshness=checkpoint.FRESHNESS_UNKNOWN
            ),
            indexer_factory=factory,
            write=False,
        )

        assert factory.scope is not None
        assert "docs/**" not in factory.scope.read_allow
        assert "docs/**" in factory.scope.deny
