"""Tests for ``atlas_tree`` / ``build_atlas.py --tree`` (add-visual-code-explainer)."""

from __future__ import annotations

import copy
import io
import json
import re
import time
from pathlib import Path

import build_atlas
import pytest
from atlas_model import build_view_model
from atlas_tree import MAX_HOPS, footer, render_tree, resolve_target

COMMITTED_GRAPH = Path("docs/architecture-analysis/architecture.graph.json")
LINE_RE = re.compile(
    r"^(?P<indent> *)(?P<name>\S.*?)\s{2}\((?P<file>[^:]*):(?P<line>\d+)\)\s{2}\[(?P<kind>[^\]]+)\]"
)


def _view(tiny_graph: dict, tmp_path: Path, *, measure: bool = True) -> dict:
    """Write graph + touch source files so coverage measure can run."""
    graph_path = tmp_path / "g.json"
    graph_path.write_text(json.dumps(tiny_graph), encoding="utf-8")
    for node in tiny_graph["nodes"]:
        f = node.get("file") or ""
        if f and f != "(unfiled)":
            p = tmp_path / f
            if not p.exists():
                # Parents matter: every fixture path was flat, so a nested
                # module could not be expressed here at all — which is part of
                # why basename resolution against `a/b.py` went untested.
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("# stub\n", encoding="utf-8")
    return build_view_model(tiny_graph, tmp_path, measure=measure)


def _tree_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln and not ln.startswith("graph @") and ln not in ("callees:", "callers:")]


def _parsed_nodes(text: str) -> list[dict]:
    nodes = []
    for ln in _tree_lines(text):
        m = LINE_RE.match(ln)
        assert m, f"unparseable tree line: {ln!r}"
        nodes.append(m.groupdict())
    return nodes


class TestCalleesOrdering:
    def test_callees_sorted_by_name_then_id(self, tiny_graph: dict, tmp_path: Path) -> None:
        view = _view(tiny_graph, tmp_path, measure=False)
        code, text = render_tree(view, "py:api.handler", hops=1, direction="out", include_footer=False)
        assert code == 0
        # handler calls _helper and save — sorted by name: _helper then save
        body = _tree_lines(text)
        assert body[0].startswith("handler  (api.py:10)  [function]")
        assert "_helper" in body[1]
        assert "save" in body[2]


class TestCallersHopCap:
    def test_callers_hops_1_and_more_suffix(self, tiny_graph: dict, tmp_path: Path) -> None:
        graph = copy.deepcopy(tiny_graph)
        # Give handler an inbound caller so hops=1 marks it with (+1 more).
        graph["nodes"].append(
            {
                "id": "py:api.entry",
                "kind": "function",
                "language": "python",
                "name": "entry",
                "file": "api.py",
                "span": {"start": 1, "end": 2},
                "tags": [],
                "signatures": {},
            }
        )
        graph["edges"].append(
            {
                "from": "py:api.entry",
                "to": "py:api.handler",
                "type": "call",
                "confidence": "high",
                "evidence": "ast:call:handler",
            }
        )
        view = _view(graph, tmp_path, measure=False)
        code, text = render_tree(view, "py:store.save", hops=1, direction="in", include_footer=False)
        assert code == 0
        body = _tree_lines(text)
        assert body[0].startswith("save  (store.py:5)  [function]")
        caller_lines = body[1:]
        assert len(caller_lines) == 2
        handler_line = next(ln for ln in caller_lines if "handler" in ln)
        assert "(+1 more)" in handler_line


class TestNonCallEdgesExcluded:
    def test_import_edges_never_appear(self, tiny_graph: dict, tmp_path: Path) -> None:
        graph = copy.deepcopy(tiny_graph)
        # B is save; add import edge handler -> something that must not show as callee
        graph["nodes"].append(
            {
                "id": "py:store.imported",
                "kind": "function",
                "language": "python",
                "name": "imported",
                "file": "store.py",
                "span": {"start": 40, "end": 41},
                "tags": [],
                "signatures": {},
            }
        )
        graph["edges"].append(
            {
                "from": "py:api.handler",
                "to": "py:store.imported",
                "type": "import",
                "confidence": "high",
                "evidence": "import",
            }
        )
        view = _view(graph, tmp_path, measure=False)
        code, text = render_tree(view, "handler", hops=2, direction="out", include_footer=False)
        assert code == 0
        assert "imported" not in text
        assert "save" in text


class TestCyclePrintedOnce:
    def test_cycle_suffix(self, tiny_graph: dict, tmp_path: Path) -> None:
        graph = copy.deepcopy(tiny_graph)
        # create A -> B -> A cycle between handler and _helper (already handler->_helper);
        # add _helper -> handler
        graph["edges"].append(
            {
                "from": "py:api._helper",
                "to": "py:api.handler",
                "type": "call",
                "confidence": "high",
                "evidence": "cycle",
            }
        )
        view = _view(graph, tmp_path, measure=False)
        code, text = render_tree(view, "py:api.handler", hops=4, direction="out", include_footer=False)
        assert code == 0
        cycle_lines = [ln for ln in text.splitlines() if "(cycle)" in ln]
        assert len(cycle_lines) >= 1
        assert any("handler" in ln and "(cycle)" in ln for ln in cycle_lines)


class TestFileTargetModuleView:
    def test_basename_roots_at_module(self, tiny_graph: dict, tmp_path: Path) -> None:
        view = _view(tiny_graph, tmp_path, measure=False)
        code, text = render_tree(view, "api.py", hops=1, direction="out", include_footer=False)
        assert code == 0
        body = _tree_lines(text)
        assert body[0].startswith("api.py  (api.py:1)  [module]")
        # hop 1 = module symbols
        names = [LINE_RE.match(ln).group("name") for ln in body[1:]]  # type: ignore[union-attr]
        assert names == ["_helper", "handler"]

    def test_basename_resolves_a_nested_module_path(
        self, tiny_graph: dict, tmp_path: Path
    ) -> None:
        """`--tree webhook.py` must find `notifications/webhook.py`.

        The spec resolves a target as "module file path or basename". The
        basename arm compared each module's whole `file` value to the target
        basename, which only ever matched modules at the repository root, so a
        nested module exited 2 while its full path succeeded.
        """
        graph = copy.deepcopy(tiny_graph)
        for node in graph["nodes"]:
            if node.get("file") == "api.py":
                node["file"] = "notifications/api.py"
        view = _view(graph, tmp_path, measure=False)

        code, text = render_tree(
            view, "api.py", hops=1, direction="out", include_footer=False
        )

        assert code == 0, text
        # Name stays the module's own name; the nested path shows in the locator.
        assert _tree_lines(text)[0].startswith("api.py  (notifications/api.py:1)  [module]")

    def test_full_nested_path_still_resolves(
        self, tiny_graph: dict, tmp_path: Path
    ) -> None:
        graph = copy.deepcopy(tiny_graph)
        for node in graph["nodes"]:
            if node.get("file") == "api.py":
                node["file"] = "notifications/api.py"
        view = _view(graph, tmp_path, measure=False)

        code, _ = render_tree(
            view, "notifications/api.py", hops=1, direction="out", include_footer=False
        )

        assert code == 0


class TestExitCodes:
    def test_unknown_target_exits_2(self, tiny_graph: dict, tmp_path: Path) -> None:
        view = _view(tiny_graph, tmp_path, measure=False)
        err = io.StringIO()
        code, text = render_tree(view, "no-such-symbol", include_footer=False, err_file=err)
        assert code == 2
        assert "not found" in err.getvalue()
        assert text == ""

    def test_ambiguous_name_exits_3(self, tiny_graph: dict, tmp_path: Path) -> None:
        graph = copy.deepcopy(tiny_graph)
        graph["nodes"].append(
            {
                "id": "py:other.handler",
                "kind": "function",
                "language": "python",
                "name": "handler",
                "file": "other.py",
                "span": {"start": 1, "end": 2},
                "tags": [],
                "signatures": {},
            }
        )
        view = _view(graph, tmp_path, measure=False)
        err = io.StringIO()
        code, _ = render_tree(view, "handler", include_footer=False, err_file=err)
        assert code == 3
        cands = [ln for ln in err.getvalue().splitlines() if ln.strip()]
        assert cands == sorted(cands)
        assert "py:api.handler" in cands
        assert "py:other.handler" in cands


class TestDeterminism:
    def test_byte_identical_across_two_runs(self, tiny_graph: dict, tmp_path: Path) -> None:
        view = _view(tiny_graph, tmp_path, measure=False)
        _, a = render_tree(view, "handler", hops=2, direction="out", include_footer=False)
        _, b = render_tree(view, "handler", hops=2, direction="out", include_footer=False)
        assert a == b


class TestCoverageFooter:
    def test_footer_matches_coverage_percent(self, tiny_graph: dict, tmp_path: Path) -> None:
        view = _view(tiny_graph, tmp_path, measure=True)
        line = footer(view)
        assert line.startswith("graph @ abc123d · ")
        assert line.endswith(" covered")
        for cov in view["coverage"]:
            token = f"{cov['language']} {cov['percent']}%"
            assert token in line
        # languages sorted
        langs = [c["language"] for c in sorted(view["coverage"], key=lambda x: x["language"])]
        positions = [line.index(f"{lang} ") for lang in langs]
        assert positions == sorted(positions)
        # one-decimal shape
        for m in re.finditer(r"(\d+\.\d+)%", line):
            assert len(m.group(1).split(".")[1]) == 1

    def test_no_coverage_omits_footer(self, tiny_graph: dict, tmp_path: Path) -> None:
        view = _view(tiny_graph, tmp_path, measure=False)
        code, text = render_tree(view, "handler", include_footer=False)
        assert code == 0
        assert "graph @" not in text

    def test_empty_coverage_list_keeps_disclosure_shape(self, tiny_graph: dict, tmp_path: Path) -> None:
        view = _view(tiny_graph, tmp_path, measure=False)
        line = footer(view)
        assert line.startswith("graph @ abc123d · ")
        assert line.endswith(" covered")
        # D5 mapping: after '· ' / before trailing ' covered' yields the list (possibly empty)
        mid = line.split("· ", 1)[1]
        assert mid.endswith(" covered")
        assert mid[: -len(" covered")] == ""


class TestPrintedNodesMatchFixture:
    def test_every_printed_node_matches_fixture(self, tiny_graph: dict, tmp_path: Path) -> None:
        view = _view(tiny_graph, tmp_path, measure=False)
        code, text = render_tree(view, "handler", hops=2, direction="out", include_footer=False)
        assert code == 0
        fixture_pairs = {(n["name"], n["file"]) for n in tiny_graph["nodes"]}
        for node in _parsed_nodes(text):
            assert (node["name"], node["file"]) in fixture_pairs


class TestDefaultsAndClamp:
    def test_default_hops_and_direction(self, tiny_graph: dict, tmp_path: Path) -> None:
        view = _view(tiny_graph, tmp_path, measure=False)
        # defaults: hops=2, direction=out — handler reaches save via _helper and directly
        code, text = render_tree(view, "handler", include_footer=False)
        assert code == 0
        assert "save" in text

    def test_hops_above_four_clamped(self, tiny_graph: dict, tmp_path: Path) -> None:
        view = _view(tiny_graph, tmp_path, measure=False)
        err = io.StringIO()
        code, _ = render_tree(view, "handler", hops=99, include_footer=False, err_file=err)
        assert code == 0
        assert str(MAX_HOPS) in err.getvalue()
        assert "clamped" in err.getvalue().lower()

    def test_negative_hops_floored(self, tiny_graph: dict, tmp_path: Path) -> None:
        view = _view(tiny_graph, tmp_path, measure=False)
        err = io.StringIO()
        code, text = render_tree(view, "handler", hops=-3, include_footer=False, err_file=err)
        assert code == 0
        assert "clamped" in err.getvalue().lower()
        body = _tree_lines(text)
        assert len(body) == 1
        assert "(+" in body[0]


class TestIOErrorExit1:
    def test_unreadable_graph_via_cli(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing.json"
        code = build_atlas.main(
            ["--tree", "handler", "--graph", str(missing), "--repo-root", str(tmp_path), "--no-coverage"]
        )
        assert code == 1


class TestResolutionPrecedence:
    def test_exact_id_before_name(self, tiny_graph: dict, tmp_path: Path) -> None:
        graph = copy.deepcopy(tiny_graph)
        # Node whose id equals another node's name ("save")
        graph["nodes"].append(
            {
                "id": "save",
                "kind": "function",
                "language": "python",
                "name": "not_save",
                "file": "x.py",
                "span": {"start": 1, "end": 2},
                "tags": [],
                "signatures": {},
            }
        )
        view = _view(graph, tmp_path, measure=False)
        resolved = resolve_target(view, "save")
        assert resolved.kind == "symbol"  # type: ignore[union-attr]
        assert resolved.id == "save"  # type: ignore[union-attr]
        code, text = render_tree(view, "save", include_footer=False)
        assert code == 0
        assert text.startswith("not_save  (x.py:1)  [function]")

    def test_unique_name_resolves(self, tiny_graph: dict, tmp_path: Path) -> None:
        view = _view(tiny_graph, tmp_path, measure=False)
        resolved = resolve_target(view, "handler")
        assert resolved.kind == "symbol"  # type: ignore[union-attr]
        assert resolved.id == "py:api.handler"  # type: ignore[union-attr]


class TestDirectionBoth:
    def test_both_labelled_sections(self, tiny_graph: dict, tmp_path: Path) -> None:
        view = _view(tiny_graph, tmp_path, measure=False)
        code, text = render_tree(view, "handler", hops=1, direction="both", include_footer=False)
        assert code == 0
        assert "callees:" in text
        assert "callers:" in text
        # callees section lists _helper/save; callers of handler is empty beyond root
        callees_idx = text.index("callees:")
        callers_idx = text.index("callers:")
        assert callees_idx < callers_idx
        assert "_helper" in text[callees_idx:callers_idx]


class TestCLIWiring:
    def test_build_atlas_tree_dispatch(self, tiny_graph: dict, tmp_path: Path) -> None:
        graph_path = tmp_path / "g.json"
        graph_path.write_text(json.dumps(tiny_graph), encoding="utf-8")
        for node in tiny_graph["nodes"]:
            f = node.get("file") or ""
            if f:
                (tmp_path / f).write_text("x\n", encoding="utf-8")
        # Capture stdout via render path through main
        import contextlib

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = build_atlas.main(
                [
                    "--tree",
                    "handler",
                    "--hops",
                    "1",
                    "--direction",
                    "out",
                    "--graph",
                    str(graph_path),
                    "--repo-root",
                    str(tmp_path),
                    "--no-coverage",
                ]
            )
        assert code == 0
        out = buf.getvalue()
        assert "handler  (api.py:10)  [function]" in out
        assert "graph @" not in out  # --no-coverage


@pytest.mark.skipif(not COMMITTED_GRAPH.is_file(), reason="committed graph absent")
class TestCommittedGraph:
    def test_timing_under_two_seconds(self) -> None:
        start = time.perf_counter()
        code = build_atlas.main(
            ["--tree", "coordination_api.py", "--no-coverage"]
        )
        elapsed = time.perf_counter() - start
        assert code in (0, 2)  # 2 if basename not in this graph snapshot
        assert elapsed <= 2.0

    def test_deterministic_on_committed_graph(self, tmp_path: Path) -> None:
        import subprocess
        import sys

        script = "skills/codebase-atlas/scripts/build_atlas.py"
        # Prefer a resolvable target from the graph; fall back to a known module basename.
        target = "coordination_api.py"
        cmd = [sys.executable, script, "--tree", target, "--no-coverage"]
        a = subprocess.run(cmd, capture_output=True, text=True, check=False)
        b = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert a.returncode == b.returncode
        if a.returncode == 0:
            assert a.stdout == b.stdout
