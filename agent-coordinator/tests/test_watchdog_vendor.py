"""Tests for WatchdogService vendor health integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.watchdog import WatchdogService


class FakeTime:
    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def _make_mock_db() -> AsyncMock:
    db = AsyncMock()
    db.query = AsyncMock(return_value=[])
    db.rpc = AsyncMock(return_value={"success": True})
    db.update = AsyncMock(return_value=[])
    db.delete = AsyncMock(return_value=None)
    return db


class TestVendorHealthCheck:
    @pytest.mark.asyncio
    @patch("src.watchdog.get_event_bus")
    async def test_skips_before_interval(self, mock_get_bus):
        mock_bus = MagicMock()
        mock_bus.failed = False
        mock_get_bus.return_value = mock_bus

        db = _make_mock_db()
        fake_time = FakeTime(start=100.0)
        svc = WatchdogService(db=db, check_interval=60, time_fn=fake_time)

        # First call sets baseline
        await svc._check_vendor_health()

        # Second call too soon — should skip
        fake_time.advance(60)  # Only 60s, interval is 300s
        db.rpc.reset_mock()
        await svc._check_vendor_health()

        # No events should have been emitted (skipped + no state change)
        notify_calls = [c for c in db.rpc.call_args_list if c.args[0] == "pg_notify_direct"]
        assert len(notify_calls) == 0

    @pytest.mark.asyncio
    @patch("src.watchdog.get_event_bus")
    async def test_first_run_sets_baseline(self, mock_get_bus):
        mock_bus = MagicMock()
        mock_bus.failed = False
        mock_get_bus.return_value = mock_bus

        db = _make_mock_db()
        fake_time = FakeTime(start=500.0)
        svc = WatchdogService(db=db, check_interval=60, time_fn=fake_time)

        await svc._check_vendor_health()

        # First run should NOT emit any events (no baseline to compare)
        notify_calls = [c for c in db.rpc.call_args_list if c.args[0] == "pg_notify_direct"]
        vendor_events = [
            c for c in notify_calls
            if "vendor." in str(c.args[1].get("p_payload", ""))
        ]
        assert len(vendor_events) == 0

    @pytest.mark.asyncio
    @patch("src.watchdog.get_event_bus")
    async def test_emits_unavailable_on_state_change(self, mock_get_bus):
        mock_bus = MagicMock()
        mock_bus.failed = False
        mock_get_bus.return_value = mock_bus

        db = _make_mock_db()
        fake_time = FakeTime(start=500.0)
        svc = WatchdogService(db=db, check_interval=60, time_fn=fake_time)

        # Set up previous state manually
        svc._previous_vendor_state = {"claude-local": True, "codex-local": True}
        svc._last_vendor_check = 0.0  # Force check to run

        # Mock vendor_health to return codex as unhealthy
        mock_report = MagicMock()
        mock_vendor_claude = MagicMock()
        mock_vendor_claude.agent_id = "claude-local"
        mock_vendor_claude.healthy = True
        mock_vendor_codex = MagicMock()
        mock_vendor_codex.agent_id = "codex-local"
        mock_vendor_codex.healthy = False
        mock_report.vendors = [mock_vendor_claude, mock_vendor_codex]

        with patch("importlib.util.spec_from_file_location") as mock_spec:
            mock_module = MagicMock()
            mock_module.check_all_vendors.return_value = mock_report
            mock_loader = MagicMock()
            mock_loader.exec_module = MagicMock(side_effect=lambda m: None)
            spec_obj = MagicMock()
            spec_obj.loader = mock_loader
            mock_spec.return_value = spec_obj

            with patch("importlib.util.module_from_spec", return_value=mock_module):
                with patch.object(Path, "exists", return_value=True):
                    await svc._check_vendor_health()

        # Should have emitted vendor.unavailable for codex-local
        notify_calls = [c for c in db.rpc.call_args_list if c.args[0] == "pg_notify_direct"]
        unavailable_events = [
            c for c in notify_calls
            if "vendor.unavailable" in str(c.args[1].get("p_payload", ""))
        ]
        assert len(unavailable_events) == 1
        assert "codex-local" in str(unavailable_events[0].args[1]["p_payload"])

    @pytest.mark.asyncio
    @patch("src.watchdog.get_event_bus")
    async def test_emits_recovered_on_state_change(self, mock_get_bus):
        mock_bus = MagicMock()
        mock_bus.failed = False
        mock_get_bus.return_value = mock_bus

        db = _make_mock_db()
        fake_time = FakeTime(start=500.0)
        svc = WatchdogService(db=db, check_interval=60, time_fn=fake_time)

        # Set up previous state: codex was down
        svc._previous_vendor_state = {"codex-local": False}
        svc._last_vendor_check = 0.0

        mock_report = MagicMock()
        mock_vendor = MagicMock()
        mock_vendor.agent_id = "codex-local"
        mock_vendor.healthy = True
        mock_report.vendors = [mock_vendor]

        with patch("importlib.util.spec_from_file_location") as mock_spec:
            mock_module = MagicMock()
            mock_module.check_all_vendors.return_value = mock_report
            mock_loader = MagicMock()
            mock_loader.exec_module = MagicMock(side_effect=lambda m: None)
            spec_obj = MagicMock()
            spec_obj.loader = mock_loader
            mock_spec.return_value = spec_obj

            with patch("importlib.util.module_from_spec", return_value=mock_module):
                with patch.object(Path, "exists", return_value=True):
                    await svc._check_vendor_health()

        notify_calls = [c for c in db.rpc.call_args_list if c.args[0] == "pg_notify_direct"]
        recovered_events = [
            c for c in notify_calls
            if "vendor.recovered" in str(c.args[1].get("p_payload", ""))
        ]
        assert len(recovered_events) == 1
