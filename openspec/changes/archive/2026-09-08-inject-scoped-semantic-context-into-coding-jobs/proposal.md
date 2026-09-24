# Change: Inject scoped semantic context into coding jobs

> Parent roadmap: `project-context-refresh-lifecycle`
> Roadmap item: `ri-12`
> Change ID: `inject-scoped-semantic-context-into-coding-jobs`
> Effort: L
> Depends on: `expose-fail-closed-semantic-code-search` (ri-03, merged),
> `add-work-package-context-impact-declarations` (ri-08, merged)

## Why

ri-01 through ri-10 built the entire producer side of semantic code context:
revision-aware index identities, incremental indexing, a fail-closed query
service, work-package read-scope declarations, and branch-local checkpoint
indexes. Nothing consumes it. The retrieval capability is complete and unused.

Every claim below was measured on this branch, whose `HEAD` (`1cf51386`)
contains `origin/main` (`git merge-base --is-ancestor origin/main HEAD` exits 0).

**The query surface exists and is reachable.**

- The service and its typed contract are `agent-coordinator/src/code_search.py`
  (`CodeSearchRequest` at line 130, `CodeSearchHit` at 198, `CodeSearchResponse`
  at 217, `CodeSearchState` at 76).
- HTTP: `GET /search/code/status` at `agent-coordinator/src/coordination_api.py:3418`
  and `POST /search/code` at `:3455`.
- MCP: `search_code` at `agent-coordinator/src/coordination_mcp.py:3149`,
  registered conditionally by `if _code_search_enabled():` at `:3216`.

**Capability discovery already exists — the ri-12 grounding brief was wrong
about this, and the correction changes the shape of the work.**

`CAN_CODE_SEARCH` is *already* implemented in both discovery paths. ri-03's
`wp-capability-discovery` package shipped it:

- `skills/coordination-bridge/scripts/check_coordinator.py` defines
  `CODE_SEARCH_STATUS_PATH` (line 31), `_is_code_search_ready` (line 123),
  `probe_code_search_status` (line 137), carries `"CAN_CODE_SEARCH": False` in
  the default dict (line 201), and sets it from the status body at line 211.
- `skills/coordination-bridge/scripts/coordination_bridge.py` lists
  `CAN_CODE_SEARCH` in `_CAPABILITY_FLAGS` (line 51), exposes it as
  `capabilities["code_search"]` (line 175), and probes it at line 386.
- `skills/coordination-bridge/scripts/tests/test_code_search_capability.py`
  covers it.

So "skills cannot discover code search" is false. What is true, and measured:

1. `CAN_CODE_SEARCH` is deliberately absent from `MCP_TOOL_PROBES`
   (`check_coordinator.py:59-70`; verified programmatically). Under MCP-only
   transport the flag therefore stays `False`. This is **intentional**, not a
   defect: ri-03's spec requirement *Truthful dynamic capability*
   (`openspec/specs/code-search/spec.md:610`) and its scenario
   `code-search.13 — Presence alone is insufficient` require exactly this, and
   ri-03's own work package described it as "remain false for unverifiable
   MCP-only detection". ri-12 preserves it and documents the consequence:
   injection is HTTP-transport-only until a body-aware MCP status probe exists.
2. There is **no transport helper to actually run a query**. `grep -c
   try_code_search skills/coordination-bridge/scripts/coordination_bridge.py`
   returns `0`, against 25 other module-level `try_*` helpers
   (`grep -c "^def try_"`). Discovery says "yes"; nothing can act on it.

**No coding job consumes semantic results.** `grep -rn "search_code\|Semantic
code context" skills/` excluding tests returns **0 matches**.
`skills/context-engineering/` contains exactly one file, `SKILL.md` — no
`scripts/` directory. Its 5-level context hierarchy (lines 51-206) has no level
for retrieved code, and its "Coordinator Detection" section (lines 213-239)
names handoff, recall and locks but not search.

**Work-package scope is already resolvable but only for indexing.** ri-08's
`index_scopes(package)` (`skills/validate-packages/scripts/context_impact.py:181`)
returns `read_allow`/`deny` with deny precedence, and ri-09's
`ReadScope.from_index_scopes` (`skills/project-context-refresh/scripts/semantic_adapter.py:243`)
already adapts it — but only onto the *write* path, `run_checkpoint`
(`skills/project-context-refresh/scripts/checkpoint.py:532`), which indexes a
work-package namespace. The symmetric read path does not exist.

**Two coordinator facts constrain the design and were verified in source.**

- `start_code_search_runtime()` calls `CodeSearchRuntime.create()` with no
  arguments (`code_search_runtime.py:536`), so `work_package_resolver` stays
  `None` (`:185`). `code_search_authorization.py:200-202` then raises
  `ScopeRejectedError("work-package scope cannot be resolved")` for **every**
  `scope.kind="work_package"` request. In production today only
  `scope.kind="explicit"` can succeed. ri-12 must build an explicit scope from
  ri-08's resolved globs rather than delegate to the coordinator resolver.
- `CodeSearchHit` (`code_search.py:198-208`) names the relevance field
  `similarity`, not `score`, and carries `source_revision` (the indexed commit),
  `index_id`, and `scope_decision`. The roadmap's acceptance wording ("score",
  "indexed commit") maps onto these exact fields; ri-12 renders them under the
  roadmap's names and records the mapping rather than renaming the contract.

## What Changes

- Add `try_code_search` to `skills/coordination-bridge/scripts/coordination_bridge.py`,
  following the existing `try_*` envelope contract (never raises; structured
  failure result). It POSTs the ri-03 `CodeSearchRequest` shape to
  `/search/code` and returns the discriminated `CodeSearchResponse` untouched.
- Add `skills/context-engineering/scripts/semantic_context.py` — the single
  shared retrieval helper. It resolves the requesting revision, namespace and
  index, builds an **explicit** scope from ri-08 `index_scopes()`, calls the
  bridge, re-applies deny locally as defense in depth, deduplicates, applies a
  deterministic budget, and returns one typed `SemanticContextResult`.
- Add a deterministic renderer producing the `Semantic code context` markdown
  section, with a per-hit provenance line carrying file, line range, score,
  indexed commit, index ID, and scope decision.
- Extend the `context-engineering` 5-level hierarchy with retrieved semantic
  code as a Level-3 augmentation, and document the retrieval/fallback protocol
  once, in that skill.
- Teach `implement-feature`, `quick-task`, `iterate-on-implementation`,
  `debugging-and-error-recovery`, `validate-feature`, and
  `parallel-review-implementation` to request the section through the shared
  helper — a short protocol block per skill that delegates to
  `context-engineering`, not seven copies of the logic.
- Define four fallback triggers — **stale**, **unavailable**, **mismatched**,
  **out-of-scope** — each emitting an explicit exact-search fallback block plus
  a machine-readable fallback record, and never blocking the coding job.
- Publish `contracts/schemas/semantic-context-section.schema.json` and
  `semantic-context-hit.schema.json` and promote them to
  `openspec/contracts/code-search/schemas/`.
- Gate the whole path behind `SEMANTIC_CONTEXT_INJECTION`, **default off**.
  With the flag unset every consumer skill behaves byte-identically to today.
  ri-13 (`gate-semantic-context-default-enablement`) owns flipping the default
  after its evaluation gates pass; ri-12 must not pre-empt it.

## Impact

**Affected specs**

- `skill-workflow` — ADDED: the injection contract, section format, determinism
  guarantees, fallback triggers, and opt-in default.
- `coordination-bridge` — ADDED: the `try_code_search` helper and the explicit
  statement that MCP-only transport keeps `CAN_CODE_SEARCH=false`.

**Affected code (all additive; no existing behavior changes while the flag is off)**

- `skills/coordination-bridge/scripts/coordination_bridge.py` (new helper)
- `skills/context-engineering/scripts/` (new directory: retrieval + renderer)
- `skills/context-engineering/SKILL.md`, plus a protocol block in the six
  consumer `SKILL.md` files
- `skills/tests/context-engineering/`, `skills/tests/coordination-bridge/`
- `openspec/contracts/code-search/schemas/` (promoted schemas)

**Explicitly out of scope**

- Wiring `work_package_resolver` into `CodeSearchRuntime.create()`. That is a
  coordinator-side change to a merged ri-03 surface; ri-12 works within the
  contract as shipped by using explicit scope.
- Any MCP-transport capability probe for code search — ri-03 decided this
  deliberately (`code-search.13`) and ri-12 does not widen it.
- Turning injection on by default (ri-13).
- Indexing. ri-09's checkpoint already writes work-package namespaces; ri-12
  only reads.
