"""Tests for the provider dispatch layer's `local` adapter.

All tests stub the HTTP layer — no real network traffic is ever issued.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

# Ensure the scripts directory is importable
_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import provider_dispatch  # noqa: E402
from provider_dispatch import (  # noqa: E402
    PhaseDispatchPayload,
    PhaseDispatchResult,
    dispatch_phase,
    local_endpoint_available,
)

_LOCAL_ENV = (
    "LOCAL_INFERENCE_BASE_URL",
    "LOCAL_INFERENCE_API_KEY",
    "LOCAL_INFERENCE_MAX_CONCURRENCY",
)


@pytest.fixture(autouse=True)
def _clean_local_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test starts with no local endpoint configured and a cold probe."""
    for name in _LOCAL_ENV:
        monkeypatch.delenv(name, raising=False)
    provider_dispatch.reset_local_adapter_state()
    yield
    provider_dispatch.reset_local_adapter_state()


def _payload(**overrides: Any) -> PhaseDispatchPayload:
    data: dict[str, Any] = {
        "schema_version": 1,
        "change_id": "demo",
        "phase": "IMPLEMENT",
        "provider": "local",
        "archetype": "runner",
        "model": "qwen3-coder-30b-a3b",
        "prompt": "do work",
        "system_prompt": "You are a focused runner.",
        "isolation": "worktree",
        "expected_outcomes": ["complete", "failed"],
    }
    data.update(overrides)
    return PhaseDispatchPayload(**data)


def _chat_response(content: str, model: str = "qwen3-coder-30b-a3b") -> dict[str, Any]:
    return {
        "id": "chatcmpl-1",
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
    }


# ---------------------------------------------------------------------------
# Provider roster
# ---------------------------------------------------------------------------


def test_local_is_a_supported_provider() -> None:
    """`local` is a first-class provider alongside the existing roster."""
    assert "local" in provider_dispatch._SUPPORTED_PROVIDERS
    assert {"claude_code", "codex", "antigravity", "grok", "pi"}.issubset(
        provider_dispatch._SUPPORTED_PROVIDERS
    )


def test_existing_providers_still_fall_back_without_a_runner() -> None:
    """Rule 4: non-local providers keep their exact pre-change behavior."""
    result = dispatch_phase(_payload(provider="codex", model="gpt-5.5"))

    assert result.dispatch_tier == "fallback"
    assert result.outcome == "failed"
    assert result.handoff_id == "fallback:codex:IMPLEMENT"
    assert any("adapter unavailable" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Unconfigured / unreachable endpoint -> structured fallback
# ---------------------------------------------------------------------------


def test_unset_base_url_degrades_to_fallback_naming_local() -> None:
    """No LOCAL_INFERENCE_BASE_URL => provider is inert, never an exception."""
    result = dispatch_phase(_payload())

    assert isinstance(result, PhaseDispatchResult)
    assert result.dispatch_tier == "fallback"
    assert result.outcome == "failed"
    assert result.provider == "local"
    assert result.handoff_id == "fallback:local:IMPLEMENT"
    assert result.warnings
    assert any("local" in w for w in result.warnings)


def test_unset_base_url_never_touches_the_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The adapter must not probe or dispatch when no endpoint is configured."""

    def _boom(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("network layer must not be called")

    monkeypatch.setattr(provider_dispatch, "_http_get_json", _boom)
    monkeypatch.setattr(provider_dispatch, "_http_post_json", _boom)

    result = dispatch_phase(_payload())

    assert result.dispatch_tier == "fallback"


def test_failing_health_probe_degrades_to_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dead endpoint is adapter unavailability, not a dispatch error."""
    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", "http://gx10.invalid:8080/v1")

    def _probe_fails(url: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        raise OSError("connection refused")

    posted: list[str] = []

    monkeypatch.setattr(provider_dispatch, "_http_get_json", _probe_fails)
    monkeypatch.setattr(
        provider_dispatch,
        "_http_post_json",
        lambda *a, **k: posted.append("post") or {},
    )

    result = dispatch_phase(_payload())

    assert result.dispatch_tier == "fallback"
    assert result.outcome == "failed"
    assert any("local" in w for w in result.warnings)
    assert posted == [], "no chat request may be sent when the probe fails"


def test_probe_failure_does_not_hang(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dead endpoint returns promptly with a bounded probe timeout."""
    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", "http://gx10.invalid:8080/v1")
    seen: list[float] = []

    def _probe(url: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        seen.append(timeout)
        raise TimeoutError("timed out")

    monkeypatch.setattr(provider_dispatch, "_http_get_json", _probe)

    started = time.monotonic()
    result = dispatch_phase(_payload())

    assert time.monotonic() - started < 5.0
    assert seen and seen[0] <= 10.0, "probe timeout must be short"
    assert result.dispatch_tier == "fallback"


def test_dispatch_error_degrades_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mid-dispatch HTTP failure degrades to the structured fallback result."""
    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", "http://gx10.local:8080/v1")
    monkeypatch.setattr(
        provider_dispatch, "_http_get_json", lambda *a, **k: {"data": []}
    )

    def _post_fails(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise OSError("connection reset")

    monkeypatch.setattr(provider_dispatch, "_http_post_json", _post_fails)

    result = dispatch_phase(_payload())

    assert result.dispatch_tier == "fallback"
    assert result.outcome == "failed"
    assert any("local" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Probe status exposure
# ---------------------------------------------------------------------------


def test_local_endpoint_available_false_when_unset() -> None:
    assert local_endpoint_available() is False


def test_local_endpoint_available_reflects_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", "http://gx10.local:8080/v1")
    monkeypatch.setattr(
        provider_dispatch, "_http_get_json", lambda *a, **k: {"data": []}
    )

    assert local_endpoint_available() is True


def test_probe_is_cached_within_its_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeat dispatches inside the TTL share one health probe."""
    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", "http://gx10.local:8080/v1")
    calls: list[str] = []

    def _probe(url: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        calls.append(url)
        return {"data": []}

    monkeypatch.setattr(provider_dispatch, "_http_get_json", _probe)
    monkeypatch.setattr(
        provider_dispatch,
        "_http_post_json",
        lambda *a, **k: _chat_response("done"),
    )

    dispatch_phase(_payload())
    dispatch_phase(_payload())
    assert local_endpoint_available() is True

    assert len(calls) == 1
    assert calls[0] == "http://gx10.local:8080/v1/models"

    provider_dispatch.reset_local_adapter_state()
    assert local_endpoint_available() is True
    assert len(calls) == 2


def test_probe_verdict_expires_after_the_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """The verdict is a cache, not a fact: it must not outlive its TTL."""
    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", "http://gx10.local:8080/v1")
    monkeypatch.setattr(provider_dispatch, "_LOCAL_PROBE_TTL_SECONDS", 0.05)
    calls: list[str] = []

    def _probe(url: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        calls.append(url)
        return {"data": []}

    monkeypatch.setattr(provider_dispatch, "_http_get_json", _probe)

    assert local_endpoint_available() is True
    assert local_endpoint_available() is True
    assert len(calls) == 1

    time.sleep(0.06)
    assert local_endpoint_available() is True
    assert len(calls) == 2


def test_transient_probe_failure_does_not_blackhole_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One bad probe must not pin `local` unavailable for the whole process."""
    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", "http://gx10.local:8080/v1")
    monkeypatch.setattr(provider_dispatch, "_LOCAL_PROBE_TTL_SECONDS", 0.05)
    attempts = {"n": 0}

    def _probe(url: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise OSError("transient connection reset")
        return {"data": []}

    monkeypatch.setattr(provider_dispatch, "_http_get_json", _probe)

    assert local_endpoint_available() is False
    time.sleep(0.06)
    assert local_endpoint_available() is True


def test_dispatch_connection_error_invalidates_the_probe_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dead-after-probe endpoint must not keep passing as reachable."""
    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", "http://gx10.local:8080/v1")
    probes = {"n": 0}

    def _probe(url: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        probes["n"] += 1
        if probes["n"] == 1:
            return {"data": []}
        raise OSError("endpoint died")

    monkeypatch.setattr(provider_dispatch, "_http_get_json", _probe)

    def _post_fails(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise OSError("connection refused")

    monkeypatch.setattr(provider_dispatch, "_http_post_json", _post_fails)

    first = dispatch_phase(_payload())
    assert first.dispatch_tier == "fallback"
    assert probes["n"] == 1

    # The cached "reachable" verdict was dropped by the connection error, so the
    # next caller re-probes (and now sees the endpoint is gone).
    assert local_endpoint_available() is False
    assert probes["n"] == 2


def test_cold_probe_is_single_flight(monkeypatch: pytest.MonkeyPatch) -> None:
    """Concurrent cold callers collapse onto one probe request."""
    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", "http://gx10.local:8080/v1")
    calls: list[str] = []
    calls_lock = threading.Lock()
    release = threading.Event()

    def _probe(url: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
        with calls_lock:
            calls.append(url)
        release.wait(2.0)
        return {"data": []}

    monkeypatch.setattr(provider_dispatch, "_http_get_json", _probe)

    verdicts: list[bool] = []
    verdicts_lock = threading.Lock()

    def _worker() -> None:
        verdict = local_endpoint_available()
        with verdicts_lock:
            verdicts.append(verdict)

    threads = [threading.Thread(target=_worker) for _ in range(5)]
    for thread in threads:
        thread.start()
    time.sleep(0.1)
    release.set()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not t.is_alive() for t in threads)
    assert verdicts == [True] * 5
    assert len(calls) == 1, f"cold probe fanned out: {len(calls)} requests"


# ---------------------------------------------------------------------------
# Endpoint URL validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw", ["file:///etc/passwd", "ftp://gx10.local/v1", "gx10.local:8080/v1"]
)
def test_non_http_base_url_is_rejected_without_probing(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    """A non-http(s) endpoint is a misconfiguration, not something to call."""
    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", raw)

    def _boom(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("network layer must not be called")

    monkeypatch.setattr(provider_dispatch, "_http_get_json", _boom)
    monkeypatch.setattr(provider_dispatch, "_http_post_json", _boom)

    assert local_endpoint_available() is False

    result = dispatch_phase(_payload())
    assert result.dispatch_tier == "fallback"
    assert any("http://" in w for w in result.warnings)


def test_https_base_url_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", "https://gx10.local:8443/v1")
    monkeypatch.setattr(
        provider_dispatch, "_http_get_json", lambda *a, **k: {"data": []}
    )

    assert local_endpoint_available() is True


# ---------------------------------------------------------------------------
# Archetype trust boundary (defence in depth for the resolver's D3 gate)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "archetype", ["implementer", "architect", "reviewer", "gatekeeper", "", None]
)
def test_untrusted_archetype_never_reaches_the_endpoint(
    monkeypatch: pytest.MonkeyPatch, archetype: str | None
) -> None:
    """No dispatch is attempted for an archetype outside the trust boundary."""
    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", "http://gx10.local:8080/v1")

    def _boom(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("trust-boundary payload must not touch the network")

    monkeypatch.setattr(provider_dispatch, "_http_get_json", _boom)
    monkeypatch.setattr(provider_dispatch, "_http_post_json", _boom)

    result = dispatch_phase(_payload(archetype=archetype, phase="IMPLEMENT"))

    assert result.dispatch_tier == "fallback"
    assert result.outcome == "failed"
    assert any("trust boundary" in w for w in result.warnings)
    assert any("local" in w for w in result.warnings)


@pytest.mark.parametrize("archetype", ["runner", "analyst", "documenter", "validator"])
def test_trusted_archetypes_dispatch(
    monkeypatch: pytest.MonkeyPatch, archetype: str
) -> None:
    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", "http://gx10.local:8080/v1")
    monkeypatch.setattr(
        provider_dispatch, "_http_get_json", lambda *a, **k: {"data": []}
    )
    monkeypatch.setattr(
        provider_dispatch, "_http_post_json", lambda *a, **k: _chat_response("done")
    )

    result = dispatch_phase(_payload(archetype=archetype))

    assert result.outcome == "complete"
    assert result.dispatch_tier == "harness"


def test_untrusted_archetype_also_fails_the_dry_run() -> None:
    """Dry run models the real decision path instead of reporting a false pass."""
    result = dispatch_phase(_payload(archetype="implementer"), dry_run=True)

    assert result.outcome == "failed"
    assert result.dispatch_tier == "dry_run"
    assert result.handoff_id == "dry-run:local:IMPLEMENT:trust-boundary"
    assert any("trust boundary" in w for w in result.warnings)


def test_trust_boundary_does_not_gate_other_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rule 4: the allowlist is inert for every pre-existing provider."""
    result = dispatch_phase(
        _payload(provider="codex", model="gpt-5.5", archetype="implementer"),
        dry_run=True,
    )

    assert result.outcome == "complete"
    assert result.dispatch_tier == "dry_run"


# ---------------------------------------------------------------------------
# Unresolved model
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("model", [None, ""])
def test_unresolved_model_degrades_instead_of_sending_a_placeholder(
    monkeypatch: pytest.MonkeyPatch, model: str | None
) -> None:
    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", "http://gx10.local:8080/v1")

    def _boom(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("a payload without a model must not be dispatched")

    monkeypatch.setattr(provider_dispatch, "_http_get_json", _boom)
    monkeypatch.setattr(provider_dispatch, "_http_post_json", _boom)

    result = dispatch_phase(_payload(model=model))

    assert result.dispatch_tier == "fallback"
    assert result.outcome == "failed"
    assert any("no model resolved" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Wall-clock deadlines and response budget
# ---------------------------------------------------------------------------


def test_trickling_endpoint_hits_the_dispatch_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A byte-trickling endpoint must not park the phase past the deadline."""
    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", "http://gx10.local:8080/v1")
    monkeypatch.setattr(provider_dispatch, "_LOCAL_DISPATCH_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(
        provider_dispatch, "_http_get_json", lambda *a, **k: {"data": []}
    )

    stop = threading.Event()

    def _trickle(*args: Any, **kwargs: Any) -> dict[str, Any]:
        stop.wait(30)  # never returns within the deadline
        return _chat_response("too late")

    monkeypatch.setattr(provider_dispatch, "_http_post_json", _trickle)

    started = time.monotonic()
    result = dispatch_phase(_payload())
    elapsed = time.monotonic() - started
    stop.set()

    assert elapsed < 5.0
    assert result.dispatch_tier == "fallback"
    assert result.outcome == "failed"
    assert any("LocalDeadlineExceeded" in w for w in result.warnings)


def test_trickling_endpoint_frees_its_concurrency_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stuck dispatch must not hold a semaphore slot forever."""
    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", "http://gx10.local:8080/v1")
    monkeypatch.setenv("LOCAL_INFERENCE_MAX_CONCURRENCY", "1")
    monkeypatch.setattr(provider_dispatch, "_LOCAL_DISPATCH_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(
        provider_dispatch, "_http_get_json", lambda *a, **k: {"data": []}
    )

    stop = threading.Event()
    calls = {"n": 0}

    def _post(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls["n"] += 1
        if calls["n"] == 1:
            stop.wait(30)
            return _chat_response("too late")
        return _chat_response("done")

    monkeypatch.setattr(provider_dispatch, "_http_post_json", _post)

    assert dispatch_phase(_payload()).dispatch_tier == "fallback"
    second = dispatch_phase(_payload())
    stop.set()

    assert second.outcome == "complete", "the wedged dispatch kept its slot"


def test_gate_timeout_degrades_to_the_structured_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", "http://gx10.local:8080/v1")
    monkeypatch.setattr(provider_dispatch, "_LOCAL_GATE_ACQUIRE_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(
        provider_dispatch, "_http_get_json", lambda *a, **k: {"data": []}
    )
    monkeypatch.setattr(
        provider_dispatch, "_http_post_json", lambda *a, **k: _chat_response("done")
    )

    # Warm the gate, then take its only slot so the dispatcher cannot get one.
    monkeypatch.setenv("LOCAL_INFERENCE_MAX_CONCURRENCY", "1")
    gate = provider_dispatch._local_gate()
    assert gate.acquire(timeout=1) is True
    try:
        result = dispatch_phase(_payload())
    finally:
        gate.release()

    assert result.dispatch_tier == "fallback"
    assert result.outcome == "failed"
    assert any("LocalGateTimeout" in w for w in result.warnings)


def test_oversized_response_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The byte budget is enforced by the transport, not the caller."""

    class _FakeResponse:
        def read(self, amount: int | None = None) -> bytes:
            assert amount is not None
            return b"x" * amount

        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, *exc: Any) -> None:
            return None

    monkeypatch.setattr(
        provider_dispatch.urllib.request, "urlopen", lambda *a, **k: _FakeResponse()
    )

    with pytest.raises(provider_dispatch.LocalResponseTooLarge):
        provider_dispatch._http_get_json("http://gx10.local:8080/v1/models", {}, 1.0)


def test_oversized_dispatch_response_degrades_to_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", "http://gx10.local:8080/v1")
    monkeypatch.setattr(
        provider_dispatch, "_http_get_json", lambda *a, **k: {"data": []}
    )

    def _too_big(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise provider_dispatch.LocalResponseTooLarge("too big")

    monkeypatch.setattr(provider_dispatch, "_http_post_json", _too_big)

    result = dispatch_phase(_payload())

    assert result.dispatch_tier == "fallback"
    assert result.outcome == "failed"
    assert any("LocalResponseTooLarge" in w for w in result.warnings)


def test_dispatch_warning_carries_only_the_exception_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Endpoint-controlled text stays out of the user-visible warning."""
    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", "http://gx10.local:8080/v1")
    monkeypatch.setattr(
        provider_dispatch, "_http_get_json", lambda *a, **k: {"data": []}
    )

    def _post_fails(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise OSError("<script>alert(1)</script> secret-token leaked here")

    monkeypatch.setattr(provider_dispatch, "_http_post_json", _post_fails)

    result = dispatch_phase(_payload())

    assert any("OSError" in w for w in result.warnings)
    assert not any("secret-token" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Configured endpoint dispatches over the OpenAI-compatible wire protocol
# ---------------------------------------------------------------------------


def test_reachable_endpoint_dispatches_and_normalizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", "http://gx10.local:8080/v1/")
    monkeypatch.setenv("LOCAL_INFERENCE_API_KEY", "secret-token")
    monkeypatch.setattr(
        provider_dispatch, "_http_get_json", lambda *a, **k: {"data": []}
    )

    captured: dict[str, Any] = {}

    def _post(
        url: str, headers: dict[str, str], body: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = body
        captured["timeout"] = timeout
        return _chat_response('{"outcome": "complete", "handoff_id": "handoff-42"}')

    monkeypatch.setattr(provider_dispatch, "_http_post_json", _post)

    result = dispatch_phase(_payload())

    assert result.outcome == "complete"
    assert result.handoff_id == "handoff-42"
    assert result.provider == "local"
    assert result.model_used == "qwen3-coder-30b-a3b"
    assert result.dispatch_tier == "harness"
    assert result.warnings == []

    assert captured["url"] == "http://gx10.local:8080/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer secret-token"
    assert captured["headers"]["Content-Type"] == "application/json"
    assert captured["body"]["model"] == "qwen3-coder-30b-a3b"
    assert captured["body"]["messages"][0] == {
        "role": "system",
        "content": "You are a focused runner.",
    }
    assert captured["body"]["messages"][-1] == {"role": "user", "content": "do work"}
    assert isinstance(captured["timeout"], (int, float))
    assert captured["timeout"] > 0


def test_no_api_key_sends_no_authorization_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", "http://gx10.local:8080/v1")
    monkeypatch.setattr(
        provider_dispatch, "_http_get_json", lambda *a, **k: {"data": []}
    )
    captured: dict[str, Any] = {}

    def _post(
        url: str, headers: dict[str, str], body: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        captured["headers"] = headers
        return _chat_response("done")

    monkeypatch.setattr(provider_dispatch, "_http_post_json", _post)

    dispatch_phase(_payload())

    assert "Authorization" not in captured["headers"]


def test_plain_text_response_normalizes_to_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", "http://gx10.local:8080/v1")
    monkeypatch.setattr(
        provider_dispatch, "_http_get_json", lambda *a, **k: {"data": []}
    )
    monkeypatch.setattr(
        provider_dispatch,
        "_http_post_json",
        lambda *a, **k: _chat_response("finished the runner phase"),
    )

    result = dispatch_phase(_payload())

    assert result.outcome == "complete"
    assert result.handoff_id  # synthesized by normalize_dispatch_result
    assert result.dispatch_tier == "harness"
    assert result.model_used == "qwen3-coder-30b-a3b"


def test_empty_response_content_is_a_failed_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", "http://gx10.local:8080/v1")
    monkeypatch.setattr(
        provider_dispatch, "_http_get_json", lambda *a, **k: {"data": []}
    )
    monkeypatch.setattr(
        provider_dispatch, "_http_post_json", lambda *a, **k: {"choices": []}
    )

    result = dispatch_phase(_payload())

    assert result.outcome == "failed"
    assert result.dispatch_tier == "harness"


def test_explicit_runner_still_wins_over_the_builtin_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A caller-supplied runner is used even for provider `local`."""
    monkeypatch.setattr(
        provider_dispatch,
        "_http_post_json",
        lambda *a, **k: pytest.fail("built-in adapter must not run"),
    )

    result = dispatch_phase(
        _payload(), runner=lambda payload: ("complete", "runner-handoff")
    )

    assert result.handoff_id == "runner-handoff"
    assert result.dispatch_tier == "harness"


# ---------------------------------------------------------------------------
# Dry-run parity
# ---------------------------------------------------------------------------


def test_local_dry_run_needs_no_environment() -> None:
    """Dry-run never touches the network and works with nothing configured."""
    result = dispatch_phase(_payload(), dry_run=True)

    assert result.outcome == "complete"
    assert result.dispatch_tier == "dry_run"
    assert result.handoff_id.startswith("dry-run:local:IMPLEMENT:")
    assert result.warnings == []


def test_local_dry_run_rejects_claude_aliases() -> None:
    """`local` is a non-Claude provider: Claude aliases stay invalid."""
    result = dispatch_phase(_payload(model="opus"), dry_run=True)

    assert result.outcome == "failed"
    assert result.handoff_id == "dry-run:local:IMPLEMENT:invalid-model"
    assert any("opus" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Concurrency cap
# ---------------------------------------------------------------------------


def test_concurrency_cap_queues_excess_dispatches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Excess dispatches queue; none are dropped or failed by the cap."""
    monkeypatch.setenv("LOCAL_INFERENCE_BASE_URL", "http://gx10.local:8080/v1")
    monkeypatch.setenv("LOCAL_INFERENCE_MAX_CONCURRENCY", "2")
    monkeypatch.setattr(
        provider_dispatch, "_http_get_json", lambda *a, **k: {"data": []}
    )

    lock = threading.Lock()
    state = {"in_flight": 0, "peak": 0}

    def _post(*args: Any, **kwargs: Any) -> dict[str, Any]:
        with lock:
            state["in_flight"] += 1
            state["peak"] = max(state["peak"], state["in_flight"])
        time.sleep(0.05)
        with lock:
            state["in_flight"] -= 1
        return _chat_response("done")

    monkeypatch.setattr(provider_dispatch, "_http_post_json", _post)

    # Warm the probe so probing does not serialize the workers.
    assert local_endpoint_available() is True

    results: list[PhaseDispatchResult] = []
    results_lock = threading.Lock()

    def _worker() -> None:
        outcome = dispatch_phase(_payload())
        with results_lock:
            results.append(outcome)

    threads = [threading.Thread(target=_worker) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert all(not t.is_alive() for t in threads)
    assert len(results) == 6
    assert all(r.outcome == "complete" for r in results)
    assert all(r.dispatch_tier == "harness" for r in results)
    assert state["peak"] <= 2, f"cap exceeded: peak={state['peak']}"


def test_default_concurrency_cap_is_four(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOCAL_INFERENCE_MAX_CONCURRENCY", raising=False)
    assert provider_dispatch._local_max_concurrency() == 4


@pytest.mark.parametrize("raw", ["", "0", "-3", "not-a-number"])
def test_invalid_concurrency_values_fall_back_to_default(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv("LOCAL_INFERENCE_MAX_CONCURRENCY", raw)
    assert provider_dispatch._local_max_concurrency() == 4


def test_absurd_concurrency_value_is_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_INFERENCE_MAX_CONCURRENCY", "100000")
    assert provider_dispatch._local_max_concurrency() == 64


def test_concurrency_cap_is_read_once_per_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-reading the cap per dispatch would swap the gate and over-admit."""
    monkeypatch.setenv("LOCAL_INFERENCE_MAX_CONCURRENCY", "2")
    gate = provider_dispatch._local_gate()

    monkeypatch.setenv("LOCAL_INFERENCE_MAX_CONCURRENCY", "8")
    assert provider_dispatch._local_gate() is gate

    provider_dispatch.reset_local_adapter_state()
    assert provider_dispatch._local_gate() is not gate
