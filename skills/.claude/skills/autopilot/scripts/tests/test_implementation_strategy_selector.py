"""Tests for implementation_strategy_selector."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

# Add scripts/ to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from implementation_strategy_selector import (
    select_lead_vendor,
    select_strategies,
)


def _write_packages(tmp_path: Path, packages: list[dict]) -> Path:
    """Helper to write a work-packages.yaml file."""
    wp_path = tmp_path / "work-packages.yaml"
    wp_path.write_text(yaml.dump({"packages": packages}))
    return wp_path


class TestSelectStrategies:
    """Tests for select_strategies()."""

    def test_small_ambiguous_package_selects_alternatives(self, tmp_path: Path) -> None:
        """loc=100, alternatives=3, kind=algorithm, 3 vendors -> alternatives."""
        wp = _write_packages(tmp_path, [
            {
                "package_id": "wp-algo",
                "metadata": {
                    "loc_estimate": 100,
                    "alternatives_count": 3,
                    "package_kind": "algorithm",
                },
            },
        ])
        result = select_strategies(
            wp,
            available_vendors=["claude", "gpt4", "gemini"],
        )
        assert result["wp-algo"] == "alternatives"

    def test_large_straightforward_selects_lead_review(self, tmp_path: Path) -> None:
        """loc=400, alternatives=0, kind=crud -> lead_review."""
        wp = _write_packages(tmp_path, [
            {
                "package_id": "wp-crud",
                "metadata": {
                    "loc_estimate": 400,
                    "alternatives_count": 0,
                    "package_kind": "crud",
                },
            },
        ])
        result = select_strategies(
            wp,
            available_vendors=["claude", "gpt4"],
        )
        assert result["wp-crud"] == "lead_review"

    def test_no_metadata_defaults_to_lead_review(self, tmp_path: Path) -> None:
        """Package without metadata -> lead_review."""
        wp = _write_packages(tmp_path, [
            {"package_id": "wp-bare"},
        ])
        result = select_strategies(
            wp,
            available_vendors=["claude", "gpt4", "gemini"],
        )
        assert result["wp-bare"] == "lead_review"

    def test_boundary_score_2_selects_alternatives(self, tmp_path: Path) -> None:
        """Exactly 2.0 score -> alternatives.

        loc < 200 (1.0) + alternatives >= 2 (1.0) = 2.0, with
        kind=crud (0.0) and 2 vendors (0.0).
        """
        wp = _write_packages(tmp_path, [
            {
                "package_id": "wp-boundary",
                "metadata": {
                    "loc_estimate": 150,
                    "alternatives_count": 2,
                    "package_kind": "crud",
                },
            },
        ])
        result = select_strategies(
            wp,
            available_vendors=["claude", "gpt4"],
        )
        assert result["wp-boundary"] == "alternatives"

    def test_boundary_score_below_2_selects_lead_review(self, tmp_path: Path) -> None:
        """Score of 1.0 -> lead_review.

        loc < 200 (1.0) only, all other criteria 0.
        """
        wp = _write_packages(tmp_path, [
            {
                "package_id": "wp-low",
                "metadata": {
                    "loc_estimate": 50,
                    "alternatives_count": 1,
                    "package_kind": "crud",
                },
            },
        ])
        result = select_strategies(
            wp,
            available_vendors=["claude", "gpt4"],
        )
        assert result["wp-low"] == "lead_review"

    def test_fewer_than_3_vendors_reduces_score(self, tmp_path: Path) -> None:
        """2 vendors -> vendor criterion = 0.0.

        Without vendor score, need 2.0 from other criteria. Here only
        loc (1.0) + kind=algorithm (1.0) = 2.0 still alternatives.
        But with alternatives_count=1 -> loc(1.0) + kind(1.0) = 2.0.
        """
        wp = _write_packages(tmp_path, [
            {
                "package_id": "wp-few-vendors",
                "metadata": {
                    "loc_estimate": 100,
                    "alternatives_count": 1,
                    "package_kind": "algorithm",
                },
            },
        ])
        # With 3 vendors: loc(1) + alt(0) + kind(1) + vendors(1) = 3 -> alternatives
        result_3v = select_strategies(
            wp,
            available_vendors=["claude", "gpt4", "gemini"],
        )
        assert result_3v["wp-few-vendors"] == "alternatives"

        # With 2 vendors: loc(1) + alt(0) + kind(1) + vendors(0) = 2 -> alternatives
        result_2v = select_strategies(
            wp,
            available_vendors=["claude", "gpt4"],
        )
        assert result_2v["wp-few-vendors"] == "alternatives"

        # With 2 vendors and kind=crud: loc(1) + alt(0) + kind(0) + vendors(0) = 1 -> lead_review
        (tmp_path / "sub").mkdir(exist_ok=True)
        wp2 = _write_packages(tmp_path / "sub", [
            {
                "package_id": "wp-few-vendors",
                "metadata": {
                    "loc_estimate": 100,
                    "alternatives_count": 1,
                    "package_kind": "crud",
                },
            },
        ])
        result_2v_crud = select_strategies(
            wp2,
            available_vendors=["claude", "gpt4"],
        )
        assert result_2v_crud["wp-few-vendors"] == "lead_review"

    def test_mixed_packages(self, tmp_path: Path) -> None:
        """Multiple packages with different metadata -> correct per-package strategy."""
        wp = _write_packages(tmp_path, [
            {
                "package_id": "wp-algo",
                "metadata": {
                    "loc_estimate": 80,
                    "alternatives_count": 3,
                    "package_kind": "algorithm",
                },
            },
            {
                "package_id": "wp-crud",
                "metadata": {
                    "loc_estimate": 500,
                    "alternatives_count": 0,
                    "package_kind": "crud",
                },
            },
            {
                "package_id": "wp-model",
                "metadata": {
                    "loc_estimate": 120,
                    "alternatives_count": 2,
                    "package_kind": "data_model",
                },
            },
        ])
        result = select_strategies(
            wp,
            available_vendors=["claude", "gpt4", "gemini"],
        )
        assert result["wp-algo"] == "alternatives"
        assert result["wp-crud"] == "lead_review"
        assert result["wp-model"] == "alternatives"

    def test_skip_integration_packages(self, tmp_path: Path) -> None:
        """Integration-type packages always get lead_review."""
        wp = _write_packages(tmp_path, [
            {
                "package_id": "wp-integration-final",
                "task_type": "integrate",
                "metadata": {
                    "loc_estimate": 50,
                    "alternatives_count": 5,
                    "package_kind": "algorithm",
                },
            },
            {
                "package_id": "wp-integration-glue",
                "metadata": {
                    "loc_estimate": 50,
                    "alternatives_count": 5,
                    "package_kind": "algorithm",
                },
            },
        ])
        result = select_strategies(
            wp,
            available_vendors=["claude", "gpt4", "gemini"],
        )
        # Explicit integration type
        assert result["wp-integration-final"] == "lead_review"
        # id starts with wp-integration
        assert result["wp-integration-glue"] == "lead_review"


class TestSelectLeadVendor:
    """Tests for select_lead_vendor()."""

    def test_recall_fn_selects_best_vendor(self) -> None:
        """Mock recall returns vendor stats -> best vendor selected as lead."""
        def mock_recall(topic: str) -> list[dict]:
            return [
                {"vendor": "claude", "fix_success_rate": 0.85},
                {"vendor": "gpt4", "fix_success_rate": 0.92},
                {"vendor": "gemini", "fix_success_rate": 0.78},
            ]

        result = select_lead_vendor(
            ["claude", "gpt4", "gemini"],
            recall_fn=mock_recall,
        )
        assert result == "gpt4"

    def test_recall_fn_unavailable_uses_first_vendor(self) -> None:
        """recall_fn=None -> first available vendor."""
        result = select_lead_vendor(["claude", "gpt4", "gemini"])
        assert result == "claude"

    def test_recall_fn_returns_empty(self) -> None:
        """recall_fn returns empty list -> first available vendor."""
        result = select_lead_vendor(
            ["gemini", "claude"],
            recall_fn=lambda topic: [],
        )
        assert result == "gemini"

    def test_recall_fn_raises_exception(self) -> None:
        """recall_fn raises -> graceful fallback to first vendor."""
        def broken_recall(topic: str) -> list[dict]:
            raise RuntimeError("connection failed")

        result = select_lead_vendor(
            ["claude", "gpt4"],
            recall_fn=broken_recall,
        )
        assert result == "claude"

    def test_empty_vendors(self) -> None:
        """No vendors -> empty string."""
        result = select_lead_vendor([])
        assert result == ""
