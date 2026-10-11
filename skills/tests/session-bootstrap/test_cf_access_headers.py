"""Every session hook that calls the coordinator sends the Cloudflare Access
service token when one is configured.

coord.rotkohl.ai sits behind a Cloudflare Access application. The edge refuses
any request without CF-Access-Client-Id/-Secret before it reaches the API, and
these hooks swallow errors by design -- so a hook missing the headers would fail
silently on every session rather than loudly once.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

HOOKS = Path(__file__).resolve().parents[2] / "session-bootstrap" / "scripts" / "hooks"
CF = {"CF-Access-Client-Id": "id.access", "CF-Access-Client-Secret": "s3cret"}


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"cf_{name}", HOOKS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cf_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "id.access")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "s3cret")
    monkeypatch.setenv("COORDINATION_API_KEY", "k")
    return monkeypatch


@pytest.mark.parametrize("hook", ["register_agent", "deregister_agent", "precompact_handoff"])
def test_hook_headers_carry_the_service_token(cf_env: pytest.MonkeyPatch, hook: str) -> None:
    headers = _load(hook)._api_headers()
    assert {k: headers[k] for k in CF} == CF
    assert headers["X-API-Key"] == "k"


@pytest.mark.parametrize("hook", ["register_agent", "deregister_agent", "precompact_handoff"])
def test_no_token_means_no_access_headers(monkeypatch: pytest.MonkeyPatch, hook: str) -> None:
    # Half a token is no token: never send an id without its secret.
    monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "id.access")
    headers = _load(hook)._api_headers()
    assert not set(CF) & set(headers)


def test_report_status_sends_the_service_token(
    cf_env: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _load("report_status")
    cf_env.setenv("COORDINATION_API_URL", "https://coord.example")
    cf_env.setattr(module, "_read_loop_state", lambda: {"current_phase": "IMPLEMENT"})
    cf_env.setattr(module, "_read_status_cache", lambda: {})
    cf_env.setattr(module, "_write_status_cache", lambda _data: None)
    sent: list[Any] = []

    def fake_urlopen(req: Any, timeout: float) -> Any:
        sent.append(req)
        raise OSError("not sending in a test")

    cf_env.setattr(module, "urlopen", fake_urlopen)
    cf_env.setattr(sys, "argv", ["report_status.py"])
    module.main()

    assert sent, "report_status did not attempt the request"
    headers = {k.lower(): v for k, v in sent[0].header_items()}
    assert headers["cf-access-client-id"] == "id.access"
    assert headers["cf-access-client-secret"] == "s3cret"
