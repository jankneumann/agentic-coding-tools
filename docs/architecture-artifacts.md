# Architecture Artifacts

The `docs/architecture-analysis/` directory contains auto-generated structural analysis of the codebase. These artifacts are committed and should be consulted by agents during planning and validation.

## Key Files

### Layer 1 — Code Analysis
- `docs/architecture-analysis/python_analysis.json` — Python module/class/function extraction
- `docs/architecture-analysis/ts_analysis.json` — TypeScript component/hook/route extraction
- `docs/architecture-analysis/postgres_analysis.json` — SQL table/index/function/trigger extraction

### Layer 2 — Graph & Insights
- `docs/architecture-analysis/architecture.graph.json` — Full canonical graph (nodes, edges, entrypoints)
- `docs/architecture-analysis/architecture.summary.json` — Compact summary with cross-layer flows, stats, disconnected endpoints
- `docs/architecture-analysis/architecture.diagnostics.json` — Validation findings (errors, warnings, info)
- `docs/architecture-analysis/parallel_zones.json` — Independent module groups for safe parallel modification
- `docs/architecture-analysis/treesitter_enrichment.json` — Tree-sitter pattern analysis (comments, exceptions, type hints, security)
- `docs/architecture-analysis/comment_insights.json` — TODO/FIXME hotspots, documentation coverage, node-marker map
- `docs/architecture-analysis/pattern_insights.json` — Exception handling summary, type hint coverage, security findings

### Layer 2.5 — Behavior Handbook
- `docs/architecture-analysis/architecture.behaviors.json` — Behavior-centric map
  (L1 system flows, L2 behavior units, L3 unit detail with verified evidence)
- `docs/architecture-analysis/views/handbook.html` — Three-level drill-down with
  persona entry presets

The graph answers "what calls what". The handbook answers **"where does behavior
X live"** — the question every change request actually asks. See
[Behavior Handbook](#behavior-handbook-layer-25) below.

### Layer 3 — Reports & Views
- `docs/architecture-analysis/architecture.report.md` — Narrative architecture report
- `docs/architecture-analysis/views/` — Auto-generated Mermaid diagrams

### Provenance & Freshness (revision-aware)
- `docs/architecture-analysis/architecture.provenance.json` — Records the exact
  analyzed Git SHA, dirty-input state, architecture producer version, relevant
  **input fingerprint**, generation mode, and SHA-256 digests of every owned
  artifact. Written by every successful `make architecture-refresh`.

Freshness is **content-based and mtime-independent**: an artifact is stale only
when a relevant input changed, the producer/tool identity changed, or an owned
artifact's bytes drifted from the recorded digest — never merely because the
graph file is "old". Two refreshes of the same revision and inputs produce
byte-identical artifacts (deterministic clock via `SOURCE_DATE_EPOCH`), so a
repeat refresh yields no repository diff.

Durable cross-process status is owned by `project-context-runtime`
(`add-durable-context-refresh-records`): the architecture adapter records one
canonical `producer_id=architecture` `ProducerResult` per `(repository, revision)`
operation and projects it onto the legacy refresh RPC status. The architecture
producer never finalizes the whole project-context operation.

Commands:
- `make architecture-refresh` — deterministic stage → validate → promote → write
  provenance. A failed generation preserves the last known-good committed set.
- `make architecture-check` — read-only freshness check; exits 0 only when
  `fresh`, and prints exact drift reason codes and stale artifact paths.
- `affected_tests.py --repo-root <path>` — content-based provenance gate for
  merge-train test selection (falls back to the full suite when not fresh).

## Usage
- **Before planning**: Read `architecture.summary.json` to understand component relationships and existing flows
- **Before implementing**: Check `parallel_zones.json` for safe parallel modification zones
- **Code quality review**: Read `pattern_insights.json` for exception handling, type coverage, and security findings
- **Tech debt tracking**: Read `comment_insights.json` for TODO/FIXME hotspots and documentation coverage
- **After implementing**: Run `make architecture-validate` to catch broken flows
- **Refresh**: Run `make architecture` to regenerate all artifacts

## Refresh Commands
```bash
make architecture              # Full refresh (includes tree-sitter enrichment if available)
make architecture-enrichment   # Tree-sitter enrichment only (requires skills venv)
make architecture-validate     # Validate only
make architecture-views        # Regenerate views only
make architecture-report       # Generate narrative report
make architecture-diff BASE_SHA=<sha>  # Compare to baseline
make architecture-feature FEATURE="file1,file2"  # Feature slice
cd skills && uv sync --all-extras  # Install skills venv (tree-sitter + analysis deps)
```

## Tree-sitter Enrichment

The enrichment pipeline uses tree-sitter for concrete syntax tree (CST) analysis:

1. **SQL Analyzer** (`skills/refresh-architecture/scripts/analyze_sql_treesitter.py`) — CST-based SQL migration parsing, replaces regex when available
2. **Enrichment Engine** (`skills/refresh-architecture/scripts/enrich_with_treesitter.py`) — Cross-language pattern extraction (Python + TypeScript)
3. **Comment Linker** (`skills/refresh-architecture/scripts/insights/comment_linker.py`) — Maps comments/TODOs to architecture graph nodes
4. **Pattern Reporter** (`skills/refresh-architecture/scripts/insights/pattern_reporter.py`) — Aggregates findings into actionable insights

Setup: `cd skills && uv sync --all-extras` (installs tree-sitter dependencies in `skills/.venv`)

---

## Behavior Handbook (Layer 2.5)

A behavior-centric reading surface over the canonical graph, adapting the
approach in [Harness Handbook (arXiv 2607.13285)](https://arxiv.org/abs/2607.13285).

### Why it exists

The canonical graph is a strong *evidence store* and a weak *reading surface*.
Its nodes are modules, classes, and functions; its edges are `call` and
`import`. Nothing in it answers "where does the lock-acquisition behavior
live" — an agent has to reconstruct that mapping from raw AST edges every
session, and pays the tokens to do so every time.

The handbook adds the missing layer and amortizes that reconstruction into a
committed, verifiable artifact.

### Three levels

| Level | Content | Budget | Who enters here |
|---|---|---|---|
| **L1** `system_flows[]` | How a request enters and which modules it crosses, grouped by entry module | ~400 tok | Newcomer |
| **L2** `behavior_units[]` | Named behaviors: responsibility, inputs, outputs, dependencies | ~150 tok/card | Reviewer (filtered by diff) |
| **L3** `unit_details{}` | Triggers, state changes, execution paths, **exception paths**, evidence | ~1500 tok/unit | Planner, Auditor |

Token budgets are **enforced by the validator**, not advisory. Progressive
disclosure only saves tokens if each level actually fits its budget, so an
over-budget section is a build failure — tighten the prose or split the unit.

L2 cards carry `member_node_count` + `primary_nodes` rather than inlining full
membership; the full `member_nodes[]` list stays in the artifact for validation
and localization ranking, but is not loaded into a reader's context.

### Verified evidence locators

Every L3 claim carries a locator: `node_id`, repo-relative `file`, `span`, and a
`content_digest` over the normalized span. The resolver re-checks it against the
working tree and classifies it:

| Status | Meaning | Effect |
|---|---|---|
| `verified` | digest matches | none |
| `drifted` | symbol resolves, content changed | warning + `handbook_locator_drift` stale reason |
| `unresolvable` | file or span gone | **error**, `make architecture-check` exits non-zero |

Digests are computed over whitespace-normalized spans, so reformatting churn
does not thrash the whole handbook.

### Synthesis is an event; verification is continuous

Synthesis may use a nondeterministic structuring backend, so it is **explicit**
and its output is reviewed and committed like source. Every refresh then runs
only the deterministic verify step. This preserves the pipeline's
byte-identical-repeat-refresh invariant.

The structuring backend can never widen the skeleton: membership comes from the
deterministic seeder alone, and any narrative that cannot be grounded in at
least one resolvable locator is dropped rather than published.

### Commands

```bash
make architecture-handbook-synthesize   # explicit: regenerate + commit the map
make architecture-handbook-validate     # schema + referential integrity + budgets
make architecture-handbook-verify       # re-verify locators against the tree
make architecture-handbook-html         # render the drill-down
make architecture-handbook              # validate + verify + render

# Scope the synthesis (default: agent-coordinator/src)
make architecture-handbook-synthesize HANDBOOK_SCOPE="agent-coordinator/src apps"
```

`make architecture-refresh` runs validation + locator verification automatically
on a committed handbook; `make architecture-check` reports handbook drift.

### Reading it as an agent (BGPD)

```bash
Q=skills/refresh-architecture/scripts/handbook_query.py
HB=docs/architecture-analysis/architecture.behaviors.json

# 1. Localize the behavior — ranked candidates, no L3 detail
python3 $Q --handbook $HB --repo-root . --locate "acquire a file lock for an agent"

# 2. Open only the winner — full detail with per-locator verification
python3 $Q --handbook $HB --repo-root . --level l3 --unit bh:<id>
```

Other entry points: `--level l1` (orientation), `--level l2 --files a.py,b.py`
(reviewer), `--level l2 --filter "retry"` (search).

### Uncovered entrypoints

Entrypoints whose expansion finds no downstream call chain are listed in
`uncovered[]` with a reason rather than silently omitted. That count is the
handbook's own honesty metric — it says what the map does not explain.
