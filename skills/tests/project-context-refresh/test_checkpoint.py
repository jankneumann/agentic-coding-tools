"""Core behaviour of the branch-local context checkpoint (ri-09 tasks 3.2-3.5).

Spec scenarios: pcro "Tracked producer outputs are unchanged by a checkpoint",
pcro "Producers are invoked in check mode", pcro "Repeated checkpoints at one
revision produce no diff", pcro "Report validates against the checkpoint
schema", pcro "Missing index configuration degrades the checkpoint", pcro
"Index error does not discard deterministic findings", pcro "Detected drift does
not fail the checkpoint".

Design decisions: D2 (the ri-08 trigger, and ``unmigrated`` reported explicitly),
D3 (check mode only), D7 (byte-stable, change-local report), D8 (drift is data),
D9 (a degradable index).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

import checkpoint
from _runtime import (
    Fallback,
    FallbackKind,
    ProducerResult,
    ProducerStatus,
    Remediation,
    ValidationResult,
    ValidationStatus,
)
from models import SemanticIndexStatus
from registry import Producer, ProducerSpec, register

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECKPOINT_SCHEMA = (
    _REPO_ROOT
    / "skills"
    / "project-context-refresh"
    / "install_assets"
    / "openspec"
    / "schemas"
    / "context-checkpoint.schema.json"
)
_TYPES_SCHEMA = (
    _REPO_ROOT
    / "skills"
    / "project-context-runtime"
    / "install_assets"
    / "openspec"
    / "schemas"
    / "context-refresh-types.schema.json"
)

CHANGE_ID = "add-branch-local-context-checkpoints"
PACKAGE_ID = "wp-checkpoint"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _rules() -> Any:
    """A minimal, self-contained ri-08 rule table.

    Built in-process rather than loaded from ``openspec/schemas`` so these tests
    pin checkpoint behaviour rather than the repository's live rule table.
    """
    from context_impact import ImpactRules

    return ImpactRules(
        surface_globs={
            "documentation": ("docs/**", "**/*.md"),
            "semantic_code": ("**/*.py",),
        },
        source=Path("test-rules.yaml"),
    )


def _package(**overrides: Any) -> dict[str, Any]:
    package: dict[str, Any] = {
        "package_id": PACKAGE_ID,
        "scope": {
            "read_allow": ["skills/project-context-refresh/**", "docs/**"],
            "write_allow": ["docs/**", "skills/project-context-refresh/**"],
            "deny": ["**/.venv/**"],
        },
        "context_impact": {"surfaces": ["documentation", "semantic_code"]},
    }
    package.update(overrides)
    return package


CHANGED_FILES = ("docs/guide.md", "skills/project-context-refresh/scripts/checkpoint.py")


def _git_repo(tmp_path: Path) -> tuple[Path, str]:
    """Initialise a repository with one commit; return ``(root, head_sha)``."""
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    for key, value in (("user.email", "t@example.com"), ("user.name", "T")):
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", key, value],
            check=True,
            capture_output=True,
        )
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "guide.md").write_text("committed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-m", "init"],
        check=True,
        capture_output=True,
    )
    head = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return tmp_path, head


class _RecordingRunner:
    """A ``registry.run_producer`` stand-in that records every dispatch."""

    def __init__(self, *, status: ProducerStatus = ProducerStatus.FRESH) -> None:
        self.calls: list[tuple[str, str]] = []
        self._status = status

    def __call__(
        self, producer_id: str, mode: str, repository: Path, source_revision: str
    ) -> ProducerResult:
        self.calls.append((producer_id, mode))
        if self._status is ProducerStatus.FRESH:
            return ProducerResult(
                producer_id=producer_id,
                producer_version="1.0.0",
                status=ProducerStatus.FRESH,
                validations=(
                    ValidationResult(
                        validation_id=f"{producer_id}-check",
                        status=ValidationStatus.PASSED,
                        summary="clean",
                    ),
                ),
            )
        return ProducerResult(
            producer_id=producer_id,
            producer_version="1.0.0",
            status=ProducerStatus.DEGRADED,
            remediation=(Remediation(summary="regenerate the managed output"),),
            fallback=Fallback(kind=FallbackKind.CUSTOM, reason="check mode wrote nothing"),
        )

    @property
    def modes(self) -> set[str]:
        return {mode for _pid, mode in self.calls}


def _run(
    repo: Path,
    revision: str,
    *,
    runner: Any,
    package: dict[str, Any] | None = None,
    changed_files: tuple[str, ...] = CHANGED_FILES,
    **kwargs: Any,
) -> Any:
    return checkpoint.run_checkpoint(
        repo,
        change_id=CHANGE_ID,
        package_id=PACKAGE_ID,
        package=package if package is not None else _package(),
        changed_files=changed_files,
        revision=revision,
        rules=_rules(),
        producer_ids=("documentation.inventory", "api.contracts"),
        producer_runner=runner,
        **kwargs,
    )


def _validator() -> Draft202012Validator:
    schema = json.loads(_CHECKPOINT_SCHEMA.read_text(encoding="utf-8"))
    types = json.loads(_TYPES_SCHEMA.read_text(encoding="utf-8"))
    registry = Registry().with_resources(
        [
            (doc["$id"], Resource.from_contents(doc, default_specification=DRAFT202012))
            for doc in (schema, types)
        ]
    )
    return Draft202012Validator(schema, registry=registry)


def _tree_digest(root: Path, *, skip: Path) -> dict[str, str]:
    """SHA-256 of every file under *root*, excluding ``.git`` and *skip*."""
    digests: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if ".git" in path.relative_to(root).parts:
            continue
        if skip in path.parents or path == skip:
            continue
        digests[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


# --------------------------------------------------------------------------- #
# D2 — the trigger decision consumed by implement-feature (wp-workflow)
# --------------------------------------------------------------------------- #
class TestShouldCheckpoint:
    def test_a_context_invalidating_package_is_checkpointed(self) -> None:
        decision = checkpoint.should_checkpoint(
            _package(), CHANGED_FILES, rules=_rules()
        )
        assert decision.should_run is True
        assert decision.status == "declared"
        assert decision.surfaces == ("documentation", "semantic_code")

    def test_a_missing_block_is_unmigrated_and_never_impact_free(self) -> None:
        package = _package()
        del package["context_impact"]
        decision = checkpoint.should_checkpoint(package, CHANGED_FILES, rules=_rules())

        assert decision.should_run is False
        assert decision.status == "unmigrated"
        # Absence of evidence: the surfaces its files DO imply are still reported,
        # so an unmigrated package can never be mistaken for one asserting no impact.
        assert decision.surfaces == ("documentation", "semantic_code")

    def test_an_explicit_empty_declaration_is_an_assertion_of_no_impact(self) -> None:
        package = _package(context_impact={"surfaces": []})
        decision = checkpoint.should_checkpoint(
            package, ("README.txt",), rules=_rules()
        )
        assert decision.should_run is False
        assert decision.status == "declared"
        assert decision.surfaces == ()

    def test_empty_declaration_and_missing_block_are_distinguishable(self) -> None:
        """The two 'no checkpoint' answers must not collapse into one reason."""
        missing = _package()
        del missing["context_impact"]
        empty = _package(context_impact={"surfaces": []})

        no_files: tuple[str, ...] = ()
        a = checkpoint.should_checkpoint(missing, no_files, rules=_rules())
        b = checkpoint.should_checkpoint(empty, no_files, rules=_rules())

        assert a.should_run is b.should_run is False
        assert a.status != b.status
        assert a.status == "unmigrated"

    def test_a_rationalized_surface_still_produces_a_checkpoint(self) -> None:
        package = _package(
            context_impact={
                "surfaces": ["documentation"],
                "rationale": {
                    "semantic_code": {
                        "reason": "vendored fixture only",
                        "approved_by": "reviewer",
                    }
                },
            }
        )
        decision = checkpoint.should_checkpoint(package, CHANGED_FILES, rules=_rules())
        assert decision.status == "rationalized"
        assert decision.should_run is True

    def test_a_blocking_status_yields_no_checkpoint(self) -> None:
        # `undeclared` fails the ri-08 gate, so it blocks before a checkpoint runs.
        package = _package(context_impact={"surfaces": ["documentation"]})
        decision = checkpoint.should_checkpoint(package, CHANGED_FILES, rules=_rules())
        assert decision.status == "undeclared"
        assert decision.should_run is False

    def test_decision_is_frozen_and_carries_the_wp_workflow_contract(self) -> None:
        decision = checkpoint.should_checkpoint(_package(), CHANGED_FILES, rules=_rules())
        assert isinstance(decision, checkpoint.CheckpointDecision)
        assert isinstance(decision.surfaces, tuple)
        assert decision.reason
        with pytest.raises(Exception):
            decision.should_run = False  # type: ignore[misc]

    def test_every_ri08_surface_is_context_invalidating(self) -> None:
        # A surface added to ri-08 but omitted here would silently stop
        # triggering checkpoints, which is the failure this pins.
        from context_impact import SURFACES

        assert checkpoint.CONTEXT_INVALIDATING_SURFACES == frozenset(SURFACES)


# --------------------------------------------------------------------------- #
# D3 — read-only, check mode only
# --------------------------------------------------------------------------- #
class TestReadOnly:
    def test_producers_are_invoked_in_check_mode_only(self, tmp_path: Path) -> None:
        repo, head = _git_repo(tmp_path)
        runner = _RecordingRunner()
        _run(repo, head, runner=runner)

        assert runner.calls, "no producer was dispatched"
        assert runner.modes == {"check"}
        assert "generate" not in runner.modes

    def test_the_default_dispatch_seam_is_the_ri05_registry(self, tmp_path: Path) -> None:
        """Without an injected runner the checkpoint must go through ri-05."""
        repo, head = _git_repo(tmp_path)
        seen: list[str] = []

        class _Fake(Producer):
            spec = ProducerSpec(
                producer_id="documentation.inventory",
                producer_version="1.0.0",
                owner="docs",
                inputs=("docs/**",),
                outputs=(),
            )

            def run(self, mode, repository, source_revision):  # noqa: ANN001
                seen.append(mode)
                return ProducerResult(
                    producer_id=self.spec.producer_id,
                    producer_version=self.spec.producer_version,
                    status=ProducerStatus.FRESH,
                )

        register(_Fake())
        result = checkpoint.run_checkpoint(
            repo,
            change_id=CHANGE_ID,
            package_id=PACKAGE_ID,
            package=_package(),
            changed_files=CHANGED_FILES,
            revision=head,
            rules=_rules(),
        )
        assert seen == ["check"]
        assert [r["producer_id"] for r in result.report["producer_results"]] == [
            "documentation.inventory"
        ]

    def test_a_dirty_tree_is_left_byte_identical(self, tmp_path: Path) -> None:
        repo, head = _git_repo(tmp_path)
        # Dirty the tree the way a mid-implementation worktree is dirty.
        (repo / "docs" / "guide.md").write_text("uncommitted edit\n", encoding="utf-8")
        (repo / "docs" / "new.md").write_text("brand new\n", encoding="utf-8")

        report_dir = repo / "openspec" / "changes" / CHANGE_ID / "context-checkpoints"
        before = _tree_digest(repo, skip=report_dir)

        _run(repo, head, runner=_RecordingRunner())

        assert _tree_digest(repo, skip=report_dir) == before

    def test_drift_is_recorded_without_failing_the_checkpoint(self, tmp_path: Path) -> None:
        repo, head = _git_repo(tmp_path)
        result = _run(
            repo, head, runner=_RecordingRunner(status=ProducerStatus.DEGRADED)
        )
        statuses = {r["status"] for r in result.report["producer_results"]}

        assert statuses == {"degraded"}
        # D8: deterministic drift is data. Gating belongs to ri-10.
        assert result.report["checkpoint_status"] != "failed"
        assert result.exit_code() == 0


# --------------------------------------------------------------------------- #
# D7 — determinism, location, schema conformance
# --------------------------------------------------------------------------- #
class TestDeterminismAndLocation:
    def test_report_lands_at_the_change_local_tracked_path(self, tmp_path: Path) -> None:
        repo, head = _git_repo(tmp_path)
        result = _run(repo, head, runner=_RecordingRunner())

        assert result.report_path == (
            f"openspec/changes/{CHANGE_ID}/context-checkpoints/{PACKAGE_ID}.json"
        )
        assert (repo / result.report_path).is_file()

    def test_two_runs_at_one_revision_are_byte_identical(self, tmp_path: Path) -> None:
        repo, head = _git_repo(tmp_path)
        first = _run(repo, head, runner=_RecordingRunner())
        first_bytes = (repo / first.report_path).read_bytes()

        second = _run(repo, head, runner=_RecordingRunner())
        second_bytes = (repo / second.report_path).read_bytes()

        assert second_bytes == first_bytes
        assert second.changed is False, "a repeat checkpoint must produce no diff"

    def test_report_carries_no_volatile_field(self, tmp_path: Path) -> None:
        repo, head = _git_repo(tmp_path)
        result = _run(repo, head, runner=_RecordingRunner())
        text = (repo / result.report_path).read_text(encoding="utf-8")

        assert str(repo) not in text, "an absolute path leaked into the report"
        for volatile in ("generated_at", "timestamp", "attempt", "duration"):
            assert volatile not in result.report

    def test_report_is_canonical_json(self, tmp_path: Path) -> None:
        repo, head = _git_repo(tmp_path)
        result = _run(repo, head, runner=_RecordingRunner())
        raw = (repo / result.report_path).read_bytes()

        assert raw.endswith(b"\n")
        assert not raw.endswith(b"\n\n")
        assert json.loads(raw.decode("utf-8")) == json.loads(json.dumps(result.report))

    def test_report_validates_against_the_published_schema(self, tmp_path: Path) -> None:
        repo, head = _git_repo(tmp_path)
        result = _run(repo, head, runner=_RecordingRunner())
        errors = sorted(
            _validator().iter_errors(result.report), key=lambda e: list(e.absolute_path)
        )
        assert errors == [], [e.message for e in errors]

    def test_namespace_is_the_work_package_pair_and_never_canonical(
        self, tmp_path: Path
    ) -> None:
        repo, head = _git_repo(tmp_path)
        result = _run(repo, head, runner=_RecordingRunner())

        assert result.report["namespace"] == {
            "kind": "work_package",
            "key": f"{CHANGE_ID}--{PACKAGE_ID}",
        }

    def test_scope_records_the_package_read_allow_and_deny(self, tmp_path: Path) -> None:
        repo, head = _git_repo(tmp_path)
        result = _run(repo, head, runner=_RecordingRunner())

        assert result.report["scope"] == {
            "read_allow": ["skills/project-context-refresh/**", "docs/**"],
            "deny": ["**/.venv/**"],
        }

    def test_a_blocking_context_impact_status_produces_no_report(
        self, tmp_path: Path
    ) -> None:
        repo, head = _git_repo(tmp_path)
        package = _package(context_impact={"surfaces": ["documentation"]})
        with pytest.raises(checkpoint.CheckpointError, match="undeclared"):
            _run(repo, head, runner=_RecordingRunner(), package=package)
        assert not (
            repo / "openspec" / "changes" / CHANGE_ID / "context-checkpoints"
        ).exists()


# --------------------------------------------------------------------------- #
# D8 / D9 — degradation never discards deterministic findings
# --------------------------------------------------------------------------- #
class TestDegradation:
    def test_missing_index_configuration_degrades_but_succeeds(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo, head = _git_repo(tmp_path)
        for var in (
            "POSTGRES_DSN",
            "PROJECT_CONTEXT_EMBEDDING_MODEL",
            "PROJECT_CONTEXT_EMBEDDING_DIMENSION",
        ):
            monkeypatch.delenv(var, raising=False)

        result = _run(repo, head, runner=_RecordingRunner())
        index = result.report["semantic_index"]

        assert index["status"] == "not-configured"
        assert index["fallback"]["kind"] == "exact-search"
        assert result.report["checkpoint_status"] == "degraded"
        # The deterministic half of the report survives in full.
        assert len(result.report["producer_results"]) == 2
        assert result.exit_code() == 0

    def test_an_index_error_is_a_bounded_reason_not_a_crash(
        self, tmp_path: Path
    ) -> None:
        repo, head = _git_repo(tmp_path)

        def exploding_indexer(repository: Path, revision: str) -> Any:
            raise RuntimeError("coordinator unreachable")

        result = _run(
            repo,
            head,
            runner=_RecordingRunner(),
            indexer_factory=lambda **_kwargs: exploding_indexer,
        )
        index = result.report["semantic_index"]

        assert index["status"] == "failed"
        assert index["fallback"]["kind"] == "exact-search"
        assert len(index["fallback"]["reason"]) <= 300
        assert len(result.report["producer_results"]) == 2
        assert result.exit_code() == 0

    def test_a_working_index_reports_succeeded(self, tmp_path: Path) -> None:
        repo, head = _git_repo(tmp_path)
        from semantic_adapter import SemanticIndexOutcome

        captured: dict[str, Any] = {}

        def factory(**kwargs: Any) -> Any:
            captured.update(kwargs)

            def indexer(repository: Path, revision: str) -> SemanticIndexOutcome:
                return SemanticIndexOutcome(
                    operation_id="op-1",
                    registry_record_id="rec-1",
                    indexed_revision=revision,
                )

            return indexer

        result = _run(repo, head, runner=_RecordingRunner(), indexer_factory=factory)

        assert result.report["semantic_index"]["status"] == "succeeded"
        assert result.report["checkpoint_status"] == "succeeded"
        # D4/D5: the namespace and the resolved read scope reach the indexer.
        assert captured["namespace"].kind == "work_package"
        assert captured["namespace"].key == f"{CHANGE_ID}--{PACKAGE_ID}"
        assert captured["scope"].deny == ("**/.venv/**",)
        assert captured["namespace"].is_canonical is False

    def test_a_self_cancelling_scope_degrades_the_index_rather_than_the_run(
        self, tmp_path: Path
    ) -> None:
        # ReadScope refuses a scope whose deny cancels every read-allow glob,
        # because an empty read_allow means "no restriction" downstream. D9 says
        # the index degrades; it must not take the whole checkpoint with it.
        repo, head = _git_repo(tmp_path)
        package = _package()
        package["scope"] = {
            "read_allow": ["docs/**"],
            "write_allow": ["docs/**", "skills/project-context-refresh/**"],
            "deny": ["docs/**"],
        }
        result = _run(repo, head, runner=_RecordingRunner(), package=package)

        assert result.report["semantic_index"]["status"] == "failed"
        assert result.report["semantic_index"]["fallback"]["kind"] == "exact-search"
        assert len(result.report["producer_results"]) == 2
        assert result.exit_code() == 0

    def test_semantic_index_status_is_a_known_ri06_value(self, tmp_path: Path) -> None:
        repo, head = _git_repo(tmp_path)
        result = _run(repo, head, runner=_RecordingRunner())
        assert result.report["semantic_index"]["status"] in {
            member.value for member in SemanticIndexStatus
        }
