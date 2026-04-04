"""Tests for gen-eval MCP service layer."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from evaluation.gen_eval.mcp_service import GenEvalMCPService


@pytest.fixture()
def service(tmp_path: Path) -> GenEvalMCPService:
    """Create a service with a temporary base directory."""
    # Create scenarios directory structure
    scenarios_dir = tmp_path / "scenarios"
    lock_dir = scenarios_dir / "lock-lifecycle"
    lock_dir.mkdir(parents=True)
    auth_dir = scenarios_dir / "auth-boundary"
    auth_dir.mkdir(parents=True)

    # Write sample scenario files
    (lock_dir / "acquire-release.yaml").write_text(textwrap.dedent("""\
        id: lock-acquire-release
        name: Basic lock acquire and release
        description: Test basic lock lifecycle
        category: lock-lifecycle
        priority: 1
        interfaces: [http, db]
        tags: [locks, success]
        steps:
          - id: acquire
            transport: http
            method: POST
            endpoint: /locks/acquire
            body:
              file_path: src/main.py
              agent_id: agent-1
            expect:
              status: 200
              body:
                success: true
          - id: verify_db
            transport: db
            sql: "SELECT 1"
            expect:
              rows: 1
    """))

    (lock_dir / "conflict.yaml").write_text(textwrap.dedent("""\
        id: lock-conflict
        name: Lock conflict detection
        description: Test conflict when two agents try same lock
        category: lock-lifecycle
        priority: 1
        interfaces: [http, mcp]
        tags: [locks, failure]
        steps:
          - id: acquire_a
            transport: http
            method: POST
            endpoint: /locks/acquire
            body:
              file_path: src/main.py
              agent_id: agent-1
            expect:
              status: 200
          - id: acquire_b_fails
            transport: mcp
            tool: acquire_lock
            params:
              file_path: src/main.py
            expect:
              body:
                success: false
        cleanup:
          - id: release
            transport: http
            method: POST
            endpoint: /locks/release
            body:
              file_path: src/main.py
              agent_id: agent-1
    """))

    (auth_dir / "valid-key.yaml").write_text(textwrap.dedent("""\
        id: auth-valid-key
        name: Valid API key accepted
        description: Test that a valid API key is accepted
        category: auth-boundary
        priority: 1
        interfaces: [http]
        tags: [auth, success]
        steps:
          - id: health_check
            transport: http
            method: GET
            endpoint: /health
            expect:
              status: 200
    """))

    return GenEvalMCPService(base_dir=tmp_path)


class TestListScenarios:
    @pytest.mark.asyncio
    async def test_list_all(self, service: GenEvalMCPService) -> None:
        result = await service.list_scenarios()
        assert len(result) == 3
        ids = {s.id for s in result}
        assert ids == {"lock-acquire-release", "lock-conflict", "auth-valid-key"}

    @pytest.mark.asyncio
    async def test_filter_by_category(self, service: GenEvalMCPService) -> None:
        result = await service.list_scenarios(category="lock-lifecycle")
        assert len(result) == 2
        assert all(s.category == "lock-lifecycle" for s in result)

    @pytest.mark.asyncio
    async def test_filter_by_interface(self, service: GenEvalMCPService) -> None:
        result = await service.list_scenarios(interface="mcp")
        assert len(result) == 1
        assert result[0].id == "lock-conflict"

    @pytest.mark.asyncio
    async def test_filter_returns_empty(self, service: GenEvalMCPService) -> None:
        result = await service.list_scenarios(category="nonexistent")
        assert result == []

    @pytest.mark.asyncio
    async def test_scenario_info_fields(self, service: GenEvalMCPService) -> None:
        result = await service.list_scenarios(category="lock-lifecycle")
        acquire = next(s for s in result if s.id == "lock-acquire-release")
        assert acquire.name == "Basic lock acquire and release"
        assert acquire.priority == 1
        assert acquire.interfaces == ["http", "db"]
        assert acquire.step_count == 2
        assert acquire.has_cleanup is False
        assert "success" in acquire.tags

        conflict = next(s for s in result if s.id == "lock-conflict")
        assert conflict.has_cleanup is True
        assert "failure" in conflict.tags


class TestGetCoverage:
    @pytest.mark.asyncio
    async def test_coverage_summary(self, service: GenEvalMCPService) -> None:
        result = await service.get_coverage()
        assert result.total_scenarios == 3
        assert len(result.categories) == 2

        lock_cat = next(c for c in result.categories if c.category == "lock-lifecycle")
        assert lock_cat.scenario_count == 2
        assert lock_cat.success_count == 1
        assert lock_cat.failure_count == 1

        auth_cat = next(c for c in result.categories if c.category == "auth-boundary")
        assert auth_cat.scenario_count == 1
        assert auth_cat.success_count == 1


class TestValidateScenario:
    @pytest.mark.asyncio
    async def test_valid_scenario(self, service: GenEvalMCPService) -> None:
        yaml_content = textwrap.dedent("""\
            id: test-scenario
            name: Test scenario
            description: A test
            category: test
            priority: 2
            interfaces: [http]
            steps:
              - id: step1
                transport: http
                method: GET
                endpoint: /health
                expect:
                  status: 200
        """)
        result = await service.validate_scenario(yaml_content)
        assert result.valid is True
        assert result.scenario_id == "test-scenario"
        assert result.step_count == 1
        assert result.interfaces == ["http"]

    @pytest.mark.asyncio
    async def test_invalid_scenario_missing_field(self, service: GenEvalMCPService) -> None:
        yaml_content = textwrap.dedent("""\
            id: bad-scenario
            name: Missing required fields
        """)
        result = await service.validate_scenario(yaml_content)
        assert result.valid is False
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_invalid_yaml(self, service: GenEvalMCPService) -> None:
        result = await service.validate_scenario("not: [valid: yaml: {{")
        assert result.valid is False


class TestCreateScenario:
    @pytest.mark.asyncio
    async def test_create_basic(self, service: GenEvalMCPService) -> None:
        result = await service.create_scenario(
            category="lock-lifecycle",
            description="Test TTL expiry",
            interfaces=["http", "db"],
        )
        assert result["scenario_id"] == "lock-lifecycle-test-ttl-expiry"
        assert "yaml" in result
        assert result["step_count"] == 2
        assert result["interfaces"] == ["http", "db"]
        assert "scenarios/lock-lifecycle/" in result["suggested_path"]

    @pytest.mark.asyncio
    async def test_create_with_mcp(self, service: GenEvalMCPService) -> None:
        result = await service.create_scenario(
            category="cross-interface",
            description="Lock via HTTP verify via MCP",
            interfaces=["http", "mcp", "db"],
            scenario_type="success",
            priority=1,
        )
        assert result["step_count"] == 3
        assert "cleanup" not in result  # cleanup is in the yaml, not top-level
        # Verify the YAML is valid
        validate_result = await service.validate_scenario(result["yaml"])
        assert validate_result.valid is True

    @pytest.mark.asyncio
    async def test_create_failure_scenario(self, service: GenEvalMCPService) -> None:
        result = await service.create_scenario(
            category="auth-boundary",
            description="Invalid key rejected",
            interfaces=["http"],
            scenario_type="failure",
        )
        assert "failure" in result["yaml"].lower() or "failure" in result["scenario_id"]


class TestGetReportSummary:
    @pytest.mark.asyncio
    async def test_no_report(self) -> None:
        """Service with an isolated base_dir should find no reports."""
        import tempfile
        isolated = Path(tempfile.mkdtemp()) / "deep" / "nested" / "geneval"
        isolated.mkdir(parents=True)
        svc = GenEvalMCPService(base_dir=isolated)
        result = await svc.get_report_summary()
        assert result is None

    @pytest.mark.asyncio
    async def test_with_report(self) -> None:
        import json
        import tempfile

        # Create an isolated directory tree:
        # root/evaluation/gen_eval/ (base_dir)
        # root/gen-eval-report.json (report at base.parent.parent)
        root = Path(tempfile.mkdtemp())
        base = root / "evaluation" / "gen_eval"
        base.mkdir(parents=True)

        report = {
            "total_scenarios": 10,
            "passed": 9,
            "failed": 1,
            "errors": 0,
            "pass_rate": 0.9,
            "coverage_pct": 75.0,
            "budget_exhausted": False,
            "per_interface": {
                "/locks/acquire": {"pass": 3, "fail": 0, "error": 0},
                "/locks/release": {"pass": 2, "fail": 1, "error": 0},
            },
            "per_category": {
                "lock-lifecycle": {"pass": 5, "fail": 1, "total": 6},
                "auth-boundary": {"pass": 4, "fail": 0, "total": 4},
            },
        }
        (root / "gen-eval-report.json").write_text(json.dumps(report))

        svc = GenEvalMCPService(base_dir=base)
        result = await svc.get_report_summary()
        assert result is not None
        assert result["pass_rate"] == 0.9
        assert result["failing_interfaces"] == ["/locks/release"]
        assert "lock-lifecycle" in result["categories_below_threshold"]
