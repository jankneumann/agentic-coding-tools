# Design: harden-review-dispatch-parse-and-timeouts

## Context

Review dispatch today:

```
converge() / CLI review_dispatcher
  → build_review_prompt()  (hand-written, missing axis/severity)
  → dispatch_and_wait(timeout_seconds=300)   # converge does not pass a timeout
  → CliVendorAdapter.dispatch()
       subprocess.run(..., timeout=timeout_seconds)
       _parse_findings(stdout)          # JSON / envelope / NDJSON
       _validate_findings_or_error()    # fail-closed schema
       on failure: error = excerpt[:500]
  → successful vendors → ConsensusSynthesizer
```

Only `grok-local` review mode injects `--json-schema @review-findings-schema`.
`vendor_review.py` already derives the PR-review prompt from
`finding_item_schema()`. `converge().build_review_prompt()` and the skill-written
`review-prompt.md` files do not share that helper.

`evidence_class` is defined on the finding and honored by the synthesizer
(judgment never increments `blocking_count`). Ingest never sets it, so the
default `deterministic` applies to every CLI model reviewer.

## Goals / Non-Goals

**Goals**

- A vendor that obeys the prompt produces a document the validator accepts.
- A vendor that almost produces a valid document gets one constrained rewrite.
- Timeouts reflect observed p90, not a global 300s that sits below Claude's median.
- Failed vendors cannot vote "no problems found."
- Model-review findings are labeled judgment at ingest.

**Non-goals**

- Parallel dispatch, packed review packets, structured output for every vendor
  (phase 3 / `pack-and-parallelize-vendor-review`).
- Finding identity across rounds, compact, delta review, blocking-policy change,
  disagreement parking, nested-loop collapse (phase 2 /
  `ledger-driven-review-convergence`).
- Replacing regex async polling or cloud lock-release (`dg-02` /
  `build-structured-vendor-result-channel`).
- Loosening `review-findings.schema.json` required fields.
- Automatic recovery from synthesis crashes (already rejected in
  `harden-multi-vendor-review-recovery`).

## Decisions

### D1: One prompt helper, derived from the canonical schema

`review_findings_schema.prompt_contract()` (name flexible) returns required
fields, enums, and a short prose block. `build_review_prompt()`, the plan/impl
review skills, and `vendor_review.py` all call it. Hand-copied field lists are
deleted. The 2026-08-24 defect cannot recur in a third caller.

### D2: Coerce, then validate. Do not loosen the schema.

A small alias table (contracted) maps known vendor vocabulary onto the enum
before `jsonschema` runs. Examples: `bug`/`logic`/`defect` → `type=correctness`;
`completeness`/`testability` → `axis=architecture`/`correctness` plus a legal
`type`; missing `severity` filled from `criticality` and vice versa using a
fixed map (`critical`↔`critical`, `high`↔`nit` is **not** used; `high`↔`critical`
prefix, `medium`↔`nit`, `low`↔`optional`). Every coercion is recorded on the
finding as an extension field `coercions: string[]` that the schema permits as
additionalProperties-or-explicit-optional, or as a sibling sidecar list in the
vendor wrapper — prefer an optional `coercions` array on the wrapper, not on
the finding, so the finding schema stays the consensus contract.

If coercion cannot produce a valid document, the repair retry runs.

### D3: Exactly one repair retry

The repair prompt is: the original prompt + the validator error list + "emit
only a JSON object with a `findings` array; no prose." Same timeout budget.
If the retry fails, the vendor is unsuccessful. No third attempt. Repair is
not a full re-review and does not re-enable tools beyond what the original
mode allowed.

### D4: Per-vendor timeout budget, passed through `converge()`

A versioned table (contract `dispatch-timeout-budget.schema.json`) maps
`vendor` → `timeout_seconds`. Seeded from archive p90 with headroom:

| Vendor        | Default seconds |
|---------------|-----------------|
| claude_code   | 720             |
| grok          | 600             |
| codex         | 480             |
| antigravity   | 240             |
| pi            | 600             |
| gemini        | 240             |
| (unknown)     | 300             |

`converge()` MUST pass this table (or the resolved per-call timeout) into
`dispatch_and_wait`. CLI `--timeout` remains an override for all vendors.
Timeout remains a hard kill (`subprocess.TimeoutExpired`); retry-on-timeout
is out of scope (phase 3 packed packets are the real fix for 10-minute repo
walks). Timeout stays classified `TRANSIENT`.

### D5: Model-review ingest is judgment

`CliVendorAdapter.dispatch` (and the SDK review path) stamps
`evidence_class=judgment` on every finding that does not already carry
`deterministic` from a **caller-side** declaration. A payload cannot promote
itself to deterministic — that rule already exists in `Finding.from_dict`
and is preserved. Deterministic emitters (playwright-validator, gen-eval
findings emitter, linters) pass `evidence_class=deterministic` at ingest
explicitly.

This does not change blocking policy in `convergence_loop._is_blocking`.
Phase 2 changes that. Phase 1 only stops the synthesizer from counting
pure-judgment findings as `blocking_count`. `_is_blocking` still treats
medium+ unconfirmed as blocking until phase 2; that is accepted — phase 1
is robustness, not resolution.

### D6: Raw stdout sidecar

For every dispatch, write `<output_dir>/raw-<vendor>-<review_type>.txt` (full
stdout) and `.stderr.txt` if non-empty, plus a small JSON metadata file
`raw-<vendor>-<review_type>.meta.json` `{bytes, truncated: false, sha256}`.
Do not truncate. If a size cap is needed later, it is a follow-up; the
motivating incident lost the document because of a 500-char excerpt.

In-process `converge()` writes the same sidecars under `.review-cache/round-N/`
via `checkpoint_findings`.

### D7: Unparseable / classified-error / blinded-empty is not success

A vendor counts as `success=True` only when (a) a findings object parsed, (b)
it passed schema validation after coercion (and optional repair), and (c) if
`findings == []`, the dispatch was not classified AUTH/UNAVAILABLE/CAPACITY
and the elapsed time is above a minimum floor (e.g. 15s) so the pi
`--no-tools` two-second empty-success cannot recur. Below-floor empty results
are `success=False` with error `empty_findings_too_fast`.

### D8: Shared helper lives in `review_findings_schema.py`

Prompt contract, alias table loader, severity↔criticality map, and
`coerce_findings_payload()` live next to the canonical schema loader so the
dispatcher, converge, and vendor_review all import one module. No new
dependency direction.

### Fitness Functions

| NFR (from proposal.md) | Verifying check | Status |
|------------------------|-----------------|--------|
| Invalid-JSON + timeout share ≤ 50% of baseline on fixture replay | New test: replay recorded failing stdout blobs through coerce+repair; assert a majority become valid or classified (not silent drop) | new |
| 1 timeout + 2 valid → no `quorum_lost` | Existing converge tests extended | new |
| Raw stdout sidecar always present | Dispatcher unit test | new |
| Valid documents still validate without coercion | Existing schema fixtures | existing |
| `converge()` passes timeout into `dispatch_and_wait` | Unit test with a fake orchestrator recording kwargs | new |

## Alternatives Considered

Covered in `proposal.md`. Additional design-level reject: stuffing `--json-schema`
into every CLI (Codex/Claude/agy/pi) in this change. Those flags are
vendor-specific and unverified except for Grok; that is phase 3.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Coercion maps a real "completeness" plan-axis finding onto the wrong review axis | Log coercions; repair retry still sees the original; compact in phase 2 re-verifies |
| Longer timeouts make a sequential 4-vendor round slower | Accepted for phase 1; phase 3 parallelizes. Quorum-lost is more expensive than waiting. |
| Judgment ingest without phase 2 blocking change leaves `_is_blocking` still firing on medium unconfirmed | Documented; synthesizer `blocking_count` drops, loop policy waits for phase 2 |
| Raw stdout may contain secrets | Sidecars live under `.review-cache/` / `reviews/` which are change-local; session-log sanitizer is not applied (out of scope). Follow-up if needed. |
| Repair retry doubles cost on the failure path | One retry, constrained prompt, same timeout; success path unchanged |

## Migration Plan

Land behind no flag — current behavior is already failing open on false
consensus and failing closed on parse. Roll forward: old findings files without
`evidence_class` remain default-deterministic at synthesizer read (existing
behavior). New CLI reviews stamp judgment. Rollback: revert the dispatcher
commit; schema unchanged.

## Open Questions

- Exact severity↔criticality cross-fill table (D2) is specified above; if
  review of this plan wants `high`↔`nit` instead of `high`↔`critical` prefix,
  that is a one-line table change, not an approach change.
- Minimum elapsed floor for empty findings (D7) defaults to 15s; tune if a
  legitimate fast empty review exists.
