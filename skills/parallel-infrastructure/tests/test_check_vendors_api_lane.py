"""Integration test: ``--check-vendors --json`` over the repo's real roster.

openrouter-review-lane task 3.9. Loads ``agent-coordinator/agents.yaml`` as
shipped, with no host CLI on PATH, and checks that the endpoint-only
``openrouter-review`` lane is probed (``GET /key`` through an injected
transport), passes the budget rule, and is reported as a verified review lane
of kind ``openrouter``. No real HTTP request is made and no key is real.

Note: this directory is not in ``skills/pyproject.toml`` testpaths; run it
explicitly (``pytest parallel-infrastructure/tests/test_check_vendors_api_lane.py``).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import openai_compat_adapter  # noqa: E402
import review_dispatcher  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENTS_YAML = REPO_ROOT / "agent-coordinator" / "agents.yaml"
FAKE_KEY = "sk-or-test-integration-not-real"


class _KeyProbeTransport:
    """GET stand-in for OpenRouter ``/key``: a key with budget headroom."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def __call__(self, url: str, headers: dict[str, str], timeout: float):
        self.urls.append(url)
        if url.endswith("/key"):
            return 200, {"data": {"limit": 20.0, "limit_remaining": 15.0, "usage": 5.0}}
        return 200, {"data": []}


@pytest.fixture
def offline_host(monkeypatch: pytest.MonkeyPatch):
    """A host with no vendor CLI on PATH, no OpenBao, and no network."""

    def _boom(*_a, **_k):
        raise AssertionError("no real HTTP request may be sent")

    monkeypatch.setattr(openai_compat_adapter, "_default_transport", _boom)
    monkeypatch.setattr(openai_compat_adapter, "_default_get_transport", _boom)
    monkeypatch.setattr(review_dispatcher.shutil, "which", lambda *_a, **_k: None)
    monkeypatch.delenv("BAO_ADDR", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)


def test_repo_roster_declares_the_openrouter_review_lane() -> None:
    text = AGENTS_YAML.read_text(encoding="utf-8")
    assert "openrouter-review:" in text


def test_check_vendors_reports_openrouter_as_verified_api_lane(offline_host) -> None:
    transport = _KeyProbeTransport()
    report = review_dispatcher.check_vendors_report(
        agents_yaml=str(AGENTS_YAML),
        cwd=REPO_ROOT,
        dry_invoke=lambda _argv: None,
        environment="cloud",
        probe_transport=transport,
        usage_fetcher=lambda: {"metered_ceiling_usd": 50.0, "metered_usd_used": 0.0},
    )

    assert "error" not in report, report
    review = report["modes"]["review"]
    assert "openrouter" in review["verified"]
    assert review["lane_kinds"]["openrouter"] == "openrouter"
    assert "https://openrouter.ai/api/v1/key" in transport.urls
    assert not any("chat/completions" in url for url in transport.urls)
    assert FAKE_KEY not in repr(report)


def test_check_vendors_reports_exhausted_ceiling_on_repo_roster(offline_host) -> None:
    report = review_dispatcher.check_vendors_report(
        agents_yaml=str(AGENTS_YAML),
        cwd=REPO_ROOT,
        dry_invoke=lambda _argv: None,
        environment="cloud",
        probe_transport=_KeyProbeTransport(),
        usage_fetcher=lambda: {"metered_ceiling_usd": 50.0, "metered_usd_used": 49.9},
    )

    review = report["modes"]["review"]
    assert "openrouter" not in review["verified"]
    assert {"vendor": "openrouter", "reason": "spend_ceiling_exceeded"} in review["unverified"]
