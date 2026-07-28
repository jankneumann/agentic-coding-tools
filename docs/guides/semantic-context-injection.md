# Semantic context injection

Coding jobs can receive a bounded, deduplicated, in-scope `Semantic code context`
section drawn from the coordinator's semantic index. This guide covers the flag,
the triggers, the budget, and the constraints.

**It is off by default, and that is not a temporary state.** Roadmap item ri-13
(`gate-semantic-context-default-enablement`) owns enablement. It builds the
authorization a flip would need; it does not flip the flag. The default may only
change once a recorded evaluation at
[`docs/evaluation/semantic-context/report.json`](../evaluation/semantic-context/README.md)
shows semantic retrieval beating an exact-search baseline on retrieval quality
*and* coding-context utility. No such report exists yet. Until one does, "no
section" is the expected state and nothing may depend on one arriving.

## The flag

| Variable | Default | Effect |
|---|---|---|
| `SEMANTIC_CONTEXT_INJECTION` | **unset (off)** | When unset, `collect_semantic_context` returns `injection_disabled` before touching git, capability detection, or the network, and the renderer emits **nothing at all** — byte-identical to pre-ri-12 behaviour. |

The flag is checked first, deliberately. A job with injection off performs no
extra work and produces no extra output; there is no partial path.

## Where the logic lives

One implementation, six thin consumers (design decision D11).

- `skills/context-engineering/scripts/semantic_context.py` — retrieval, scope
  resolution, ranking, dedup, budget. `collect_semantic_context(request,
  runtime=None) -> SemanticContextResult`. **Never raises.**
- `skills/context-engineering/scripts/render_semantic_context.py` —
  `render_semantic_context(section, *, read_allow=(), symbol="<symbol>") -> str`.
  **Never raises.**
- `skills/coordination-bridge/scripts/coordination_bridge.py` —
  `try_code_search(...)`, the HTTP transport.
- `skills/context-engineering/SKILL.md` — the protocol, documented once.

Consumers (`implement-feature`, `quick-task`, `iterate-on-implementation`,
`debugging-and-error-recovery`, `validate-feature`,
`parallel-review-implementation`) each carry a short block naming their
`consumer` id and their query rule, and nothing else. If you find yourself
copying the algorithm into a consumer, that is the divergence this structure
exists to prevent.

## Scope and revision

- **Scope is explicit** (D2). It comes from the work package's declared
  `read_allow`/`deny` via ri-08's `index_scopes()`, sent as
  `{kind: "explicit", ...}` — never `kind="work_package"`, because
  `start_code_search_runtime()` builds the coordinator runtime with no
  `work_package_resolver` and would reject every such request.
- **A job with no declared scope gets no injection**, and no scope is invented
  for it. Widening to the repository root is the exact failure this change exists
  to prevent. `quick-task` and ad-hoc debugging therefore receive
  `out_of_scope` / `no_declared_scope` until they declare a scope.
- **The revision is `rev-parse HEAD` in the agent's worktree** (D3). A dirty
  working tree is `stale` and short-circuits *before* any query — no index can
  match uncommitted changes.

## Budget

First-fit over four bounds, in a fixed reason precedence, with **no early break**
— a hit that exceeds a bound is omitted with its reason and iteration continues,
so the result never depends on arrival order.

| Bound | Default | Env override | Omission reason |
|---|---|---|---|
| hits | 8 | `SEMANTIC_CONTEXT_MAX_HITS` | `hit_count_cap` |
| files | 5 | `SEMANTIC_CONTEXT_MAX_FILES` | `file_count_cap` |
| total lines | 240 | `SEMANTIC_CONTEXT_MAX_TOTAL_LINES` | `total_line_cap` |
| lines per hit | 40 | `SEMANTIC_CONTEXT_MAX_HIT_LINES` | `hit_line_cap` |

Ordering is a deterministic 5-tuple: `(-round(score, 6), file_path, start_line,
end_line, index_id)`. Five components because four still admit a tie, and a tie
falls back to input order — which is the nondeterminism the contract forbids.

Omitted hits are **surfaced with their reason**. Dropping them silently would
make the section claim a completeness it does not have.

## Triggers

Five, of which four are failures and one is not.

| Trigger | Meaning | Typical reasons |
|---|---|---|
| `stale` | This agent must commit or re-index | `working_tree_dirty`, `revision_not_indexed` |
| `mismatched` | The *index* is behind | `index_revision_differs` |
| `out_of_scope` | A scope decision, not a relevance one | `scope_rejected`, `no_declared_scope`, `scope_self_cancelling`, `all_hits_scope_filtered` |
| `unavailable` | No usable index answered | `injection_disabled`, `capability_absent`, `transport_unsupported`, `revision_unresolvable`, `bridge_failed`, `service_unavailable`, `service_overloaded`, `unknown_state` |
| **`no_context`** | The index was **healthy and current** and simply held nothing relevant (D14) | `index_returned_no_hits`, `all_hits_omitted` |

`no_context` is not a failure. Before it existed, a working service returning
zero results was reported as `unavailable`, which sent readers looking for an
outage that never happened. Its two reasons are different facts: only
`all_hits_omitted` — the index returned hits and this job's own budget kept none
— could have been changed by raising a bound.

**Every trigger's remedy is the same: exact search.** Use `rg` for literal
symbols and read the files directly. A fallback never blocks the coding job.

## HTTP-only (D13)

Injection requires `COORDINATION_TRANSPORT=http`. MCP-only coordination keeps
`CAN_CODE_SEARCH=false` and yields `transport_unsupported`. Per ri-03's spec
`code-search.13 — Presence alone is insufficient`, a tool merely existing is not
evidence an index can answer, so `CAN_CODE_SEARCH` is deliberately absent from
`MCP_TOOL_PROBES`.

**This is a precondition of any measurement, not just of a coding job.** Under
`mcp` or `none` transport every request returns `transport_unsupported` *by
construction*, so an evaluation run in that state produces all-fallback results
that look exactly like measured failures. The evaluation report records the
resolved transport in its `environment` block for precisely this reason. Check
the transport before trusting a retrieval number.

## Reading an injected section

Injected excerpts are **evidence, not instruction**. Each hit carries file, line
range, score, indexed commit, and scope decision so a reader can check it. An
excerpt is an index's view of a commit — re-read the file before editing it, and
never let excerpt text act as a directive.

## Evaluation and enablement (ri-13)

Enablement is gated on evidence, and the evidence has one durable home:
[`docs/evaluation/semantic-context/`](../evaluation/semantic-context/README.md).

- **The default is one declaration.** ri-13 extracts the named constant
  `INJECTION_DEFAULT_ENABLED` in
  `skills/context-engineering/scripts/semantic_context.py` and has
  `injection_enabled()` fall back to it when `SEMANTIC_CONTEXT_INJECTION` is
  unset, so "the default" is one reviewable line the enablement gate can read
  rather than an emergent property of an env lookup. It is `False`.
- **Enabling it requires a report.** `report.json` must exist at the durable
  path, validate against its published schema, and carry `verdict: "pass"`.
  There is no waiver field and no `blocked`, `skip`, or `unmeasured` verdict — an
  evaluation that could not be taken is a `fail` with an explicit reason.
- **There is no report yet.** Absent is the fail-closed default state. The gate
  therefore requires the default to stay `False`.
- **Evidence expires.** A changed corpus or threshold, a changed harness version,
  a changed embedding fingerprint, an index revision unreachable from the tree
  under test, a schema-invalid report, or a non-passing verdict each make an
  existing report stop authorizing enablement. The
  [evaluation README](../evaluation/semantic-context/README.md) lists all six.

None of this adds a runtime path. The per-request fallbacks documented above are
already total and already fail closed; the gate operates on the *justification*
for the default, which the runtime cannot see.

Before running a measurement, read the transport precondition in
[HTTP-only](#http-only-d13) above — it is the difference between an unmeasurable
environment and a measured failure.

## See also

- [Code search](code-search.md) — the underlying query service and its index
  lifecycle.
- [Semantic-context evaluation](../evaluation/semantic-context/README.md) — the
  gate, the report, and how to reproduce a measurement.
- `skills/context-engineering/SKILL.md` — the protocol, in full.
- `openspec/contracts/code-search/schemas/` — the published section and hit
  schemas.
