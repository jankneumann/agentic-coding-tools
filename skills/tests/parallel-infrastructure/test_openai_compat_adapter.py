"""wp-dispatch adapter tests (task 4.1) — OpenSpec add-adaptive-model-router.

Verifies the OpenAI-compatible adapter's header construction, base_url routing,
generation-id capture, and error/fallback handling using an injected fake
transport (no network). conftest.py puts parallel-infrastructure/scripts on the
path.
"""

from __future__ import annotations

import json
import logging
import socket
import urllib.error

import pytest
from openai_compat_adapter import OpenAICompatAdapter, ProbeResult
from review_dispatcher import ErrorClass, ReviewResult


class FakeTransport:
    """Records calls and returns queued responses (or raises queued errors)."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append({"url": url, "headers": headers, "body": body, "timeout": timeout})
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


# A minimal, valid review-findings envelope — the adapter parses assistant
# content with the same extractor as the CLI/SDK adapters, which requires a
# top-level ``findings`` key. Tests that only care about dispatch mechanics
# (routing, gen-id, fallback) use this default.
_FINDINGS_JSON = '{"review_type": "pr", "findings": []}'


def _ok(content=_FINDINGS_JSON, gen_id="gen-abc123"):
    return {"id": gen_id, "choices": [{"message": {"role": "assistant", "content": content}}]}


def _adapter(endpoint_kind="openrouter", base_url="https://openrouter.ai/api/v1",
             vendor="openrouter", model="qwen/qwen3-coder", **kw):
    return OpenAICompatAdapter(
        agent_id="a1", vendor=vendor, model=model,
        base_url=base_url, endpoint_kind=endpoint_kind, **kw
    )


# ── headers ──────────────────────────────────────────────────────────────────

def test_openrouter_headers_include_auth_and_attribution():
    headers = _adapter().build_headers("sk-key")
    assert headers["Authorization"] == "Bearer sk-key"
    assert headers["HTTP-Referer"]
    assert headers["X-Title"]


def test_local_headers_omit_attribution():
    headers = _adapter(endpoint_kind="local", base_url="http://localhost:11434/v1").build_headers(None)
    assert "HTTP-Referer" not in headers
    assert "Authorization" not in headers  # local may be keyless


# ── base_url routing + generation-id capture ─────────────────────────────────

def test_dispatch_routes_to_base_url_and_captures_generation_id():
    tr = FakeTransport([_ok(gen_id="gen-xyz")])
    result = _adapter().dispatch("review", "prompt", api_key="sk-key", transport=tr)
    assert result.success
    assert result.generation_id == "gen-xyz"
    assert result.model_used == "qwen/qwen3-coder"
    assert result.findings == {"review_type": "pr", "findings": []}
    assert tr.calls[0]["url"] == "https://openrouter.ai/api/v1/chat/completions"


def test_local_endpoint_base_url_respected():
    tr = FakeTransport([_ok()])
    adapter = _adapter(endpoint_kind="local", base_url="http://localhost:11434/v1",
                       vendor="local", model="qwen3-coder-32b")
    result = adapter.dispatch("review", "p", api_key=None, transport=tr)
    assert result.success
    assert tr.calls[0]["url"] == "http://localhost:11434/v1/chat/completions"


def test_request_body_shape():
    tr = FakeTransport([_ok()])
    _adapter().dispatch("review", "hello", api_key="k", transport=tr)
    body = tr.calls[0]["body"]
    assert body["model"] == "qwen/qwen3-coder"
    assert body["messages"] == [{"role": "user", "content": "hello"}]
    assert body["temperature"] == 0


# ── auth / feasibility ───────────────────────────────────────────────────────

def test_openrouter_without_key_fails_auth():
    result = _adapter().dispatch("review", "p", api_key=None, transport=FakeTransport([]))
    assert not result.success
    assert result.error_class == ErrorClass.AUTH


# ── model fallback on capacity ───────────────────────────────────────────────

def test_capacity_error_falls_back_to_next_model():
    tr = FakeTransport([RuntimeError("HTTP 429 rate limit"), _ok()])
    adapter = _adapter(model_fallbacks=["meta/llama-3"])
    result = adapter.dispatch("review", "p", api_key="k", transport=tr)
    assert result.success
    assert result.model_used == "meta/llama-3"
    assert result.models_attempted == ["qwen/qwen3-coder", "meta/llama-3"]


def test_non_capacity_error_returns_immediately():
    tr = FakeTransport([RuntimeError("HTTP 401 unauthorized")])
    adapter = _adapter(model_fallbacks=["meta/llama-3"])
    result = adapter.dispatch("review", "p", api_key="k", transport=tr)
    assert not result.success
    assert result.error_class == ErrorClass.AUTH
    assert result.models_attempted == ["qwen/qwen3-coder"]  # no fallback attempted


def test_all_models_exhausted_returns_capacity():
    tr = FakeTransport([RuntimeError("429"), RuntimeError("rate limit")])
    adapter = _adapter(model_fallbacks=["meta/llama-3"])
    result = adapter.dispatch("review", "p", api_key="k", transport=tr)
    assert not result.success
    assert result.error_class == ErrorClass.CAPACITY


def test_empty_content_is_unsuccessful():
    tr = FakeTransport([{"id": "g", "choices": [{"message": {"content": ""}}]}])
    result = _adapter().dispatch("review", "p", api_key="k", transport=tr)
    assert not result.success
    assert result.error == "Empty response content"


def test_non_findings_json_is_unsuccessful():
    # Non-empty content that is NOT valid review-findings JSON must fail loudly
    # rather than be recorded as a successful review with zero findings.
    tr = FakeTransport([_ok(content="Looks good to me, no issues found.")])
    result = _adapter().dispatch("review", "p", api_key="k", transport=tr)
    assert not result.success
    assert result.error_class == ErrorClass.UNKNOWN
    assert "review-findings JSON" in result.error
    assert result.generation_id == "gen-abc123"  # gen-id still captured for reconciliation


def test_can_dispatch_review_only():
    a = _adapter()
    assert a.can_dispatch("review")
    assert not a.can_dispatch("alternative")


# ── cost capture (openrouter-review-lane, tasks 1.3/1.4, design D4) ─────────

# One substantive, schema-valid finding: survives the shared ingest pipeline
# (schema validation, placeholder check, fast-empty floor) regardless of elapsed.
_ONE_FINDING_JSON = json.dumps({
    "review_type": "plan",
    "target": "test-feature",
    "reviewer_vendor": "openrouter",
    "findings": [
        {"id": 1, "type": "security", "criticality": "high",
         "description": "Token is compared with == instead of a constant-time compare",
         "disposition": "fix", "axis": "security", "severity": "critical"},
    ],
})


def _ok_with_usage(usage, content=_ONE_FINDING_JSON, gen_id="gen-abc"):
    resp = _ok(content=content, gen_id=gen_id)
    if usage is not None:
        resp["usage"] = usage
    return resp


def test_request_body_asks_for_inline_usage_accounting():
    tr = FakeTransport([_ok_with_usage(None)])
    _adapter().dispatch("review", "hello", api_key="k", transport=tr)
    assert tr.calls[0]["body"]["usage"] == {"include": True}


def test_reported_cost_and_tokens_map_to_review_result():
    tr = FakeTransport([_ok_with_usage(
        {"prompt_tokens": 1200, "completion_tokens": 300, "total_tokens": 1500,
         "cost": 0.0042},
    )])
    result = _adapter().dispatch("review", "p", api_key="k", transport=tr)
    assert result.success
    assert result.generation_id == "gen-abc"
    assert result.prompt_tokens == 1200
    assert result.completion_tokens == 300
    assert result.cost_usd == 0.0042
    assert result.cost_source == "reported"
    assert result.spend_recorded is None  # set by the dispatcher's recorder (3.10)


def test_missing_cost_is_estimated():
    tr = FakeTransport([_ok_with_usage({"prompt_tokens": 10, "completion_tokens": 5})])
    result = _adapter().dispatch("review", "p", api_key="k", transport=tr)
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 5
    assert result.cost_usd is None
    assert result.cost_source == "estimated"


def test_missing_usage_block_is_estimated():
    tr = FakeTransport([_ok_with_usage(None)])
    result = _adapter().dispatch("review", "p", api_key="k", transport=tr)
    assert result.prompt_tokens is None
    assert result.completion_tokens is None
    assert result.cost_usd is None
    assert result.cost_source == "estimated"


def test_cost_is_captured_on_unsuccessful_response_too():
    # A response that was billed but failed ingest still carries its spend.
    tr = FakeTransport([_ok_with_usage(
        {"prompt_tokens": 7, "completion_tokens": 3, "cost": 0.001},
        content="not json at all",
    )])
    result = _adapter().dispatch("review", "p", api_key="k", transport=tr)
    assert not result.success
    assert result.cost_usd == 0.001
    assert result.cost_source == "reported"


def test_local_lane_is_not_metered():
    tr = FakeTransport([_ok_with_usage({"prompt_tokens": 4, "completion_tokens": 2})])
    adapter = _adapter(endpoint_kind="local", base_url="http://localhost:11434/v1",
                       vendor="local", model="qwen3-coder-32b")
    result = adapter.dispatch("review", "p", api_key=None, transport=tr)
    assert "usage" not in tr.calls[0]["body"]
    assert result.prompt_tokens == 4
    assert result.cost_source is None


def test_review_result_cost_fields_default_to_none():
    r = ReviewResult(vendor="codex", success=True)
    assert (r.prompt_tokens, r.completion_tokens, r.cost_usd, r.cost_source,
            r.spend_recorded) == (None, None, None, None, None)


# ── probe (openrouter-review-lane, tasks 1.1/1.2, design D3) ────────────────

_SENTINEL = "sk-or-test-SENTINEL-5555555555"


class FakeGetTransport:
    """GET transport double: returns ``(status, body)`` or raises a queued error."""

    def __init__(self, item):
        self._item = item
        self.calls = []

    def __call__(self, url, headers, timeout):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        if isinstance(self._item, BaseException):
            raise self._item
        return self._item


def _key_body(limit=20.0, usage=5.0, limit_remaining=15.0):
    return {"data": {"label": "sk-or-v1-abc...", "limit": limit, "usage": usage,
                     "limit_remaining": limit_remaining, "is_free_tier": False}}


def test_probe_openrouter_gets_key_endpoint():
    tr = FakeGetTransport((200, _key_body()))
    result = _adapter().probe("sk-key", transport=tr)
    assert len(tr.calls) == 1
    assert tr.calls[0]["url"] == "https://openrouter.ai/api/v1/key"
    assert tr.calls[0]["timeout"] == 10
    assert tr.calls[0]["headers"]["Authorization"] == "Bearer sk-key"
    assert isinstance(result, ProbeResult)


def test_probe_local_gets_models_endpoint():
    tr = FakeGetTransport((200, {"data": [{"id": "qwen3-coder-32b"}]}))
    adapter = _adapter(endpoint_kind="local", base_url="http://localhost:11434/v1",
                       vendor="local", model="qwen3-coder-32b")
    result = adapter.probe(None, transport=tr)
    assert tr.calls[0]["url"] == "http://localhost:11434/v1/models"
    assert result.ok is True
    assert result.reason is None
    assert result.budget is None  # no budget rule for local lanes


def test_probe_200_is_ok_with_numeric_budget():
    result = _adapter().probe("sk-key", transport=FakeGetTransport((200, _key_body())))
    assert result.ok is True
    assert result.reason is None
    assert result.budget == {"limit": 20.0, "usage": 5.0, "limit_remaining": 15.0}


def test_probe_budget_keeps_only_numeric_fields():
    body = {"data": {"limit": None, "usage": "lots", "limit_remaining": True,
                     "label": _SENTINEL}}
    result = _adapter().probe("sk-key", transport=FakeGetTransport((200, body)))
    assert result.ok is True
    assert result.budget == {"limit": None, "usage": None, "limit_remaining": None}


def test_probe_body_without_data_has_no_budget():
    result = _adapter().probe("sk-key", transport=FakeGetTransport((200, {"error": "?"})))
    assert result.ok is True
    assert result.budget is None


@pytest.mark.parametrize("status", [401, 403])
def test_probe_rejected_key_is_auth_failed(status):
    result = _adapter().probe("sk-key", transport=FakeGetTransport((status, None)))
    assert result.ok is False
    assert result.reason == "auth_failed"
    assert result.budget is None


def test_probe_openrouter_without_key_is_auth_failed_without_request():
    tr = FakeGetTransport((200, _key_body()))
    result = _adapter().probe(None, transport=tr)
    assert result.reason == "auth_failed"
    assert tr.calls == []


@pytest.mark.parametrize("exc", [
    TimeoutError("timed out"),
    socket.timeout("timed out"),
    urllib.error.URLError(socket.timeout("timed out")),
])
def test_probe_timeout(exc):
    result = _adapter().probe("sk-key", transport=FakeGetTransport(exc))
    assert result.ok is False
    assert result.reason == "probe_timeout"


@pytest.mark.parametrize("exc", [
    ConnectionRefusedError("refused"),
    urllib.error.URLError("Name or service not known"),
    OSError("network unreachable"),
])
def test_probe_connection_error_is_endpoint_unreachable(exc):
    result = _adapter().probe("sk-key", transport=FakeGetTransport(exc))
    assert result.ok is False
    assert result.reason == "endpoint_unreachable"


def test_probe_server_error_is_endpoint_unreachable():
    result = _adapter().probe("sk-key", transport=FakeGetTransport((502, None)))
    assert result.ok is False
    assert result.reason == "endpoint_unreachable"


def test_probe_never_discloses_credentials(caplog, capsys):
    """Sentinel: a transport echoing headers leaks nothing into result/logs/errors."""

    def echo(url, headers, timeout):
        return 200, {"data": {"limit": 20.0, "usage": 1.0, "limit_remaining": 19.0,
                              "echo": dict(headers), "label": headers["Authorization"]}}

    def raising_echo(url, headers, timeout):
        raise urllib.error.URLError(f"boom {headers['Authorization']}")

    caplog.set_level(logging.DEBUG)
    ok = _adapter().probe(_SENTINEL, transport=echo)
    failed = _adapter().probe(_SENTINEL, transport=raising_echo)

    assert ok.ok is True
    assert failed.reason == "endpoint_unreachable"
    out = capsys.readouterr()
    for text in (repr(ok), repr(failed), str(ok.budget), caplog.text, out.out, out.err):
        assert _SENTINEL not in text
