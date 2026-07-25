"""Tests for the atlas view-model: grouping, aggregation, nesting, coverage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from atlas_model import (
    AtlasInputError,
    aggregate_edges,
    build_view_model,
    group_modules,
    load_graph,
    measure_coverage,
    module_key,
    nest_symbols,
)


class TestLoadGraph:
    def test_missing_file_names_the_remedy(self, tmp_path: Path) -> None:
        with pytest.raises(AtlasInputError, match="make architecture"):
            load_graph(tmp_path / "nope.json")

    def test_invalid_json_is_reported_as_such(self, tmp_path: Path) -> None:
        bad = tmp_path / "g.json"
        bad.write_text("{not json", encoding="utf-8")
        with pytest.raises(AtlasInputError, match="not valid JSON"):
            load_graph(bad)

    def test_missing_node_list_is_rejected(self, tmp_path: Path) -> None:
        bad = tmp_path / "g.json"
        bad.write_text(json.dumps({"edges": []}), encoding="utf-8")
        with pytest.raises(AtlasInputError, match="missing a 'nodes' list"):
            load_graph(bad)

    def test_roundtrips_a_valid_graph(self, tmp_path: Path, tiny_graph: dict) -> None:
        path = tmp_path / "g.json"
        path.write_text(json.dumps(tiny_graph), encoding="utf-8")
        assert len(load_graph(path)["nodes"]) == 6


class TestGrouping:
    def test_groups_by_language_and_file(self, tiny_graph: dict) -> None:
        modules = group_modules(tiny_graph["nodes"])
        assert [m.file for m in modules] == [
            "api.py",
            "store.py",
            "(unfiled)",
            "001_init.sql",
        ]

    def test_nodes_without_a_file_land_in_the_unfiled_group(self, tiny_graph: dict) -> None:
        modules = {m.file: m for m in group_modules(tiny_graph["nodes"])}
        # The SQL analyzer emits indexes and triggers with no file attribution.
        # They must be grouped, never silently dropped.
        assert [s["id"] for s in modules["(unfiled)"].symbols] == ["pg:idx_things"]

    def test_symbols_are_ordered_by_declaration_line(self, tiny_graph: dict) -> None:
        modules = {m.file: m for m in group_modules(tiny_graph["nodes"])}
        assert [s["line"] for s in modules["api.py"].symbols] == [10, 30]

    def test_kind_counts_and_tags_summarise_the_module(self, tiny_graph: dict) -> None:
        modules = {m.file: m for m in group_modules(tiny_graph["nodes"])}
        assert modules["api.py"].kind_counts == {"function": 2}
        assert modules["api.py"].tags == ["async", "entry_point", "private"]

    def test_grouping_is_stable_regardless_of_input_order(self, tiny_graph: dict) -> None:
        forward = [m.key for m in group_modules(tiny_graph["nodes"])]
        reverse = [m.key for m in group_modules(list(reversed(tiny_graph["nodes"])))]
        assert forward == reverse

    def test_nodes_without_an_id_are_skipped(self) -> None:
        assert group_modules([{"kind": "function", "file": "a.py"}]) == []


class TestNesting:
    def test_columns_nest_under_their_table(self, tiny_graph: dict) -> None:
        modules = {m.file: m for m in group_modules(tiny_graph["nodes"])}
        tree = nest_symbols(modules["001_init.sql"].symbols)
        assert [t["name"] for t in tree] == ["public.things"]
        assert [c["name"] for c in tree[0]["children"]] == ["id"]

    def test_modules_without_containers_stay_flat(self, tiny_graph: dict) -> None:
        modules = {m.file: m for m in group_modules(tiny_graph["nodes"])}
        tree = nest_symbols(modules["api.py"].symbols)
        assert [t["name"] for t in tree] == ["handler", "_helper"]
        assert all(t["children"] == [] for t in tree)

    def test_no_symbol_is_lost_when_nesting(self, tiny_graph: dict) -> None:
        modules = {m.file: m for m in group_modules(tiny_graph["nodes"])}
        for module in modules.values():
            tree = nest_symbols(module.symbols)
            flat = []

            def walk(items: list) -> None:
                for item in items:
                    flat.append(item["id"])
                    walk(item["children"])

            walk(tree)
            assert sorted(flat) == sorted(s["id"] for s in module.symbols)

    def test_nesting_picks_the_most_specific_container(self) -> None:
        symbols = [
            {"id": "pg:a", "name": "a", "kind": "table", "line": 1, "tags": (), "signature": {}},
            {"id": "pg:a.b", "name": "b", "kind": "table", "line": 2, "tags": (), "signature": {}},
            {"id": "pg:a.b.c", "name": "c", "kind": "column", "line": 3, "tags": (), "signature": {}},
        ]
        tree = {t["id"]: t for t in nest_symbols(symbols)}
        # pg:a.b.c prefixes-matches both pg:a and pg:a.b; the deeper one wins.
        assert [c["id"] for c in tree["pg:a.b"]["children"]] == ["pg:a.b.c"]
        assert tree["pg:a"]["children"] == []


class TestEdgeAggregation:
    def test_repeated_pairs_accumulate_weight(self, tiny_graph: dict) -> None:
        modules = group_modules(tiny_graph["nodes"])
        mapping = {s["id"]: m.key for m in modules for s in m.symbols}
        edges = aggregate_edges(tiny_graph["edges"], mapping)
        assert len(edges) == 1
        assert edges[0]["weight"] == 2
        assert edges[0]["source"] == module_key("python", "api.py")
        assert edges[0]["target"] == module_key("python", "store.py")

    def test_intra_module_edges_are_dropped(self, tiny_graph: dict) -> None:
        modules = group_modules(tiny_graph["nodes"])
        mapping = {s["id"]: m.key for m in modules for s in m.symbols}
        edges = aggregate_edges(tiny_graph["edges"], mapping)
        assert all(e["source"] != e["target"] for e in edges)

    def test_edges_to_unknown_nodes_are_dropped(self, tiny_graph: dict) -> None:
        edges = aggregate_edges(tiny_graph["edges"], {})
        assert edges == []


class TestCoverage:
    def test_reports_the_gap_between_graph_and_disk(self, tmp_path: Path) -> None:
        (tmp_path / "covered").mkdir()
        (tmp_path / "covered" / "seen.py").write_text("", encoding="utf-8")
        (tmp_path / "hidden").mkdir()
        for i in range(3):
            (tmp_path / "hidden" / f"unseen{i}.py").write_text("", encoding="utf-8")

        nodes = [{"id": "py:seen.f", "language": "python", "file": "seen.py"}]
        coverage = {c.language: c for c in measure_coverage(tmp_path, nodes)}

        assert coverage["python"].files_in_graph == 1
        assert coverage["python"].files_matched == 1
        assert coverage["python"].files_missing == 0
        assert coverage["python"].files_on_disk == 4
        assert coverage["python"].percent == 25.0
        assert coverage["python"].uncovered_top_dirs == (("hidden", 3),)

    def test_graph_naming_absent_files_is_reported_as_staleness(self, tmp_path: Path) -> None:
        (tmp_path / "still_here.py").write_text("", encoding="utf-8")
        nodes = [
            {"id": "py:still_here.f", "language": "python", "file": "still_here.py"},
            {"id": "py:deleted.f", "language": "python", "file": "deleted.py"},
        ]
        coverage = {c.language: c for c in measure_coverage(tmp_path, nodes)}
        # Percent must be driven by matched files, never by the raw graph count,
        # or a stale graph would claim >100% coverage and hide the gap.
        assert coverage["python"].files_in_graph == 2
        assert coverage["python"].files_matched == 1
        assert coverage["python"].files_missing == 1
        assert coverage["python"].percent == 100.0

    def test_percent_never_exceeds_full_coverage(self, tmp_path: Path) -> None:
        (tmp_path / "one.py").write_text("", encoding="utf-8")
        nodes = [
            {"id": f"py:g{i}.f", "language": "python", "file": f"gone{i}.py"}
            for i in range(5)
        ]
        coverage = {c.language: c for c in measure_coverage(tmp_path, nodes)}
        assert coverage["python"].percent == 0.0

    def test_excluded_directories_are_not_counted(self, tmp_path: Path) -> None:
        for name in (".venv", "node_modules", "__pycache__", "site-packages"):
            d = tmp_path / name
            d.mkdir()
            (d / "vendor.py").write_text("", encoding="utf-8")
        (tmp_path / "real.py").write_text("", encoding="utf-8")

        coverage = {c.language: c for c in measure_coverage(tmp_path, [])}
        assert coverage["python"].files_on_disk == 1

    def test_languages_absent_from_the_graph_report_zero(self, tmp_path: Path) -> None:
        (tmp_path / "app.ts").write_text("", encoding="utf-8")
        coverage = {c.language: c for c in measure_coverage(tmp_path, [])}
        # A configured-but-nonexistent analyzer root shows up as 0%, which is the
        # signal that made the empty ts_analysis.json visible in the first place.
        assert coverage["typescript"].files_in_graph == 0
        assert coverage["typescript"].percent == 0.0

    def test_percent_is_zero_when_nothing_is_on_disk(self, tmp_path: Path) -> None:
        coverage = measure_coverage(tmp_path, [])
        assert all(c.percent == 0.0 for c in coverage)


class TestViewModel:
    def test_meta_counts_match_the_source_graph(self, tiny_graph: dict, tmp_path: Path) -> None:
        vm = build_view_model(tiny_graph, tmp_path, measure=False)
        assert vm["meta"]["nodeCount"] == 6
        assert vm["meta"]["edgeCount"] == 4
        assert vm["meta"]["moduleCount"] == 4
        assert vm["meta"]["gitSha"] == "abc123def456"

    def test_dangling_edges_are_counted_not_hidden(self, tiny_graph: dict, tmp_path: Path) -> None:
        vm = build_view_model(tiny_graph, tmp_path, measure=False)
        # One edge targets py:ghost.missing, which is absent from the node list.
        assert vm["meta"]["danglingEdges"] == 1
        assert len(vm["symbolEdges"]) == 3

    def test_entrypoints_are_flagged_on_symbols(self, tiny_graph: dict, tmp_path: Path) -> None:
        vm = build_view_model(tiny_graph, tmp_path, measure=False)
        entries = {s["id"]: s["entry"] for s in vm["symbols"]}
        assert entries["py:api.handler"] is True
        assert entries["py:store.save"] is False

    def test_every_symbol_maps_to_a_declared_module(self, tiny_graph: dict, tmp_path: Path) -> None:
        vm = build_view_model(tiny_graph, tmp_path, measure=False)
        keys = {m["key"] for m in vm["modules"]}
        assert {s["module"] for s in vm["symbols"]} <= keys

    def test_measure_false_skips_the_disk_scan(self, tiny_graph: dict, tmp_path: Path) -> None:
        assert build_view_model(tiny_graph, tmp_path, measure=False)["coverage"] == []

    def test_view_model_is_deterministic(self, tiny_graph: dict, tmp_path: Path) -> None:
        first = build_view_model(tiny_graph, tmp_path, measure=False)
        shuffled = dict(tiny_graph)
        shuffled["nodes"] = list(reversed(tiny_graph["nodes"]))
        shuffled["edges"] = list(reversed(tiny_graph["edges"]))
        second = build_view_model(shuffled, tmp_path, measure=False)
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
