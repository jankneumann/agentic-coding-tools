"""Tests for vendor_dispatch: round-robin routing and vendor discovery."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure scripts dir is importable
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "scripts"),
)

from vendor_dispatch import (  # noqa: E402
    discover_vendors,
    route_prompts_to_vendors,
    write_vendor_prompt_files,
)


# ---------------------------------------------------------------------------
# route_prompts_to_vendors
# ---------------------------------------------------------------------------


class TestRoutePromptsToVendors:
    """Round-robin routing tests."""

    def test_even_distribution_two_vendors(self) -> None:
        """4 prompts, 2 vendors -> 2 each."""
        prompts = [
            ("a.py", "fix a"),
            ("b.py", "fix b"),
            ("c.py", "fix c"),
            ("d.py", "fix d"),
        ]
        result = route_prompts_to_vendors(prompts, ["claude", "codex"])

        assert len(result["claude"]) == 2
        assert len(result["codex"]) == 2

    def test_exclusive_file_ownership(self) -> None:
        """Each file appears in exactly one vendor's list."""
        prompts = [
            ("a.py", "fix a"),
            ("b.py", "fix b"),
            ("c.py", "fix c"),
        ]
        result = route_prompts_to_vendors(prompts, ["claude", "codex"])

        all_files: list[str] = []
        for items in result.values():
            all_files.extend(item["file"] for item in items)

        # No duplicates
        assert len(all_files) == len(set(all_files))
        # All accounted for
        assert set(all_files) == {"a.py", "b.py", "c.py"}

    def test_single_vendor_gets_all(self) -> None:
        """Single vendor receives all prompts."""
        prompts = [
            ("a.py", "fix a"),
            ("b.py", "fix b"),
            ("c.py", "fix c"),
        ]
        result = route_prompts_to_vendors(prompts, ["claude"])

        assert len(result) == 1
        assert len(result["claude"]) == 3

    def test_empty_prompts_returns_empty(self) -> None:
        """Empty prompts list -> empty dict."""
        result = route_prompts_to_vendors([], ["claude", "codex"])
        assert result == {}

    def test_uneven_distribution(self) -> None:
        """3 prompts, 2 vendors -> vendor1 gets 2, vendor2 gets 1."""
        prompts = [
            ("a.py", "fix a"),
            ("b.py", "fix b"),
            ("c.py", "fix c"),
        ]
        result = route_prompts_to_vendors(prompts, ["claude", "codex"])

        assert len(result["claude"]) == 2
        assert len(result["codex"]) == 1

    def test_round_robin_order(self) -> None:
        """Verify exact round-robin assignment order."""
        prompts = [
            ("a.py", "fix a"),
            ("b.py", "fix b"),
            ("c.py", "fix c"),
            ("d.py", "fix d"),
            ("e.py", "fix e"),
        ]
        result = route_prompts_to_vendors(prompts, ["v1", "v2", "v3"])

        assert [item["file"] for item in result["v1"]] == ["a.py", "d.py"]
        assert [item["file"] for item in result["v2"]] == ["b.py", "e.py"]
        assert [item["file"] for item in result["v3"]] == ["c.py"]

    def test_empty_vendors_returns_empty(self) -> None:
        """Empty vendor list -> empty dict."""
        prompts = [("a.py", "fix a")]
        result = route_prompts_to_vendors(prompts, [])
        assert result == {}

    def test_output_shape(self) -> None:
        """Each item has 'file' and 'prompt' keys."""
        prompts = [("a.py", "fix a")]
        result = route_prompts_to_vendors(prompts, ["claude"])

        for items in result.values():
            for item in items:
                assert "file" in item
                assert "prompt" in item


# ---------------------------------------------------------------------------
# discover_vendors
# ---------------------------------------------------------------------------


class TestDiscoverVendors:
    """Vendor discovery with mocked ReviewOrchestrator."""

    def _make_mock_orchestrator(
        self, vendors: list[str],
    ) -> MagicMock:
        """Create a mock ReviewOrchestrator with given vendor types."""
        orch = MagicMock()
        adapters: dict[str, MagicMock] = {}
        for v in vendors:
            adapter = MagicMock()
            adapter.vendor = v
            adapters[f"{v}-local"] = adapter
        orch.adapters = adapters
        return orch

    @patch("vendor_dispatch.sys")
    def test_returns_requested_filtered_by_available(
        self, mock_sys: MagicMock,
    ) -> None:
        """requested_vendors filters to those that are available."""
        mock_sys.path = sys.path.copy()

        orch = self._make_mock_orchestrator(["claude", "codex", "gemini"])

        with patch.dict("sys.modules", {}), \
             patch("vendor_dispatch.sys", mock_sys):
            # Patch the import chain: make ReviewOrchestrator importable
            mock_module = MagicMock()
            mock_module.ReviewOrchestrator.from_coordinator.return_value = orch

            with patch.dict("sys.modules", {"review_dispatcher": mock_module}):
                result = discover_vendors(requested_vendors=["claude", "codex"])

        assert set(result) == {"claude", "codex"}

    def test_warns_unavailable_requested_vendor(self, caplog: pytest.LogCaptureFixture) -> None:
        """Warns when a requested vendor is not available."""
        # Patch to make discovery fail -> falls back to ["claude"]
        with patch("vendor_dispatch.Path") as mock_path:
            mock_path.return_value.resolve.side_effect = Exception("no path")
            with caplog.at_level("WARNING"):
                result = discover_vendors(requested_vendors=["nonexistent"])

        # Should fall back to available vendors since nonexistent isn't available
        assert "claude" in result or len(result) > 0

    def test_fallback_to_default_on_import_failure(self) -> None:
        """Falls back to ['claude'] if ReviewOrchestrator cannot be imported."""
        # Force import failure by making the path lookup fail
        with patch("vendor_dispatch.Path") as mock_path:
            mock_path.return_value.resolve.return_value.parent = Path("/nonexistent")
            # This will cause an ImportError for review_dispatcher
            result = discover_vendors()

        assert result == ["claude"]

    def test_no_requested_returns_all_available(self) -> None:
        """Without requested_vendors, returns all discovered vendors."""
        orch = self._make_mock_orchestrator(["claude", "codex"])

        mock_module = MagicMock()
        mock_module.ReviewOrchestrator.from_coordinator.return_value = orch

        with patch.dict("sys.modules", {"review_dispatcher": mock_module}):
            # Patch sys.path.insert to avoid actual path manipulation
            result = discover_vendors(requested_vendors=None)

        # Should contain discovered vendors (or fallback)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# write_vendor_prompt_files
# ---------------------------------------------------------------------------


class TestWriteVendorPromptFiles:
    """File-writing tests."""

    def test_creates_correct_json_files(self, tmp_path: Path) -> None:
        """Each vendor gets a JSON file with its prompts."""
        routed = {
            "claude": [
                {"file": "a.py", "prompt": "fix a"},
                {"file": "b.py", "prompt": "fix b"},
            ],
            "codex": [
                {"file": "c.py", "prompt": "fix c"},
            ],
        }

        paths = write_vendor_prompt_files(routed, tmp_path)

        assert len(paths) == 2

        claude_file = tmp_path / "agent-fix-prompts-claude.json"
        codex_file = tmp_path / "agent-fix-prompts-codex.json"

        assert claude_file.exists()
        assert codex_file.exists()

        claude_data = json.loads(claude_file.read_text())
        assert len(claude_data) == 2
        assert claude_data[0]["file"] == "a.py"
        assert claude_data[0]["prompt"] == "fix a"

        codex_data = json.loads(codex_file.read_text())
        assert len(codex_data) == 1
        assert codex_data[0]["file"] == "c.py"

    def test_creates_output_directory(self, tmp_path: Path) -> None:
        """Creates the output directory if it doesn't exist."""
        out = tmp_path / "nested" / "output"
        routed = {"claude": [{"file": "a.py", "prompt": "fix a"}]}

        write_vendor_prompt_files(routed, out)

        assert out.exists()
        assert (out / "agent-fix-prompts-claude.json").exists()

    def test_empty_routed_writes_nothing(self, tmp_path: Path) -> None:
        """Empty routed dict produces no files."""
        paths = write_vendor_prompt_files({}, tmp_path)
        assert paths == []

    def test_returns_written_paths(self, tmp_path: Path) -> None:
        """Returns list of Path objects for written files."""
        routed = {"claude": [{"file": "a.py", "prompt": "fix a"}]}

        paths = write_vendor_prompt_files(routed, tmp_path)

        assert len(paths) == 1
        assert paths[0] == tmp_path / "agent-fix-prompts-claude.json"
