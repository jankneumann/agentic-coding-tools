"""Tests for the roadmap renderer (YAML → markdown)."""

from __future__ import annotations

import pytest
from models import (
    DepEdge,
    DepEdgeSource,
    Effort,
    ItemStatus,
    Roadmap,
    RoadmapItem,
    RoadmapStatus,
    Scope,
)
from renderer import (
    check_roadmap_sync,
    render_roadmap,
)


def _make_roadmap(items: list[RoadmapItem] | None = None) -> Roadmap:
    """Create a test roadmap."""
    if items is None:
        items = [
            RoadmapItem(
                item_id="db-setup",
                title="Database Setup",
                status=ItemStatus.CANDIDATE,
                priority=1,
                effort=Effort.M,
                description="Set up the database layer.",
                acceptance_outcomes=["PostgreSQL running", "Migrations work"],
                change_id="db-setup",
            ),
            RoadmapItem(
                item_id="auth-service",
                title="Auth Service",
                status=ItemStatus.CANDIDATE,
                priority=2,
                effort=Effort.L,
                depends_on=["db-setup"],
                description="Implement authentication.",
                acceptance_outcomes=["OAuth2 works", "JWT issued"],
                change_id="auth-service",
                dep_edges=[
                    DepEdge(
                        id="db-setup",
                        source=DepEdgeSource.DETERMINISTIC,
                        rationale="write_allow overlap on src/db/**",
                    )
                ],
            ),
        ]
    return Roadmap(
        schema_version=1,
        roadmap_id="roadmap-test",
        source_proposal="docs/test-proposal.md",
        items=items,
        status=RoadmapStatus.PLANNING,
    )


class TestRenderBasic:
    def test_produces_markdown(self):
        md = render_roadmap(_make_roadmap())
        assert isinstance(md, str)
        assert len(md) > 100

    def test_contains_title(self):
        md = render_roadmap(_make_roadmap())
        assert "# Roadmap: roadmap-test" in md

    def test_contains_phase_table(self):
        md = render_roadmap(_make_roadmap())
        assert "| Priority | Item | Effort | Status | Dependencies |" in md
        assert "Database Setup" in md
        assert "Auth Service" in md

    def test_contains_item_details(self):
        md = render_roadmap(_make_roadmap())
        assert "### db-setup: Database Setup" in md
        assert "### auth-service: Auth Service" in md


class TestGeneratedMarkers:
    def test_markers_present(self):
        md = render_roadmap(_make_roadmap())
        assert "<!-- GENERATED: begin phase-table -->" in md
        assert "<!-- GENERATED: end phase-table -->" in md
        assert "<!-- GENERATED: begin dependency-dag -->" in md
        assert "<!-- GENERATED: end dependency-dag -->" in md
        assert "<!-- GENERATED: begin item-details -->" in md
        assert "<!-- GENERATED: end item-details -->" in md

    def test_markers_paired(self):
        md = render_roadmap(_make_roadmap())
        for name in ["phase-table", "dependency-dag", "item-details"]:
            begin = f"<!-- GENERATED: begin {name} -->"
            end = f"<!-- GENERATED: end {name} -->"
            assert md.count(begin) == 1
            assert md.count(end) == 1
            assert md.index(begin) < md.index(end)


class TestRoundTrip:
    def test_preserves_human_content(self):
        """Re-rendering should preserve human-authored sections."""
        roadmap = _make_roadmap()
        initial_md = render_roadmap(roadmap)

        # Inject human content between generated blocks
        modified_md = initial_md.replace(
            "<!-- GENERATED: end phase-table -->",
            "<!-- GENERATED: end phase-table -->\n\n"
            "## Cross-Cutting Themes\n\n"
            "All services must use structured logging.\n"
            "Security review required before each release.\n",
        )

        # Re-render with the modified markdown
        re_rendered = render_roadmap(roadmap, existing_md=modified_md)

        # Human content should survive
        assert "All services must use structured logging." in re_rendered
        assert "Security review required before each release." in re_rendered


class TestDepEdgeAttribution:
    def test_edges_show_source_in_details(self):
        """Rendered details should show DepEdge source and rationale."""
        md = render_roadmap(_make_roadmap())
        assert "deterministic" in md
        assert "write_allow overlap on src/db/**" in md


class TestMermaidDag:
    def test_dag_contains_mermaid(self):
        md = render_roadmap(_make_roadmap())
        assert "```mermaid" in md
        assert "graph TD" in md

    def test_dag_contains_edges(self):
        md = render_roadmap(_make_roadmap())
        assert "db-setup -->" in md


class TestEmptyRoadmap:
    def test_empty_items(self):
        roadmap = _make_roadmap(items=[])
        md = render_roadmap(roadmap)
        assert "# Roadmap: roadmap-test" in md
        assert "<!-- GENERATED: begin phase-table -->" in md


class TestCheckSync:
    def test_detects_no_drift_after_fresh_render(self, tmp_path):
        import yaml

        roadmap = _make_roadmap()
        md = render_roadmap(roadmap)

        yaml_path = tmp_path / "roadmap.yaml"
        md_path = tmp_path / "roadmap.md"
        yaml_path.write_text(
            yaml.dump(roadmap.to_dict(), default_flow_style=False, sort_keys=False)
        )
        md_path.write_text(md)

        drifts = check_roadmap_sync(yaml_path, md_path)
        assert drifts == []

    def test_detects_drift_after_yaml_change(self, tmp_path):
        import yaml

        roadmap = _make_roadmap()
        md = render_roadmap(roadmap)

        # Change the YAML
        roadmap.items[0].status = ItemStatus.COMPLETED

        yaml_path = tmp_path / "roadmap.yaml"
        md_path = tmp_path / "roadmap.md"
        yaml_path.write_text(
            yaml.dump(roadmap.to_dict(), default_flow_style=False, sort_keys=False)
        )
        md_path.write_text(md)

        drifts = check_roadmap_sync(yaml_path, md_path)
        assert len(drifts) > 0
        assert any("phase-table" in d for d in drifts)
