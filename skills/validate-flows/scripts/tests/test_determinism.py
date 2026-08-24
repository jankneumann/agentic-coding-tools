"""Determinism guards for architecture.diagnostics.json (issue #362).

``architecture.diagnostics.json`` is a committed artifact whose content digest
the architecture provenance system records, so two validations of one graph MUST
produce identical bytes. Two defects broke that:

* findings were emitted by iterating *sets* of node ids, so their order followed
  the hash seed rather than the graph, and
* ``generated_at`` was stamped from the wall clock instead of the pipeline's
  ``SOURCE_DATE_EPOCH``-aware clock.

Both are only observable across processes — ``PYTHONHASHSEED`` is fixed at
interpreter start — so these tests run the validator in subprocesses under
several pinned seeds and compare the results.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
ARCHITECTURE_SCRIPTS = (
    SCRIPTS_DIR.parents[1] / "refresh-architecture" / "scripts"
)

#: Enough distinct seeds that an accidental agreement across all of them is not
#: a plausible explanation for a green run.
_SEEDS = ("0", "1", "2", "3", "4")

_EPOCH = "1700000000"

_RUNNER = """
import sys
from pathlib import Path

sys.path.insert(0, {scripts!r})
from validate_flows import validate_flows

validate_flows(Path(sys.argv[1]), Path(sys.argv[2]), None)
"""


def _graph() -> dict:
    """A graph whose findings come from set-iterated collections.

    The route names are deliberately unsorted relative to their node ids so that
    "happened to come out in graph order" and "came out sorted" are
    distinguishable outcomes.
    """
    route_names = ["zeta_route", "alpha_route", "mid_route", "beta_route", "yank_route"]
    nodes = [
        {
            "id": f"py:api.{name}",
            "kind": "function",
            "language": "python",
            "name": name,
            "file": "src/api.py",
            "span": {"start": 10 + index, "end": 20 + index},
            "tags": [],
            # Two decorators shared by every route, plus one node below that has
            # neither -- that makes `dominant_decorators[kind] - decorators` a
            # multi-element set difference, another order-sensitive emit point.
            "signatures": {"decorators": ["router.get", "traced"]},
        }
        for index, name in enumerate(route_names)
    ]
    nodes.append(
        {
            "id": "py:api.undecorated_route",
            "kind": "function",
            "language": "python",
            "name": "undecorated_route",
            "file": "src/api.py",
            "span": {"start": 90, "end": 99},
            "tags": [],
            "signatures": {"decorators": []},
        }
    )

    return {
        "nodes": nodes,
        "edges": [],
        "entrypoints": [
            {"node_id": node["id"], "kind": "route", "method": "GET", "path": f"/{node['name']}"}
            for node in nodes
        ],
        "snapshots": [{"generated_at": "2026-01-01T00:00:00+00:00", "git_sha": "deadbeef"}],
    }


def _run(graph_path: Path, out_path: Path, seed: str) -> bytes:
    """Validate *graph_path* in a subprocess pinned to *seed*; return the bytes."""
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = seed
    env["SOURCE_DATE_EPOCH"] = _EPOCH
    result = subprocess.run(
        [sys.executable, "-c", _RUNNER.format(scripts=str(SCRIPTS_DIR)),
         str(graph_path), str(out_path)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"validator failed under seed {seed}:\n{result.stderr}"
    return out_path.read_bytes()


@pytest.fixture
def graph_path(tmp_path: Path) -> Path:
    """Write the shared graph fixture and return its path."""
    path = tmp_path / "architecture.graph.json"
    path.write_text(json.dumps(_graph()))
    return path


def test_findings_order_is_hash_seed_independent(graph_path: Path, tmp_path: Path) -> None:
    """Findings must carry a total order, not the iteration order of a set."""
    orders = []
    for seed in _SEEDS:
        out = tmp_path / f"diagnostics-{seed}.json"
        report = json.loads(_run(graph_path, out, seed))
        orders.append([
            (f["category"], f["severity"], f.get("node_id"), f["message"])
            for f in report["findings"]
        ])

    baseline = orders[0]
    assert baseline, "fixture produced no findings — the guard would be vacuous"
    for seed, order in zip(_SEEDS[1:], orders[1:]):
        assert order == baseline, (
            f"finding order under PYTHONHASHSEED={seed} differs from seed "
            f"{_SEEDS[0]} — diagnostics ordering is not total"
        )


def test_diagnostics_bytes_are_reproducible(graph_path: Path, tmp_path: Path) -> None:
    """The whole artifact, not just the findings list, must be reproducible."""
    digests = {
        seed: _run(graph_path, tmp_path / f"bytes-{seed}.json", seed)
        for seed in _SEEDS
    }
    baseline = digests[_SEEDS[0]]
    for seed in _SEEDS[1:]:
        assert digests[seed] == baseline, (
            f"architecture.diagnostics.json differs between PYTHONHASHSEED="
            f"{_SEEDS[0]} and {seed} under a pinned SOURCE_DATE_EPOCH"
        )


def test_generated_at_honors_source_date_epoch(graph_path: Path, tmp_path: Path) -> None:
    """``generated_at`` comes from the pipeline clock, not the wall clock."""
    report = json.loads(_run(graph_path, tmp_path / "clock.json", _SEEDS[0]))
    assert report["generated_at"] == "2023-11-14T22:13:20+00:00", (
        "generated_at ignored SOURCE_DATE_EPOCH; every refresh rewrites the "
        "artifact even when nothing changed"
    )
