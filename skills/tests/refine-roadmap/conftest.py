"""Path setup and fixtures for refine-roadmap tests."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

_SKILLS_ROOT = Path(__file__).resolve().parents[2]
for scripts_dir in (
    _SKILLS_ROOT / "refine-roadmap" / "scripts",
    _SKILLS_ROOT / "plan-roadmap" / "scripts",
    _SKILLS_ROOT / "roadmap-runtime" / "scripts",
):
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    """Create the minimum repository shape required by roadmap validators."""
    source_schema = (
        _SKILLS_ROOT
        / "roadmap-runtime"
        / "install_assets"
        / "openspec"
        / "schemas"
        / "roadmap.schema.json"
    )
    schema_dir = tmp_path / "openspec" / "schemas"
    schema_dir.mkdir(parents=True)
    shutil.copy2(source_schema, schema_dir / "roadmap.schema.json")
    return tmp_path
