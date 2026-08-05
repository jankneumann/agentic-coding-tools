"""Tests for analyzer-relative -> repo-relative path resolution.

Layer 1 analyzers record paths relative to their own source root, so a handbook
locator built naively from ``node["file"]`` points at nothing. These tests pin
the mapping that makes evidence openable from the repository root.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from source_roots import (
    DEFAULT_SOURCE_ROOTS,
    parse_source_roots,
    resolve_existing_path,
    resolve_node_path,
)


def test_python_node_resolves_under_python_source_root() -> None:
    node = {"language": "python", "file": "coordination_api.py"}
    assert resolve_node_path(node) == "agent-coordinator/src/coordination_api.py"


def test_nested_python_path_is_preserved() -> None:
    node = {"language": "python", "file": "model_routing/__init__.py"}
    assert resolve_node_path(node) == "agent-coordinator/src/model_routing/__init__.py"


def test_typescript_node_resolves_under_apps() -> None:
    node = {"language": "typescript", "file": "kanban-viz/src/App.tsx"}
    assert resolve_node_path(node) == "apps/kanban-viz/src/App.tsx"


def test_sql_node_resolves_under_migrations() -> None:
    node = {"language": "sql", "file": "000_bootstrap.sql"}
    assert resolve_node_path(node) == (
        "agent-coordinator/database/migrations/000_bootstrap.sql"
    )


def test_node_without_a_file_resolves_to_none() -> None:
    assert resolve_node_path({"language": "sql", "file": ""}) is None
    assert resolve_node_path({"language": "python"}) is None


def test_unknown_language_falls_back_to_the_raw_path() -> None:
    node = {"language": "ruby", "file": "app/thing.rb"}
    assert resolve_node_path(node) == "app/thing.rb"


def test_overrides_replace_defaults() -> None:
    roots = parse_source_roots(["python=src"])
    assert roots["python"] == "src"
    assert roots["typescript"] == DEFAULT_SOURCE_ROOTS["typescript"]


def test_override_trailing_slash_is_normalized() -> None:
    roots = parse_source_roots(["python=src/"])
    assert resolve_node_path({"language": "python", "file": "a.py"}, roots) == "src/a.py"


def test_malformed_override_raises() -> None:
    with pytest.raises(ValueError):
        parse_source_roots(["python"])


def test_resolve_existing_path_returns_none_for_missing_file(tmp_path: Path) -> None:
    node = {"language": "python", "file": "ghost.py"}
    assert resolve_existing_path(node, tmp_path, {"python": "src"}) is None


def test_resolve_existing_path_returns_path_for_real_file(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "real.py").write_text("x = 1\n", encoding="utf-8")

    node = {"language": "python", "file": "real.py"}
    assert resolve_existing_path(node, tmp_path, {"python": "src"}) == "src/real.py"
