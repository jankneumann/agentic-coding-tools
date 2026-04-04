"""MCP service layer for gen-eval operations.

Provides the business logic behind gen-eval MCP tools — scenario listing,
coverage analysis, validation, scenario generation, and evaluation runs.
Follows the singleton pattern used by other coordination services.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ScenarioInfo:
    """Summary of a single scenario file."""

    id: str
    name: str
    category: str
    priority: int
    interfaces: list[str]
    step_count: int
    tags: list[str]
    has_cleanup: bool
    file_path: str


@dataclass
class CategoryCoverage:
    """Coverage summary for one scenario category."""

    category: str
    scenario_count: int
    success_count: int
    failure_count: int
    interfaces: list[str]


@dataclass
class CoverageSummary:
    """Overall scenario coverage summary."""

    total_scenarios: int
    categories: list[CategoryCoverage]
    total_interfaces: int
    interfaces_covered: int
    coverage_pct: float


@dataclass
class ValidationResult:
    """Result of validating scenario YAML."""

    valid: bool
    scenario_id: str | None = None
    step_count: int = 0
    interfaces: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class GenEvalMCPService:
    """Service providing gen-eval operations for MCP tools."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir

    def _find_base_dir(self) -> Path:
        """Find the gen_eval package directory."""
        if self._base_dir:
            return self._base_dir
        # Default: relative to this file
        return Path(__file__).parent

    def _scenarios_dir(self) -> Path:
        return self._find_base_dir() / "scenarios"

    def _descriptors_dir(self) -> Path:
        return self._find_base_dir() / "descriptors"

    def _find_latest_report(self) -> Path | None:
        """Find the most recent gen-eval report JSON."""
        base = self._find_base_dir()
        candidates = [
            base.parent.parent / "gen-eval-report.json",  # agent-coordinator/
            base.parent.parent.parent / "gen-eval-report.json",  # repo root
        ]
        for path in candidates:
            if path.exists():
                return path
        return None

    async def list_scenarios(
        self,
        category: str | None = None,
        interface: str | None = None,
    ) -> list[ScenarioInfo]:
        """List all scenarios, optionally filtered by category or interface."""
        import yaml

        scenarios: list[ScenarioInfo] = []
        scenarios_dir = self._scenarios_dir()

        if not scenarios_dir.exists():
            return []

        for category_dir in sorted(scenarios_dir.iterdir()):
            if not category_dir.is_dir():
                continue
            if category and category_dir.name != category:
                continue

            for yaml_file in sorted(category_dir.glob("*.yaml")):
                try:
                    data = yaml.safe_load(yaml_file.read_text())
                    if not isinstance(data, dict):
                        continue

                    interfaces = data.get("interfaces", [])
                    if interface and interface not in interfaces:
                        continue

                    scenarios.append(ScenarioInfo(
                        id=data.get("id", yaml_file.stem),
                        name=data.get("name", ""),
                        category=data.get("category", category_dir.name),
                        priority=data.get("priority", 2),
                        interfaces=interfaces,
                        step_count=len(data.get("steps", [])),
                        tags=data.get("tags", []),
                        has_cleanup=bool(data.get("cleanup")),
                        file_path=str(yaml_file.relative_to(scenarios_dir.parent)),
                    ))
                except Exception:
                    continue

        return scenarios

    async def get_coverage(self) -> CoverageSummary:
        """Compute scenario coverage summary."""
        scenarios = await self.list_scenarios()

        categories: dict[str, CategoryCoverage] = {}
        all_interfaces: set[str] = set()

        for s in scenarios:
            all_interfaces.update(s.interfaces)
            if s.category not in categories:
                categories[s.category] = CategoryCoverage(
                    category=s.category,
                    scenario_count=0,
                    success_count=0,
                    failure_count=0,
                    interfaces=[],
                )
            cat = categories[s.category]
            cat.scenario_count += 1
            if "success" in s.tags:
                cat.success_count += 1
            elif "failure" in s.tags or "edge" in s.tags:
                cat.failure_count += 1
            for iface in s.interfaces:
                if iface not in cat.interfaces:
                    cat.interfaces.append(iface)

        # Estimate total interfaces from descriptor
        total_interfaces = 4  # http, mcp, cli, db (default)
        descriptor_path = self._descriptors_dir() / "agent-coordinator.yaml"
        if descriptor_path.exists():
            try:
                import yaml
                desc = yaml.safe_load(descriptor_path.read_text())
                if isinstance(desc, dict):
                    total_interfaces = sum(
                        len(svc.get("endpoints", []))
                        + len(svc.get("tools", []))
                        + len(svc.get("commands", []))
                        for svc in desc.get("services", [])
                        if isinstance(svc, dict)
                    )
            except Exception:
                pass

        return CoverageSummary(
            total_scenarios=len(scenarios),
            categories=list(categories.values()),
            total_interfaces=total_interfaces,
            interfaces_covered=len(all_interfaces),
            coverage_pct=(len(all_interfaces) / max(total_interfaces, 1)) * 100,
        )

    async def validate_scenario(self, yaml_content: str) -> ValidationResult:
        """Validate scenario YAML against the Pydantic model."""
        import yaml as yaml_lib

        from evaluation.gen_eval.models import Scenario

        try:
            data = yaml_lib.safe_load(yaml_content)
            if not isinstance(data, dict):
                return ValidationResult(
                    valid=False,
                    errors=["YAML content must be a mapping, not " + type(data).__name__],
                )

            scenario = Scenario(**data)
            return ValidationResult(
                valid=True,
                scenario_id=scenario.id,
                step_count=len(scenario.steps),
                interfaces=list(scenario.interfaces),
            )
        except Exception as e:
            return ValidationResult(
                valid=False,
                errors=[str(e)],
            )

    async def create_scenario(
        self,
        category: str,
        description: str,
        interfaces: list[str],
        scenario_type: str = "success",
        priority: int = 2,
    ) -> dict[str, Any]:
        """Generate a scenario YAML scaffold from a description.

        Returns a dict with the generated YAML string and suggested file path.
        Does NOT write the file — the caller decides whether to persist.
        """
        import yaml as yaml_lib

        # Build a scaffold scenario
        scenario_id = f"{category}-{_slugify(description)}"
        tags = [category, scenario_type]

        steps: list[dict[str, Any]] = []
        cleanup: list[dict[str, Any]] = []

        for i, iface in enumerate(interfaces):
            step: dict[str, Any] = {"id": f"step_{i + 1}", "transport": iface}
            if iface == "http":
                step["method"] = "POST"
                step["endpoint"] = "/TODO"
                step["body"] = {}
                step["expect"] = {"status": 200, "body": {"success": True}}
            elif iface == "mcp":
                step["tool"] = "TODO_tool_name"
                step["params"] = {}
                step["expect"] = {"body": {"success": True}}
            elif iface == "cli":
                step["command"] = "TODO subcommand --flag value"
                step["expect"] = {"exit_code": 0}
            elif iface == "db":
                step["sql"] = "SELECT COUNT(*) as cnt FROM TODO_table WHERE condition"
                step["expect"] = {"rows": 1, "row": {"cnt": 1}}
            elif iface == "wait":
                step["seconds"] = 1.0
            steps.append(step)

        # Add a cleanup step for transports that create state
        if any(t in interfaces for t in ("http", "mcp")):
            cleanup.append({
                "id": "cleanup_state",
                "transport": "http",
                "method": "POST",
                "endpoint": "/TODO-cleanup",
                "body": {},
            })

        scenario_data: dict[str, Any] = {
            "id": scenario_id,
            "name": description,
            "description": (
                f"{'Success' if scenario_type == 'success' else 'Failure'}"
                f" scenario: {description}"
            ),
            "category": category,
            "priority": priority,
            "interfaces": interfaces,
            "tags": tags,
            "steps": steps,
        }
        if cleanup:
            scenario_data["cleanup"] = cleanup

        yaml_str = yaml_lib.dump(
            scenario_data,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )

        file_path = f"scenarios/{category}/{scenario_id}.yaml"

        return {
            "scenario_id": scenario_id,
            "yaml": yaml_str,
            "suggested_path": file_path,
            "step_count": len(steps),
            "interfaces": interfaces,
        }

    async def get_report_summary(self) -> dict[str, Any] | None:
        """Read and summarize the latest gen-eval report."""
        report_path = self._find_latest_report()
        if not report_path:
            return None

        try:
            data = json.loads(report_path.read_text())
            return {
                "report_path": str(report_path),
                "total_scenarios": data.get("total_scenarios", 0),
                "passed": data.get("passed", 0),
                "failed": data.get("failed", 0),
                "errors": data.get("errors", 0),
                "pass_rate": data.get("pass_rate", 0),
                "coverage_pct": data.get("coverage_pct", 0),
                "budget_exhausted": data.get("budget_exhausted", False),
                "failing_interfaces": [
                    iface for iface, stats in data.get("per_interface", {}).items()
                    if stats.get("fail", 0) > 0 or stats.get("error", 0) > 0
                ],
                "categories_below_threshold": [
                    cat for cat, stats in data.get("per_category", {}).items()
                    if stats.get("total", 0) > 0
                    and (stats.get("pass", 0) / stats["total"]) < 0.95
                ],
            }
        except Exception:
            return None

    async def run_evaluation(
        self,
        mode: str = "template-only",
        categories: list[str] | None = None,
        time_budget_minutes: float = 60.0,
    ) -> dict[str, Any]:
        """Run gen-eval and return the report summary.

        This is a potentially long-running operation. For template-only mode
        with --no-services, it completes in seconds. For CLI-augmented mode,
        it can take the full time budget.
        """
        import asyncio
        import subprocess

        base = self._find_base_dir()
        project_root = base.parent.parent  # evaluation/gen_eval -> agent-coordinator
        descriptor = base / "descriptors" / "agent-coordinator.yaml"

        if not descriptor.exists():
            return {"success": False, "error": "No descriptor found"}

        python = project_root / ".venv" / "bin" / "python"
        if not python.exists():
            python = Path("python3")

        cmd = [
            str(python), "-m", "evaluation.gen_eval",
            "--descriptor", str(descriptor),
            "--mode", mode,
            "--no-services",
            "--report-format", "json",
            "--output-dir", str(project_root),
        ]
        if categories:
            cmd.extend(["--categories"] + categories)
        if mode != "template-only":
            cmd.extend(["--time-budget", str(time_budget_minutes)])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                summary = await self.get_report_summary()
                return {"success": True, "report": summary}
            else:
                return {
                    "success": False,
                    "exit_code": proc.returncode,
                    "stderr": stderr.decode()[-500:] if stderr else "",
                }
        except Exception as e:
            return {"success": False, "error": str(e)}


def _slugify(text: str) -> str:
    """Convert text to kebab-case slug."""
    import re
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug[:60].rstrip("-")


_gen_eval_service: GenEvalMCPService | None = None


def get_gen_eval_service() -> GenEvalMCPService:
    """Get the global gen-eval MCP service instance."""
    global _gen_eval_service
    if _gen_eval_service is None:
        _gen_eval_service = GenEvalMCPService()
    return _gen_eval_service
