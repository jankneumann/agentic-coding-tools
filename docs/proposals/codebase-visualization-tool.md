# Interactive Codebase Visualization & Navigation Tool

**Roadmap ID**: codeviz
**Status**: Draft
**Created**: 2026-05-12

## Context and Goals

Coding agents in this repo (Claude, Codex, Jules) generate code faster than humans can read it as conventional diffs. Markdown documentation helps but reads linearly; modern codebases form a web of modules, services, tests, OpenSpec changes, and machine artifacts that cannot be navigated through a flat file tree. We already generate a rich structural substrate — `docs/architecture-analysis/architecture.graph.json` (1,471 nodes, 901 edges), `parallel_zones.json`, `comment_insights.json`, `pattern_insights.json`, `architecture.diagnostics.json`, plus per-language analyses and Mermaid views — but we lack an interactive surface that lets a reviewer (human or agent) move fluidly across scales (repo → service → module → file → symbol → line), across versions (commit history), and across artifact types (code ↔ proposal ↔ test ↔ finding).

This proposal specifies a local-first interactive visualization and AI-augmented navigation tool that consumes the existing architecture artifacts, layers a temporal/queryable index on top via **FalkorDB** (a Cypher-over-Redis graph store) modeled with patterns reused from `jankneumann/agentic-content-analyzer`'s **Graphiti** integration (bi-temporal knowledge-graph episodes, entity/relationship typing, embedding-based retrieval), and exposes a single-page web UI for graph navigation, diff overlay, temporal scrubbing, and AI chat anchored to graph selections.

## Why

VS Code and other editors are file-tree + symbol-driven and stop at the function level inside a single repo and a single point in time. They have no concept of (a) architectural zones / layers, (b) cross-PR blast radius over a dependency graph, (c) temporal navigation of subsystems across commits, (d) cross-artifact linkage (proposal ↔ symbol ↔ test ↔ finding), or (e) AI grounded in an architectural slice rather than open editor tabs. Copilot Chat sees open files; an agent-friendly visualization must see *architectural neighborhoods*.

We already have most of the substrate. The cost-to-value of building the UX layer is favorable because (i) we are not greenfielding extraction, (ii) FalkorDB and Graphiti patterns are already validated in our content-analyzer codebase, and (iii) our agents will be heavy users — a graph surface with a documented action API benefits humans and agents simultaneously.

## Guiding Principles

- **JSON files remain canonical** and committed to git. FalkorDB is a derived index, rebuilt from JSON on demand. Diffability of architecture state in PRs is preserved.
- **Local-first, multi-repo from day one.** Single-operator local SPA + local FalkorDB container; per-repo namespacing baked into the schema so federation is not a later refactor.
- **Stability beats beauty.** Graph layout must be deterministic and stable across refreshes; nodes do not migrate when the graph changes unless their structural position changes. Cluster anchors come from `parallel_zones.json`.
- **AI is anchored to graph selection.** The chat panel auto-attaches the selected subgraph (nodes, edges, source slices, related artifacts) as context rather than dumping the whole repo into a vector store.
- **Reuse the content-analyzer stack.** FalkorDB + Graphiti-style temporal episodes; do not invent a new graph database, query language, or temporal model.
- **2D first.** Cytoscape.js is the primary render target. 3D (three.js / CodeCity metaphor) is an optional later view, never the default.
- **No vendor lock-in for the UI.** All data is fetched via a documented HTTP API the SPA consumes; agents and CLI tools can hit the same endpoints.

## Constraints

- The tool MUST run fully offline (no required cloud calls) for the primary single-operator workflow.
- The graph store MUST be FalkorDB (Cypher-over-Redis), reusing operational learnings and embedding patterns from `agentic-content-analyzer`.
- JSON snapshot artifacts under `docs/architecture-analysis/` MUST remain the canonical, committed source of truth. FalkorDB MUST be rebuildable from them deterministically.
- Multi-repo support MUST be designed in from the first ingestion implementation (per-repo namespace label on every node + every edge), even if only one repo is initially indexed.
- The AI panel MUST operate on a retrieved subgraph + source slices, never on the full repository corpus.
- Graph layout MUST be stable: a node's screen position MUST NOT change unless its graph-theoretic position changes.
- Every visualization MUST be reachable via a shareable URL encoding the lens (filter set + zoom + time + selection).

### Artifact temporal model

Three classes of machine artifact exist in this repo and the tool MUST treat them differently:

- **Snapshot artifacts** (e.g. `architecture.graph.json`, `parallel_zones.json`, `*_analysis.json`) are *derived* from current code state. They are regenerable and overwritten in place on refresh. Their temporal history lives in **git**, not on disk. They MUST carry a mandatory header `{ schema_version, generated_at, git_sha, generator }`. FalkorDB ingestion stamps `valid_from_commit = git_sha` on derived nodes/edges.
- **Event/run artifacts** (e.g. gen-eval reports, validate-feature phase outputs, security-review reports, review findings, merge/session logs) record *what happened at a moment*. They are NOT regenerable and MUST accumulate (one file per run, never overwritten). They MUST be stored under dated paths (`<artifact-dir>/<YYYY-MM-DD>/<run-id>.json`) with the same mandatory header plus a `run_id` and `event_kind`. Each becomes a temporal node in FalkorDB.
- **Linkage artifacts** (OpenSpec proposals, tasks, design docs, configuration YAML) are authored, versioned by git like code, and require no special temporal treatment.

The tool MUST NOT switch snapshot artifacts to on-disk append-only storage — that duplicates git's job and bloats the repo. The tool MUST add a diff artifact alongside each snapshot refresh so FalkorDB can apply incremental updates cheaply.

## Rejected Alternatives

A parallel Codex-authored proposal (PR #155, `docs/proposals/agentic-code-nav-roadmap.md`) framed prototype selection at the *architecture* level rather than the *rendering* level. Those alternatives were considered and explicitly rejected before this proposal was finalized:

- **A. FalkorDB-native pipeline (no JSON canonical layer).** FalkorDB owns the architecture state directly; JSON files are not generated. *Rejected because* it loses git-native diffability — reviewers can no longer read PR diffs of `architecture.graph.json` and parallel-zone changes — and it forces a hard dependency on a running FalkorDB instance for every refresh, breaking the offline-by-default invariant.
- **C. Local-cache-first incremental symbol indexer (no graph store).** A file/symbol-level index with aggressive local caching, no graph database, no Cypher. *Rejected because* it cannot express the bi-temporal and cross-artifact queries that drive the AI-anchored navigation, blast-radius, and lens-switching capabilities. Reimplementing temporal episodes on top of a flat index is exactly the work Graphiti already does.

The chosen architecture (Codex's option B, refined) is **JSON canonical on disk + FalkorDB as a derived cache/index + web SPA front end + multi-repo namespacing from day one**. The Phase 0 capabilities encode this decision: snapshot artifacts remain committed, ingestion is idempotent, and FalkorDB is rebuildable from JSON at any time.

IDE-extension-as-primary-delivery (Codex's preferred surface) was also rejected for v1. A web SPA was chosen because (i) it works uniformly across editors and review tools, (ii) it supports headless agent use through the Action API, and (iii) it can be deep-linked from GitHub PR comments. An IDE extension remains a viable follow-up phase but is out of v1 scope.

## Phase 0 — Foundations and Substrate

### Capability: Mandatory artifact header schema

Define and enforce a common header on every generated machine artifact under `docs/architecture-analysis/`, `docs/security-review/`, `docs/merge-logs/`, gen-eval reports, validate-feature outputs, and review findings. Header fields: `schema_version`, `generated_at` (ISO-8601 UTC), `git_sha`, `generator` (skill or script name + version), and (for event artifacts) `run_id` and `event_kind`. Provide a Python helper `skills/shared/artifact_header.py` that writes and validates the header. Add a CI lint that fails on missing or malformed headers in artifacts touched by a PR.

Acceptance outcomes:
- All current snapshot artifacts MUST be backfilled with the header on first refresh.
- A CI lint MUST flag any newly-introduced artifact lacking the header.
- The helper MUST be reused by at least three existing skills (`refresh-architecture`, `validate-feature`, `security-review`).
- Header schema MUST be documented at `docs/codeviz/artifact-header.md`.

### Capability: Artifact classification and retention policy

Document and enforce three artifact classes (snapshot, event, linkage). Snapshots remain disposable on disk and committed in place; event artifacts MUST be written to `<dir>/<YYYY-MM-DD>/<run-id>.json` and never overwritten; linkage artifacts follow normal source-versioning. Update `docs/architecture-artifacts.md` with the classification table and migrate any currently-clobbered event artifacts (notably security-review outputs and validate-feature phase results) to dated paths. Provide a small inventory CLI (`codeviz-artifact-inventory`) that scans the repo and reports the class of each artifact directory.

Acceptance outcomes:
- A classification table MUST be present in `docs/architecture-artifacts.md` listing every generated artifact and its class.
- All event artifacts MUST be written under `<dir>/<YYYY-MM-DD>/<run-id>.json`.
- A migration script MUST move existing event artifacts into dated paths idempotently.
- `codeviz-artifact-inventory` MUST output JSON conforming to a checked-in schema.

### Capability: Architecture fitness CI checks

Extend the existing `make architecture-validate` target with a fitness-rule engine that enforces structural invariants on every PR: no new cross-layer flows beyond an allowlist, no new disconnected endpoints, no removal of `IMPLEMENTS_PROPOSAL` edges for active OpenSpec changes, no new TODO/FIXME markers in nodes flagged as `critical_path`. Rules expressed as YAML in `architecture-fitness.yaml`. Fitness violations are emitted as event artifacts (carrying the mandatory header) so they participate in the temporal layer.

Acceptance outcomes:
- A fitness-rule engine MUST be implemented and invokable via `make architecture-validate --fitness`.
- At least four rules MUST ship in `architecture-fitness.yaml` with documented rationale.
- A CI step MUST fail the build on fitness violations and post a structured comment to the PR.
- Fitness reports MUST be written as event artifacts under `docs/architecture-analysis/fitness/<YYYY-MM-DD>/<run-id>.json`.

### Capability: FalkorDB local container + bootstrap script

Package a docker-compose service (or `docker run` wrapper) for FalkorDB pinned to a known version, with a host-mounted volume for persistence. Provide `make codeviz-up`, `make codeviz-down`, `make codeviz-reset` targets. Document required ports, memory budget, and reset semantics. Reuses the same compose pattern established for the coordinator Postgres container.

Acceptance outcomes:
- `make codeviz-up` MUST start a healthy FalkorDB instance reachable on a configurable port within 10 seconds.
- `make codeviz-down` MUST stop the container cleanly without data loss.
- `make codeviz-reset` MUST wipe persisted state and reinitialize.
- Compose file MUST be checked in under `docker/codeviz/` and referenced from `docs/codeviz/setup.md`.

### Capability: Temporal graph schema and Cypher migrations

Define the FalkorDB schema as a set of versioned Cypher migration files. Node labels include `Repo`, `Service`, `Module`, `File`, `Symbol` (function/class/method), `Test`, `Endpoint`, `Table`, `Proposal`, `Finding`, `Commit`. Edge types include `CONTAINS`, `CALLS`, `IMPORTS`, `WRITES_TO`, `READS_FROM`, `TESTS`, `IMPLEMENTS_PROPOSAL`, `FLAGS`, `INTRODUCED_IN`, `REMOVED_IN`. Every node and edge carries a `repo_id` namespace property and bi-temporal validity (`valid_from_commit`, `valid_to_commit`) reusing the Graphiti episode pattern from `agentic-content-analyzer`. Includes constraints/indexes on `(repo_id, node_id)` and full-text indexes on symbol names.

Acceptance outcomes:
- Schema MUST be expressed as numbered Cypher migration files under `codeviz/schema/`.
- A migration runner MUST apply migrations idempotently and record applied versions.
- All node and edge types MUST be documented in `docs/codeviz/schema.md` with examples.
- Bi-temporal validity columns MUST be present on every edge.

### Capability: Ingestion pipeline — JSON snapshots to FalkorDB

A Python ingestion script that reads `architecture.graph.json`, `parallel_zones.json`, `comment_insights.json`, `pattern_insights.json`, `architecture.diagnostics.json`, `python_analysis.json`, `ts_analysis.json`, and `postgres_analysis.json` and writes them into FalkorDB under a given `repo_id`. Uses MERGE semantics so re-ingestion is idempotent. Stamps nodes with `valid_from_commit` from the snapshot's `git_sha`. Supports `--repo-id`, `--snapshot-dir`, `--commit-sha`, `--full-rebuild`. Depends on the schema migration capability.

Acceptance outcomes:
- Full ingestion of the current `docs/architecture-analysis/` snapshot MUST complete in under 60 seconds on a developer laptop.
- Re-ingesting the same snapshot MUST be a no-op (idempotent).
- A second ingestion with a different `--commit-sha` MUST preserve prior temporal validity and only update edges that changed.
- Ingestion logs MUST report node/edge counts created, updated, deprecated per type.

### Capability: HTTP API server (FastAPI) over FalkorDB

A FastAPI service exposing read endpoints — `/repos`, `/repos/{id}/graph?filter=...`, `/repos/{id}/symbols/{symbol_id}`, `/repos/{id}/subgraph?seed=...&hops=N`, `/repos/{id}/at/{commit_sha}/subgraph?...`, `/cypher` (admin-only) — plus a streaming `/ai/query` endpoint used by the AI panel. CORS configured for the local SPA dev origin. Read-only by default. Reuses FastAPI patterns from `agent-coordinator/`. Depends on the ingestion pipeline.

Acceptance outcomes:
- Subgraph queries with `hops <= 3` MUST return in under 100 ms at p95 on a 2k-node graph.
- OpenAPI schema MUST be auto-generated and committed.
- `/cypher` MUST be disabled by default and require an explicit env flag.
- Server MUST refuse cross-repo queries unless `repo_id` is explicitly specified.

## Phase 1 — Single-Page Web App Shell

### Capability: SPA render scaffold (rendering choice via prototype phase)

A TypeScript + Vite SPA. The primary canvas implementation is selected via the `/prototype-feature` skill, which produces competing working skeletons across four candidate render layers — Cytoscape.js 2D (fcose layout), Sigma.js + graphology (WebGL), three.js CodeCity 3D, and Observable Framework + d3 — each fed the same subgraph payload from a stubbed HTTP API. Variants are scored on initial-render performance, layout stability, interaction richness (selection, lasso, semantic zoom), and developer ergonomics; the winning variant is promoted to production and the others retained as feature-flagged experimental views. Semantic coloring by layer (Python / TS / SQL / config / docs), hover tooltips, click selection, lasso multi-select, and pan/zoom with semantic zoom levels (repo → service → module → file → symbol) are required of the production variant. Depends on the HTTP API server.

Acceptance outcomes:
- Four prototype skeletons MUST exist, each rendering the same 1,471-node fixture from a stub API.
- A scoring matrix MUST be checked in at `openspec/roadmaps/codeviz/render-comparison.md` covering performance, stability, interactions, and ergonomics.
- The selected production variant MUST render the full 1,471-node graph in under 2 seconds on a developer laptop.
- Production layout MUST be deterministic across page reloads given the same data (seeded RNG or persisted positions).
- Selection state MUST be reflected in the URL.
- Zoom level changes MUST progressively reveal/hide node detail (label, type badges).

### Capability: Source viewer panel with deep links

A right-side panel that opens when a node is selected, showing the source file with the relevant symbol highlighted. Includes "Open in VS Code" deep link (`vscode://file/...`) and "View on GitHub" link. Syntax highlighting via Shiki. Read-only.

Acceptance outcomes:
- Selecting a Symbol node MUST display its source within 300 ms.
- "Open in VS Code" MUST launch the user's editor at the correct file:line.
- Files larger than 1 MB MUST stream incrementally.

### Capability: Filter and query pane

Left-side pane with structured filters — repo, layer, node type, has-TODOs, has-security-findings, in-parallel-zone, modified-since-commit. A free-text Cypher query box (advanced mode) that executes against the API. Saved filter presets persisted in localStorage and encoded in URLs.

Acceptance outcomes:
- Each filter change MUST update the canvas in under 200 ms for the local graph.
- Cypher queries MUST be syntax-validated client-side before submission.
- A saved filter MUST be restorable from its URL alone.

### Capability: Lens-switching framework

A single switching control on the SPA that exposes named lenses, each a saved combination of coloring, edge weighting, node filtering, and overlay activation. Built-in lenses: **structure** (default layer-colored), **diff** (commit-range delta), **ownership** (CODEOWNERS-derived), **risk** (churn × fan-in × findings), **incident** (recent runtime/incident markers), **change-set** (touched-by current PR or OpenSpec change). Lenses MUST compose with filters: a lens defines defaults, the filter pane can override. Lens choice MUST be encoded in the URL so saved views round-trip.

This capability supersedes ad-hoc overlays. Existing capabilities — diff overlay, security finding overlay, test-coverage edges, parallel-zone clustering — register *as* lenses against the same framework rather than as bespoke renderers. Depends on the SPA render scaffold.

Acceptance outcomes:
- A lens registry MUST expose at least six built-in lenses on first load.
- Switching lenses MUST update the canvas in under 200 ms without re-fetching from the API for state already cached.
- A lens MUST be expressible declaratively (YAML schema) so new lenses can be added without code changes for the common cases.
- Lens choice MUST be URL-encoded and survive page reload.

## Phase 2 — Diff and Temporal Navigation

### Capability: Diff-graph artifact generator

A script that diffs two `architecture.graph.json` snapshots (by commit SHA) and emits `diff-graph.json` containing `nodes_added`, `nodes_removed`, `nodes_modified`, `edges_added`, `edges_removed`, `parallel_zones_touched`, `blast_radius_summary`. Invoked by `make architecture-diff` (already partially exists) and by a Git hook on push. Output is committed under `docs/architecture-analysis/diffs/<commit-sha>.json`.

Acceptance outcomes:
- Diff between two snapshots of the current repo MUST complete in under 5 seconds.
- Output JSON MUST conform to a checked-in schema.
- Blast-radius summary MUST report transitive callers up to depth 3.
- A no-op commit (no graph change) MUST emit an empty-but-valid diff.

### Capability: Diff overlay rendering in SPA

The SPA accepts a `?diff=<commit-sha>` URL parameter and renders the diff over the current graph — color-codes nodes by change kind (added / removed / modified / touched-by-callers), highlights affected edges, and exposes a "blast radius" Sankey panel showing transitive impact across parallel zones. Depends on diff-graph artifact generator.

Acceptance outcomes:
- Loading a diff over a 1.5k-node graph MUST add no more than 500 ms to initial render.
- The Sankey panel MUST be interactive (click a band to filter the canvas).
- Removed nodes MUST remain visible at low opacity until explicitly dismissed.

### Capability: Temporal snapshot store and scrubber

Persist multiple snapshots in FalkorDB keyed by `valid_from_commit` / `valid_to_commit`. The SPA exposes a horizontal slider scrubber across known commits; scrubbing updates the rendered graph to the state at that commit. A "play" button animates through recent history at a configurable speed.

Acceptance outcomes:
- Scrubbing between adjacent commits MUST transition in under 300 ms.
- Layout positions MUST stay stable across temporal transitions (nodes persisted across commits keep their position).
- The scrubber MUST display commit metadata (author, message, SHA) on hover.

## Phase 3 — AI-Anchored Navigation

### Capability: Subgraph retrieval and context assembly

A retrieval service that, given a selection (one or more node IDs), expands to a configurable N-hop neighborhood, fetches source slices for each Symbol in the neighborhood, attaches related artifacts (OpenSpec proposals, comment insights, security findings), and returns a structured context bundle bounded by a token budget. Reuses the Graphiti-style embedding patterns from `agentic-content-analyzer` for similarity-based expansion when structural hops are insufficient. Depends on the HTTP API server.

Acceptance outcomes:
- Context assembly for a 1-hop neighborhood of a single symbol MUST complete in under 200 ms.
- Bundles MUST not exceed a configurable token budget (default 32k).
- Each context item MUST carry provenance (node ID, file path, line range, commit SHA).
- Similarity expansion MUST be opt-in via a query parameter.

### Capability: AI chat panel with selection-anchored context

A chat UI in the SPA that consumes the streaming `/ai/query` endpoint. Selected node(s) auto-attach as context. The model can emit Cypher queries against FalkorDB (tool-use), receive subgraph results, and cite specific nodes and source lines in responses. Citations are clickable and select the cited node on the canvas. Supports follow-up questions over the same anchored context.

Every citation MUST be tagged with an `evidence_kind` in `{static, runtime, historical}` so the UI can surface confidence: **static** evidence comes from the structural graph (CALLS/IMPORTS/etc.), **runtime** evidence comes from `INVOKES_AT_RUNTIME` edges produced by the runtime-correlation ingester, and **historical** evidence comes from commit-history or incident records. The model MUST NOT mix evidence kinds in a single claim without explicitly labeling each.

Acceptance outcomes:
- First token MUST stream within 1 second of submission for a typical query.
- Citations in responses MUST be clickable and select/navigate the canvas.
- Every citation MUST carry a visible `evidence_kind` badge (`static` / `runtime` / `historical`).
- The model MUST refuse to make a claim of kind X if no edges of kind X exist in the retrieved subgraph.
- The model MUST refuse to answer questions whose context exceeds the budget without confirmation.
- A "show me the Cypher" toggle MUST reveal any tool-call queries the model executed.

### Capability: Action API for agents

Document and expose a stable subset of SPA actions (select, filter, zoom, query, scrub) as REST endpoints so external agents (Claude Code, Codex) can drive the visualization headlessly and capture screenshots or subgraph snapshots for reports. Reuses the FastAPI service from Phase 0.

Acceptance outcomes:
- Action API MUST be documented in `docs/codeviz/agent-api.md` with example invocations.
- Headless screenshots MUST be reproducible from a URL alone.
- A sample skill (`codeviz-snapshot`) MUST demonstrate end-to-end agent use.

## Phase 4 — Multi-Repo and Cross-Artifact Linkage

### Capability: Multi-repo ingestion and federated views

Extend ingestion to consume snapshots from multiple repos, each with a distinct `repo_id`. Add cross-repo edges discovered via shared API contracts, shared schemas, or explicit repo-link manifests (`codeviz.links.yaml`). The SPA gains a repo-picker and a "federated" view rendering multiple repos as compound clusters.

Acceptance outcomes:
- Ingesting two repos MUST namespace cleanly with no node-ID collisions.
- A federated view of two repos with a shared API edge MUST render the connecting edge.
- A repo can be unloaded without affecting other repos in the index.

### Capability: OpenSpec proposal linkage

Index every OpenSpec change directory (`openspec/changes/<id>/`) as a `Proposal` node, with `IMPLEMENTS_PROPOSAL` edges to the symbols/files touched by its tasks. Source: the existing `comment_insights.json` node-marker map, plus task-list parsing.

Acceptance outcomes:
- Every active OpenSpec change MUST appear as a `Proposal` node.
- Each proposal node MUST have at least one outgoing edge if its tasks reference any committed file.
- The SPA MUST surface "related proposals" in the source viewer panel.

### Capability: Test ↔ symbol linkage

Add edges connecting `Test` nodes to the `Symbol` nodes they exercise, inferred from import graphs and naming conventions in `python_analysis.json` and `ts_analysis.json`. Surface "tested by" in the source viewer.

Acceptance outcomes:
- Coverage rate of `TESTS` edges across all Symbol nodes MUST be reported in `architecture.diagnostics.json`.
- A symbol with no `TESTS` edge MUST be visually flagged on the canvas.

### Capability: Security finding overlay

Surface findings from `pattern_insights.json` and the security-review skill output as `Finding` nodes with `FLAGS` edges to the affected symbol. Color-code on the canvas; expose a "show findings only" filter.

Acceptance outcomes:
- Every security finding currently in `pattern_insights.json` MUST appear as a `Finding` node.
- A click on a Finding node MUST display the original finding text and severity.

### Capability: Runtime and incident correlation

Ingest runtime evidence and link it to the static architecture graph: (a) OpenTelemetry traces (or compatible JSON dumps) producing `INVOKES_AT_RUNTIME` edges between Service/Endpoint nodes, (b) an `incidents.yaml` file (or a connector to an external incident store) producing `Incident` nodes with `AFFECTS` edges to the implicated symbols/services. Surface "runtime-vs-static discrepancy" warnings: edges observed at runtime with no static counterpart, and vice versa. Powers the **incident** lens and feeds the AI panel with runtime evidence for confidence-tagged answers.

Acceptance outcomes:
- An ingester MUST consume at least one OpenTelemetry trace format and produce `INVOKES_AT_RUNTIME` edges.
- An ingester MUST consume an `incidents.yaml` schema (checked in) and produce `Incident` nodes with `AFFECTS` edges.
- Discrepancy detection (runtime edge with no static counterpart) MUST be queryable via the HTTP API.
- Runtime evidence MUST be tagged with `evidence_kind=runtime` for use by the AI chat panel.

### Capability: Ownership, churn, and risk scoring

Derive ownership from `CODEOWNERS` and `git blame`, churn from commit frequency over a sliding window, and a composite risk score per node (function of churn, fan-in, recent findings, and absence of tests). Stamps every File/Symbol node with `owner_team`, `churn_30d`, `risk_score` properties. Powers the **ownership** and **risk** lenses.

Acceptance outcomes:
- An ingester MUST parse `CODEOWNERS` and stamp `owner_team` on every File node it claims to own.
- `git blame` aggregation MUST stamp `last_modified_by` and `last_modified_at` on every Symbol node.
- A risk-score function MUST be documented in `docs/codeviz/risk-score.md` with its inputs and weights.
- The ownership and risk lenses MUST visibly color nodes by their derived properties.

### Capability: Graph pack export and import

Define a portable graph-pack format: a tarball containing the snapshot JSON files for a given commit + a manifest listing repo IDs, schema version, and signatures. Export endpoint produces a graph pack for the current state or a named commit; import endpoint ingests a pack into a fresh FalkorDB instance. Enables offline review, per-branch sharing, and reproducible bug reports.

Acceptance outcomes:
- A graph pack MUST be a single tarball with a checked-in manifest schema at `contracts/graph-pack.schema.json`.
- `/repos/{id}/export?at={commit_sha}` MUST stream a pack in under 30 seconds for a 1.5k-node repo.
- `codeviz-pack import <file>` MUST repopulate a fresh FalkorDB instance idempotently.
- The pack MUST include the mandatory artifact header on every embedded JSON.

## Phase 5 — Polish and Extensibility

### Capability: Saved views and URL-as-state

Every UI lens (filter set + zoom + time + selection + diff overlay) MUST be encodable as a URL. A "save view" action persists named views to localStorage and optionally to a per-repo `codeviz.views.yaml` for sharing. Depends on Phase 1 and 2 capabilities.

Acceptance outcomes:
- Every interactive state MUST be restorable from URL alone.
- Saved views MUST round-trip through the YAML file with no loss.

### Capability: Optional CodeCity 3D view (experimental)

A toggle that switches the canvas to a three.js CodeCity-style 3D treemap — buildings as classes/files, districts as packages, height as LOC, color as complexity or recent-change heat. Flagged as experimental; not the default surface.

Acceptance outcomes:
- 3D view MUST render the current graph in under 3 seconds.
- Switching between 2D and 3D MUST preserve selection state.
- 3D view MUST be feature-flagged and disabled by default.

### Capability: Documentation and onboarding

Author `docs/codeviz/` covering: architecture, schema, API reference, agent API, ingestion runbook, troubleshooting. Add a `make codeviz-demo` target that loads a fixture snapshot and opens the SPA at a curated starting view.

Acceptance outcomes:
- `docs/codeviz/README.md` MUST link from the repo root README.
- `make codeviz-demo` MUST work on a fresh clone after `make codeviz-up`.
- Schema doc MUST include at least one example Cypher query per node and edge type.
