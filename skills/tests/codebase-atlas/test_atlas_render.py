"""Tests for rendering and the CLI contract.

The rendered page is the deliverable, so these tests assert the properties that
make it safe to open and share: self-containment, correct escaping, an honest
coverage disclosure, and byte-stable output for a fixed input.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import build_atlas
import pytest
from atlas_model import build_view_model
from atlas_render import render_page


@pytest.fixture
def page(tiny_graph: dict, tmp_path: Path) -> str:
    return render_page(build_view_model(tiny_graph, tmp_path, measure=False))


class TestSelfContainment:
    def test_page_makes_no_external_requests(self, page: str) -> None:
        # A strict reading of "self-contained": no scheme-bearing URLs at all, so
        # the page works offline, from a file:// path, and under a strict CSP.
        for pattern in (r'src\s*=\s*["\']https?:', r'href\s*=\s*["\']https?:',
                        r"@import", r"fetch\(", r"XMLHttpRequest", r"WebSocket"):
            assert not re.search(pattern, page), f"page references {pattern}"

    def test_styles_and_scripts_are_inline(self, page: str) -> None:
        assert "<style>" in page and "<script>" in page
        assert not re.search(r"<link[^>]+stylesheet", page)

    def test_page_is_a_complete_document(self, page: str) -> None:
        assert page.startswith("<!doctype html>")
        assert page.rstrip().endswith("</html>")


class TestDataEmbedding:
    def test_payload_parses_back_out_of_the_page(self, page: str) -> None:
        raw = re.search(
            r'<script id="atlas-data" type="application/json">(.*?)</script>',
            page,
            re.DOTALL,
        )
        assert raw is not None
        payload = json.loads(raw.group(1))
        assert payload["meta"]["moduleCount"] == 4

    def test_script_terminator_in_data_cannot_break_out(self, tiny_graph: dict, tmp_path: Path) -> None:
        # A hostile (or merely unlucky) symbol name must not end the script tag.
        hostile = dict(tiny_graph)
        hostile["nodes"] = [
            dict(tiny_graph["nodes"][0], name="</script><script>alert(1)</script>")
        ]
        page = render_page(build_view_model(hostile, tmp_path, measure=False))
        body = page.split('<script id="atlas-data"', 1)[1].split("</script>", 1)[0]
        assert "alert(1)" not in body or "\\u003c" in body
        assert "<script>alert(1)" not in page

    def test_embedded_json_escapes_angle_brackets(self, tiny_graph: dict, tmp_path: Path) -> None:
        hostile = dict(tiny_graph)
        hostile["nodes"] = [dict(tiny_graph["nodes"][0], name="a<b>c")]
        page = render_page(build_view_model(hostile, tmp_path, measure=False))
        raw = re.search(
            r'<script id="atlas-data" type="application/json">(.*?)</script>',
            page,
            re.DOTALL,
        ).group(1)
        assert "\\u003c" in raw
        # JSON.parse restores the original characters, so no data is corrupted.
        assert json.loads(raw)["symbols"][0]["name"] == "a<b>c"


class TestCoverageBanner:
    def test_gap_is_announced_as_an_alert(self, tiny_graph: dict, tmp_path: Path) -> None:
        (tmp_path / "unseen.py").write_text("", encoding="utf-8")
        page = render_page(build_view_model(tiny_graph, tmp_path, measure=True))
        assert 'role="alert"' in page
        assert "Partial coverage" in page

    def test_banner_names_the_uncovered_directories(self, tiny_graph: dict, tmp_path: Path) -> None:
        (tmp_path / "untouched").mkdir()
        (tmp_path / "untouched" / "x.py").write_text("", encoding="utf-8")
        page = render_page(build_view_model(tiny_graph, tmp_path, measure=True))
        assert "untouched" in page

    def test_full_coverage_reports_status_not_alert(self, tmp_path: Path) -> None:
        (tmp_path / "api.py").write_text("", encoding="utf-8")
        graph = {
            "snapshots": [{"generated_at": "t", "git_sha": "s"}],
            "nodes": [{"id": "py:api.f", "kind": "function", "language": "python",
                       "name": "f", "file": "api.py", "span": {"start": 1}, "tags": []}],
            "edges": [],
        }
        page = render_page(build_view_model(graph, tmp_path, measure=True))
        assert 'role="status"' in page
        assert "Partial coverage" not in page

    def test_no_banner_when_measurement_is_skipped(self, page: str) -> None:
        assert "Partial coverage" not in page
        assert 'role="alert"' not in page


class TestEscaping:
    def test_html_metacharacters_in_metadata_are_escaped(self, tiny_graph: dict, tmp_path: Path) -> None:
        graph = dict(tiny_graph)
        graph["snapshots"] = [{"generated_at": '<img src=x onerror=alert(1)>', "git_sha": "s"}]
        page = render_page(build_view_model(graph, tmp_path, measure=False))
        assert "<img src=x" not in page
        assert "&lt;img" in page


class TestDeterminism:
    def test_identical_input_renders_identical_bytes(self, tiny_graph: dict, tmp_path: Path) -> None:
        a = render_page(build_view_model(tiny_graph, tmp_path, measure=False))
        b = render_page(build_view_model(tiny_graph, tmp_path, measure=False))
        assert a == b

    def test_input_ordering_does_not_change_output(self, tiny_graph: dict, tmp_path: Path) -> None:
        a = render_page(build_view_model(tiny_graph, tmp_path, measure=False))
        shuffled = dict(tiny_graph)
        shuffled["nodes"] = list(reversed(tiny_graph["nodes"]))
        shuffled["edges"] = list(reversed(tiny_graph["edges"]))
        b = render_page(build_view_model(shuffled, tmp_path, measure=False))
        assert a == b


class TestCli:
    @pytest.fixture
    def repo(self, tmp_path: Path, tiny_graph: dict) -> Path:
        (tmp_path / ".git").mkdir()
        graph_dir = tmp_path / "docs" / "architecture-analysis"
        graph_dir.mkdir(parents=True)
        (graph_dir / "architecture.graph.json").write_text(
            json.dumps(tiny_graph), encoding="utf-8"
        )
        return tmp_path

    def test_writes_the_default_output_path(self, repo: Path, capsys) -> None:
        assert build_atlas.main(["--repo-root", str(repo), "--no-coverage"]) == 0
        out = repo / "docs" / "architecture-analysis" / "atlas" / "index.html"
        assert out.is_file()
        assert "Codebase Atlas" in out.read_text(encoding="utf-8")
        assert "wrote" in capsys.readouterr().out

    def test_missing_graph_exits_one(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        assert build_atlas.main(["--repo-root", str(tmp_path)]) == 1

    def test_check_reports_drift_when_output_absent(self, repo: Path) -> None:
        assert build_atlas.main(["--repo-root", str(repo), "--no-coverage", "--check"]) == 2

    def test_check_is_clean_immediately_after_a_write(self, repo: Path) -> None:
        build_atlas.main(["--repo-root", str(repo), "--no-coverage"])
        assert build_atlas.main(["--repo-root", str(repo), "--no-coverage", "--check"]) == 0

    def test_check_detects_a_stale_output(self, repo: Path) -> None:
        build_atlas.main(["--repo-root", str(repo), "--no-coverage"])
        out = repo / "docs" / "architecture-analysis" / "atlas" / "index.html"
        out.write_text("stale", encoding="utf-8")
        assert build_atlas.main(["--repo-root", str(repo), "--no-coverage", "--check"]) == 2

    def test_check_never_writes(self, repo: Path) -> None:
        out = repo / "docs" / "architecture-analysis" / "atlas" / "index.html"
        build_atlas.main(["--repo-root", str(repo), "--no-coverage", "--check"])
        assert not out.exists()

    def test_json_only_emits_the_view_model(self, repo: Path, capsys) -> None:
        assert build_atlas.main(["--repo-root", str(repo), "--no-coverage", "--json-only"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["meta"]["moduleCount"] == 4

    def test_explicit_output_path_is_honoured(self, repo: Path, tmp_path: Path) -> None:
        target = tmp_path / "custom" / "atlas.html"
        assert build_atlas.main(
            ["--repo-root", str(repo), "--no-coverage", "--output", str(target)]
        ) == 0
        assert target.is_file()

    def test_repo_root_is_discovered_from_a_subdirectory(self, repo: Path, monkeypatch) -> None:
        nested = repo / "a" / "b"
        nested.mkdir(parents=True)
        monkeypatch.chdir(nested)
        assert build_atlas.main(["--no-coverage"]) == 0
        assert (repo / "docs" / "architecture-analysis" / "atlas" / "index.html").is_file()


class TestCoverageBannerGapPredicate:
    """Regressions for the success-banner threshold found in review of PR #276."""

    def _graph(self, files: list[str]) -> dict:
        return {
            "snapshots": [{"generated_at": "t", "git_sha": "s"}],
            "nodes": [
                {
                    "id": f"py:{i}",
                    "kind": "function",
                    "language": "python",
                    "name": f"f{i}",
                    "file": f,
                    "span": {"start": 1},
                    "tags": [],
                }
                for i, f in enumerate(files)
            ],
            "edges": [],
        }

    def test_high_but_incomplete_coverage_still_alerts(self, tmp_path: Path) -> None:
        # 199 of 200 files covered = 99.5%, which the old `< 99.0` threshold
        # rendered as full coverage.
        covered = [f"m{i}.py" for i in range(199)]
        for name in [*covered, "forgotten.py"]:
            (tmp_path / name).write_text("", encoding="utf-8")

        page = render_page(build_view_model(self._graph(covered), tmp_path, measure=True))
        assert 'role="alert"' in page
        assert "Partial coverage" in page

    def test_stale_graph_alerts_even_at_full_disk_coverage(self, tmp_path: Path) -> None:
        (tmp_path / "present.py").write_text("", encoding="utf-8")
        graph = self._graph(["present.py", "deleted.py"])

        # Every file on disk is matched, so coverage is 100% — but the graph still
        # names a file that is gone, which must not read as a clean bill of health.
        page = render_page(build_view_model(graph, tmp_path, measure=True))
        assert 'role="alert"' in page
        assert "no longer exist" in page

    def test_genuinely_complete_coverage_reports_success(self, tmp_path: Path) -> None:
        (tmp_path / "only.py").write_text("", encoding="utf-8")
        page = render_page(build_view_model(self._graph(["only.py"]), tmp_path, measure=True))
        assert 'role="status"' in page
        assert 'role="alert"' not in page


class TestCliCoverageOutput:
    def test_prints_the_matched_numerator(self, tmp_path: Path, tiny_graph: dict, capsys) -> None:
        (tmp_path / ".git").mkdir()
        graph_dir = tmp_path / "docs" / "architecture-analysis"
        graph_dir.mkdir(parents=True)
        (graph_dir / "architecture.graph.json").write_text(
            json.dumps(tiny_graph), encoding="utf-8"
        )
        (tmp_path / "api.py").write_text("", encoding="utf-8")
        (tmp_path / "elsewhere.py").write_text("", encoding="utf-8")

        assert build_atlas.main(["--repo-root", str(tmp_path)]) == 0
        out = capsys.readouterr().out
        # api.py matches; store.py is named by the graph but absent. The printed
        # numerator must be the matched count (1), the same basis as the percent —
        # printing filesInGraph (2) contradicted the percentage on the same line.
        assert "coverage python: <=1/2 files (<=50.0%), from 2 distinct name(s)" in out
        assert "1 graph file(s) absent from disk (stale)" in out


class TestCoverageBannerDisclosesBothBounds:
    def test_banner_shows_upper_bound_and_distinct_name_floor(self, tmp_path: Path) -> None:
        # Three packages share __init__.py; the graph names it once. Basename
        # matching credits all three, so the file count is an upper bound and the
        # distinct-name count is the floor. Both must appear, or the reader cannot
        # tell an inflated number from a real one.
        for name in ("a", "b", "c"):
            d = tmp_path / name
            d.mkdir()
            (d / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "never_seen.py").write_text("", encoding="utf-8")

        graph = {
            "snapshots": [{"generated_at": "t", "git_sha": "s"}],
            "nodes": [{"id": "py:__init__", "kind": "module", "language": "python",
                       "name": "__init__", "file": "__init__.py",
                       "span": {"start": 1}, "tags": []}],
            "edges": [],
        }
        page = render_page(build_view_model(graph, tmp_path, measure=True))
        assert "at most 3 of 4 files" in page
        assert "1 distinct file name(s) the analyzer examined" in page
        assert "upper bound" in page
