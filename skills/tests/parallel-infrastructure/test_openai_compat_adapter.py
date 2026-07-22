"""wp-dispatch adapter tests (task 4.1) — OpenSpec add-adaptive-model-router.

Verifies the OpenAI-compatible adapter's header construction, base_url routing,
generation-id capture, and error/fallback handling using an injected fake
transport (no network). conftest.py puts parallel-infrastructure/scripts on the
path.
"""

from __future__ import annotations

from openai_compat_adapter import OpenAICompatAdapter
from review_dispatcher import ErrorClass


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
_FINDINGS_JSON = (
    '{"review_type": "implementation", "target": "PR #1", "findings": []}'
)


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
    assert result.findings == {
        "review_type": "implementation",
        "target": "PR #1",
        "findings": [],
    }
    assert result.raw_output == _FINDINGS_JSON
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
    assert result.raw_output == "Looks good to me, no issues found."


def test_can_dispatch_review_only():
    a = _adapter()
    assert a.can_dispatch("review")
    assert not a.can_dispatch("alternative")
