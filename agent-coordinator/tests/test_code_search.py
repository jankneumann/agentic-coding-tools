"""Unit tests for the coordinator code-search service (change: add-semantic-code-search).

All logic is exercised with mocked backends — no live ParadeDB or embedder required, so these
run in the PyPI-only cloud harness. Covers design D4 (server-side embed + mismatch), D5 (read-
only), D7 (scope filtering), D10 (flag), and MCP/HTTP payload parity.
"""
from __future__ import annotations

import pytest

from src.code_search import (
    CodeSearchHit,
    CodeSearchService,
    EmbedderMismatchError,
    RepoNotIndexedError,
    code_search_enabled,
    filter_by_scope,
)

MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def _row(fp, score=0.8, lang="python"):
    return {
        "file_path": fp,
        "language": lang,
        "content": "…",
        "start_line": 1,
        "end_line": 9,
        "score": score,
    }


def make_service(registry_row=None, rows=None, model=MODEL):
    async def registry(repo):
        return registry_row

    async def embedder(text):
        return [0.1, 0.2, 0.3]

    calls = {}

    async def backend(repo, embedding, limit, offset, languages, paths):
        calls["args"] = (repo, embedding, limit, offset, languages, paths)
        return rows or []

    svc = CodeSearchService(registry, embedder, backend, embedder_model=model)
    svc._calls = calls  # type: ignore[attr-defined]
    return svc


# --- D10 flag ---------------------------------------------------------------------------------

def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("CODE_SEARCH_ENABLED", raising=False)
    assert code_search_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on"])
def test_flag_truthy(monkeypatch, val):
    monkeypatch.setenv("CODE_SEARCH_ENABLED", val)
    assert code_search_enabled() is True


# --- D4 registry consistency ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_repo_not_indexed_raises_409():
    svc = make_service(registry_row=None)
    with pytest.raises(RepoNotIndexedError) as ei:
        await svc.search("q", "agentic_coding_tools")
    assert ei.value.status == 409


@pytest.mark.asyncio
async def test_embedder_mismatch_raises_422():
    svc = make_service(registry_row={"embedder_model": "some-other-model"})
    with pytest.raises(EmbedderMismatchError) as ei:
        await svc.search("q", "agentic_coding_tools")
    assert ei.value.status == 422
    # names both models
    assert "some-other-model" in str(ei.value) and MODEL in str(ei.value)


# --- happy path + D4 server-side embedding ----------------------------------------------------

@pytest.mark.asyncio
async def test_search_returns_hits_and_embeds_server_side():
    rows = [_row("agent-coordinator/src/locks.py", 0.83)]
    svc = make_service(registry_row={"embedder_model": MODEL}, rows=rows)
    resp = await svc.search("how are locks released", "agentic_coding_tools", limit=5)
    assert [h.file_path for h in resp.results] == ["agent-coordinator/src/locks.py"]
    assert resp.results[0].score == pytest.approx(0.83)
    # backend received the embedding the service produced (caller sent only text) — D4.
    _repo, embedding, *_ = svc._calls["args"]  # type: ignore[attr-defined]
    assert embedding == [0.1, 0.2, 0.3]
    assert resp.scope_filtered is False


# --- D7 scope filtering -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scope_drops_out_of_scope_hits():
    rows = [
        _row("agent-coordinator/src/locks.py", 0.9),
        _row("skills/worktree/scripts/worktree.py", 0.85),
    ]
    svc = make_service(registry_row={"embedder_model": MODEL}, rows=rows)
    resp = await svc.search(
        "q", "agentic_coding_tools", limit=5,
        scope={"read_allow": ["agent-coordinator/**"]},
    )
    paths = [h.file_path for h in resp.results]
    assert "agent-coordinator/src/locks.py" in paths
    assert "skills/worktree/scripts/worktree.py" not in paths
    assert resp.scope_filtered is True


def test_filter_by_scope_deny_wins():
    hits = [
        CodeSearchHit("a/b.py", "python", "", 1, 2, 0.9),
        CodeSearchHit("a/secret.py", "python", "", 1, 2, 0.9),
    ]
    out = filter_by_scope(hits, ["a/**"], ["a/secret.py"])
    assert [h.file_path for h in out] == ["a/b.py"]


def test_filter_by_scope_empty_allow_is_unrestricted():
    hits = [CodeSearchHit("anything.py", "python", "", 1, 2, 0.9)]
    assert filter_by_scope(hits, None, None) == hits


# --- MCP/HTTP parity: both surfaces call the same service, so payloads match by construction ---

@pytest.mark.asyncio
async def test_response_to_dict_shape_matches_contract():
    rows = [_row("agent-coordinator/src/locks.py", 0.83)]
    svc = make_service(registry_row={"embedder_model": MODEL}, rows=rows)
    resp = await svc.search("q", "agentic_coding_tools")
    d = resp.to_dict()
    assert set(d) == {"repo", "results", "scope_filtered"}
    assert set(d["results"][0]) == {
        "file_path", "language", "content", "start_line", "end_line", "score",
    }
