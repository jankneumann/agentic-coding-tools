"""Composed drift gate tests (ri-10 wp-gate tasks 3.1-3.3, design D1/D5/D6/D7).

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
* ``TestLocalReproduction`` — the ``gate`` subcommand and the
  ``context-drift-gate`` Makefile target exist and agree with ``run_gate``.
Producer fixtures are synthetic on purpose. This repository's live producer state
is in flux while a sibling package fixes a ``decisions.timeline`` false positive,
so asserting against real repository drift would pin the tests to noise.
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
_SKILL_ASSETS = (
    _REPO_ROOT
    / "skills"
    / "project-context-refresh"
    / "install_assets"
    / "openspec"
    / "schemas"
)
_RUNTIME_ASSETS = (
    _REPO_ROOT
    / "skills"
    / "project-context-runtime"
    / "install_assets"
    / "openspec"
    / "schemas"
)
_GATE_SCHEMA = _SKILL_ASSETS / "context-drift-gate.schema.json"
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


# --------------------------------------------------------------------------- #
# Task 3.3 — context-impact scoping and usage-error mapping (D7)
# --------------------------------------------------------------------------- #
_WP_A = "openspec/changes/change-a/work-packages.yaml"
_WP_B = "openspec/changes/change-b/work-packages.yaml"


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


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
class _StubProducer(Producer):
    """A registry entry that exists only to supply a canonical owner."""

    def __init__(self, pid: str, owner: str = "stub-owner"):
        self.spec = ProducerSpec(
            producer_id=pid,
            producer_version="1",
            owner=owner,
            inputs=("x",),
            outputs=(),
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
