# Deferred Tasks: add-behavior-handbook-layer

Ordered by what most likely closes the −21 pp F1 gap in `validation-report.md`.
Items 1–3 are prerequisites for lifting the D7 expansion gate.

## 1. LLM structuring backend (highest value — the paper's actual mechanism)

`OfflineBackend` renames deterministic reachability clusters; it does not group,
split, or name behaviors. The paper's gains come from LLM-assisted behavioral
structuring over the skeleton, which is unimplemented.

- Add a structuring backend behind the existing `StructuringBackend` protocol
  (`synthesize_behaviors.py`) — the seam already exists and is tested.
- The backend must respect the D4 contract: it may merge, split, name, and
  narrate seed clusters, but never add a member node.
- Record `model_id` and `prompt_hash` in `snapshot` (already wired).
- Keep `offline` as the CI/default path so tests stay credential-free and
  deterministic.
- Re-run the benchmark; the gate is `f1_delta_pp > 0` at `k=3`.

## 2. Fix cluster granularity (bimodal distribution)

Median cluster is 2 nodes; two clusters are 29 and 46. Neither is a behavior.

- **Cap transitive expansion depth** in `behavior_seeder.seed_behaviors` (BFS
  currently runs to full reachability via `reachable_from`). A depth of 2–3 is
  the obvious first experiment.
- **Exclude shared-utility sinks** from expansion — nodes with very high
  in-degree (already computed in `high_impact_nodes.json`) pull unrelated
  entrypoints into one closure.
- **Merge trivial clusters**: an entrypoint-plus-one-callee cluster should fold
  into a sibling behavior rather than become its own unit.
- Add a granularity assertion to the validator (e.g. warn outside 3–20 members)
  so regressions surface at synthesis time.

## 3. Semantic localization ranking

`handbook_query.locate` scores lexical token overlap. A request phrased in
different vocabulary than the unit card scores zero.

- The repo already has `packages/code-search` with semantic indexing — reuse it
  for candidate ranking rather than adding an embedding dependency.
- Keep the lexical path as the offline fallback.

## 4. Strengthen the benchmark

- **Better ground truth**: `scope.write_allow` is a permission boundary, not the
  edited file set. Mine actual touched files from the merge commit range per
  archived change instead.
- **More scenarios**: 41 archives lack `work-packages.yaml`; recover request /
  touched-file pairs for them from git history to grow n well past 20.
- Report per-scenario outliers so granularity failures are attributable.

## 5. Read the source paper

Every fetch to `arxiv.org`, `huggingface.co`, and the project page returned 403
under this environment's network policy. The design was derived from the
abstract and secondary coverage. Re-derive the L3 schema, the BGPD stage
definitions (stage/state routing, call-relation expansion, verification), and
the evaluation protocol from the full text, and reconcile any divergence with
`design.md`.

## 6. Whole-repo expansion (gated)

Blocked on items 1–2 and a positive benchmark. Today `HANDBOOK_SCOPE` defaults
to `agent-coordinator/src`; expansion means adding `apps` and the migrations
root, and re-checking that the L1 grouping and per-card budgets still hold at
that size.

## 7. Planner integration (gated)

`skills/context-engineering` documents the handbook as a packing source, but no
orchestrator skill calls `handbook_query` automatically. Wire it into
`plan-feature` / `implement-feature` worker dispatch only once the benchmark
shows the handbook beats the graph baseline — until then, automatic use would
degrade localization.

## 8. Smaller follow-ups

- **Exception-path coverage is thin**: 2 of 54 units carry exception paths,
  because most `broad_except` findings sit in nodes outside any cluster. Improves
  automatically with item 2.
- **Unit titles are mechanical** (`Coordination api create coordination api
  acquire lock`) — resolved by item 1.
- **`L1_MAX_FLOWS` omission is currently 0** but untested at repo scale; verify
  the `flows_omitted_from_l1` counter surfaces in the HTML when it is non-zero.
- **`--level l2 --files` filtering** matches evidence-locator paths only; a unit
  whose member node has no stamped locator will not match a reviewer's diff.
