"""Scoped validation must match changed files to graph nodes (#635).

Analyzers record each node's ``file`` relative to their own source root
(``agents_config.py``, not ``agent-coordinator/src/agents_config.py``), while
``--files`` / ``--diff`` supply repo-relative paths. The exact comparison never
matched, so every scoped run checked 0 entrypoints and reported a vacuous pass.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from validate_flows import validate_flows  # noqa: E402


def _repo(tmp_path: Path, config: str | None) -> Path:
    if config is not None:
        (tmp_path / "architecture.config.yaml").write_text(config)
    graph_dir = tmp_path / "docs" / "architecture-analysis"
    graph_dir.mkdir(parents=True)
    graph = {
        "nodes": [
            {"id": "py:api.handler", "name": "handler", "kind": "function", "file": "model_routing/api.py"},
            {"id": "py:svc.do", "name": "do", "kind": "function", "file": "service.py"},
        ],
        "edges": [{"from": "py:api.handler", "to": "py:svc.do", "type": "call"}],
        "entrypoints": [
            {"node_id": "py:api.handler", "kind": "route", "method": "POST", "path": "/x"}
        ],
    }
    path = graph_dir / "architecture.graph.json"
    path.write_text(json.dumps(graph))
    return path


_CONFIG = "analysis:\n  python_src_dir: agent-coordinator/src\n"


def test_repo_relative_changed_file_matches_a_root_relative_node(tmp_path: Path) -> None:
    graph = _repo(tmp_path, _CONFIG)

    report = validate_flows(
        graph, tmp_path / "out.json", ["agent-coordinator/src/model_routing/api.py"]
    )

    assert report["summary"]["entrypoints_checked"] == 1
    # The report still names the files the caller passed, not the aliases.
    assert report["changed_files"] == ["agent-coordinator/src/model_routing/api.py"]


def test_unrelated_changed_file_stays_out_of_scope(tmp_path: Path) -> None:
    graph = _repo(tmp_path, _CONFIG)

    report = validate_flows(graph, tmp_path / "out.json", ["skills/other/api.py"])

    assert report["summary"]["entrypoints_checked"] == 0


def test_without_config_root_relative_paths_still_match(tmp_path: Path) -> None:
    graph = _repo(tmp_path, None)

    report = validate_flows(graph, tmp_path / "out.json", ["model_routing/api.py"])

    assert report["summary"]["entrypoints_checked"] == 1
