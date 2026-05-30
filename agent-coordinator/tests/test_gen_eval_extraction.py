"""Extraction-contract test for the gen-eval package (task 4.1).

Asserts:
  (a) ``from gen_eval.mcp_service import get_gen_eval_service`` resolves —
      confirming the package is installed and the [mcp] extra is present.
  (b) The ``/gen-eval/scenarios`` endpoint returns at least one scenario
      when the coordinator's TestClient is used (meaning the coordinator's
      evaluation/scenarios/ directory is discoverable and the service
      initialises correctly with GEN_EVAL_DATA_DIR pointing at it).

This test pins the file name ``test_gen_eval_extraction.py`` for scope hygiene —
see wp-coordinator-migrate scope in work-packages.yaml.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# (a) Package import: gen_eval.mcp_service is importable
# ---------------------------------------------------------------------------


def test_gen_eval_mcp_service_importable() -> None:
    """gen_eval.mcp_service must be importable after extraction."""
    from gen_eval.mcp_service import get_gen_eval_service  # noqa: F401

    service = get_gen_eval_service()
    assert service is not None, "get_gen_eval_service() returned None"


# ---------------------------------------------------------------------------
# (b) Endpoint: /gen-eval/list-scenarios returns scenarios
# ---------------------------------------------------------------------------


@pytest.fixture()
def gen_eval_data_dir(tmp_path: Path) -> Path:
    """Create a minimal scenarios directory so list_scenarios returns results."""
    scenario_dir = tmp_path / "scenarios" / "test-category"
    scenario_dir.mkdir(parents=True)
    scenario_yaml = scenario_dir / "basic.yaml"
    scenario_yaml.write_text(
        "id: test-basic\n"
        "name: Basic scenario\n"
        "category: test-category\n"
        "priority: 2\n"
        "interfaces: [http]\n"
        "steps: []\n"
    )
    return tmp_path


@pytest.mark.asyncio
async def test_list_scenarios_endpoint_returns_scenarios(
    gen_eval_data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /gen-eval/scenarios returns >= 1 scenario via async TestClient."""
    # Reset the service singleton so it picks up the patched env var.
    import gen_eval.mcp_service as svc_mod

    monkeypatch.setenv("GEN_EVAL_DATA_DIR", str(gen_eval_data_dir))
    monkeypatch.setattr(svc_mod, "_gen_eval_service", None)

    from httpx import ASGITransport, AsyncClient

    # Set required environment variables before importing coordination_api
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://localhost:1/nope")
    monkeypatch.setenv("DB_BACKEND", "postgres")

    from src.coordination_api import create_coordination_api

    app = create_coordination_api()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/gen-eval/scenarios")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    # The /gen-eval/scenarios endpoint returns {"scenarios": [...], ...}
    scenarios = data.get("scenarios", data) if isinstance(data, dict) else data
    assert isinstance(scenarios, list), f"Expected list of scenarios, got {type(scenarios)}: {data}"
    assert len(scenarios) >= 1, "Expected at least 1 scenario from the test fixture"

    first = scenarios[0]
    assert first["id"] == "test-basic"
    assert first["category"] == "test-category"
