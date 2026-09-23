"""Exact-lane capacity reporting contract."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


def test_capacity_result_reports_exact_lane_and_reset_metadata() -> None:
    from vendor_limit_reporter import report_vendor_limit_result

    bridge = MagicMock(return_value={"status": "ok"})
    result = SimpleNamespace(
        agent_id="codex-local",
        vendor="codex",
        error_class=SimpleNamespace(value="capacity_exhausted"),
        error="429 capacity",
        capacity_scope="model",
        capacity_model="gpt-5.6",
        capacity_reset_at=None,
        capacity_retry_after_seconds=120,
    )

    outcome = report_vendor_limit_result(result, reporter=bridge)

    assert outcome == {"status": "ok"}
    agent_id, payload = bridge.call_args.args
    assert agent_id == "codex-local"
    assert payload["scope"] == "model"
    assert payload["model"] == "gpt-5.6"
    assert payload["retry_after_seconds"] == 120
    assert payload["reason"] == "429 capacity"


def test_provider_only_capacity_is_skipped_without_lane_inference(caplog) -> None:
    from vendor_limit_reporter import report_vendor_limit_result

    bridge = MagicMock()
    result = SimpleNamespace(
        agent_id=None,
        vendor="codex",
        error_class=SimpleNamespace(value="capacity_exhausted"),
        error="429 capacity",
    )

    with caplog.at_level(logging.WARNING):
        outcome = report_vendor_limit_result(result, reporter=bridge)

    assert outcome["status"] == "skipped"
    assert outcome["reason"] == "exact_agent_id_required"
    bridge.assert_not_called()
    assert "ambiguous" in caplog.text
