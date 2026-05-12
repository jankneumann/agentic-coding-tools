# Agentic Code Navigation & Architecture Intelligence Roadmap

## Context
Coding agents now generate code faster than humans can interpret via linear diffs. Conventional PR review and static docs are insufficient for understanding architectural impact across modules, APIs, tests, services, and repositories.

We need an interactive, multi-scale, temporal UX that combines semantic and graph-native navigation, from high-level architecture down to exact lines, commits, and machine artifacts.

## Existing Assets to Reuse
- Reuse learnings from `agentic-content-analyzer` where FalkorDB and Graphiti are already used for semantic + temporal graph search.
- Reuse existing skill-generated artifacts (OpenSpec YAML/JSON, validation evidence, roadmap outputs) as first-class graph entities.

## Vision
Build an Architectural Time Navigator that augments IDEs with:
1. Topology-first views over code, tests, docs, services, and artifacts.
2. Time-travel across commits/PRs/releases to visualize graph deltas.
3. AI-assisted interrogation over grounded graph evidence.
4. Seamless transitions from architecture map to source lines and docs.

## Capability Areas

### C1. Unified Code Knowledge Graph
- Ingest multi-language repositories into a shared schema.
- Model entities: repo, service, module, file, symbol, test, endpoint, DB object, docs, build artifact, OpenSpec artifact, CI run, git commit.
- Model relations: imports, calls, ownership, test coverage, API dependencies, deployment associations, temporal transitions.

### C2. Temporal & Versioned Architecture
- Snapshot graph by commit and PR.
- Compute graph deltas (added/removed nodes/edges, changed centrality/hotspots).
- Support sliding windows for churn/risk trends.

### C3. Interactive UX Layers
- High-level service/module map with clustering.
- Mid-level dependency/call topology.
- Low-level symbol and line navigation with provenance.
- Switchable lenses: structure, ownership, risk, incident, change-set.

### C4. Review-Centric Workflows
- PR architecture impact summary panel.
- "What changed structurally?" and "What could this break?" queries.
- Overlay failing tests and CI checks onto impacted subgraph.

### C5. AI-Grounded Navigation
- Natural language graph queries with deterministic graph query execution.
- Answer cards with evidence links to nodes/edges, files, lines, commits.
- Confidence levels by evidence type (static inference, runtime observation, historical correlation).

### C6. Runtime and Incident Correlation
- Ingest traces/log-derived service interactions.
- Connect incidents/postmortems to architecture regions.
- Surface runtime-vs-static discrepancy hotspots.

### C7. Platform & Extensibility
- IDE extension + optional web canvas.
- APIs for external tools and agent skills.
- Export/import graph packs for offline or per-branch analysis.

## Constraints
- Must prioritize incremental adoption and low friction in existing workflows.
- Must preserve provenance and explainability for every AI-generated claim.
- Must remain performant on large mono-repos and multi-repo portfolios.
- Must support privacy controls for source and metadata.
- Must be compatible with FalkorDB + Graphiti patterns already validated.

## Milestones

### Phase 1: Foundations
- Define schema and ingestion pipeline.
- Build baseline graph snapshots and deltas.
- Deliver read-only architecture explorer MVP.

### Phase 2: Review Intelligence
- Add PR diff overlays and impact radius.
- Add test/CI overlay and structural regression alerts.
- Add ownership/churn/risk scoring.

### Phase 3: AI Query & Guidance
- Add natural language interrogation and evidence-backed answer cards.
- Add task-oriented flows (onboarding, incident triage, refactor planning).
- Add recommendation engine for reviewers.

### Phase 4: Runtime Convergence
- Fuse runtime traces with static graph.
- Add discrepancy detection and reliability guidance.
- Enable architecture fitness checks in CI.

### Phase 5: Scale & Ecosystem
- Multi-repo federation.
- Plugin framework for custom analyzers.
- Benchmarks and adoption telemetry.

## Prototype Decision Track
Before committing to final architecture, dispatch competing prototypes exploring:
- A: FalkorDB-native graph pipeline + lightweight IDE panel.
- B: Hybrid graph store + web-first visualization + IDE deep links.
- C: Incremental file/symbol indexer with aggressive local-first caching.

Evaluate on ingestion speed, query latency, graph fidelity, UX comprehension gains, and integration effort.
