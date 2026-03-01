"""Tests for DAG scheduler (Phase A preflight)."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml

# Ensure scripts/ is on path for validate_work_packages imports
import sys

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

_SKILL_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SKILL_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPTS_DIR))

from dag_scheduler import (
    DAGScheduler,
    PackageState,
    build_context_slice,
    compute_topo_order,
    prepare_task_submissions,
    validate_contracts_exist,
)


# --- Fixtures ---


def _make_package(
    pid: str,
    depends_on: list[str] | None = None,
    priority: int = 5,
    task_type: str = "implement",
    write_allow: list[str] | None = None,
    lock_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Create a minimal valid work package dict."""
    return {
        "package_id": pid,
        "title": f"Package {pid}",
        "task_type": task_type,
        "description": f"Test package {pid}",
        "priority": priority,
        "depends_on": depends_on or [],
        "locks": {
            "files": [],
            "keys": lock_keys or [],
        },
        "scope": {
            "write_allow": write_allow or [f"src/{pid}/**"],
            "read_allow": ["src/**"],
        },
        "worktree": {"name": pid},
        "timeout_minutes": 60,
        "retry_budget": 1,
        "min_trust_level": 2,
        "verification": {
            "tier_required": "A",
            "steps": [
                {
                    "name": "test",
                    "kind": "command",
                    "command": "pytest",
                    "evidence": {"artifacts": [], "result_keys": ["test_count"]},
                }
            ],
        },
        "outputs": {"result_keys": ["files_modified"]},
    }


def _make_work_packages_data(
    packages: list[dict[str, Any]],
    feature_id: str = "test-feature",
) -> dict[str, Any]:
    """Create a full work-packages.yaml data structure."""
    return {
        "schema_version": 1,
        "feature": {
            "id": feature_id,
            "title": "Test Feature",
            "plan_revision": 1,
        },
        "contracts": {
            "revision": 1,
            "openapi": {
                "primary": "contracts/openapi/v1.yaml",
                "files": ["contracts/openapi/v1.yaml"],
            },
        },
        "packages": packages,
    }


@pytest.fixture
def linear_dag() -> list[dict[str, Any]]:
    """A -> B -> C linear chain."""
    return [
        _make_package("wp-a"),
        _make_package("wp-b", depends_on=["wp-a"]),
        _make_package("wp-c", depends_on=["wp-b"]),
    ]


@pytest.fixture
def diamond_dag() -> list[dict[str, Any]]:
    """Diamond: contracts -> backend + frontend -> integration."""
    return [
        _make_package("wp-contracts", task_type="contracts", priority=1),
        _make_package(
            "wp-backend",
            depends_on=["wp-contracts"],
            write_allow=["src/api/**"],
            lock_keys=["api:GET /v1/users"],
        ),
        _make_package(
            "wp-frontend",
            depends_on=["wp-contracts"],
            write_allow=["src/frontend/**"],
            lock_keys=["event:user.created"],
        ),
        _make_package(
            "wp-integration",
            depends_on=["wp-backend", "wp-frontend"],
            task_type="integrate",
            write_allow=["**"],
        ),
    ]


@pytest.fixture
def sample_yaml(tmp_path: Path, diamond_dag: list[dict[str, Any]]) -> Path:
    """Write a valid work-packages.yaml to tmp_path and create contract file."""
    data = _make_work_packages_data(diamond_dag)
    yaml_path = tmp_path / "work-packages.yaml"
    yaml_path.write_text(yaml.dump(data, default_flow_style=False))
    # Create the contract file so contract validation passes
    contract_dir = tmp_path / "contracts" / "openapi"
    contract_dir.mkdir(parents=True)
    (contract_dir / "v1.yaml").write_text("openapi: 3.1.0\ninfo:\n  title: Test\n  version: 1.0.0\npaths: {}")
    return yaml_path


# --- Tests: compute_topo_order ---


class TestComputeTopoOrder:
    def test_linear_chain(self, linear_dag: list[dict[str, Any]]) -> None:
        order = compute_topo_order(linear_dag)
        assert order == ["wp-a", "wp-b", "wp-c"]

    def test_diamond(self, diamond_dag: list[dict[str, Any]]) -> None:
        order = compute_topo_order(diamond_dag)
        assert order[0] == "wp-contracts"
        assert order[-1] == "wp-integration"
        # backend and frontend can be in either order but both before integration
        middle = set(order[1:3])
        assert middle == {"wp-backend", "wp-frontend"}

    def test_single_package(self) -> None:
        pkgs = [_make_package("wp-only")]
        assert compute_topo_order(pkgs) == ["wp-only"]

    def test_no_dependencies(self) -> None:
        pkgs = [
            _make_package("wp-c"),
            _make_package("wp-a"),
            _make_package("wp-b"),
        ]
        # All independent, should be alphabetical (deterministic)
        order = compute_topo_order(pkgs)
        assert order == ["wp-a", "wp-b", "wp-c"]

    def test_cycle_raises(self) -> None:
        pkgs = [
            _make_package("wp-a", depends_on=["wp-b"]),
            _make_package("wp-b", depends_on=["wp-a"]),
        ]
        with pytest.raises(ValueError, match="Cycle detected"):
            compute_topo_order(pkgs)

    def test_complex_dag(self) -> None:
        """A -> B, A -> C, B -> D, C -> D."""
        pkgs = [
            _make_package("wp-a"),
            _make_package("wp-b", depends_on=["wp-a"]),
            _make_package("wp-c", depends_on=["wp-a"]),
            _make_package("wp-d", depends_on=["wp-b", "wp-c"]),
        ]
        order = compute_topo_order(pkgs)
        assert order[0] == "wp-a"
        assert order[-1] == "wp-d"
        assert order.index("wp-b") < order.index("wp-d")
        assert order.index("wp-c") < order.index("wp-d")


# --- Tests: validate_contracts_exist ---


class TestValidateContractsExist:
    def test_contracts_present(self, tmp_path: Path) -> None:
        contract_dir = tmp_path / "contracts" / "openapi"
        contract_dir.mkdir(parents=True)
        (contract_dir / "v1.yaml").write_text("openapi: 3.1.0")

        data = _make_work_packages_data([_make_package("wp-a")])
        missing = validate_contracts_exist(data, tmp_path)
        assert missing == []

    def test_contracts_missing(self, tmp_path: Path) -> None:
        data = _make_work_packages_data([_make_package("wp-a")])
        missing = validate_contracts_exist(data, tmp_path)
        assert missing == ["contracts/openapi/v1.yaml"]

    def test_multiple_contract_files(self, tmp_path: Path) -> None:
        data = _make_work_packages_data([_make_package("wp-a")])
        data["contracts"]["openapi"]["files"] = [
            "contracts/openapi/v1.yaml",
            "contracts/openapi/models.yaml",
        ]
        (tmp_path / "contracts" / "openapi").mkdir(parents=True)
        (tmp_path / "contracts" / "openapi" / "v1.yaml").write_text("ok")
        missing = validate_contracts_exist(data, tmp_path)
        assert missing == ["contracts/openapi/models.yaml"]


# --- Tests: build_context_slice ---


class TestBuildContextSlice:
    def test_context_contains_package_info(self) -> None:
        pkg = _make_package("wp-backend", task_type="implement")
        data = _make_work_packages_data([pkg])
        ctx = build_context_slice(pkg, data)

        assert ctx["feature_id"] == "test-feature"
        assert ctx["plan_revision"] == 1
        assert ctx["contracts_revision"] == 1
        assert ctx["package"]["package_id"] == "wp-backend"
        assert ctx["package"]["task_type"] == "implement"

    def test_context_includes_scope(self) -> None:
        pkg = _make_package("wp-api", write_allow=["src/api/**"])
        data = _make_work_packages_data([pkg])
        ctx = build_context_slice(pkg, data)
        assert ctx["package"]["scope"]["write_allow"] == ["src/api/**"]

    def test_context_includes_contracts(self) -> None:
        pkg = _make_package("wp-x")
        data = _make_work_packages_data([pkg])
        ctx = build_context_slice(pkg, data)
        assert "openapi" in ctx["contracts"]
        assert ctx["contracts"]["openapi"]["primary"] == "contracts/openapi/v1.yaml"


# --- Tests: prepare_task_submissions ---


class TestPrepareTaskSubmissions:
    def test_submission_count_matches_packages(
        self, diamond_dag: list[dict[str, Any]]
    ) -> None:
        data = _make_work_packages_data(diamond_dag)
        order = compute_topo_order(diamond_dag)
        subs = prepare_task_submissions(data, order)
        assert len(subs) == 4

    def test_submission_order_matches_topo(
        self, diamond_dag: list[dict[str, Any]]
    ) -> None:
        data = _make_work_packages_data(diamond_dag)
        order = compute_topo_order(diamond_dag)
        subs = prepare_task_submissions(data, order)
        sub_ids = [s["package_id"] for s in subs]
        assert sub_ids[0] == "wp-contracts"
        assert sub_ids[-1] == "wp-integration"

    def test_submission_has_required_fields(
        self, diamond_dag: list[dict[str, Any]]
    ) -> None:
        data = _make_work_packages_data(diamond_dag)
        order = compute_topo_order(diamond_dag)
        subs = prepare_task_submissions(data, order)
        for sub in subs:
            assert "package_id" in sub
            assert "task_type" in sub
            assert "description" in sub
            assert "priority" in sub
            assert "input_data" in sub
            assert "depends_on_packages" in sub
            assert "timeout_minutes" in sub
            assert "retry_budget" in sub

    def test_submission_depends_on_tracks_packages(
        self, diamond_dag: list[dict[str, Any]]
    ) -> None:
        data = _make_work_packages_data(diamond_dag)
        order = compute_topo_order(diamond_dag)
        subs = prepare_task_submissions(data, order)
        sub_map = {s["package_id"]: s for s in subs}

        assert sub_map["wp-contracts"]["depends_on_packages"] == []
        assert sub_map["wp-backend"]["depends_on_packages"] == ["wp-contracts"]
        assert sub_map["wp-frontend"]["depends_on_packages"] == ["wp-contracts"]
        assert set(sub_map["wp-integration"]["depends_on_packages"]) == {
            "wp-backend",
            "wp-frontend",
        }


# --- Tests: DAGScheduler full preflight ---


class TestDAGSchedulerPreflight:
    def test_valid_preflight(self, sample_yaml: Path) -> None:
        scheduler = DAGScheduler(sample_yaml, sample_yaml.parent)
        result = scheduler.preflight()
        assert result["valid"] is True
        assert len(result["topo_order"]) == 4
        assert len(result["submissions"]) == 4

    def test_missing_yaml(self, tmp_path: Path) -> None:
        scheduler = DAGScheduler(tmp_path / "nonexistent.yaml")
        result = scheduler.preflight()
        assert result["valid"] is False
        assert any("not found" in e for e in result["errors"])

    def test_missing_contracts(self, tmp_path: Path, diamond_dag: list[dict[str, Any]]) -> None:
        data = _make_work_packages_data(diamond_dag)
        yaml_path = tmp_path / "work-packages.yaml"
        yaml_path.write_text(yaml.dump(data, default_flow_style=False))
        # No contract file created
        scheduler = DAGScheduler(yaml_path, tmp_path)
        result = scheduler.preflight()
        assert result["valid"] is False
        assert any("contract" in e.lower() for e in result["errors"])

    def test_preflight_populates_package_statuses(self, sample_yaml: Path) -> None:
        scheduler = DAGScheduler(sample_yaml, sample_yaml.parent)
        result = scheduler.preflight()
        assert result["valid"]
        assert len(scheduler.package_statuses) == 4
        # wp-contracts has no deps, should be READY
        assert scheduler.package_statuses["wp-contracts"].state == PackageState.READY
        # Others should be PENDING
        assert scheduler.package_statuses["wp-backend"].state == PackageState.PENDING
        assert scheduler.package_statuses["wp-frontend"].state == PackageState.PENDING
        assert scheduler.package_statuses["wp-integration"].state == PackageState.PENDING


# --- Tests: DAGScheduler state management ---


class TestDAGSchedulerStateManagement:
    def _setup_scheduler(self, sample_yaml: Path) -> DAGScheduler:
        scheduler = DAGScheduler(sample_yaml, sample_yaml.parent)
        scheduler.preflight()
        return scheduler

    def test_get_ready_packages_initial(self, sample_yaml: Path) -> None:
        scheduler = self._setup_scheduler(sample_yaml)
        ready = scheduler.get_ready_packages()
        assert ready == ["wp-contracts"]

    def test_completing_root_unblocks_dependents(self, sample_yaml: Path) -> None:
        scheduler = self._setup_scheduler(sample_yaml)
        scheduler.mark_submitted("wp-contracts", "task-001")
        scheduler.mark_in_progress("wp-contracts")
        scheduler.mark_completed("wp-contracts")

        ready = scheduler.get_ready_packages()
        assert set(ready) == {"wp-backend", "wp-frontend"}

    def test_completing_all_impl_unblocks_integration(self, sample_yaml: Path) -> None:
        scheduler = self._setup_scheduler(sample_yaml)
        scheduler.mark_completed("wp-contracts")
        scheduler.mark_completed("wp-backend")
        scheduler.mark_completed("wp-frontend")

        ready = scheduler.get_ready_packages()
        assert ready == ["wp-integration"]

    def test_cancel_dependents(self, sample_yaml: Path) -> None:
        scheduler = self._setup_scheduler(sample_yaml)
        scheduler.mark_completed("wp-contracts")
        scheduler.mark_failed("wp-backend", "test failure")

        cancelled = scheduler.cancel_dependents("wp-backend")
        assert "wp-integration" in cancelled
        assert scheduler.package_statuses["wp-integration"].state == PackageState.CANCELLED

    def test_cancel_does_not_affect_independent_packages(self, sample_yaml: Path) -> None:
        scheduler = self._setup_scheduler(sample_yaml)
        scheduler.mark_completed("wp-contracts")
        scheduler.mark_failed("wp-backend", "test failure")
        scheduler.cancel_dependents("wp-backend")

        # wp-frontend is independent of wp-backend
        assert scheduler.package_statuses["wp-frontend"].state == PackageState.PENDING
        # But wp-frontend is now ready since contracts completed
        ready = scheduler.get_ready_packages()
        assert "wp-frontend" in ready

    def test_status_summary(self, sample_yaml: Path) -> None:
        scheduler = self._setup_scheduler(sample_yaml)
        scheduler.mark_completed("wp-contracts")
        scheduler.mark_completed("wp-backend")

        summary = scheduler.get_status_summary()
        assert summary["all_done"] is False
        assert summary["counts"]["completed"] == 2
        assert summary["counts"]["pending"] == 2

    def test_all_done_detection(self, sample_yaml: Path) -> None:
        scheduler = self._setup_scheduler(sample_yaml)
        for pid in ["wp-contracts", "wp-backend", "wp-frontend", "wp-integration"]:
            scheduler.mark_completed(pid)

        summary = scheduler.get_status_summary()
        assert summary["all_done"] is True
        assert summary["counts"]["completed"] == 4


# --- Tests: CLI ---


class TestCLI:
    def test_cli_valid_yaml(self, sample_yaml: Path) -> None:
        import subprocess

        result = subprocess.run(
            [sys.executable, "-m", "dag_scheduler", str(sample_yaml), "--base-dir", str(sample_yaml.parent)],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        assert result.returncode == 0
        assert "PASS" in result.stdout

    def test_cli_json_output(self, sample_yaml: Path) -> None:
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "dag_scheduler",
                str(sample_yaml),
                "--base-dir",
                str(sample_yaml.parent),
                "--json",
            ],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["valid"] is True
        assert len(data["topo_order"]) == 4

    def test_cli_missing_file(self, tmp_path: Path) -> None:
        import subprocess

        result = subprocess.run(
            [sys.executable, "-m", "dag_scheduler", str(tmp_path / "missing.yaml")],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        assert result.returncode == 1
