## Context

AI coding agents working on multi-layer codebases (Python + TypeScript + Postgres) lack structural context about how components relate across layers. The initial approach of generating three independent analysis reports (Python call graph, TS dependency graph, Postgres schema) treats each layer as an isolated silo. The primary user complaint — disconnected flows and inconsistent patterns — is only solved by a unified system map with cross-language linking edges.

This design addresses: canonical graph schema, tool selection (free tools only), cross-language linking strategy, confidence/evidence model, flow validation, CI integration, view generation, and integration with the existing Task()-based parallel execution model.

## Goals / Non-Goals

- Goals:
  - Define a single canonical graph schema that all per-language analyzers feed into
  - Generate machine-readable architecture artifacts consumable by Claude Code and other AI agents
  - Trace end-to-end flows across frontend, backend, and database layers via cross-language linking
  - Validate flow connectivity and test coverage alignment
  - Track confidence and evidence on every edge to keep the graph honest
  - Auto-generate C4-ish views (container, component, DB ERD, feature slice) from the canonical graph
  - Provide CI gates and baseline diffing for architectural drift detection
  - Identify safe parallel modification zones for Task() agents
  - Use only free/open-source tools suitable for private commercial repositories
  - Commit artifacts to track structural evolution

- Non-Goals:
  - Runtime profiling or dynamic analysis (static analysis only for now; dynamic instrumentation is a future enhancement)
  - Paid tooling (CodeQL requires GHAS at $30/user/month; Semgrep advanced dataflow requires paid tier)
  - Real-time incremental analysis (batch refresh is sufficient for the initial version)
  - Supporting languages beyond Python and TypeScript
  - Replacing existing linters or type checkers (mypy, ruff, ESLint)
  - Graph database storage (JSON files and SQLite are sufficient; property graph DB is a future option if query complexity grows)

## Decisions

### Decision 1: Canonical graph schema as the single source of truth

**Choice**: Define a normalized JSON schema with four top-level objects: `nodes[]`, `edges[]`, `entrypoints[]`, and `snapshots[]`. All per-language analyzers produce intermediate outputs that a compiler step normalizes into this schema.

**Schema outline**:
```json
{
  "snapshots": [{"generated_at": "ISO8601", "git_sha": "abc123", "tool_versions": {}}],
  "nodes": [{"id": "py:backend.api.routes.get_user", "kind": "function", "language": "python", "name": "get_user", "file": "backend/api/routes.py", "span": {"start": 42, "end": 58}, "tags": ["async", "entrypoint"], "signatures": {"decorators": ["@router.get('/api/users/{id}')"]}}],
  "edges": [{"from": "ts:UserProfile", "to": "py:backend.api.routes.get_user", "type": "api_call", "confidence": "high", "evidence": "string_match:/api/users/{id}"}],
  "entrypoints": [{"node_id": "py:backend.api.routes.get_user", "kind": "route", "method": "GET", "path": "/api/users/{id}"}]
}
```

**Alternatives considered**:
- Per-language outputs only: Three separate worlds that don't compose. Agents must mentally link them, defeating the purpose.
- Heavyweight ontology (RDF/OWL): Over-engineered for this use case.

**Rationale**: A single schema prevents the common failure mode where each tool emits something different and all effort goes to writing glue. The compiler step is the only place that needs to understand multiple formats. Downstream consumers (validators, view generators, agents) work with one consistent model.

### Decision 2: Custom AST analysis for Python, ts-morph for TypeScript

**Choice**: Use Python's `ast` stdlib for Python analysis and `ts-morph` (MIT, free) for TypeScript. Add dependency-cruiser (MIT, free) for TypeScript architectural rule enforcement. Do not depend on PyCG, CodeQL, or Semgrep's paid features.

**Tool availability assessment (free for private repos)**:

| Tool | License | Free for Private? | Status | Role in this system |
|------|---------|-------------------|--------|---------------------|
| Python `ast` stdlib | PSF | Yes | Maintained | Python call graph + metadata extraction |
| ts-morph | MIT | Yes | Active (v27) | TypeScript component/function analysis |
| dependency-cruiser | MIT | Yes | Active | TS architectural rule enforcement |
| Madge | MIT | Yes | Active | TS module-level dependency visualization |
| Semgrep OSS | MIT | Yes (intra-procedural only) | Active | Simple pattern-based guardrail rules |
| NetworkX | BSD | Yes | Active | Graph algorithms (components, paths, cycles) |
| CodeQL | Proprietary | **No** ($30/user/mo GHAS) | N/A | Excluded |
| PyCG | Apache 2.0 | Yes but **archived** | Unmaintained | Excluded |
| Semgrep Code | Proprietary | **No** (cross-file dataflow) | N/A | Excluded for advanced features |

**Rationale**: Custom AST analysis gives full control over extracted metadata (decorators, async markers, line numbers, framework-specific patterns). PyCG is archived and shouldn't be used. CodeQL is the gold standard for semantic analysis but costs $30/user/month for private repos. Semgrep OSS is useful for simple intra-procedural pattern rules but can't do cross-file dataflow without the paid tier.

**Keep custom scripts for**: framework-specific entrypoint detection (FastAPI routers, DI containers), output normalization into canonical schema, cross-language linking logic. Use dependency-cruiser for TS layer boundary enforcement. Use Semgrep OSS for simple pattern guardrails (e.g., "services must not import from API layer").

### Decision 3: Cross-language linking via convention-based matching with confidence/evidence

**Choice**: The graph compiler performs cross-language linking by matching:
- **Frontend → Backend**: API call URLs in TypeScript (fetch, axios, typed API client methods) matched to Python route decorator paths
- **Backend → Database**: ORM model usage, raw SQL strings, and query builder patterns in Python mapped to table/column names from the schema
- **Frontend → Database (indirect)**: Inferred via endpoint→service→query→table chain

Every edge carries `confidence` (high/medium/low) and `evidence` (e.g., `"string_match:/api/users"`, `"decorator:@router.get"`, `"ast:CallExpression"`, `"orm:User.query"`).

**Alternatives considered**:
- OpenTelemetry traces: Requires instrumented running application.
- Manual annotation: Requires developers to maintain flow maps.
- CodeQL dataflow: Best accuracy but not free for private repos.

**Rationale**: Convention-based matching works without runtime instrumentation and is sufficient for advisory context. The confidence/evidence model keeps the graph honest — planning agents can prefer high-confidence paths, and reviewers can spot "guessed" links. False positives are acceptable because the output is context for agents, not enforcement (enforcement comes from the separate validation step).

### Decision 4: Adaptive confidence threshold for summary inclusion

**Choice**: The summary includes all `high`-confidence flow traces, then adds `medium` traces until reaching a configurable limit (default: 50 flow entries), then adds `low` traces only if space remains. Full traces at all confidence levels remain in `architecture.graph.json`.

**Rationale**: A codebase with 5 traces should include all of them regardless of confidence. A codebase with 500 traces should prioritize high-confidence ones to keep the summary consumable. The threshold adapts to the volume rather than applying a fixed cutoff that may be too restrictive or too permissive.

### Decision 5: Commit artifacts to track evolution

**Choice**: Commit `.architecture/` artifacts to the repository. Summary files and the canonical graph are committed; large intermediate per-language outputs are optional (can be committed or generated as CI artifacts).

**Alternatives considered**:
- Gitignore and regenerate: Loses evolution history, unavailable in environments without analyzer dependencies.
- Commit only summaries: Loses the graph detail agents need for deep investigation.

**Rationale**: Architecture artifacts document structural evolution. Committing them provides: (1) consistent context across clones, (2) diffable history, (3) availability in CI and Claude Code web sessions where running analyzers may not be possible. Regeneration churn is mitigated by refreshing only before major feature work, not on every commit.

### Decision 6: Validation as reachability + test coverage alignment

**Choice**: The flow validator checks two things:
- **Reachability**: For each entrypoint, verify at least one downstream service + DB/side-effect dependency exists (or tag as "pure")
- **Test coverage alignment**: For each critical flow (configurable list), verify at least one test touches the flow's key edges

**Alternatives considered**:
- Full path coverage: Too strict; would require every possible path to be tested.
- No validation: Generates artifacts without actionable diagnostics.

**Rationale**: The validation loop closes the gap between "the graph says it's connected" and "tests actually execute the path." This directly addresses the user's stated problem of insufficient testing. The reachability check catches broken wiring (new endpoint with no service layer). The test alignment check catches undertested flows (endpoint works in dev but has no automated test).

### Decision 7: Auto-generated C4-ish views from the canonical graph

**Choice**: Generate Mermaid diagrams from the canonical graph at multiple zoom levels:
- **Container view**: Frontend, backend, DB, external services
- **Component view (backend)**: Backend packages/modules with dependency edges
- **Component view (frontend)**: Frontend modules with import edges
- **DB ERD**: Tables with FK relationships
- **Feature slice view**: Subgraph of nodes/edges touched by a specific feature (filtered by file list or path pattern)

**Rationale**: These are the artifacts humans and agents actually consume for planning. Raw JSON graphs are powerful for programmatic queries but hard to reason about visually. Mermaid is renderable in GitHub, VS Code, and most documentation systems without additional tooling.

### Decision 8: CI gates with baseline diffing

**Choice**: Provide `make architecture` (full generation), `make architecture:diff BASE_SHA=...` (compare to baseline), and diagnostics as an optional CI gate. Diff reports: new cycles introduced, new high-impact modules, routes added without tests, DB tables touched without migrations.

**Rationale**: Day-to-day operationalization is what makes the system useful beyond initial analysis. Without CI integration, artifacts become stale documentation. Baseline diffing catches architectural drift in the review process.

### Decision 9: Integrate into planning and validation skill workflows

**Choice**: The `plan-feature` skill SHALL consult architecture summaries and cross-layer flows as planning context. The `implement-feature` and `validate-feature` skills SHALL run the flow validator and include diagnostics in their reports. This is in-scope (not deferred).

**Rationale**: The entire purpose of generating architecture artifacts is to improve planning accuracy and implementation completeness. The skill modifications are lightweight (adding artifact consultation steps to existing skill prompts).

### Decision 10: NetworkX for graph algorithms, with optional SQLite for queryable storage

**Choice**: Use NetworkX for in-memory graph operations (connected components, path finding, cycle detection). Optionally emit a SQLite database for nodes/edges to support ad-hoc queries ("show all flows that write table X", "what breaks if I change module Z?").

**Rationale**: NetworkX is the standard Python graph library and sufficient for the graph sizes involved. SQLite is optional but provides real querying capability that JSON traversal doesn't, without requiring a separate database server.

## Risks / Trade-offs

- **False positives in cross-language linking** — Convention-based matching will produce false matches (e.g., a URL string in TypeScript that happens to match a route but isn't actually called). Mitigation: confidence/evidence model makes every edge auditable; summary uses adaptive threshold to prioritize high-confidence traces.

- **Stale artifacts** — Committed artifacts can drift from code. Mitigation: `generated_at` + `git_sha` in every artifact; `make architecture:diff` in CI catches drift; refresh before major feature work.

- **Migration file parsing limitations** — SQL migration files may use complex PL/pgSQL or vendor-specific syntax. Mitigation: Start with CREATE TABLE/ALTER TABLE/CREATE INDEX parsing; skip unparseable statements with warnings; live DB mode available as fallback.

- **Large codebase performance** — AST analysis of thousands of files could be slow. Mitigation: `--include`/`--exclude` glob patterns; parallelize file parsing; ts-morph lazy loading.

- **Custom AST limitations vs. CodeQL** — Custom AST walkers miss dynamic dispatch, reflection, DI containers, and framework magic that CodeQL's semantic analysis would catch. Mitigation: confidence/evidence model explicitly marks these as lower-confidence edges; framework-specific detection scripts handle common patterns (FastAPI routers, SQLAlchemy models); CodeQL can be added later if GHAS becomes available.

- **Semgrep OSS single-function scope** — Semgrep OSS only does intra-procedural analysis, so it can't enforce rules that span multiple files. Mitigation: Use Semgrep OSS only for simple pattern rules; use dependency-cruiser for module-level architectural rules in TypeScript; use the canonical graph + NetworkX for cross-module analysis in Python.
