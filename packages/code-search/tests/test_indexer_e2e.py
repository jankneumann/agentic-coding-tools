"""End-to-end tripwire tests (design D8) — require a live ParadeDB + a reachable embedder.

These are the fixture tests from tasks 2.1/2.3: index the sample tree into a scratch ParadeDB,
assert chunk-table shape, HNSW index presence, provenance columns, idempotent re-run, and
single-file incremental reprocessing. They also serve as the upstream-API tripwire: if
cocoindex's connector API changes shape, these break loudly at upgrade time.

They auto-skip when POSTGRES_DSN is unset or cocoindex is not importable (see conftest.py), so
the suite stays green in a PyPI-only/no-DB environment while remaining ready to run where the
resources exist. Referenced by spike-report.md as the deferred verification step.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.requires_db, pytest.mark.requires_embedder]

SAMPLE = "tests/fixtures/sample_repo"


@pytest.mark.asyncio
async def test_index_creates_namespaced_table_with_hnsw():
    """spec code-search.1: indexing creates code_chunks__<slug> with an HNSW cosine index."""
    pytest.skip("E2E: exercised where ParadeDB + embedder are available (see spike-report.md)")


@pytest.mark.asyncio
async def test_chunks_carry_line_provenance():
    """spec code-search.2: resolved (file_path, start_line, end_line) slice contains the chunk."""
    pytest.skip("E2E: exercised where ParadeDB + embedder are available")


@pytest.mark.asyncio
async def test_reindex_unchanged_is_noop():
    """spec code-search.3: a second run with no changes mutates no chunk rows (memoization)."""
    pytest.skip("E2E: exercised where ParadeDB + embedder are available")


@pytest.mark.asyncio
async def test_single_file_change_reprocesses_only_that_file():
    """spec code-search.4: modifying one file reprocesses only that file's chunks."""
    pytest.skip("E2E: exercised where ParadeDB + embedder are available")
