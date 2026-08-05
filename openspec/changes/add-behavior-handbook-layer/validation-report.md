# Validation Report: add-behavior-handbook-layer

## Summary

The infrastructure landed and is verified. **The adoption gate in design D7 is NOT
met**: the handbook arm loses to the graph-only baseline on localization F1. The
token saving is real and large, but it is bought with precision, not earned.

Per D7 ("handbook arm must beat graph-only on localization F1 without exceeding
its token budget"), **whole-repo expansion is blocked** pending the granularity
work in `deferred-tasks.md`.

## What was built and verified

| Component | Status | Evidence |
|---|---|---|
| Handbook schema + validator (R1) | ✅ | 22 tests; referential integrity + budgets enforced |
| Verified evidence locators (R2) | ✅ | 15 tests; 182/182 locators verified on the real artifact |
| Provenance / freshness (R3) | ✅ | `make architecture-check` → `fresh`; handbook + HTML digested |
| Progressive-disclosure query CLI (R4) | ✅ | 19 tests; level boundaries enforced |
| HTML drill-down + personas (R5) | ✅ | 14 tests; self-contained, 296 KB, refuses invalid input |
| Behavior seeding (R6) | ✅ | 18 tests; 8 uncovered entrypoints accounted for |

Test suite: **325 passed**, `ruff` clean. Full architecture suite (including the
12 pre-existing modules) green.

### Determinism and freshness

- Repeat synthesis at one revision is **byte-identical** (verified by diff).
- `make architecture-refresh` runs schema validation + locator verification
  after promotion and before provenance; `make architecture-check` → `fresh`.
- Absence of a handbook is fresh-by-absence, so the feature is safe to land
  before any map exists.

### First scoped synthesis (`agent-coordinator/src`)

| Metric | Value |
|---|---|
| Behavior units | 54 |
| System flows (L1, grouped by entry module) | 2 |
| Uncovered entrypoints | 8 (of 96 total entrypoints) |
| Clustered nodes | 188 |
| Locators | 182 verified, 0 drifted, 0 unresolvable |
| L1 / L2-max-card / L3-max budgets | 136/400, 145/150, 402/1500 |

## Benchmark: handbook BGPD vs. graph-only

20 scenarios mined from `openspec/changes/archive/` (75 excluded: 41 without
`work-packages.yaml`, 31 whose targets no longer exist at HEAD, 3 without
request text). Ground truth = `scope.write_allow` expanded to surviving files
under `agent-coordinator/src/`.

| k | Arm | Precision | Recall | F1 | Tokens |
|---|---|---|---|---|---|
| 1 | graph | 0.694 | 0.393 | **0.421** | 373 |
| 1 | handbook | 0.275 | 0.382 | 0.235 | **142** |
| 3 | graph | 0.506 | 0.603 | **0.441** | 1095 |
| 3 | handbook | 0.234 | 0.479 | 0.230 | **423** |
| 5 | graph | 0.464 | 0.687 | **0.443** | 1820 |
| 5 | handbook | 0.217 | 0.582 | 0.223 | **691** |
| 10 | graph | 0.357 | 0.736 | **0.367** | 3505 |
| 10 | handbook | 0.211 | 0.654 | 0.227 | **1343** |

**F1 delta at k=3: −21.1 pp. Token delta: −61.4%.**

### Reading the result

The loss is stable across every k, so it is not an artifact of how much width
each arm was given. **Recall is comparable** (0.38–0.65 vs 0.39–0.74);
**precision is where the handbook loses** (0.21–0.28 vs 0.36–0.69).

Root cause is cluster granularity, and it is bimodal:

- **Median cluster = 2 nodes.** Most "behavior units" are an entrypoint plus one
  callee — not a behavior, just a renamed function.
- **Two clusters have 29 and 46 nodes.** Unbounded transitive expansion over
  `call` edges reaches deep into shared utilities, so localizing to one of them
  returns dozens of files when the change touched one or two.

Neither shape is a curated behavior unit. That curation is exactly what the
paper's LLM-assisted structuring step performs, and the `OfflineBackend` used
here does none of it — it renames deterministic reachability clusters. **What
this benchmark measures is offline clustering, not the paper's method.**

The token saving (−61%) is therefore not yet a win: it reflects returning less,
not returning better.

## Honest limitations

1. **The paper was not read in full.** Every fetch to arxiv.org returned 403
   under this environment's network policy; the design derives from the
   abstract, project page, and secondary coverage. Schema details, prompt
   design, and ablations were unavailable and may matter.
2. **No LLM structuring backend was built.** Only `OfflineBackend` exists, so
   the central mechanism of the paper is unimplemented. The gate result should
   not be read as "the handbook approach fails" — it is "deterministic
   clustering with cosmetic naming fails."
3. **Ground truth is coarse.** `scope.write_allow` globs are permission
   boundaries, not the exact files a change edited; they likely over-count and
   may favor the wide graph baseline.
4. **Small n.** 20 scenarios, single subsystem.
5. **Localization ranking is lexical.** No embeddings; a semantically-phrased
   request that shares no tokens with a unit will not rank it.

## Verdict

Land the infrastructure — it is correct, tested, deterministic, and covered by
the existing freshness gate, and the HTML drill-down and query CLI are usable
today. Do **not** expand scope or wire the handbook into planner defaults until
the granularity work lands and the benchmark is re-run.

Reproduce with:

```bash
skills/.venv/bin/python \
  packages/agent-scenarios/scenarios/behavior-localization/benchmark.py \
  --repo-root . --k 3
```
