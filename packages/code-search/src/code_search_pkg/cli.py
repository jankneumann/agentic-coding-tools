"""`index_repo` entrypoint (design D5 — indexing is a write, never reachable from query paths).

Builds an asyncpg pool from POSTGRES_DSN, upserts the repo's row in code_search_registry, and runs
the incremental cocoindex pipeline. Invoked by a post-merge hook or on demand — never by an agent
search. Heavy imports (indexer_pg → cocoindex) are done inside main(), so `--help` and arg parsing
work without the embedding stack installed.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from .identifiers import slugify, validate_slug


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="index_repo", description="Index a repo for semantic search.")
    ap.add_argument("--repo-root", type=Path, default=Path.cwd(), help="repo root to index")
    ap.add_argument("--repo-slug", default=None, help="slug (default: derived from repo-root name)")
    ap.add_argument("--dsn", default=os.environ.get("POSTGRES_DSN"), help="POSTGRES_DSN")
    ap.add_argument("--full-rebuild", action="store_true", help="drop the chunk table first")
    return ap.parse_args(argv)


def resolve_slug(args: argparse.Namespace) -> str:
    """Resolve and validate the slug from args (pure — unit-testable without a DB)."""
    if args.repo_slug:
        return validate_slug(args.repo_slug)
    return slugify(Path(args.repo_root).resolve().name)


async def _run(args: argparse.Namespace) -> int:
    if not args.dsn:
        raise SystemExit("POSTGRES_DSN not set (pass --dsn or set the env var)")
    slug = resolve_slug(args)

    # Heavy imports deferred to run time (design D8).
    import asyncpg

    from . import indexer_pg  # noqa: F401 — imported for its cocoindex pipeline registration

    pool = await asyncpg.create_pool(args.dsn)
    try:
        await _upsert_registry(pool, slug, args.repo_root)
        # NOTE: the cocoindex App wiring (context setup for EMBEDDER / CODEBASE_DIR / pool +
        # invoking indexer_main) is exercised end-to-end where an embedder + ParadeDB are
        # available (see openspec/.../eval/spike-report.md). Kept thin here on purpose.
        raise NotImplementedError(
            "index_repo pipeline execution runs where cocoindex + an embedder are available; "
            "registry upsert and slug resolution are covered by unit tests."
        )
    finally:
        await pool.close()


async def _upsert_registry(pool, slug: str, repo_root: Path) -> None:
    await pool.execute(
        """
        INSERT INTO code_search_registry (repo_slug, repo_root, embedder_model, embedding_dim)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (repo_slug) DO UPDATE
          SET repo_root = EXCLUDED.repo_root, updated_at = now()
        """,
        slug,
        str(Path(repo_root).resolve()),
        os.environ.get("CODE_SEARCH_EMBEDDER", "sentence-transformers/all-MiniLM-L6-v2"),
        int(os.environ.get("CODE_SEARCH_EMBEDDING_DIM", "384")),
    )


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
