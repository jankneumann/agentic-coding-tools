# Proposal: Clean Up verification_gateway/

## Change ID
`cleanup-verification-gateway`

## Summary

Remove the `verification_gateway/` prototype directory and rewrite its HTTP API
functionality into `src/coordination_api.py` using the established service layer
pattern. Drop newsletter-specific code, the SDK client class, and the inline
Supabase client. Delete the entire `verification_gateway/` directory.

## Motivation

The `verification_gateway/` directory is a parallel prototype that evolved
independently from the main `src/` codebase. It has several problems:

- **Not in CI**: No linting, type-checking, or tests run against it
- **Not in wheel build**: `pyproject.toml` only packages `src/`
- **Duplicate code**: `coordination_mcp.py` is a strict subset of the main one
- **Inline DB calls**: Uses raw `httpx` instead of the service layer
- **Newsletter code**: Contains domain-specific newsletter processing logic
- **Outdated deps**: `requirements.txt` diverges from `pyproject.toml`
- **Hardcoded config**: Environment variables read inline, not via `Config`

## Approach

1. Add `ApiConfig` dataclass to `src/config.py`
2. Create `src/coordination_api.py` using service singletons (locks, memory,
   work queue, guardrails, profiles, audit, policy engine)
3. Rewrite `tests/test_coordination_api.py` to import from `src/`
4. Add `coordination-api` entry point to `pyproject.toml`
5. Update `agent-coordinator/CLAUDE.md`
6. Delete `verification_gateway/`

## What is NOT in scope

- **Newsletter code**: Dropped entirely
- **gateway.py verification routing**: Newsletter-specific, not ported
- **SDK client class**: Convenience wrapper, not needed
- **Working memory / procedural memory HTTP endpoints**: Simplified to match
  the service layer's `remember()` and `recall()` interface

## Affected specs

- `agent-coordinator` spec: HTTP API Interface requirement updated

## Risks

- Low: The verification_gateway code is not used in CI or production
- The new API is a clean rewrite, not a migration
