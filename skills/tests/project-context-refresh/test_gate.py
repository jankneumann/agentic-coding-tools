"""Composed drift gate tests (ri-10 wp-gate tasks 3.1-3.3, design D1/D4/D5/D6/D7).

The gate composes three arms — the deterministic producers via
``orchestrator.check``, architecture freshness via the orchestrator's
architecture seam, and ri-08's context-impact validator over the work-package
files in the diff under test — and adds the one thing none of them expresses: an
exit code derived from ``classify_degradation``'s four disjoint groups rather
than from the collapsed ``OperationState``.

Organised by the requirement each class pins:

* ``TestExitCodes`` — "Gate exit codes derive from the classification": the four
  documented conditions, failure outranking drift, an absent optional owner
  passing alone, and projection drift never blocking (D3/D5).
* ``TestExistingEntryPointsKeepTheirCodes`` — the same producer set that makes the
  gate exit ``0`` still makes ``refresh-check`` exit ``2``. The gate is a third
  caller; it does not redefine anyone else's mapping.
* ``TestReportConformance`` — the report validates against the published
  contract, names every stale artifact individually by repository-relative path,
  is byte-stable, and reports the semantic index as ``not-attempted`` without
  ever constructing an indexer (D1/D6).
* ``TestReadOnly`` — a dirty checkout is byte-identical afterwards, tracked and
  untracked, and no durable operation or manifest is recorded.
* ``TestContextImpact`` — validation is scoped to the work-package files in the
  diff, ``--strict-legacy`` is never passed, ``unmigrated`` never fails, and the
  validator's usage exit code ``2`` maps to the gate's ``1`` (D7).
* ``TestBaseResolution`` — the base name resolves to exactly one revision, that
  revision is recorded in the report, the remote ref wins over a stale local one,
  and one tree yields one verdict across checkout shapes (D1).
* ``TestEventAwareExitCodes`` — "Gate exit codes derive from the classification",
  event half: inherited blocking drift is reported on a ``pull_request`` and
  blocks on ``merge_group`` and ``push``, introduced drift blocks everywhere, an
  omitted event keeps today's verdict, and an event with no rule is an error (D4).
* ``TestCiEventCoverage`` — "Gate event coverage is normative": the job runs on
  all three declared events with no job-level ``if:``, and its shell fragment is
  driven under ``bash -e`` rather than only pattern-matched (D4).
* ``TestLocalReproduction`` — the ``gate`` subcommand and the
  ``context-drift-gate`` Makefile target exist and agree with ``run_gate``,
  including the event CI passes through it.
Producer fixtures are synthetic on purpose. This repository's live producer state
is in flux while a sibling package fixes a ``decisions.timeline`` false positive,
so asserting against real repository drift would pin the tests to noise.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

import cli
import gate
import orchestrator
import results as R
from _runtime import (
    ChangeKind,
    Fallback,
    FallbackKind,
    ProducerResult,
    ProducerStatus,
    Remediation,
    RepositoryArtifact,
    SafeError,
    ValidationResult,
    ValidationStatus,
)
from registry import (
    API_CONTRACTS,
    DOCUMENTATION_INVENTORY,
    OPENSPEC_PROJECTION,
    Producer,
    ProducerSpec,
    register,
)

FULL_SHA = "c" * 40

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RUNTIME_ASSETS = (
    _REPO_ROOT
    / "skills"
    / "project-context-runtime"
    / "install_assets"
    / "openspec"
    / "schemas"
)
# The report is validated against the repository's own published contract -- the
# same file this skill's gate verification runs `check_schema` over -- rather than
# against the copy under project-context-refresh/install_assets/. The two are
# pinned byte-identical by
# skills/tests/install_sh/test_openspec_assets.py::test_skill_assets_match_the_repository_openspec_tree,
# so this reads the same contract from the authoritative side: openspec/ is where
# a change lands, and the shipped asset is the copy that has to follow it.
_GATE_SCHEMA = _REPO_ROOT / "openspec" / "schemas" / "context-drift-gate.schema.json"
_TYPES_SCHEMA = _RUNTIME_ASSETS / "context-refresh-types.schema.json"


# --------------------------------------------------------------------------- #
# Fixtures and builders
# --------------------------------------------------------------------------- #
def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    """Validator wired to a local registry so the sibling ``$ref``s resolve offline."""
    schema = _load(_GATE_SCHEMA)
    Draft202012Validator.check_schema(schema)
    registry = Registry().with_resources(
        [
            (doc["$id"], Resource.from_contents(doc, default_specification=DRAFT202012))
            for doc in (schema, _load(_TYPES_SCHEMA))
        ]
    )
    return Draft202012Validator(schema, registry=registry)


def _fresh(pid: str) -> ProducerResult:
    return R.fresh(
        pid,
        "1",
        validations=[R.passed(f"{pid}-check", "clean")],
    )


def _drift(pid: str, *paths: str) -> ProducerResult:
    return R.drift(
        pid,
        "1",
        artifacts=R.sort_artifacts(
            RepositoryArtifact(
                path=path,
                change=ChangeKind.MODIFIED,
                sha256=hashlib.sha256(path.encode()).hexdigest(),
            )
            for path in paths
        ),
        validations=[R.failed_validation(R.vid(pid, "render"), "would change")],
        remediation=[Remediation(summary=f"re-run {pid}", command=f"make {pid}")],
    )


def _drift_without_artifacts(pid: str, summary: str = "would change") -> ProducerResult:
    return R.drift(
        pid,
        "1",
        artifacts=(),
        validations=[R.failed_validation(R.vid(pid, "render"), summary)],
        remediation=[Remediation(summary=f"re-run {pid}")],
    )


def _not_configured(pid: str) -> ProducerResult:
    return R.not_configured(
        pid,
        "1",
        fallback=Fallback(kind=FallbackKind.SKIP, reason="optional owner absent"),
        remediation=[Remediation(summary=f"install {pid}")],
    )


def _failed(pid: str) -> ProducerResult:
    return R.failed(
        pid,
        "1",
        error=SafeError(error_class="FixtureError", summary="could not render"),
        remediation=[Remediation(summary=f"repair {pid}")],
    )


def _refresh(*producer_results: ProducerResult) -> orchestrator.RefreshResult:
    outcome, _error = orchestrator.decide_outcome(producer_results, None)
    return orchestrator.RefreshResult(
        operation_id=None,
        outcome=outcome,
        producer_results=tuple(producer_results),
        semantic_index=None,
    )


def _checker(*producer_results: ProducerResult):
    """A stand-in for ``orchestrator.check`` returning fixed results."""

    def _run(repository, **_kwargs):  # noqa: ANN001, ANN003
        return _refresh(*producer_results)

    return _run


def _impact_runner(payload: dict[str, Any] | None = None, code: int = 0):
    """A stand-in for the ri-08 validator invocation, recording every argv."""
    calls: list[list[str]] = []

    def _run(argv):  # noqa: ANN001
        calls.append(list(argv))
        return code, json.dumps(payload or {"packages": []})

    _run.calls = calls  # type: ignore[attr-defined]
    return _run


def _run_gate(tmp_path: Path, *producer_results: ProducerResult, **kwargs: Any):
    kwargs.setdefault("revision", FULL_SHA)
    kwargs.setdefault("changed_files", ())
    kwargs.setdefault("check_runner", _checker(*producer_results))
    kwargs.setdefault("context_impact_runner", _impact_runner())
    return gate.run_gate(tmp_path, **kwargs)


# Work-package paths shared by the base-resolution and context-impact suites.
_WP_A = "openspec/changes/change-a/work-packages.yaml"
_WP_B = "openspec/changes/change-b/work-packages.yaml"


# --------------------------------------------------------------------------- #
# Task 3.1 — exit codes derive from the classification (D5)
# --------------------------------------------------------------------------- #
class TestExitCodes:
    def test_all_fresh_exits_zero(self, tmp_path):
        result = _run_gate(tmp_path, _fresh(DOCUMENTATION_INVENTORY))
        assert result.exit_code == 0
        assert result.report["outcome"] == "fresh"

    def test_blocking_drift_exits_two(self, tmp_path):
        result = _run_gate(
            tmp_path, _drift(DOCUMENTATION_INVENTORY, "docs/architecture-analysis/a.md")
        )
        assert result.exit_code == 2
        assert result.report["outcome"] == "drift"
        assert [f["producer_id"] for f in result.report["blocking_drift"]] == [
            DOCUMENTATION_INVENTORY
        ]

    def test_failure_outranks_drift(self, tmp_path):
        result = _run_gate(
            tmp_path,
            _drift(DOCUMENTATION_INVENTORY, "docs/architecture-analysis/a.md"),
            _failed(API_CONTRACTS),
        )
        assert result.exit_code == 1
        assert result.report["outcome"] == "failed"
        # The drift is still reported; the failure only outranks it for the code.
        assert [f["producer_id"] for f in result.report["blocking_drift"]] == [
            DOCUMENTATION_INVENTORY
        ]
        assert [f["producer_id"] for f in result.report["failed"]] == [API_CONTRACTS]

    def test_absent_optional_owner_alone_passes(self, tmp_path):
        result = _run_gate(tmp_path, _not_configured(API_CONTRACTS))
        assert result.exit_code == 0
        assert result.report["outcome"] == "fresh"
        assert [d["producer_id"] for d in result.report["not_configured"]] == [
            API_CONTRACTS
        ]

    def test_projection_drift_alone_passes(self, tmp_path):
        """D3: a repository always has active changes, so this must never block."""
        result = _run_gate(
            tmp_path, _drift(OPENSPEC_PROJECTION, "openspec/specs/x/spec.md")
        )
        assert result.exit_code == 0
        assert result.report["outcome"] == "fresh"
        assert [f["producer_id"] for f in result.report["informational_drift"]] == [
            OPENSPEC_PROJECTION
        ]
        assert result.report["blocking_drift"] == []

    def test_projection_drift_does_not_mask_blocking_drift(self, tmp_path):
        result = _run_gate(
            tmp_path,
            _drift(OPENSPEC_PROJECTION, "openspec/specs/x/spec.md"),
            _drift(DOCUMENTATION_INVENTORY, "docs/architecture-analysis/a.md"),
        )
        assert result.exit_code == 2
        assert [f["producer_id"] for f in result.report["blocking_drift"]] == [
            DOCUMENTATION_INVENTORY
        ]
        assert [f["producer_id"] for f in result.report["informational_drift"]] == [
            OPENSPEC_PROJECTION
        ]

    def test_drift_without_a_named_artifact_is_an_apparatus_failure(self, tmp_path):
        """A drift claim the report cannot name is not a precise artifact list.

        The requirement is that every stale artifact is named individually, so a
        drifted producer with neither artifacts nor declared managed outputs is
        reported as an apparatus failure rather than as unnameable drift.
        """
        result = _run_gate(tmp_path, _drift_without_artifacts("architecture"))
        assert result.exit_code == 1
        assert [d["producer_id"] for d in result.report["failed"]] == ["architecture"]
        assert result.report["blocking_drift"] == []

    def test_unnameable_drift_still_reports_the_producer_s_own_reason(self, tmp_path):
        """Refusing to name an artifact is not a reason to discard the reason.

        The generic "reported drift without naming any artifact" message used to
        *replace* the producer's failed validations, leaving a reader with a
        report that named neither a stale file nor a drift code — the gate's own
        verdict became the least actionable thing in it. The guard stays; the
        diagnostic rides along.
        """
        result = _run_gate(
            tmp_path,
            _drift_without_artifacts("architecture", "INPUT_FINGERPRINT_MISMATCH: inputs moved"),
        )
        reason = result.report["failed"][0]["reason"]
        assert "INPUT_FINGERPRINT_MISMATCH: inputs moved" in reason

    def test_exit_code_field_matches_the_process_exit_code(self, tmp_path):
        for producers, expected in (
            ((_fresh(DOCUMENTATION_INVENTORY),), 0),
            ((_drift(DOCUMENTATION_INVENTORY, "docs/a.md"),), 2),
            ((_failed(DOCUMENTATION_INVENTORY),), 1),
        ):
            result = _run_gate(tmp_path, *producers)
            assert result.exit_code == expected
            assert result.report["exit_code"] == expected


class TestArchitectureBlock:
    def test_missing_provenance_is_unverifiable_and_blocks(self, tmp_path):
        arch = R.drift(
            "architecture",
            "1.0.0",
            artifacts=(
                RepositoryArtifact(
                    path=gate.ARCHITECTURE_PROVENANCE_PATH,
                    change=ChangeKind.DELETED,
                    sha256=None,
                ),
            ),
            validations=[
                R.failed_validation(
                    "architecture-provenance",
                    "PROVENANCE_MISSING: no committed architecture provenance",
                )
            ],
            remediation=[Remediation(summary="make architecture-refresh")],
        )
        result = _run_gate(tmp_path, arch)
        assert result.report["architecture"] == {
            "freshness": "unverifiable",
            "provenance": "missing",
        }
        assert result.exit_code == 2

    def test_absent_owner_degrades_without_blocking(self, tmp_path):
        result = _run_gate(tmp_path, _not_configured("architecture"))
        assert result.report["architecture"]["freshness"] == "not-configured"
        assert result.exit_code == 0

    def test_stale_digests_are_stale_not_unverifiable(self, tmp_path):
        provenance = tmp_path / gate.ARCHITECTURE_PROVENANCE_PATH
        provenance.parent.mkdir(parents=True, exist_ok=True)
        provenance.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
        arch = R.drift(
            "architecture",
            "1.0.0",
            artifacts=(
                RepositoryArtifact(
                    path="docs/architecture-analysis/architecture.graph.json",
                    change=ChangeKind.MODIFIED,
                    sha256="d" * 64,
                ),
            ),
            validations=[
                R.failed_validation(
                    "architecture-ARTIFACT-DIGEST-MISMATCH",
                    "ARTIFACT_DIGEST_MISMATCH: digest differs",
                )
            ],
            remediation=[Remediation(summary="make architecture-refresh")],
        )
        result = _run_gate(tmp_path, arch)
        assert result.report["architecture"] == {
            "freshness": "stale",
            "provenance": "present",
        }
        assert result.exit_code == 2

    def test_malformed_provenance_is_reported_separately(self, tmp_path):
        provenance = tmp_path / gate.ARCHITECTURE_PROVENANCE_PATH
        provenance.parent.mkdir(parents=True, exist_ok=True)
        provenance.write_text("{not json", encoding="utf-8")
        result = _run_gate(tmp_path, _fresh("architecture"))
        assert result.report["architecture"]["provenance"] == "malformed"


class TestExistingEntryPointsKeepTheirCodes:
    """The gate is a third caller with its own mapping (D5)."""

    def test_per_producer_exit_code_mapping_is_unchanged(self):
        assert cli._exit_code(ProducerStatus.FRESH) == 0
        assert cli._exit_code(ProducerStatus.DEGRADED) == 2
        assert cli._exit_code(ProducerStatus.FAILED) == 1
        # not-configured stays 1 here even though the gate treats it as 0.
        assert cli._exit_code(ProducerStatus.NOT_CONFIGURED) == 1

    def test_refresh_check_still_exits_two_where_the_gate_exits_zero(self, tmp_path):
        """The sharpest contrast: same results, deliberately different codes."""
        absent = _not_configured(API_CONTRACTS)
        assert orchestrator.RefreshResult(
            operation_id=None,
            outcome=orchestrator.decide_outcome((absent,), None)[0],
            producer_results=(absent,),
        ).exit_code() == 2
        assert _run_gate(tmp_path, absent).exit_code == 0

    def test_refresh_check_exit_code_for_projection_drift_is_unchanged(self, tmp_path):
        drifted = _drift(OPENSPEC_PROJECTION, "openspec/specs/x/spec.md")
        refresh = _refresh(drifted)
        # refresh-check keeps calling projection drift degraded -> 2 ...
        assert refresh.exit_code() == 2
        # ... while the gate classifies the same result as informational -> 0.
        assert _run_gate(tmp_path, drifted).exit_code == 0


# --------------------------------------------------------------------------- #
# Task 3.2 — report conformance, artifact list, semantic block (D1/D6)
# --------------------------------------------------------------------------- #
class TestReportConformance:
    def test_report_validates_against_the_published_schema(self, tmp_path, validator):
        result = _run_gate(
            tmp_path,
            _drift(
                DOCUMENTATION_INVENTORY,
                "docs/architecture-analysis/skills-inventory.md",
            ),
            _drift(API_CONTRACTS, "docs/architecture-analysis/contracts-inventory.md"),
            _drift(OPENSPEC_PROJECTION, "openspec/specs/x/spec.md"),
            _not_configured("architecture"),
        )
        errors = sorted(
            validator.iter_errors(result.report),
            key=lambda err: list(err.absolute_path),
        )
        assert errors == [], [
            (list(e.absolute_path), e.message) for e in errors
        ]

    def test_every_stale_artifact_is_named_individually(self, tmp_path):
        stale = (
            "docs/architecture-analysis/skills-inventory.md",
            "docs/architecture-analysis/contracts-inventory.md",
        )
        result = _run_gate(tmp_path, _drift(DOCUMENTATION_INVENTORY, *stale))
        finding = result.report["blocking_drift"][0]
        assert finding["artifacts"] == sorted(stale)
        assert result.exit_code == 2
        # A count is not a list: the rendered text names both paths too.
        rendered = gate.render_text(result.report)
        for path in stale:
            assert path in rendered

    def test_findings_carry_the_registry_owner(self, tmp_path):
        register(_StubProducer(DOCUMENTATION_INVENTORY, owner="doc-owner"))
        result = _run_gate(tmp_path, _drift(DOCUMENTATION_INVENTORY, "docs/a.md"))
        assert result.report["blocking_drift"][0]["owner"] == "doc-owner"

    def test_architecture_owner_is_recovered_outside_the_registry(self, tmp_path):
        result = _run_gate(tmp_path, _not_configured("architecture"))
        assert result.report["not_configured"][0]["owner"] == "refresh-architecture"

    def test_report_is_byte_stable(self, tmp_path):
        producers = (
            _drift(DOCUMENTATION_INVENTORY, "docs/b.md", "docs/a.md"),
            _drift(API_CONTRACTS, "docs/c.md"),
        )
        first = _run_gate(tmp_path, *producers).report
        second = _run_gate(tmp_path, *producers).report
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
        # Groups are sorted by producer id, not by arrival order.
        assert [f["producer_id"] for f in first["blocking_drift"]] == sorted(
            [API_CONTRACTS, DOCUMENTATION_INVENTORY]
        )

    def test_source_revision_is_the_evaluated_revision(self, tmp_path):
        result = _run_gate(tmp_path, _fresh(DOCUMENTATION_INVENTORY))
        assert result.report["source_revision"] == FULL_SHA
        assert result.report["schema_version"] == gate.GATE_SCHEMA_VERSION

    def test_semantic_is_reported_not_attempted(self, tmp_path):
        result = _run_gate(tmp_path, _fresh(DOCUMENTATION_INVENTORY))
        assert result.report["semantic"]["status"] == "not-attempted"
        assert result.report["semantic"]["reason"].strip()
        assert len(result.report["semantic"]["reason"]) <= 300

    def test_no_indexer_is_constructed_even_with_full_configuration(
        self, tmp_path, monkeypatch
    ):
        """D6: the gate never probes, so complete configuration changes nothing."""
        import semantic_adapter

        monkeypatch.setenv("POSTGRES_DSN", "postgresql://postgres:postgres@localhost/x")
        monkeypatch.setenv("PROJECT_CONTEXT_EMBEDDING_MODEL", "test-model")
        monkeypatch.setenv("PROJECT_CONTEXT_EMBEDDING_DIMENSION", "8")
        assert semantic_adapter.semantic_index_configuration() is not None

        def _boom(*args, **kwargs):  # noqa: ANN002, ANN003
            raise AssertionError("the gate constructed a semantic indexer")

        monkeypatch.setattr(semantic_adapter, "default_semantic_indexer", _boom)
        monkeypatch.setattr(semantic_adapter, "build_subprocess_indexer", _boom)
        monkeypatch.setattr(semantic_adapter, "resolve_semantic_index", _boom)
        monkeypatch.setattr(orchestrator, "resolve_semantic_index", _boom)

        result = _run_gate(tmp_path, _fresh(DOCUMENTATION_INVENTORY))
        assert result.report["semantic"] == {
            "status": "not-attempted",
            "reason": gate.SEMANTIC_NOT_ATTEMPTED_REASON,
        }
        # And the semantic status never gates.
        assert result.exit_code == 0


class TestReadOnly:
    def test_gate_leaves_a_dirty_checkout_byte_identical(self, tmp_path):
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        register(_StubProducer(DOCUMENTATION_INVENTORY))
        tracked = tmp_path / "tracked.md"
        tracked.write_text("committed\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "tracked.md"],
            check=True,
            capture_output=True,
        )
        # Deliberately dirty: an uncommitted edit plus an untracked scratch file.
        tracked.write_text("uncommitted edit\n", encoding="utf-8")
        (tmp_path / "scratch.txt").write_text("untracked\n", encoding="utf-8")

        before = _digest_tree(tmp_path)
        result = gate.run_gate(
            tmp_path,
            revision=FULL_SHA,
            changed_files=(),
            architecture=lambda repo, rev, mode: _not_configured("architecture"),
            context_impact_runner=_impact_runner(),
        )
        after = _digest_tree(tmp_path)

        assert before == after
        assert not (tmp_path / ".git-context").exists()
        assert result.report["exit_code"] in (0, 1, 2)


class TestTreeIdentification:
    """Issue #385 — the report names the exact tree the verdict applies to.

    A green local run and a red CI run at "the same revision" turned out to be
    two different trees (a checkout 59 commits behind the tested tip). The
    verdict itself was right both times; what was missing was the report saying
    which tree it graded, so the divergence read as gate nondeterminism.
    """

    @staticmethod
    def _commit(repo: Path, message: str) -> str:
        subprocess.run(
            [
                "git", "-C", str(repo),
                "-c", "user.email=gate@test", "-c", "user.name=gate",
                "commit", "--allow-empty", "-m", message,
            ],
            check=True, capture_output=True,
        )
        head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        )
        return head.stdout.strip()

    def test_non_git_tree_falls_back_to_the_explicit_revision(self, tmp_path):
        result = _run_gate(tmp_path, _fresh(DOCUMENTATION_INVENTORY))
        tree = result.report["tree"]
        assert tree["head"] == FULL_SHA
        assert tree["dirty"] is False
        assert tree["base"] == gate.DEFAULT_BASE
        assert tree["base_upstream"] is None
        assert tree["commits_behind_base_upstream"] is None
        assert tree["commits_ahead_of_base_upstream"] is None

    def test_clean_tree_renders_without_warning(self, tmp_path):
        result = _run_gate(tmp_path, _fresh(DOCUMENTATION_INVENTORY))
        text = gate.render_text(result.report)
        assert "tree:" in text
        assert "[WARN]" not in text

    def test_dirty_checkout_is_named_and_warned(self, tmp_path):
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        self._commit(tmp_path, "base")
        # Untracked content counts: producers render from the live filesystem,
        # so an untracked skills/<new>/SKILL.md is part of the graded tree.
        (tmp_path / "scratch.txt").write_text("untracked\n", encoding="utf-8")
        result = _run_gate(tmp_path, _fresh(DOCUMENTATION_INVENTORY))
        assert result.report["tree"]["dirty"] is True
        text = gate.render_text(result.report)
        assert "uncommitted changes" in text
        assert "[WARN]" in text

    def test_head_behind_base_upstream_is_counted_and_warned(self, tmp_path):
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        first = self._commit(tmp_path, "one")
        second = self._commit(tmp_path, "two")
        subprocess.run(
            ["git", "-C", str(tmp_path), "update-ref", "refs/remotes/origin/main", second],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "checkout", "--detach", first],
            check=True, capture_output=True,
        )
        result = _run_gate(tmp_path, _fresh(DOCUMENTATION_INVENTORY))
        tree = result.report["tree"]
        assert tree["head"] == first
        assert tree["base_upstream"] == "origin/main"
        assert tree["commits_behind_base_upstream"] == 1
        assert tree["commits_ahead_of_base_upstream"] == 0
        text = gate.render_text(result.report)
        assert "1 commit(s) behind origin/main" in text
        assert "[WARN]" in text

    def test_report_with_tree_block_validates(self, tmp_path, validator):
        result = _run_gate(tmp_path, _fresh(DOCUMENTATION_INVENTORY))
        assert list(validator.iter_errors(result.report)) == []


# --------------------------------------------------------------------------- #
# Task 1.1-1.3 — the base name resolves to exactly one revision (D1)
# --------------------------------------------------------------------------- #
class TestBaseResolution:
    """A base NAME is not a revision, and the report has to say which one it used.

    ``origin/main`` and a local ``main`` branch name the same thing right up until
    the local ref falls behind, at which point they name two different trees. The
    gate used to consult both in a single run -- the changed-file diff against the
    raw name, ``describe_tree`` against ``origin/<base>`` -- so one report could
    state ``commits_behind_base_upstream: 0`` beside 53 changed files, and one tree
    could be green in CI (fresh checkout, no local ``main``) and red locally (local
    ``main`` dozens of commits behind). Resolution order is ``origin/<base>``, then
    the local ref: a fresh ``actions/checkout`` has no local base branch, so CI is
    already effectively on the remote.
    """

    @staticmethod
    def _git(repo: Path, *args: str) -> str:
        completed = subprocess.run(
            [
                "git", "-C", str(repo),
                "-c", "user.email=gate@test", "-c", "user.name=gate",
                *args,
            ],
            check=True, capture_output=True, text=True,
        )
        return completed.stdout.strip()

    @classmethod
    def _commit(cls, repo: Path, message: str, files: dict[str, str]) -> str:
        for rel, content in files.items():
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        cls._git(repo, "add", "-A")
        cls._git(repo, "commit", "-m", message)
        return cls._git(repo, "rev-parse", "HEAD")

    @classmethod
    def _origin(cls, root: Path) -> dict[str, str]:
        """One upstream: ``main`` advances by one commit, ``feature`` branches off its tip."""
        subprocess.run(
            ["git", "init", "-b", "main", str(root)], check=True, capture_output=True
        )
        older = cls._commit(root, "older base", {"README.md": "one\n"})
        base = cls._commit(root, "base tip", {"README.md": "two\n"})
        cls._git(root, "checkout", "-b", "feature")
        branch = cls._commit(
            root, "branch work", {_WP_A: "schema_version: 1\npackages: []\n"}
        )
        return {"older": older, "base": base, "branch": branch}

    @classmethod
    def _checkout(cls, origin: Path, dest: Path, *, stale_local_base: str | None) -> Path:
        """One checkout of *origin* at ``feature``, optionally with a trailing local base.

        ``stale_local_base=None`` is the fresh ``actions/checkout`` shape: the only
        thing naming the base is ``refs/remotes/origin/main``.
        """
        subprocess.run(
            ["git", "clone", "--branch", "feature", str(origin), str(dest)],
            check=True, capture_output=True,
        )
        if stale_local_base is not None:
            cls._git(dest, "branch", "main", stale_local_base)
        return dest

    def test_resolved_base_revision_is_recorded_in_the_report(self, tmp_path):
        """Scenario "Resolved base is recorded": the revision is readable without git."""
        revisions = self._origin(tmp_path / "origin")
        checkout = self._checkout(
            tmp_path / "origin", tmp_path / "work", stale_local_base=None
        )

        result = _run_gate(
            checkout, _fresh(DOCUMENTATION_INVENTORY), changed_files=None
        )

        tree = result.report["tree"]
        assert tree["base_resolved_revision"] == revisions["base"]
        assert tree["base_resolved_from"] == "remote"

    def test_unresolvable_base_is_recorded_as_null_rather_than_guessed(self, tmp_path):
        """A shallow or detached checkout is not an apparatus failure; it is an absent base."""
        result = _run_gate(tmp_path, _fresh(DOCUMENTATION_INVENTORY))

        tree = result.report["tree"]
        assert tree["base_resolved_revision"] is None
        assert tree["base_resolved_from"] is None

    def test_remote_ref_wins_over_a_stale_local_base(self, tmp_path):
        """The local ``main`` trails its remote, and the remote is what the run uses."""
        revisions = self._origin(tmp_path / "origin")
        checkout = self._checkout(
            tmp_path / "origin", tmp_path / "work", stale_local_base=revisions["older"]
        )
        runner = _impact_runner({"packages": []})

        result = _run_gate(
            checkout,
            _fresh(DOCUMENTATION_INVENTORY),
            changed_files=None,
            context_impact_runner=runner,
        )

        tree = result.report["tree"]
        assert tree["base_resolved_revision"] == revisions["base"]
        assert tree["base_resolved_revision"] != revisions["older"]
        assert tree["base_resolved_from"] == "remote"
        # The diff itself used that revision, not the stale local ref: README.md
        # changed between the local base and the remote base, so its presence in
        # the validator argv would mean the changed-file arm consulted the other ref.
        assert runner.calls, "the context-impact arm never ran"
        assert "README.md" not in runner.calls[0]

    def test_one_tree_yields_one_verdict_across_checkout_shapes(self, tmp_path):
        """The regression pin for the CI-green/local-red split (job 98378668232).

        Same upstream, same branch commit, two checkout shapes. Before the base was
        pinned, the fresh clone's ``git diff main...HEAD`` failed outright and the
        gate graded an empty diff to a clean exit 0, while the checkout with a
        trailing local ``main`` graded a diff that reached back over the base's own
        history and exited 2. One tree, two verdicts.
        """
        revisions = self._origin(tmp_path / "origin")
        undeclared = {
            "packages": [
                _pkg("wp-one", "undeclared", ["apis"], undeclared=["documentation"])
            ]
        }
        shapes = {
            "fresh-clone": None,
            "stale-local-base": revisions["older"],
        }
        reports = {}
        for shape, stale_local_base in shapes.items():
            checkout = self._checkout(
                tmp_path / "origin", tmp_path / shape, stale_local_base=stale_local_base
            )
            result = _run_gate(
                checkout,
                _fresh(DOCUMENTATION_INVENTORY),
                changed_files=None,
                context_impact_runner=_impact_runner(undeclared, code=1),
            )
            reports[shape] = result

        fresh, stale = reports["fresh-clone"], reports["stale-local-base"]
        assert (fresh.exit_code, fresh.report["outcome"]) == (
            stale.exit_code,
            stale.report["outcome"],
        )
        assert fresh.exit_code == 2
        assert fresh.report["context_impact"]["evaluated"] == [_WP_A]
        assert stale.report["context_impact"]["evaluated"] == [_WP_A]
        for report in (fresh.report, stale.report):
            assert report["tree"]["base_resolved_revision"] == revisions["base"]
            assert report["tree"]["base_resolved_from"] == "remote"


# --------------------------------------------------------------------------- #
# Task 2.1-2.3 — drift is attributed inherited or introduced (D2/D3)
# --------------------------------------------------------------------------- #
class TestDriftAttribution:
    """Whose fault is this finding: the branch, or the branch it forked from?

    On a ``pull_request`` event ``actions/checkout`` grades the merge commit, so
    every open PR inherits whatever drift already sits on the integration branch
    -- which is how one stale artifact on ``main`` failed the gate on 12
    unrelated PRs including one-line dependabot bumps. Attribution is a separate
    axis from the four disjoint groups (D3): the groups say how severe a finding
    is, attribution says who owns it.

    The evidence is path-level ancestry, not content (D2):
    ``git diff --name-only <recorded revision>..<merge base> -- <declared inputs>``.
    If a declared input already moved between the revision the producer's output
    was last written at and the merge base, the producer was *already* stale
    there and the finding is inherited; if nothing moved, the base was fresh and
    the branch introduced it. The inference can only fail in the direction of
    calling introduced drift inherited (a file that changed and changed back),
    which is the safe direction for a gate whose bug is false blame.
    """

    @staticmethod
    def _git(repo: Path, *args: str) -> str:
        completed = subprocess.run(
            [
                "git", "-C", str(repo),
                "-c", "user.email=gate@test", "-c", "user.name=gate",
                *args,
            ],
            check=True, capture_output=True, text=True,
        )
        return completed.stdout.strip()

    @classmethod
    def _commit(cls, repo: Path, message: str, files: dict[str, str]) -> str:
        for rel, content in files.items():
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        cls._git(repo, "add", "-A")
        cls._git(repo, "commit", "-m", message)
        return cls._git(repo, "rev-parse", "HEAD")

    @classmethod
    def _repo(cls, root: Path, *, input_moved_on_base: bool) -> dict[str, str]:
        """A branch off ``origin/main``, differing only in what moved on the base.

        Both shapes regenerate the producer's output at the first commit, so its
        recorded revision is the same in each. ``input_moved_on_base`` decides
        whether the *base* advanced over a declared input afterwards, which is
        the single fact attribution reads.
        """
        subprocess.run(
            ["git", "init", "-b", "main", str(root)], check=True, capture_output=True
        )
        regenerated = cls._commit(
            root,
            "regenerate the inventory",
            {"inputs/a.md": "one\n", "out/inventory.md": "rendered from one\n"},
        )
        base = cls._commit(
            root,
            "base advances",
            {"inputs/a.md": "two\n"} if input_moved_on_base else {"README.md": "hi\n"},
        )
        cls._git(root, "update-ref", "refs/remotes/origin/main", base)
        cls._git(root, "checkout", "-b", "feature")
        branch = cls._commit(
            root,
            "branch work",
            {"README.md": "branch\n"} if input_moved_on_base else {"inputs/a.md": "three\n"},
        )
        return {"regenerated": regenerated, "base": base, "branch": branch}

    @staticmethod
    def _register_inventory() -> None:
        register(
            _StubProducer(
                DOCUMENTATION_INVENTORY,
                owner="project-context-refresh",
                inputs=("inputs/*.md",),
                outputs=("out/inventory.md",),
            )
        )

    def test_drift_already_present_at_the_merge_base_is_inherited(self, tmp_path):
        """Scenario "Inherited drift names the integration branch as owner"."""
        self._register_inventory()
        self._repo(tmp_path, input_moved_on_base=True)

        result = _run_gate(
            tmp_path, _drift(DOCUMENTATION_INVENTORY, "out/inventory.md")
        )

        finding = result.report["blocking_drift"][0]
        assert finding["producer_id"] == DOCUMENTATION_INVENTORY
        assert finding["attribution"] == "inherited"
        assert finding["attributed_owner"] == gate.DEFAULT_BASE

    def test_drift_caused_by_the_branch_is_introduced(self, tmp_path):
        """Scenario "Introduced drift is attributed to the branch"."""
        self._register_inventory()
        self._repo(tmp_path, input_moved_on_base=False)

        result = _run_gate(
            tmp_path, _drift(DOCUMENTATION_INVENTORY, "out/inventory.md")
        )

        finding = result.report["blocking_drift"][0]
        assert finding["attribution"] == "introduced"
        assert finding["attributed_owner"] == "feature"

    def test_indeterminate_attribution_resolves_to_inherited(self, tmp_path):
        """Scenario "Ambiguous attribution errs toward inherited".

        A checkout with no resolvable base -- shallow, detached, or simply not a
        git tree -- has no merge base to compare against. That is recorded as
        ``indeterminate`` rather than silently guessed, and the finding is still
        owned by the integration branch, because erring toward inherited is what
        keeps the gate from blaming a branch on absent evidence.
        """
        result = _run_gate(
            tmp_path, _drift(DOCUMENTATION_INVENTORY, "out/inventory.md")
        )

        assert result.report["tree"]["base_resolved_revision"] is None
        finding = result.report["blocking_drift"][0]
        assert finding["attribution"] == "indeterminate"
        assert finding["attributed_owner"] == gate.DEFAULT_BASE
        # Attribution is observable before it is enforced: the verdict is today's.
        assert result.exit_code == 2


# --------------------------------------------------------------------------- #
# Tasks 3.1-3.3, 3.6 — the blocking verdict is event-aware (D4)
# --------------------------------------------------------------------------- #
class TestEventAwareExitCodes:
    """Which findings contribute to the drift exit code depends on the event.

    Attribution says *who owns* a finding; the event says *whether this run is
    the one that must block on it*. On a ``pull_request`` the branch is asked
    only about drift it introduced -- blocking a one-line dependabot bump for a
    stale artifact that was already on ``main`` is the failure this fixes -- so
    inherited blocking drift is reported and does not contribute. On
    ``merge_group`` and on a ``push`` to the integration branch every blocking
    finding contributes, because at those points there is no other branch to
    inherit from: the merge candidate is the tree that is about to become the
    integration branch, and its debt is nobody else's.

    The two axes compose rather than replace each other. A failure still
    outranks drift on every event, and informational drift still blocks nowhere.
    """

    @staticmethod
    def _inventory_drift() -> ProducerResult:
        return _drift(DOCUMENTATION_INVENTORY, "out/inventory.md")

    def test_inherited_only_drift_passes_a_pull_request(self, tmp_path):
        """Scenario "Inherited drift alone does not fail a pull request"."""
        TestDriftAttribution._register_inventory()
        TestDriftAttribution._repo(tmp_path, input_moved_on_base=True)

        result = _run_gate(tmp_path, self._inventory_drift(), event="pull_request")

        assert result.exit_code == 0
        # Reported, not discarded: the finding survives with its owner named, so
        # exit 0 here is a legible "someone else's debt", not a silent pass.
        finding = result.report["blocking_drift"][0]
        assert finding["producer_id"] == DOCUMENTATION_INVENTORY
        assert finding["attribution"] == "inherited"
        assert finding["attributed_owner"] == gate.DEFAULT_BASE
        assert result.report["outcome"] == "drift"

    def test_introduced_drift_fails_a_pull_request(self, tmp_path):
        """Scenario "Introduced drift fails a pull request"."""
        TestDriftAttribution._register_inventory()
        TestDriftAttribution._repo(tmp_path, input_moved_on_base=False)

        result = _run_gate(tmp_path, self._inventory_drift(), event="pull_request")

        assert result.exit_code == 2
        assert result.report["outcome"] == "drift"
        assert result.report["blocking_drift"][0]["attribution"] == "introduced"

    @pytest.mark.parametrize("event", ["merge_group", "push"])
    def test_inherited_drift_blocks_on_the_integration_branch(self, tmp_path, event):
        """Scenario "Inherited drift blocks on the integration branch"."""
        TestDriftAttribution._register_inventory()
        TestDriftAttribution._repo(tmp_path, input_moved_on_base=True)

        result = _run_gate(tmp_path, self._inventory_drift(), event=event)

        assert result.exit_code == 2
        assert result.report["blocking_drift"][0]["attribution"] == "inherited"

    @pytest.mark.parametrize("event", ["pull_request", "merge_group", "push"])
    def test_introduced_drift_blocks_on_every_event(self, tmp_path, event):
        TestDriftAttribution._register_inventory()
        TestDriftAttribution._repo(tmp_path, input_moved_on_base=False)

        result = _run_gate(tmp_path, self._inventory_drift(), event=event)

        assert result.exit_code == 2

    def test_indeterminate_drift_passes_a_pull_request_and_blocks_the_candidate(
        self, tmp_path
    ):
        """The seam where an unfalsifiable green would otherwise appear.

        An unresolvable base makes every finding ``indeterminate``, which
        resolves toward inherited, which on a ``pull_request`` does not
        contribute. That is intended -- but only because the same tree is asked
        again at ``merge_group``, where it blocks. Pinning both halves in one
        test is what keeps the pull-request half from being read as a pass.
        """
        drifted = self._inventory_drift()
        pr = _run_gate(tmp_path, drifted, event="pull_request")
        candidate = _run_gate(tmp_path, drifted, event="merge_group")

        assert pr.report["blocking_drift"][0]["attribution"] == "indeterminate"
        assert pr.exit_code == 0
        assert candidate.report["blocking_drift"][0]["attribution"] == "indeterminate"
        assert candidate.exit_code == 2

    def test_failure_outranks_inherited_drift_on_a_pull_request(self, tmp_path):
        """The event axis never demotes a failure: exit 1 outranks everything."""
        TestDriftAttribution._register_inventory()
        TestDriftAttribution._repo(tmp_path, input_moved_on_base=True)

        result = _run_gate(
            tmp_path, self._inventory_drift(), _failed(API_CONTRACTS), event="pull_request"
        )

        assert result.exit_code == 1
        assert result.report["outcome"] == "failed"

    def test_context_impact_drift_blocks_a_pull_request(self, tmp_path):
        """The context-impact arm is authored by the branch by construction.

        It evaluates only the work-package files present in ``<base>...HEAD``, so
        wherever a base resolves it is attributed ``introduced`` and the
        pull-request rule cannot downgrade it. The repository here is a real one
        for exactly that reason: with no resolvable base every finding is
        ``indeterminate``, which is a different case, pinned separately above.
        """
        TestDriftAttribution._register_inventory()
        TestDriftAttribution._repo(tmp_path, input_moved_on_base=True)
        runner = _impact_runner(
            {"packages": [_pkg("wp-one", "undeclared", ["apis"], undeclared=["decisions"])]}
        )
        result = _run_gate(
            tmp_path,
            _fresh(DOCUMENTATION_INVENTORY),
            changed_files=(_WP_A,),
            context_impact_runner=runner,
            event="pull_request",
        )
        assert result.exit_code == 2
        assert result.report["blocking_drift"][0]["producer_id"] == "context.impact"

    def test_omitting_the_event_keeps_todays_verdict(self, tmp_path):
        """Safe default: no event means every blocking finding contributes.

        Every caller that predates this change -- ``make context-drift-gate``,
        the convergence runner, a developer at a shell -- passes no event and
        must get exactly the verdict it got before. Defaulting the other way
        would turn every local run into the permissive pull-request rule and
        make the strict answer the one nobody sees.
        """
        TestDriftAttribution._register_inventory()
        TestDriftAttribution._repo(tmp_path, input_moved_on_base=True)

        result = _run_gate(tmp_path, self._inventory_drift())

        assert result.exit_code == 2
        assert result.report["blocking_drift"][0]["attribution"] == "inherited"

    @pytest.mark.parametrize(
        "event", ["workflow_dispatch", "schedule", "PULL_REQUEST", ""]
    )
    def test_unhandled_event_fails(self, tmp_path, event):
        """Scenario "Unknown event fails loudly" (task 3.6).

        An event with no rule is an error, never a pass. A gate that quietly
        applied its most permissive rule to an unrecognised trigger would report
        success without having asked the question.
        """
        with pytest.raises(gate.GateError) as excinfo:
            _run_gate(tmp_path, _fresh(DOCUMENTATION_INVENTORY), event=event)

        assert "event" in str(excinfo.value)

    def test_unhandled_event_is_refused_before_any_producer_runs(
        self, tmp_path, capsys, monkeypatch
    ):
        """Through the CLI the refusal is exit 1 -- apparatus failure, not drift.

        Deliberately not argparse ``choices``: argparse exits ``2`` on a rejected
        value, and ``2`` is this gate's drift code. An unrecognised trigger is an
        apparatus failure, so it is validated in the gate and surfaces as ``1``.

        The refusal happens before the deterministic arm runs, which is why the
        check runner here raises: a gate that cannot say what rule applies has
        nothing to learn from running the producers first.
        """

        def _never(repository, **_kwargs):  # noqa: ANN001, ANN003
            raise AssertionError("producers ran under an event with no rule")

        monkeypatch.setattr(gate, "_default_check_runner", _never)
        code = cli.main(
            [
                "--repo", str(tmp_path),
                "--revision", FULL_SHA,
                "gate",
                "--event", "workflow_dispatch",
            ]
        )
        assert code == 1
        assert "workflow_dispatch" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# Task 3.7 — the gate job runs on every declared event (D4)
# --------------------------------------------------------------------------- #
class TestCiEventCoverage:
    """Static assertions over the workflow, because the hazard is a *skip*.

    A required check that does not run reports success to branch protection, so
    "the job is guarded off pull requests" and "the job passed" are
    indistinguishable downstream. The event set therefore has to be normative
    and assertable from the repository, not a CI implementation detail.
    """

    @staticmethod
    def _workflow() -> dict[str, Any]:
        import yaml

        return yaml.safe_load((_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text())

    @classmethod
    def _gate_job(cls) -> dict[str, Any]:
        return cls._workflow()["jobs"]["context-drift-gate"]

    def test_workflow_declares_all_three_events(self):
        workflow = self._workflow()
        # PyYAML 1.1 reads a bare `on:` key as the boolean True.
        triggers = workflow.get("on", workflow.get(True))
        assert set(triggers) == {"push", "pull_request", "merge_group"}
        assert triggers["push"]["branches"] == ["main"]

    def test_gate_job_is_not_conditioned_on_the_event(self):
        assert "if" not in self._gate_job()

    def test_gate_step_dispatches_on_the_event_name(self):
        step = self._gate_step()
        assert step["env"]["EVENT_NAME"] == "${{ github.event_name }}"
        assert 'case "$EVENT_NAME"' in step["run"]
        for event in ("pull_request)", "merge_group)", "push)"):
            assert event in step["run"]

    def test_gate_step_fails_on_an_unhandled_event(self):
        run = self._gate_step()["run"]
        arm = run.split("*)", 1)
        assert len(arm) == 2, "no catch-all arm in the event dispatch"
        assert "exit 1" in arm[1]

    def test_gate_step_passes_the_event_through_the_makefile_target(self):
        run = self._gate_step()["run"]
        assert "make context-drift-gate" in run
        assert "CONTEXT_GATE_EVENT" in run

    @pytest.mark.parametrize("gate_status", [0, 1, 2])
    @pytest.mark.parametrize(
        "event", ["pull_request", "merge_group", "push", "workflow_dispatch"]
    )
    def test_the_dispatch_fragment_behaves_as_specified(
        self, tmp_path, event, gate_status
    ):
        """Drive the step's shell, rather than only asserting on its text.

        Run under ``bash -e``, which is how Actions invokes a ``run:`` step with
        no ``shell:`` key. That is the condition the fragment's own ``set +e``
        exists for: without it the gate's exit 2 would abort the step before the
        ``::error::`` annotation naming the stale artifacts is ever printed.

        ``make`` is stubbed so the assertion is about the dispatch, not about
        this repository's current freshness. Every known event must reach it and
        propagate its status; the unknown event must fail without reaching it,
        because a trigger with no rule is an error and never a pass.
        """
        bash = shutil.which("bash")
        if bash is None:  # pragma: no cover - CI and dev shells both have bash
            pytest.skip("bash is unavailable")

        fragment = tmp_path / "fragment.sh"
        fragment.write_text(self._gate_step()["run"], encoding="utf-8")
        stub = tmp_path / "make"
        stub.write_text(f'#!/bin/sh\necho "make $@"\nexit {gate_status}\n', encoding="utf-8")
        stub.chmod(0o755)

        completed = subprocess.run(
            [bash, "-e", str(fragment)],
            env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "EVENT_NAME": event},
            capture_output=True,
            text=True,
        )

        if event == "workflow_dispatch":
            assert completed.returncode == 1
            assert "unhandled event 'workflow_dispatch'" in completed.stdout
            assert "make context-drift-gate" not in completed.stdout
            return
        assert f"CONTEXT_GATE_EVENT={event}" in completed.stdout
        # Drift (2) and apparatus failure (1) both fail the job, and both are
        # annotated -- the annotation is the only thing a reviewer reads first.
        assert completed.returncode == (0 if gate_status == 0 else 1)
        assert ("::error::" in completed.stdout) is (gate_status != 0)

    # ----------------------------------------------------------------- #
    # The gate's own telemetry row (D7 -- metrics)
    # ----------------------------------------------------------------- #
    # `gate.py` has built a `context_gate` row since wp-metrics and refuses to
    # write it anywhere inside the checkout it grades, so nothing in this
    # repository could name a destination for it and the event type was
    # declared-but-unreachable. The gate's own job is the one place that both
    # runs on every declared event and has somewhere outside the tree to write
    # to, which is why these assertions live beside the event-coverage ones.

    def test_the_gate_step_names_a_metrics_destination(self):
        assert "CONTEXT_GATE_METRICS_PATH" in self._gate_step()["env"], (
            "the gate builds a context_gate row for every run; with no "
            "destination named it is discarded and the event type is unreachable"
        )

    def test_the_metrics_destination_is_runner_scratch_not_the_workspace(self):
        """A destination inside the checkout is refused by the gate itself.

        Leaving the graded tree byte-identical is a ratified scenario, so
        ``emit_gate_metrics`` declines any path under the repository root and
        warns instead of writing. A workspace-relative destination here would
        therefore produce a wire that silently records nothing -- which is the
        failure this pins, not a style preference about paths.
        """
        destination = self._gate_step()["env"]["CONTEXT_GATE_METRICS_PATH"]
        assert re.match(r"^\$\{\{\s*runner\.temp\s*\}\}/", destination), destination
        assert "github.workspace" not in destination
        assert "github.workspace" not in self._upload_step()["with"]["path"]

    def test_the_upload_takes_exactly_what_the_gate_wrote(self):
        assert (
            self._upload_step()["with"]["path"]
            == self._gate_step()["env"]["CONTEXT_GATE_METRICS_PATH"]
        )

    def test_the_upload_survives_a_red_or_crashed_gate(self):
        """The verdict is the product; the row is evidence about the product.

        A gate that exits 2 is the population the inherited-versus-introduced
        split exists to describe, so the failing runs are the ones whose row
        matters most -- ``success()`` would drop exactly those. And a run that
        wrote no row at all (an apparatus failure before the report, or the
        unhandled-event arm) must still fail on the gate's exit code rather than
        on a missing artifact.
        """
        step = self._upload_step()
        assert step["uses"] == "actions/upload-artifact@v7"
        assert step["if"] == "always()"
        assert step["with"]["if-no-files-found"] == "ignore"

    def test_the_artifact_name_cannot_collide(self):
        name = self._upload_step()["with"]["name"]
        for expression in ("github.event_name", "github.run_id", "github.run_attempt"):
            assert expression in name, name

    def test_the_gate_job_asks_for_no_write_grant(self):
        """An artifact upload needs no elevated token.

        The workflow-level grant is ``contents: read`` and the repository's only
        write grant is confined to one unrelated job; telemetry is not a reason
        to widen either.
        """
        assert "permissions" not in self._gate_job()
        workflow = self._workflow()
        assert workflow["permissions"] == {"contents": "read"}
        assert "permissions" not in self._gate_step()
        assert "permissions" not in self._upload_step()

    @classmethod
    def _upload_step(cls) -> dict[str, Any]:
        steps = [
            step
            for step in cls._gate_job()["steps"]
            if str(step.get("uses", "")).startswith("actions/upload-artifact@")
        ]
        assert len(steps) == 1, "expected exactly one telemetry upload step"
        return steps[0]

    @classmethod
    def _gate_step(cls) -> dict[str, Any]:
        steps = [
            step
            for step in cls._gate_job()["steps"]
            if "case" in str(step.get("run", ""))
        ]
        assert len(steps) == 1, "expected exactly one event-dispatching gate step"
        return steps[0]


# --------------------------------------------------------------------------- #
# Task 3.3 — context-impact scoping and usage-error mapping (D7)
# --------------------------------------------------------------------------- #
class TestContextImpact:
    def test_only_work_package_files_in_the_diff_are_validated(self, tmp_path):
        runner = _impact_runner({"packages": [_pkg("wp-one", "declared", ["apis"])]})
        result = _run_gate(
            tmp_path,
            _fresh(DOCUMENTATION_INVENTORY),
            changed_files=(_WP_A, "docs/guide.md", "skills/x/scripts/y.py"),
            context_impact_runner=runner,
        )
        assert result.report["context_impact"]["evaluated"] == [_WP_A]
        # The report stays repository-relative; the validator is handed a path it
        # can open regardless of the process working directory.
        assert [call[0] for call in runner.calls] == [str(tmp_path / _WP_A)]
        assert _WP_B not in json.dumps(result.report)

    def test_unchanged_diff_evaluates_nothing(self, tmp_path):
        runner = _impact_runner()
        result = _run_gate(
            tmp_path,
            _fresh(DOCUMENTATION_INVENTORY),
            changed_files=("docs/guide.md",),
            context_impact_runner=runner,
        )
        assert result.report["context_impact"] == {"evaluated": [], "findings": []}
        assert runner.calls == []

    def test_strict_legacy_is_never_passed(self, tmp_path):
        runner = _impact_runner({"packages": [_pkg("wp-one", "unmigrated", [])]})
        _run_gate(
            tmp_path,
            _fresh(DOCUMENTATION_INVENTORY),
            changed_files=(_WP_A, _WP_B),
            context_impact_runner=runner,
        )
        assert runner.calls, "the validator was never invoked"
        for call in runner.calls:
            assert "--strict-legacy" not in call
        # The full changed-file list is forwarded so surfaces can be inferred.
        assert call.count("--changed-file") == 2

    def test_unmigrated_packages_pass(self, tmp_path):
        runner = _impact_runner(
            {"packages": [_pkg("wp-legacy", "unmigrated", [], implied=["documentation"])]}
        )
        result = _run_gate(
            tmp_path,
            _fresh(DOCUMENTATION_INVENTORY),
            changed_files=(_WP_A,),
            context_impact_runner=runner,
        )
        assert result.exit_code == 0
        assert result.report["context_impact"]["findings"] == [
            {
                "package_id": "wp-legacy",
                "status": "unmigrated",
                "surfaces": ["documentation"],
            }
        ]

    def test_undeclared_surface_blocks_as_drift(self, tmp_path):
        runner = _impact_runner(
            {
                "packages": [
                    _pkg(
                        "wp-one",
                        "undeclared",
                        ["apis"],
                        undeclared=["documentation"],
                    )
                ]
            },
            code=1,
        )
        result = _run_gate(
            tmp_path,
            _fresh(DOCUMENTATION_INVENTORY),
            changed_files=(_WP_A,),
            context_impact_runner=runner,
        )
        assert result.exit_code == 2
        finding = next(
            f
            for f in result.report["blocking_drift"]
            if f["producer_id"] == gate.CONTEXT_IMPACT_PRODUCER_ID
        )
        assert finding["artifacts"] == [_WP_A]
        assert finding["owner"] == gate.CONTEXT_IMPACT_OWNER
        assert result.report["context_impact"]["findings"][0]["status"] == "undeclared"

    def test_validator_usage_error_is_an_apparatus_failure(self, tmp_path):
        """The validator's ``2`` means *usage error*, which collides with drift."""
        runner = _impact_runner({"packages": []}, code=2)
        result = _run_gate(
            tmp_path,
            _fresh(DOCUMENTATION_INVENTORY),
            changed_files=(_WP_A,),
            context_impact_runner=runner,
        )
        assert result.exit_code == 1
        assert result.report["blocking_drift"] == []
        failure = next(
            d
            for d in result.report["failed"]
            if d["producer_id"] == gate.CONTEXT_IMPACT_PRODUCER_ID
        )
        assert _WP_A in failure["reason"]
        assert len(failure["reason"]) <= 300

    def test_unreadable_rule_table_is_an_apparatus_failure(self, tmp_path):
        """End-to-end through the real validator: exit 2, mapped to the gate's 1."""
        wp_dir = tmp_path / "openspec" / "changes" / "change-a"
        wp_dir.mkdir(parents=True)
        (wp_dir / "work-packages.yaml").write_text(
            "schema_version: 1\npackages: []\n", encoding="utf-8"
        )
        broken_rules = tmp_path / "broken-rules.yaml"
        broken_rules.write_text("surfaces: not-a-list\n", encoding="utf-8")

        result = _run_gate(
            tmp_path,
            _fresh(DOCUMENTATION_INVENTORY),
            changed_files=(_WP_A,),
            rules=broken_rules,
            context_impact_runner=None,
        )
        assert result.exit_code == 1
        assert any(
            d["producer_id"] == gate.CONTEXT_IMPACT_PRODUCER_ID
            for d in result.report["failed"]
        )

    def test_report_with_context_impact_findings_validates(self, tmp_path, validator):
        runner = _impact_runner(
            {
                "packages": [
                    _pkg("wp-one", "declared", ["apis", "semantic_code"]),
                    _pkg("wp-legacy", "unmigrated", [], implied=["documentation"]),
                ]
            }
        )
        result = _run_gate(
            tmp_path,
            _fresh(DOCUMENTATION_INVENTORY),
            changed_files=(_WP_A,),
            context_impact_runner=runner,
        )
        assert list(validator.iter_errors(result.report)) == []
        assert [f["package_id"] for f in result.report["context_impact"]["findings"]] == [
            "wp-legacy",
            "wp-one",
        ]

    def test_changed_files_default_to_the_git_diff(self, tmp_path):
        seen: list[tuple[Path, str]] = []

        def _resolver(repository, base):  # noqa: ANN001
            seen.append((repository, base))
            return (_WP_A,)

        runner = _impact_runner({"packages": [_pkg("wp-one", "declared", ["apis"])]})
        result = gate.run_gate(
            tmp_path,
            revision=FULL_SHA,
            base="origin/main",
            check_runner=_checker(_fresh(DOCUMENTATION_INVENTORY)),
            changed_files_resolver=_resolver,
            context_impact_runner=runner,
        )
        assert seen == [(tmp_path, "origin/main")]
        assert result.report["context_impact"]["evaluated"] == [_WP_A]


# --------------------------------------------------------------------------- #
# Task 3.7 — the local reproduction seam
# --------------------------------------------------------------------------- #
class TestLocalReproduction:
    def test_gate_subcommand_emits_the_report_and_the_gate_exit_code(
        self, tmp_path, capsys, monkeypatch
    ):
        drifted = _drift(DOCUMENTATION_INVENTORY, "docs/architecture-analysis/a.md")
        monkeypatch.setattr(gate, "_default_check_runner", _checker(drifted))
        code = cli.main(
            [
                "--repo",
                str(tmp_path),
                "--revision",
                FULL_SHA,
                "gate",
            ]
        )
        report = json.loads(capsys.readouterr().out)
        assert code == 2
        assert report["exit_code"] == 2
        assert report["blocking_drift"][0]["artifacts"] == [
            "docs/architecture-analysis/a.md"
        ]

    def test_makefile_target_reproduces_the_ci_invocation(self):
        makefile = (_REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        assert "context-drift-gate:" in makefile
        target = makefile.split("context-drift-gate:", 1)[1]
        body = target.split("\n.PHONY", 1)[0]
        assert "gate" in body
        assert "--strict-legacy" not in body

    def test_makefile_target_carries_the_event_ci_passes(self):
        """Task 3.8: the event must not break the local/CI equivalence.

        CI hands the target ``CONTEXT_GATE_EVENT``; the target forwards it as
        ``--event``. The forwarding is conditional because the *local* default is
        no event at all -- passing an empty ``--event`` would be an event the
        gate has no rule for, and would turn every bare ``make
        context-drift-gate`` into exit 1.
        """
        makefile = (_REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        body = makefile.split("context-drift-gate:", 1)[1].split("\n.PHONY", 1)[0]
        assert "CONTEXT_GATE_EVENT" in makefile
        assert "$(if $(CONTEXT_GATE_EVENT),--event $(CONTEXT_GATE_EVENT))" in body

    def test_bare_makefile_invocation_passes_no_event(self):
        """``make -n`` is the ground truth for what the local command expands to."""
        completed = subprocess.run(
            ["make", "-n", "context-drift-gate"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "cli.py gate --base main" in completed.stdout
        assert "--event" not in completed.stdout

    def test_makefile_invocation_with_an_event_forwards_it(self):
        completed = subprocess.run(
            ["make", "-n", "context-drift-gate", "CONTEXT_GATE_EVENT=pull_request"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "--event pull_request" in completed.stdout


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
class _StubProducer(Producer):
    """A registry entry that exists only to supply a canonical owner.

    ``inputs``/``outputs`` are overridable because attribution reads them: the
    declared inputs are the pathspec the ancestry diff is taken over, and the
    declared outputs are how the producer's recorded revision is located.
    """

    def __init__(
        self,
        pid: str,
        owner: str = "stub-owner",
        inputs: tuple[str, ...] = ("x",),
        outputs: tuple[str, ...] = (),
    ):
        self.spec = ProducerSpec(
            producer_id=pid,
            producer_version="1",
            owner=owner,
            inputs=inputs,
            outputs=outputs,
        )

    def run(self, mode, repository, source_revision):  # noqa: ANN001
        return ProducerResult(
            producer_id=self.spec.producer_id,
            producer_version="1",
            status=ProducerStatus.FRESH,
            validations=(
                ValidationResult(
                    validation_id=f"{self.spec.producer_id}-check",
                    status=ValidationStatus.PASSED,
                    summary="ok",
                ),
            ),
        )


def _pkg(
    package_id: str,
    status: str,
    declared: list[str],
    *,
    implied: list[str] | None = None,
    undeclared: list[str] | None = None,
    spurious: list[str] | None = None,
) -> dict[str, Any]:
    """One entry of the ri-08 validator's ``--json`` ``packages`` array."""
    return {
        "package_id": package_id,
        "status": status,
        "declared": sorted(declared) if status != "unmigrated" else None,
        "implied": {surface: ["f.py"] for surface in (implied or [])},
        "undeclared": undeclared or [],
        "rationalized": [],
        "spurious": spurious or [],
    }


def _digest_tree(root: Path) -> dict[str, str]:
    """Digest every path under *root*, tracked and untracked, excluding ``.git``."""
    digests: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if ".git" in path.relative_to(root).parts[:1]:
            continue
        rel = str(path.relative_to(root))
        if path.is_dir():
            digests[rel + "/"] = "<dir>"
        else:
            digests[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests
