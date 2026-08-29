# Design — fix-architecture-freshness-evidence

## Context

Architecture provenance is the repository's only content-based freshness authority.
`docs/architecture-analysis/architecture.summary.json` currently describes 1,903 nodes
and 1,199 edges across 77 modules, generated from three input roots
(`agent-coordinator/src`, `apps`, `agent-coordinator/database/migrations`). The evidence
that this graph is current lives in `architecture.provenance.json`, and three consumers
depend on it:

| Consumer | Layer | Reads provenance via |
|---|---|---|
| `make context-drift-gate` | Governance | `orchestrator.py:261` → `check_freshness` |
| Merge-train test selection | Coordination | `merge_train_service.py:220` → RPC `is_graph_stale` |
| Branch-local checkpoints | Execution | `checkpoint.py:313` → `architecture_freshness` |

Two of those three already reach the content-based path. The middle one does not, and
that is the defect this change repairs.

## Cross-layer flow

```
merge_train_service.py:220          (Coordination)
  └─ RefreshRpcClient.is_graph_stale(max_age_hours=6)
       └─ rpc_server.main() ──> get_server()          (Execution)
            │
            │   TODAY: RefreshServer(graph_path=<relative>)   repo_root = None
            │            └─ rpc_server.py:252  →  mtime vs 6h  →  reason="mtime"
            │                 provenance fields all null
            │
            └─  AFTER: RefreshServer(graph_path=<abs>, repo_root=<resolved>)
                     └─ _provenance_projection()
                          └─ provenance.check_freshness(repo_root)
                               → reason = a real drift code, or fresh
```

The bug is entirely in the construction step. Everything downstream of `repo_root`
already works and is covered by `test_rpc_server.py:276-313`.

## Decisions

### D1 — `tier` is required, not optional-with-default

The artifact schema sets `additionalProperties: false` and freshness fails closed on
schema-invalid provenance. A `tier` that defaults when absent would let a record written
before this change be read as `committed` for every entry — the exact silent
misclassification the field exists to prevent. Required-and-enumerated means an old
record is rejected loudly instead of reinterpreted quietly.

**Consequence**: every recorded artifact must be assigned a tier at write time, so
`_OWNED_TOP_LEVEL` (`provenance.py:94-106`) grows from `(name, required)` pairs to
`(name, required, tier)` triples.

### D2 — `schema_version` becomes `const: 2`, not `enum: [1, 2]`

Accepting both versions would require the validator to carry two artifact shapes and
every reader to branch on version. The producer-identity bump (D6) already invalidates
pre-change records, so dual acceptance buys compatibility that nothing can use: a v1
record paired with a v1.2.0 producer version is stale on producer identity regardless of
whether its artifact entries validate.

**Rejected alternative**: `enum: [1, 2]` with `tier` optional when `schema_version == 1`.
Rejected because it makes the schema conditionally shaped, which JSON Schema expresses
only through `if/then`, and because it contradicts D1.

### D3 — Schema-version drift gets its own reason code

`check_freshness` currently reports schema problems through the generic invalid-provenance
path. Scenario `architecture-refresh.19` requires that a version mismatch be
distinguishable from artifact drift, because the two have different remediations:
regenerate the record versus regenerate a file. A new `PROVENANCE_SCHEMA_VERSION_MISMATCH`
code (alongside the existing codes at `provenance.py:141-146`) keeps the gate's
"name the exact remediation" contract intact.

### D4 — `repo_root` resolution is explicit, ordered, and still allows legacy

`get_server()` resolves in this order:

1. `REFRESH_RPC_REPO_ROOT` if set — an explicit operator override.
2. `git rev-parse --show-toplevel`, run from the directory containing the resolved graph
   path, not from the process CWD.
3. `None` — the deprecated mtime probe.

Step 3 is retained deliberately. The spec says the deprecated fields **MAY** remain, and
`input_enumeration_strategy` (`provenance.py:313`) still supports a `.git`-less source
export. What changes is that legacy mode becomes reachable only when there is genuinely
no repository, rather than by an entry point forgetting to look — which is the whole
defect.

Step 2 runs from the graph path's directory rather than the CWD because
`DEFAULT_GRAPH_PATH` (`rpc_server.py:58`) is relative today; resolving it against a CWD
that is not the repository root is what produces the observed
`stale: true, graph_mtime: null`.

### D5 — The server singleton gets an explicit reset seam

`_SERVER` (`rpc_server.py:390`) is a module-global memoized under `_SERVER_LOCK` with no
reset hook, and no existing test constructs through `get_server()` — only
`TestMainEntryPoint` (`test_rpc_server.py:221`) reaches it indirectly. Testing D4
requires resetting it between cases.

A public `reset_server()` is added rather than having tests assign
`rpc_server._SERVER = None` directly. Reaching into another module's private global from a
test is a coupling that survives refactors silently; a named seam does not.

### D6 — `PRODUCER_VERSION` and `PROVENANCE_SCHEMA_VERSION` both move

`PROVENANCE_SCHEMA_VERSION` 1 → 2 records the record-shape change. `PRODUCER_VERSION`
1.2.0 → 1.3.0 records that the *set of artifacts this producer commits* changed. They are
distinct facts and both are compared: a reader that only saw the schema bump could not
tell whether the artifact set had changed, and a reader that only saw the producer bump
could not tell whether the record shape had.

### D7 — Which artifacts move, and why the graph does not

| Artifact | Size | Tier | Reason |
|---|---|---|---|
| `treesitter_enrichment.json` | 1.25 MB | `local-cache` | No reader outside the pipeline; `pattern_reporter.py:160` and `comment_linker.py:162` log-and-skip |
| `python_analysis.json` | 991 KB | `local-cache` | No reader outside `refresh-architecture/scripts`; only mention is the diagram at `SKILL.md:65` |
| `parallel_zones.json` | 520 KB | `local-cache` | One reader (`architecture_report.py:1140`) plus two agent-prose references |
| `architecture.graph.json` | 890 KB | `committed` | Read from **git history** by `checkpoint.py:339` and `architecture-diff`; `required=True`; ~20 readers |
| `architecture.diagnostics.json` | 1.03 MB | `committed` | bug-scrub degrades to `skipped`, but it is the flow-validation output that `validate_flows.py:756` orders deterministically *specifically* because provenance digests the committed file |

The graph and diagnostics stay committed in this change. D1's vocabulary is what would
make moving them a configuration decision later rather than another schema migration.

## Migration

The change is a single commit containing code, schema, and a regenerated
`architecture.provenance.json` at `schema_version: 2`. This mirrors the existing
requirement that "Regenerating architecture artifacts SHALL update the committed
provenance in the same commit."

Ordering within the commit matters for anyone bisecting:

1. Schema and `provenance.py` land together — a v2 writer with a v1 schema fails its own
   contract test.
2. `git rm --cached` the three artifacts and add the `.gitignore` entries.
3. Run `make architecture-refresh`; commit the resulting provenance.
4. Run `install.sh` to re-sync the `.claude/skills/` and `.agents/skills/` mirrors.

Between step 1 and step 3, `make context-drift-gate` reports stale with the D3 reason
code. That window is inside one commit and never reaches CI.

## Rollback

`git revert` of the single commit restores the v1 schema, the v1 provenance record, and
the tracked artifacts — *provided* the revert also removes the `.gitignore` entries,
which a revert does automatically since they were added in the same commit. The one
manual step is re-running `make architecture-refresh` afterwards, because the reverted
provenance names a producer version the reverted code no longer emits.

No consumer needs coordinated rollback: the three artifacts moving to `local-cache` have
no hard readers, and the RPC change only ever makes a verdict *more* accurate.

## Risks

| Risk | Mitigation |
|---|---|
| A reader of the published schema outside this repo breaks on `const: 2` | The schema is published under `openspec/schemas/`, consumed only by `test_architecture_provenance_contract.py` in-repo; no external consumer is known |
| Merge-train behavior changes once freshness becomes real — trains that used to run full-suite now select | This is the intended fix; the fallback at `merge_train_service.py:234` remains for genuine staleness |
| `git rev-parse` in `get_server()` adds a subprocess to a hot path | `get_server()` is memoized per process behind `_SERVER_LOCK`; the resolution runs once |
| The mirror-drift gate (`gate-drift-with-mirrors-hooks-and-blocking-ci`) fails on unsynced skills | `install.sh` is an explicit task, not a checkpoint afterthought |
