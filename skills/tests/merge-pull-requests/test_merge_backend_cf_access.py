"""The merge-train backend reaches the coordinator through Cloudflare Access,
whose edge refuses any request without the service token."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "merge-pull-requests" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from merge_backend import CoordinatorTrainBackend  # noqa: E402


def test_train_requests_carry_the_service_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "id.access")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "s3cret")
    headers = CoordinatorTrainBackend(api_url="https://coord.example", api_key="k")._headers()
    assert headers["CF-Access-Client-Id"] == "id.access"
    assert headers["CF-Access-Client-Secret"] == "s3cret"
    assert headers["X-API-Key"] == "k"


def test_no_token_means_no_access_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CF_ACCESS_CLIENT_ID", raising=False)
    monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)
    headers = CoordinatorTrainBackend(api_url="https://coord.example")._headers()
    assert "CF-Access-Client-Id" not in headers
