"""Tests for the semantic decomposer and Pass 1 structural extensions.

Three tiers:
  1. Structural tests — always run, no LLM, no oracle
  2. Semantic decomposer with mocked LLM — always run
  3. Oracle-based regression — skips when files missing
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from decomposer import (
    _classify_sections,
    _extract_table_items,
    _generate_clean_id,
    _parse_sections,
    make_repo_relative,
    scan_archive_state,
)
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
from semantic_decomposer import (
    _apply_verdict,
    _CandidateBlock,
    _tier_b0_can_prune,
    semantic_decompose,
)

# ---------------------------------------------------------------------------
# Tier 1: Structural tests (always run, no LLM, no oracle)
# ---------------------------------------------------------------------------


class TestCodeBlockStripping:
    """Headings inside fenced code blocks should NOT be extracted as sections."""

    def test_heading_inside_backtick_fence_ignored(self):
        md = """\
# Real Title

Some intro text.

```yaml
### This Is Not A Real Heading
key: value
```

## Real Section

Content here.
"""
        sections = _parse_sections(md)
        titles = [s.title for s in sections]
        assert "Real Title" in titles
        assert "Real Section" in titles
        assert "This Is Not A Real Heading" not in titles

    def test_heading_inside_tilde_fence_ignored(self):
        md = """\
# Title

~~~python
## Fake Section
def foo():
    pass
~~~

## Actual Section
"""
        sections = _parse_sections(md)
        titles = [s.title for s in sections]
        assert "Title" in titles
        assert "Actual Section" in titles
        assert "Fake Section" not in titles

    def test_heading_outside_fence_still_works(self):
        md = """\
# Title

```
code block
```

## After Code Block

Content.
"""
        sections = _parse_sections(md)
        assert len(sections) == 2
        assert sections[0].title == "Title"
        assert sections[1].title == "After Code Block"

    def test_nested_fences_handled(self):
        """Fence with language identifier (```yaml) should be tracked."""
        md = """\
# Title

```yaml
schedules:
  morning_briefing:
    cron: "0 7 * * 1-5"
    role: chief_of_staff
### Not a heading
```

## Real Section
"""
        sections = _parse_sections(md)
        titles = [s.title for s in sections]
        assert "Not a heading" not in titles
        assert "Real Section" in titles


class TestTableRowExtraction:
    """Priority tables should have each row extracted as a section."""

    def test_basic_priority_table(self):
        body = """\
| Module | Status | Priority | Notes |
|--------|--------|----------|-------|
| `core/memory.py` | Referenced | P0 | Central to cross-session |
| `http_tools/_build_tool()` | Placeholder | P0 | HTTP tool layer |
| `delegation/router.py` | Missing | P1 | Intent classification |
"""
        items = _extract_table_items(body)
        assert len(items) == 3
        assert items[0].title == "core/memory.py"
        assert items[1].title == "http_tools/_build_tool()"
        assert items[2].title == "delegation/router.py"
        assert all(item.is_capability for item in items)

    def test_no_priority_table_returns_empty(self):
        body = """\
| Name | Age |
|------|-----|
| Alice | 30 |
"""
        items = _extract_table_items(body)
        assert items == []

    def test_table_with_p0_p1_values(self):
        body = """\
| Priority | Module | Notes |
|----------|--------|-------|
| P0 | Memory | Core memory |
| P1 | Router | Delegation |
"""
        items = _extract_table_items(body)
        assert len(items) == 2


class TestSubsectionPropagation:
    """H4/H5 children of capability H3 should inherit the classification."""

    def test_h4_inherits_from_capability_h3(self):
        md = """\
# Proposal

## Phase 1

### Authentication Service

Main auth system.

#### OAuth2 Provider

OAuth2 implementation details.

#### JWT Management

Token handling.
"""
        sections = _parse_sections(md)
        sections = _classify_sections(sections)

        # "Authentication Service" is a capability (matches "service")
        auth = next(s for s in sections if s.title == "Authentication Service")
        assert auth.is_capability

        # "OAuth2 Provider" and "JWT Management" should inherit
        oauth = next(s for s in sections if s.title == "OAuth2 Provider")
        jwt = next(s for s in sections if s.title == "JWT Management")
        assert oauth.is_capability
        assert jwt.is_capability

    def test_h4_under_constraint_not_propagated(self):
        md = """\
# Proposal

## Constraints

### Security Requirements

Must pass review.

#### Specific Constraint

Details.
"""
        sections = _parse_sections(md)
        sections = _classify_sections(sections)

        # "Specific Constraint" should not be classified as capability
        specific = next(s for s in sections if s.title == "Specific Constraint")
        assert not specific.is_capability


class TestArchiveStateScan:
    """scan_archive_state should map change_ids to status from directory structure."""

    def test_scans_archived_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = root / "openspec" / "changes" / "archive"
            (archive / "2026-04-01-add-feature").mkdir(parents=True)
            (archive / "2026-03-15-fix-bug").mkdir(parents=True)

            state = scan_archive_state(root)
            assert state["add-feature"] == "completed"
            assert state["fix-bug"] == "completed"

    def test_scans_active_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            changes = root / "openspec" / "changes"
            (changes / "my-feature").mkdir(parents=True)
            (changes / "archive").mkdir(parents=True)

            state = scan_archive_state(root)
            assert state["my-feature"] == "in_progress"
            assert "archive" not in state

    def test_archived_takes_precedence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = root / "openspec" / "changes" / "archive"
            (archive / "2026-01-01-my-change").mkdir(parents=True)
            (root / "openspec" / "changes" / "my-change").mkdir(parents=True)

            state = scan_archive_state(root)
            assert state["my-change"] == "completed"


class TestRepoRelativePath:
    """make_repo_relative should normalize absolute paths."""

    def test_absolute_to_relative(self, tmp_path):
        result = make_repo_relative(
            str(tmp_path / "docs" / "proposal.md"),
            tmp_path,
        )
        assert result == "docs/proposal.md"

    def test_already_relative_unchanged(self, tmp_path):
        result = make_repo_relative(
            "docs/proposal.md",
            tmp_path,
        )
        assert result == "docs/proposal.md"

    def test_unrelated_absolute_unchanged(self, tmp_path):
        other = tmp_path / "other"
        result = make_repo_relative(
            str(other / "file.md"),
            tmp_path / "project",
        )
        # Not under repo_root, so stays absolute
        assert "file.md" in result


class TestCleanIdGeneration:
    """_generate_clean_id should produce kebab-case without ri- prefix."""

    def test_simple_title(self):
        assert _generate_clean_id("Memory Architecture") == "memory-architecture"

    def test_strips_numeric_prefix(self):
        assert _generate_clean_id("1.1 No Observability Layer") == "no-observability-layer"

    def test_strips_section_numbers(self):
        assert _generate_clean_id("7.4 No pyproject.toml Entry Point") == "no-pyproject-toml-entry-point"

    def test_truncates_long_title(self):
        title = "A Very Long Title That Goes On And On And Really Should Be Truncated At Sixty Characters For Readability"
        result = _generate_clean_id(title)
        assert len(result) <= 60

    def test_special_characters_removed(self):
        assert _generate_clean_id("HTTP Tools (discover + build)") == "http-tools-discover-build"


# ---------------------------------------------------------------------------
# Tier 2: Semantic decomposer with mocked LLM (always run)
# ---------------------------------------------------------------------------

SIMPLE_PROPOSAL = """\
# Test Proposal

## Phase 1: Foundation

### Database Service

Implement the database layer.

- Must support PostgreSQL
- Should handle migrations

### Auth Component

Authentication system.

- OAuth2 support
- JWT token management
"""

MOCK_LLM_RESPONSE = json.dumps({
    "items": [
        {
            "decision": "yes",
            "item_id": "database-service",
            "title": "Database Service",
            "description": "Implement the database layer with PostgreSQL support.",
            "acceptance_outcomes": [
                "PostgreSQL 15+ supported",
                "Automated migrations work",
            ],
            "effort": "M",
            "kind": "phase",
        },
        {
            "decision": "yes",
            "item_id": "auth-component",
            "title": "Auth Component",
            "description": "Authentication system with OAuth2 and JWT.",
            "acceptance_outcomes": [
                "OAuth2 provider integration works",
                "JWT tokens issued and validated",
            ],
            "effort": "M",
            "kind": "phase",
        },
        {
            "decision": "no",
        },
    ]
})

MOCK_TIER_B_RESPONSE = json.dumps({
    "verdicts": [
        {
            "item_a": "database-service",
            "item_b": "auth-component",
            "depends_on": "yes",
            "rationale": "Auth needs database for user storage",
            "confidence": "high",
        }
    ]
})


class TestFallbackToStructural:
    """When llm_client=None, should fall back to structural decomposition."""

    def test_produces_valid_roadmap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "openspec" / "changes" / "archive").mkdir(parents=True)

            roadmap = semantic_decompose(
                SIMPLE_PROPOSAL,
                "proposals/test.md",
                repo_root=root,
                llm_client=None,
            )
            assert isinstance(roadmap, Roadmap)
            assert len(roadmap.items) >= 2
            assert roadmap.source_proposal == "proposals/test.md"

    def test_uses_clean_ids(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "openspec" / "changes" / "archive").mkdir(parents=True)

            roadmap = semantic_decompose(
                SIMPLE_PROPOSAL,
                "proposals/test.md",
                repo_root=root,
                llm_client=None,
            )
            for item in roadmap.items:
                assert not item.item_id.startswith("ri-"), (
                    f"Expected clean ID, got: {item.item_id}"
                )


class TestSemanticWithMockLlm:
    """Semantic decomposer with mocked LLM responses."""

    def _make_mock_client(self):
        """Create a mock LLM client returning canned responses."""
        mock = MagicMock()
        mock.structured_call = MagicMock()

        # First call = Pass 2 (item classification)
        # Second call = Pass 3 Tier B (dependency inference)
        from llm_client import LlmResult

        mock.structured_call.side_effect = [
            LlmResult(content=MOCK_LLM_RESPONSE, model_used="test", vendor="test"),
            LlmResult(content=MOCK_TIER_B_RESPONSE, model_used="test", vendor="test"),
        ]
        return mock

    def test_produces_items_from_llm(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "openspec" / "changes" / "archive").mkdir(parents=True)

            roadmap = semantic_decompose(
                SIMPLE_PROPOSAL,
                "proposals/test.md",
                repo_root=root,
                llm_client=self._make_mock_client(),
            )
            assert len(roadmap.items) == 2
            ids = {item.item_id for item in roadmap.items}
            assert "database-service" in ids
            assert "auth-component" in ids

    def test_items_have_clean_ids(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "openspec" / "changes" / "archive").mkdir(parents=True)

            roadmap = semantic_decompose(
                SIMPLE_PROPOSAL,
                "proposals/test.md",
                repo_root=root,
                llm_client=self._make_mock_client(),
            )
            for item in roadmap.items:
                assert not item.item_id.startswith("ri-")
                assert item.change_id == item.item_id

    def test_source_proposal_relative(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "openspec" / "changes" / "archive").mkdir(parents=True)

            roadmap = semantic_decompose(
                SIMPLE_PROPOSAL,
                str(root / "proposals" / "test.md"),
                repo_root=root,
                llm_client=self._make_mock_client(),
            )
            assert not roadmap.source_proposal.startswith("/")

    def test_dag_is_acyclic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "openspec" / "changes" / "archive").mkdir(parents=True)

            roadmap = semantic_decompose(
                SIMPLE_PROPOSAL,
                "proposals/test.md",
                repo_root=root,
                llm_client=self._make_mock_client(),
            )
            assert not roadmap.has_cycle()


class TestArchiveCrosscheck:
    """Items matching archived change IDs should get status=completed."""

    def test_archived_item_marked_completed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = root / "openspec" / "changes" / "archive"
            (archive / "2026-01-01-database-service").mkdir(parents=True)

            mock = MagicMock()
            from llm_client import LlmResult

            mock.structured_call.side_effect = [
                LlmResult(content=MOCK_LLM_RESPONSE, model_used="test", vendor="test"),
                LlmResult(content=MOCK_TIER_B_RESPONSE, model_used="test", vendor="test"),
            ]

            roadmap = semantic_decompose(
                SIMPLE_PROPOSAL,
                "proposals/test.md",
                repo_root=root,
                llm_client=mock,
            )

            db_item = roadmap.get_item("database-service")
            assert db_item is not None
            assert db_item.status == ItemStatus.COMPLETED


class TestNoNoiseItems:
    """Known-bad tokens should be absent from decomposer output."""

    NOISE_TOKENS = [
        "or-as-an-extension",
        "personas-work-extensions-manif",
        "recommended-implementation-o",
        "implementation-completeness",
        "5-implementation",
        "8-recommended",
    ]

    def test_no_noise_in_fallback_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "openspec" / "changes" / "archive").mkdir(parents=True)

            roadmap = semantic_decompose(
                SIMPLE_PROPOSAL,
                "proposals/test.md",
                repo_root=root,
                llm_client=None,
            )
            for item in roadmap.items:
                for noise in self.NOISE_TOKENS:
                    assert noise not in item.item_id, (
                        f"Noise token '{noise}' found in item_id: {item.item_id}"
                    )


class TestMalformedLlmFallback:
    """When LLM returns invalid JSON, should fall back to structural."""

    def test_invalid_json_falls_back(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "openspec" / "changes" / "archive").mkdir(parents=True)

            mock = MagicMock()
            from llm_client import LlmResult

            mock.structured_call.return_value = LlmResult(
                content="This is not JSON at all!",
                model_used="test",
                vendor="test",
            )

            roadmap = semantic_decompose(
                SIMPLE_PROPOSAL,
                "proposals/test.md",
                repo_root=root,
                llm_client=mock,
            )
            # Should fall back to structural and still produce items
            assert isinstance(roadmap, Roadmap)
            assert len(roadmap.items) >= 1


# ---------------------------------------------------------------------------
# Tier 2b: Dependency inference unit tests
# ---------------------------------------------------------------------------


class TestTierB0Pruning:
    """Tier B-0 cheap pruning should skip obviously independent pairs."""

    def _make_item(self, item_id: str, title: str, priority: int,
                   description: str = "") -> RoadmapItem:
        return RoadmapItem(
            item_id=item_id,
            title=title,
            status=ItemStatus.CANDIDATE,
            priority=priority,
            effort=Effort.M,
            description=description,
        )

    def test_prune_unrelated_items(self):
        a = self._make_item("auth-service", "Authentication Service", 1)
        b = self._make_item("email-notifier", "Email Notification System", 2)
        assert _tier_b0_can_prune(a, b, [a, b])

    def test_keep_related_items(self):
        a = self._make_item(
            "database-setup", "Database Infrastructure Setup", 1,
            "PostgreSQL database schema, migrations, connection pooling",
        )
        b = self._make_item(
            "auth-database", "Authentication Database Layer", 2,
            "User database schema with PostgreSQL, authentication storage",
        )
        assert not _tier_b0_can_prune(a, b, [a, b])


class TestApplyVerdict:
    """Verdict application should follow conservative policy."""

    def _make_item(self, item_id: str, priority: int) -> RoadmapItem:
        return RoadmapItem(
            item_id=item_id,
            title=f"Item {item_id}",
            status=ItemStatus.CANDIDATE,
            priority=priority,
            effort=Effort.M,
        )

    def test_yes_adds_edge(self):
        a = self._make_item("a", 1)
        b = self._make_item("b", 2)
        _apply_verdict(a, b, {
            "depends_on": "yes",
            "rationale": "B needs A",
            "confidence": "high",
        })
        assert "a" in b.depends_on

    def test_no_high_confidence_skips(self):
        a = self._make_item("a", 1)
        b = self._make_item("b", 2)
        _apply_verdict(a, b, {
            "depends_on": "no",
            "rationale": "Independent",
            "confidence": "high",
        })
        assert "a" not in b.depends_on

    def test_no_low_confidence_adds_edge(self):
        """Conservative policy: low-confidence 'no' keeps the edge."""
        a = self._make_item("a", 1)
        b = self._make_item("b", 2)
        _apply_verdict(a, b, {
            "depends_on": "no",
            "rationale": "Maybe independent",
            "confidence": "low",
        })
        assert "a" in b.depends_on

    def test_unclear_adds_edge(self):
        """Conservative policy: unclear → keep edge."""
        a = self._make_item("a", 1)
        b = self._make_item("b", 2)
        _apply_verdict(a, b, {
            "depends_on": "unclear",
            "rationale": "Cannot determine",
            "confidence": "low",
        })
        assert "a" in b.depends_on


# ---------------------------------------------------------------------------
# Tier 2c: DepEdge model tests
# ---------------------------------------------------------------------------


class TestDepEdge:
    """DepEdge dataclass and legacy-shape loader."""

    def test_round_trip(self):
        edge = DepEdge(
            id="auth-service",
            source=DepEdgeSource.DETERMINISTIC,
            rationale="write_allow overlap on src/auth/**",
        )
        d = edge.to_dict()
        restored = DepEdge.from_dict(d)
        assert restored.id == "auth-service"
        assert restored.source == DepEdgeSource.DETERMINISTIC
        assert restored.rationale == "write_allow overlap on src/auth/**"
        assert restored.confidence is None

    def test_llm_edge_with_confidence(self):
        edge = DepEdge(
            id="db-setup",
            source=DepEdgeSource.LLM,
            rationale="Auth needs DB for user storage",
            confidence="high",
        )
        d = edge.to_dict()
        assert d["confidence"] == "high"
        restored = DepEdge.from_dict(d)
        assert restored.confidence == "high"

    def test_roadmap_item_legacy_depends_on(self):
        """Legacy string list should be normalized."""
        data = {
            "item_id": "my-item",
            "title": "My Item",
            "status": "candidate",
            "priority": 1,
            "effort": "M",
            "depends_on": ["dep-a", "dep-b"],
        }
        item = RoadmapItem.from_dict(data)
        assert item.depends_on == ["dep-a", "dep-b"]
        assert item.dep_edges == []  # no rich edges from legacy format

    def test_roadmap_item_rich_depends_on(self):
        """Rich DepEdge format should populate both depends_on and dep_edges."""
        data = {
            "item_id": "my-item",
            "title": "My Item",
            "status": "candidate",
            "priority": 1,
            "effort": "M",
            "depends_on": [
                {
                    "id": "dep-a",
                    "source": "deterministic",
                    "rationale": "scope overlap",
                },
                {
                    "id": "dep-b",
                    "source": "llm",
                    "rationale": "inferred",
                    "confidence": "medium",
                },
            ],
        }
        item = RoadmapItem.from_dict(data)
        assert item.depends_on == ["dep-a", "dep-b"]
        assert len(item.dep_edges) == 2
        assert item.dep_edges[0].source == DepEdgeSource.DETERMINISTIC
        assert item.dep_edges[1].confidence == "medium"

    def test_scope_round_trip(self):
        data = {
            "item_id": "scoped",
            "title": "Scoped Item",
            "status": "candidate",
            "priority": 1,
            "effort": "M",
            "scope": {
                "write_allow": ["src/db/**"],
                "read_allow": ["src/config/**"],
                "lock_keys": ["db:schema:users"],
            },
        }
        item = RoadmapItem.from_dict(data)
        assert item.scope is not None
        assert item.scope.write_allow == ["src/db/**"]
        assert item.scope.lock_keys == ["db:schema:users"]

        d = item.to_dict()
        assert "scope" in d
        assert d["scope"]["write_allow"] == ["src/db/**"]


# ---------------------------------------------------------------------------
# Tier 3: Oracle-based regression (skips when files missing)
# ---------------------------------------------------------------------------

_ORACLE_DIR = Path(__file__).resolve().parent.parent.parent.parent
# Oracle files are in the sibling agentic-assistant repo — resolve via
# environment variable or default relative path from repo root's parent.
_SIBLING_REPO = Path(
    os.environ.get("AGENTIC_ASSISTANT_DIR", _ORACLE_DIR.parent / "agentic-assistant")
)
_PERPLEXITY_PATH = _SIBLING_REPO / "docs" / "perplexity-feedback.md"
_ROADMAP_ORACLE = _SIBLING_REPO / "openspec" / "roadmap.yaml"


@pytest.mark.skipif(
    not _PERPLEXITY_PATH.exists() or not _ROADMAP_ORACLE.exists(),
    reason="Oracle files not available",
)
class TestOracleRegression:
    """Regression tests against hand-authored roadmap.yaml oracle."""

    @pytest.fixture
    def oracle_items(self):
        import yaml

        data = yaml.safe_load(_ROADMAP_ORACLE.read_text())
        return {item["item_id"] for item in data["items"]}

    @pytest.fixture
    def oracle_completed(self):
        import yaml

        data = yaml.safe_load(_ROADMAP_ORACLE.read_text())
        return {
            item["item_id"]
            for item in data["items"]
            if item["status"] == "completed"
        }

    def test_structural_fallback_coverage(self, oracle_items):
        """Structural fallback should find a reasonable number of items."""
        text = _PERPLEXITY_PATH.read_text()
        roadmap = semantic_decompose(
            text,
            "docs/perplexity-feedback.md",
            repo_root=Path.cwd(),
            llm_client=None,
        )
        found_ids = {item.item_id for item in roadmap.items}
        assert len(roadmap.items) >= 8, (
            f"Expected >=8 items from structural fallback, got {len(roadmap.items)}"
        )

    def test_source_proposal_is_relative(self):
        text = _PERPLEXITY_PATH.read_text()
        roadmap = semantic_decompose(
            text,
            "docs/perplexity-feedback.md",
            repo_root=Path.cwd(),
            llm_client=None,
        )
        assert not roadmap.source_proposal.startswith("/")

    def test_no_noise_tokens_in_ids(self):
        """Known-bad noise tokens should not appear in item IDs."""
        noise_tokens = [
            "or-as-an-extension",
            "personas-work-extensions-manif",
            "recommended-implementation-o",
            "implementation-completeness",
            "5-implementation",
            "8-recommended",
        ]
        text = _PERPLEXITY_PATH.read_text()
        roadmap = semantic_decompose(
            text,
            "docs/perplexity-feedback.md",
            repo_root=Path.cwd(),
            llm_client=None,
        )
        for item in roadmap.items:
            for noise in noise_tokens:
                assert noise not in item.item_id, (
                    f"Noise '{noise}' in item_id '{item.item_id}'"
                )
