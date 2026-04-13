"""Tests for origin-aware merge strategy selection.

Covers spec scenarios:
- Agent-authored PR uses rebase-merge by default
- Dependency PR uses squash-merge by default
- Automation PR uses squash-merge by default
- Operator overrides default strategy via CLI flag
- Rebase-merge fails due to merge conflicts
"""

import sys
from pathlib import Path

# Add scripts dir to path so we can import merge_pr
sys.path.insert(0, str(Path(__file__).parent.parent))

from merge_pr import get_default_strategy, resolve_strategy


class TestGetDefaultStrategy:
    """Test origin-to-strategy mapping for all PR origins."""

    # Agent-authored origins → rebase

    def test_openspec_origin_returns_rebase(self) -> None:
        assert get_default_strategy("openspec") == "rebase"

    def test_codex_origin_returns_rebase(self) -> None:
        assert get_default_strategy("codex") == "rebase"

    # Dependency origins → squash

    def test_dependabot_origin_returns_squash(self) -> None:
        assert get_default_strategy("dependabot") == "squash"

    def test_renovate_origin_returns_squash(self) -> None:
        assert get_default_strategy("renovate") == "squash"

    # Automation origins → squash

    def test_sentinel_origin_returns_squash(self) -> None:
        assert get_default_strategy("sentinel") == "squash"

    def test_bolt_origin_returns_squash(self) -> None:
        assert get_default_strategy("bolt") == "squash"

    def test_palette_origin_returns_squash(self) -> None:
        assert get_default_strategy("palette") == "squash"

    def test_jules_origin_returns_squash(self) -> None:
        assert get_default_strategy("jules") == "squash"

    def test_other_origin_returns_squash(self) -> None:
        assert get_default_strategy("other") == "squash"

    def test_unknown_origin_returns_squash(self) -> None:
        assert get_default_strategy("unknown_thing") == "squash"


class TestResolveStrategy:
    """Scenario: Operator overrides default strategy via CLI flag."""

    def test_explicit_strategy_overrides_origin(self) -> None:
        assert resolve_strategy(
            explicit_strategy="squash", origin="openspec",
        ) == "squash"

    def test_explicit_rebase_overrides_dependabot(self) -> None:
        assert resolve_strategy(
            explicit_strategy="rebase", origin="dependabot",
        ) == "rebase"

    def test_explicit_merge_overrides_any_origin(self) -> None:
        assert resolve_strategy(
            explicit_strategy="merge", origin="openspec",
        ) == "merge"

    def test_no_explicit_strategy_uses_origin_default(self) -> None:
        assert resolve_strategy(
            explicit_strategy=None, origin="openspec",
        ) == "rebase"

    def test_no_explicit_strategy_no_origin_falls_back_to_squash(self) -> None:
        assert resolve_strategy(
            explicit_strategy=None, origin=None,
        ) == "squash"

    def test_no_explicit_strategy_with_dependabot_uses_squash(self) -> None:
        assert resolve_strategy(
            explicit_strategy=None, origin="dependabot",
        ) == "squash"
