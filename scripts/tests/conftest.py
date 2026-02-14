"""Shared fixtures for architecture analysis tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

# Ensure scripts/ is on sys.path for imports
SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(SCRIPTS_DIR / "insights") not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR / "insights"))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def python_analysis() -> dict[str, Any]:
    """Load the Python analysis fixture."""
    with open(FIXTURES_DIR / "python_analysis.json") as f:
        return json.load(f)


@pytest.fixture
def ts_analysis() -> dict[str, Any]:
    """Load the TypeScript analysis fixture."""
    with open(FIXTURES_DIR / "ts_analysis.json") as f:
        return json.load(f)


@pytest.fixture
def postgres_analysis() -> dict[str, Any]:
    """Load the Postgres analysis fixture."""
    with open(FIXTURES_DIR / "postgres_analysis.json") as f:
        return json.load(f)


@pytest.fixture
def input_dir(tmp_path: Path, python_analysis: dict, ts_analysis: dict, postgres_analysis: dict) -> Path:
    """Create a temporary input directory with all Layer 1 fixtures."""
    with open(tmp_path / "python_analysis.json", "w") as f:
        json.dump(python_analysis, f)
    with open(tmp_path / "ts_analysis.json", "w") as f:
        json.dump(ts_analysis, f)
    with open(tmp_path / "postgres_analysis.json", "w") as f:
        json.dump(postgres_analysis, f)
    return tmp_path


@pytest.fixture
def built_graph(input_dir: Path) -> dict[str, Any]:
    """Build a canonical graph from fixtures and return it."""
    from insights.graph_builder import build_graph

    graph_path = input_dir / "architecture.graph.json"
    rc = build_graph(input_dir=input_dir, output_path=graph_path)
    assert rc == 0, "graph_builder.build_graph() failed"
    with open(graph_path) as f:
        return json.load(f)
