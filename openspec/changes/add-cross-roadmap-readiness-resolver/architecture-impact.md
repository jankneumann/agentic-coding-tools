# Architecture Impact: Add Cross-Roadmap Readiness Resolver

**Status**: degraded advisory check; direct architecture review passed

The required architecture refresh `--ensure` command was attempted before planning. It could not produce a current graph because this repository does not contain the configured `src/` and `web/` roots; no committed architecture artifacts were modified or promoted.

Direct source review verified the bounded runtime flow:

1. `roadmap.yaml` and optional sibling `checkpoint.json` are the only resolver inputs.
2. `roadmap-runtime/scripts/resolve_readiness.py` validates and reconciles them, then calls the sole admission helper in `readiness.py`.
3. `autopilot-roadmap` imports that helper directly; `supervise` groups resolver output without re-evaluating readiness.
4. The CLI emits JSON only and performs no writes or network calls.

The package changes no dependency direction, service boundary, database, network API, deployment unit, or persistent schema. AST ownership tests, 465 focused tests, Ruff, and two-vendor implementation review found no broken architectural flow.
