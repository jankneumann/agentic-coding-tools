"""Install-boundary checks for the lightweight shared code-search package."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "agent-coordinator" / "Dockerfile"


def test_clean_coordinator_environment_imports_light_modules() -> None:
    script = """
import sys
import code_search_pkg.identifiers
import code_search_pkg.query_pg
import code_search_pkg.registry_models
import code_search_pkg.embedding_protocol
assert "cocoindex" not in sys.modules
assert "sentence_transformers" not in sys.modules
assert "torch" not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_docker_installs_code_search_wheel_without_runtime_source_copy() -> None:
    dockerfile = DOCKERFILE.read_text()
    assert "COPY packages/code-search/ /packages/code-search/" in dockerfile
    assert "COPY packages/code-search/src/code_search_pkg/ /app/code_search_pkg/" not in dockerfile
    assert "uv sync --all-extras --no-dev --no-install-project" in dockerfile
