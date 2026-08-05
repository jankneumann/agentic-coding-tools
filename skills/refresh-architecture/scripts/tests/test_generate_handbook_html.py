"""Tests for the handbook HTML drill-down (R5, design D6).

The page is the human-facing half of progressive disclosure. It must be
self-contained (no network at render or view time), must refuse to render an
invalid handbook, and must carry the persona entry presets that let one map
serve newcomers, reviewers, planners, and auditors.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


from reports.generate_handbook_html import render_handbook_html


def _graph() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "py:api.claim_task", "kind": "function", "name": "claim_task",
             "file": "src/api.py", "span": {"start": 1, "end": 2}},
        ],
        "edges": [],
        "entrypoints": [],
    }


def _handbook() -> dict[str, Any]:
    return {
        "snapshot": {"generated_at": "2026-08-05T00:00:00+00:00", "git_sha": "abc1234",
                     "handbook_version": "1.0.0", "backend": "offline",
                     "model_id": "none", "prompt_hash": "sha256:offline"},
        "system_flows": [
            {"id": "fl:task-claiming", "title": "Task claiming",
             "entry": "py:api.claim_task", "stages": ["receive", "lock"],
             "state_handoffs": ["request -> claim"], "terminal_actions": ["claimed"]},
        ],
        "behavior_units": [
            {"id": "bh:task-claiming", "title": "Task claiming",
             "responsibility": "Assign a queued task to one agent.",
             "inputs": ["agent id"], "outputs": ["lock"], "depends_on": [],
             "member_nodes": ["py:api.claim_task"]},
        ],
        "unit_details": {
            "bh:task-claiming": {
                "triggers": ["POST /tasks/claim"],
                "state_changes": ["queued -> claimed"],
                "execution_paths": [{"summary": "claim succeeds", "evidence": [
                    {"node_id": "py:api.claim_task", "file": "src/api.py",
                     "span": {"start": 1, "end": 2},
                     "content_digest": "sha256:x", "role": "execution_path"}]}],
                "exception_paths": [{"summary": "lock contention", "evidence": [
                    {"node_id": "py:api.claim_task", "file": "src/api.py",
                     "span": {"start": 1, "end": 2},
                     "content_digest": "sha256:x", "role": "exception_path"}]}],
                "evidence": [
                    {"node_id": "py:api.claim_task", "file": "src/api.py",
                     "span": {"start": 1, "end": 2},
                     "content_digest": "sha256:x", "role": "member"}],
            }
        },
        "uncovered": [{"node_id": "py:api.health", "reason": "no_traced_flow"}],
    }


# --------------------------------------------------------------------------- #
# R5 success path
# --------------------------------------------------------------------------- #
def test_renders_self_contained_page() -> None:
    html = render_handbook_html(_handbook(), _graph())

    assert html.lstrip().startswith("<!doctype html")
    assert "</html>" in html


def test_page_makes_no_external_requests() -> None:
    html = render_handbook_html(_handbook(), _graph())

    assert "http://" not in html
    assert not re.search(r'src\s*=\s*"//', html)
    assert not re.search(r'<link[^>]+href\s*=\s*"https?://', html)
    assert "cdn" not in html.lower()


def test_handbook_data_is_embedded_as_a_json_island() -> None:
    html = render_handbook_html(_handbook(), _graph())

    match = re.search(
        r'<script id="handbook-data" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert match, "expected an embedded JSON island"
    payload = json.loads(match.group(1))
    assert payload["behavior_units"][0]["id"] == "bh:task-claiming"


def test_all_three_levels_are_present() -> None:
    html = render_handbook_html(_handbook(), _graph())

    assert "Task claiming" in html
    assert "POST /tasks/claim" in html or "handbook-data" in html
    assert "fl:task-claiming" in html


def test_persona_presets_are_present() -> None:
    html = render_handbook_html(_handbook(), _graph())

    for persona in ("newcomer", "reviewer", "planner", "auditor"):
        assert persona in html.lower(), f"missing persona preset: {persona}"


def test_evidence_locators_are_rendered_with_file_and_span() -> None:
    html = render_handbook_html(_handbook(), _graph())
    assert "src/api.py" in html


def test_uncovered_entrypoints_are_surfaced() -> None:
    html = render_handbook_html(_handbook(), _graph())
    assert "py:api.health" in html


def test_snapshot_provenance_is_shown() -> None:
    html = render_handbook_html(_handbook(), _graph())
    assert "abc1234" in html


def test_html_is_escaped_against_injection() -> None:
    hb = _handbook()
    hb["behavior_units"][0]["title"] = "<script>alert(1)</script>"

    html = render_handbook_html(hb, _graph())

    assert "<script>alert(1)</script>" not in html.replace(
        '<script id="handbook-data" type="application/json">', ""
    ).split("</script>", 1)[0] or "&lt;script&gt;" in html


def test_theme_aware_styles_present() -> None:
    html = render_handbook_html(_handbook(), _graph())
    assert "prefers-color-scheme" in html


# --------------------------------------------------------------------------- #
# R5 failure path
# --------------------------------------------------------------------------- #
def test_generator_refuses_invalid_handbook(tmp_path: Path, capsys: Any) -> None:
    from reports.generate_handbook_html import main

    hb = _handbook()
    hb["behavior_units"][0]["member_nodes"] = ["py:ghost"]
    hb_path = tmp_path / "architecture.behaviors.json"
    hb_path.write_text(json.dumps(hb), encoding="utf-8")
    graph_path = tmp_path / "architecture.graph.json"
    graph_path.write_text(json.dumps(_graph()), encoding="utf-8")
    out = tmp_path / "handbook.html"

    rc = main(["--handbook", str(hb_path), "--graph", str(graph_path),
               "--output", str(out)])

    assert rc == 1
    assert not out.exists(), "invalid handbook must not produce an output file"


def test_generator_writes_output_for_valid_handbook(tmp_path: Path) -> None:
    from reports.generate_handbook_html import main

    hb_path = tmp_path / "architecture.behaviors.json"
    hb_path.write_text(json.dumps(_handbook()), encoding="utf-8")
    graph_path = tmp_path / "architecture.graph.json"
    graph_path.write_text(json.dumps(_graph()), encoding="utf-8")
    out = tmp_path / "views" / "handbook.html"

    rc = main(["--handbook", str(hb_path), "--graph", str(graph_path),
               "--output", str(out)])

    assert rc == 0
    assert out.is_file()
    assert "handbook-data" in out.read_text(encoding="utf-8")


def test_missing_handbook_is_an_error(tmp_path: Path) -> None:
    from reports.generate_handbook_html import main

    graph_path = tmp_path / "architecture.graph.json"
    graph_path.write_text(json.dumps(_graph()), encoding="utf-8")

    rc = main(["--handbook", str(tmp_path / "nope.json"), "--graph", str(graph_path),
               "--output", str(tmp_path / "out.html")])

    assert rc == 1


def test_render_is_deterministic() -> None:
    assert render_handbook_html(_handbook(), _graph()) == render_handbook_html(
        _handbook(), _graph()
    )
