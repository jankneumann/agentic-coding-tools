"""Tests for deployable-surface-conditional required phases (issue #432).

A skills-only change must produce a validation-report.md and pass the
pre-merge gate without --force. Container-dependent phases (smoke,
security, E2E) are not applicable, not skipped. A change that touches a
deployable service still requires those phases. Ambiguity fails closed.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from gate_logic import (  # noqa: E402
    REQUIRED_PHASES,
    check_phase_status,
    classify_deployable_surface,
    pre_merge_gate,
    resolve_required_phases,
)

_SPEC_PASS = "## Spec Compliance\n\n- **Status**: pass\n"
_CONTAINER_PASS = (
    "## Smoke Tests\n\n- **Status**: pass\n\n"
    "## Security\n\n- **Status**: pass\n\n"
    "## E2E Tests\n\n- **Status**: pass\n"
)
_CONTAINER_N_A = (
    "## Smoke Tests\n\n- **Status**: not applicable\n"
    "- **Reason**: no deployable surface\n\n"
    "## Security\n\n- **Status**: not applicable\n"
    "- **Reason**: no deployable surface\n\n"
    "## E2E Tests\n\n- **Status**: not applicable\n"
    "- **Reason**: no deployable surface\n"
)


def _write_change_dir(
    tmp_path: Path,
    *,
    deployable: bool | None = None,
    work_packages: bool = False,
) -> Path:
    change_dir = tmp_path / "openspec" / "changes" / "demo"
    change_dir.mkdir(parents=True)
    if work_packages or deployable is not None:
        feature = "id: demo\n  plan_revision: 1\n"
        if deployable is not None:
            feature += f"  deployable: {'true' if deployable else 'false'}\n"
        (change_dir / "work-packages.yaml").write_text(
            "schema_version: 1\n"
            f"feature:\n  {feature}"
            "contracts:\n  revision: 1\n  openapi:\n    primary: x.yaml\n"
            "    files: [x.yaml]\n"
            "packages: []\n",
            encoding="utf-8",
        )
    return change_dir


class TestClassifyDeployableSurface:
    def test_declared_false_wins(self, tmp_path: Path) -> None:
        change_dir = _write_change_dir(tmp_path, deployable=False)
        surface = classify_deployable_surface(
            change_dir=change_dir,
            changed_files=["agent-coordinator/src/api.py"],
        )
        assert surface.deployable is False
        assert surface.source == "declared"

    def test_declared_true_wins_over_skills_paths(self, tmp_path: Path) -> None:
        change_dir = _write_change_dir(tmp_path, deployable=True)
        surface = classify_deployable_surface(
            change_dir=change_dir,
            changed_files=["skills/validate-feature/SKILL.md"],
        )
        assert surface.deployable is True
        assert surface.source == "declared"

    def test_skills_only_paths_are_not_deployable(self) -> None:
        surface = classify_deployable_surface(
            changed_files=[
                "skills/validate-feature/SKILL.md",
                "docs/guides/workflow.md",
                "openspec/changes/demo/proposal.md",
            ]
        )
        assert surface.deployable is False
        assert surface.source == "derived"

    def test_dot_directory_paths_are_not_deployable(self) -> None:
        surface = classify_deployable_surface(
            changed_files=[
                ".github/workflows/ci.yml",
                ".agents/skills/example/SKILL.md",
                ".githooks/pre-commit",
            ]
        )
        assert surface.deployable is False
        assert surface.source == "derived"

    def test_agent_coordinator_path_is_deployable(self) -> None:
        surface = classify_deployable_surface(
            changed_files=["agent-coordinator/src/coordination_api.py"]
        )
        assert surface.deployable is True
        assert surface.source == "derived"

    def test_ambiguous_path_fails_closed(self) -> None:
        surface = classify_deployable_surface(changed_files=["install.sh"])
        assert surface.deployable is True
        assert surface.source == "unknown"

    def test_no_files_and_no_declaration_fails_closed(self) -> None:
        surface = classify_deployable_surface()
        assert surface.deployable is True
        assert surface.source == "unknown"


class TestResolveRequiredPhasesBySurface:
    def test_skills_only_omits_container_phases(self) -> None:
        surface = classify_deployable_surface(
            changed_files=["skills/foo/SKILL.md"]
        )
        phases = resolve_required_phases(surface=surface)
        assert "Smoke Tests" not in phases
        assert "Security" not in phases
        assert "E2E Tests" not in phases
        assert "Spec Compliance" in phases

    def test_deployable_keeps_container_phases(self) -> None:
        surface = classify_deployable_surface(
            changed_files=["packages/gen-eval/src/cli.py"]
        )
        phases = resolve_required_phases(surface=surface)
        assert set(REQUIRED_PHASES) <= set(phases)
        assert "Spec Compliance" in phases

    def test_unknown_fails_closed_to_container_phases(self) -> None:
        phases = resolve_required_phases()
        assert set(REQUIRED_PHASES) <= set(phases)

    def test_work_packages_keep_evidence_non_blocking(self, tmp_path: Path) -> None:
        change_dir = _write_change_dir(tmp_path, deployable=False, work_packages=True)
        surface = classify_deployable_surface(change_dir=change_dir)
        phases = resolve_required_phases(surface=surface, change_dir=change_dir)
        assert "Evidence" not in phases
        assert "Smoke Tests" not in phases


class TestNotApplicableStatus:
    def test_parses_not_applicable(self, tmp_path: Path) -> None:
        report = tmp_path / "validation-report.md"
        report.write_text(
            "## Smoke Tests\n\n- **Status**: not applicable\n"
            "- **Reason**: no deployable surface\n"
        )
        assert check_phase_status(str(report), "Smoke Tests") == "not_applicable"


class TestPreMergeGateBySurface:
    def test_skills_only_passes_without_container_phases(
        self, tmp_path: Path
    ) -> None:
        report = tmp_path / "validation-report.md"
        report.write_text(_SPEC_PASS + "\n" + _CONTAINER_N_A)
        action, reason, statuses = pre_merge_gate(
            str(report),
            changed_files=["skills/validate-feature/SKILL.md"],
        )
        assert action == "continue"
        assert "Smoke Tests" not in statuses
        assert statuses["Spec Compliance"] == "pass"
        assert "not applicable" not in reason.lower() or "skipped" not in reason.lower()

    def test_skills_only_does_not_need_force(self, tmp_path: Path) -> None:
        report = tmp_path / "validation-report.md"
        report.write_text(_SPEC_PASS)
        action, _reason, _statuses = pre_merge_gate(
            str(report),
            changed_files=["docs/guides/workflow.md", "openspec/specs/x/spec.md"],
        )
        assert action == "continue"

    def test_deployable_change_still_halts_on_missing_smoke(
        self, tmp_path: Path
    ) -> None:
        report = tmp_path / "validation-report.md"
        report.write_text(_SPEC_PASS)
        action, reason, statuses = pre_merge_gate(
            str(report),
            changed_files=["agent-coordinator/src/coordination_api.py"],
        )
        assert action == "halt"
        assert "Smoke tests: missing" in reason
        assert statuses["Smoke Tests"] == "missing"

    def test_unknown_surface_requires_container_phases(self, tmp_path: Path) -> None:
        report = tmp_path / "validation-report.md"
        report.write_text(_SPEC_PASS)
        action, reason, _statuses = pre_merge_gate(str(report))
        assert action == "halt"
        assert "Smoke tests: missing" in reason

    def test_force_still_overrides(self, tmp_path: Path) -> None:
        report = tmp_path / "validation-report.md"
        report.write_text(_SPEC_PASS)
        action, reason, _statuses = pre_merge_gate(
            str(report),
            force=True,
            changed_files=["agent-coordinator/src/api.py"],
        )
        assert action == "continue"
        assert "FORCED OVERRIDE" in reason
