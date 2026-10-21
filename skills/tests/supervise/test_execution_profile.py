"""Supervisor execution-profile ranking (D8).

openrouter-review-lane, task group 6.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_SUITE = Path(__file__).resolve().parent
if str(_SUITE) not in sys.path:
    sys.path.insert(0, str(_SUITE))

from test_execution import (  # noqa: E402
    FakeClock,
    _adapter,
    _prepare,
    _workspace,
)

import execution  # noqa: E402
from execution import resolve_execution_profile  # noqa: E402

_LADDER = ["vendor-cli", "vendor-sdk", "openrouter"]


def _report(review: dict[str, Any]) -> tuple[int, str]:
    return 0, json.dumps(
        {
            "modes": {"review": review},
            "probe_command": "review_dispatcher.py --check-vendors --json",
        }
    )


@pytest.fixture(autouse=True)
def _fixed_ladder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(execution, "_tier_order", lambda: list(_LADDER))


# --------------------------------------------------------------------------- #
# 6.1 / 6.2 — ranking reads lane_kinds (design D8)
# --------------------------------------------------------------------------- #


def test_a_verified_openrouter_lane_is_ranked_as_metered() -> None:
    _profile, requirements = resolve_execution_profile(
        _report(
            {
                "verified": ["claude_code", "openrouter"],
                "unverified": [],
                "lane_kinds": {"claude_code": "vendor-cli", "openrouter": "openrouter"},
            }
        )
    )
    assert requirements["counting_lanes"] == ["claude_code", "openrouter"]
    assert set(requirements["min_quorum"].values()) == {2}


def test_lane_kinds_rank_openrouter_after_an_unverified_vendor_cli_lane() -> None:
    # The old inference treats every lane without ``probe_unsupported`` as
    # vendor-cli, so a verified openrouter lane would outrank an unverified CLI
    # lane. With lane_kinds the cost ladder decides.
    _profile, requirements = resolve_execution_profile(
        _report(
            {
                "verified": ["openrouter"],
                "unverified": [{"vendor": "codex", "reason": "cli_not_found"}],
                "lane_kinds": {"openrouter": "openrouter", "codex": "vendor-cli"},
            }
        )
    )
    assert requirements["counting_lanes"] == ["codex", "openrouter"]


def test_lane_kinds_order_follows_the_whole_ladder() -> None:
    _profile, requirements = resolve_execution_profile(
        _report(
            {
                "verified": ["openrouter", "local", "gemini", "claude_code"],
                "unverified": [],
                "lane_kinds": {
                    "openrouter": "openrouter",
                    "local": "local",
                    "gemini": "vendor-sdk",
                    "claude_code": "vendor-cli",
                },
            }
        )
    )
    # ``local`` is not on the ladder, so it sorts after every rung.
    assert requirements["counting_lanes"] == ["claude_code", "gemini", "openrouter", "local"]


def test_a_report_without_lane_kinds_still_ranks_by_the_old_inference() -> None:
    _profile, requirements = resolve_execution_profile(
        _report(
            {
                "verified": ["openrouter"],
                "unverified": [
                    {"vendor": "codex", "reason": "cli_not_found"},
                    {"vendor": "gemini", "reason": "probe_unsupported"},
                ],
            }
        )
    )
    # vendor-cli verified, vendor-cli unverified, then the vendor-sdk lane.
    assert requirements["counting_lanes"] == ["openrouter", "codex", "gemini"]


def test_prepare_succeeds_with_a_report_without_lane_kinds(tmp_path: Path) -> None:
    repo, workspace, managed_root = _workspace(tmp_path)
    adapter = _adapter(managed_root, FakeClock())
    adapter.profile_probe = lambda _repo: _report(
        {"verified": ["claude_code", "codex"], "unverified": []}
    )
    request = _prepare(adapter, workspace, repo, managed_root)["requests"][0]
    assert request["review_requirements"]["counting_lanes"] == ["claude_code", "codex"]
