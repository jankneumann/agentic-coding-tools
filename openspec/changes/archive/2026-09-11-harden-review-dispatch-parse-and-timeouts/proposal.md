# Change: harden-review-dispatch-parse-and-timeouts

**Series**: multi-vendor review robustness (phase 1 of 3)
**Depends on**: none
**Unlocks**: `ledger-driven-review-convergence`, `pack-and-parallelize-vendor-review`

## Why

Multi-vendor review fails often enough that the panel is not a gate, it is a coin
flip. Across 59 archived `review-manifest.json` files (183 dispatches), **29% of
vendor dispatches failed** and **29% of review runs never reached a 2-vendor
quorum**. The two largest failure classes are invalid JSON (22) and timeouts (17).

Those failures are not mysterious:

- Only Grok is dispatched with `--json-schema`. Claude, Codex, Antigravity, and
  pi are prompt-only. The prompt `converge()` sends still asks for
  `id, type, criticality, description, disposition` — it never mentions the
  required `axis` and `severity` fields. A vendor that obeys the prompt is
  rejected by the validator. This was recorded as a defect on 2026-08-24 for
  `vendor_review.py`; that prompt was later derived from the schema.
  `build_review_prompt()` was not.
- Default timeout is 300s. Successful Claude reviews in the archive have
  p50 = 410s and p90 = 633s. Claude's failed-dispatch p50 is **exactly 300s**.
  `converge()` does not pass `timeout_seconds` through to `dispatch_and_wait()`.
- On parse or schema failure the dispatcher keeps a 500-character excerpt and
  drops the vendor. There is no repair retry, no alias coercion, and no raw
  stdout sidecar. pi has been rejected for invented enums
  (`completeness` / `testability`) that are iterate-on-plan axes, not
  review-findings types.
- `evidence_class` exists so model judgment does not gate, but ingest defaults
  to `deterministic`. Every LLM finding is treated as a reproducible observation.

Until a 4-vendor panel usually returns 3–4 valid documents, phases 2 and 3
(ledger-driven rounds, packed parallel review) are building on sand.

## What Changes

- Every review prompt (converge, plan/impl review skills, PR vendor review) is
  derived from `openspec/schemas/review-findings.schema.json` at dispatch time.
  Required fields and enums appear in the prompt. Hand-copied field lists are
  deleted.
- Parsed findings are **coerced then validated**: known type/axis aliases
  (`bug` → `correctness`, `completeness`/`testability` → axis + type) and
  missing `severity`/`criticality` cross-fills run before the hard schema check.
  Coercions are logged. The schema itself is not loosened.
- One **schema-repair retry** per vendor: on parse or validation failure,
  re-dispatch that vendor with the validator errors and "emit only the findings
  object." Do not re-run a full review. Then drop the vendor.
- Persist **full raw stdout/stderr** next to the findings file (not a 500-char
  excerpt). Sidecar is the forensic record for repair and postmortem.
- `converge()` passes a real timeout through to `dispatch_and_wait()`. Timeout
  is **per-vendor**, taken from a versioned budget table seeded with archive
  p90s (Claude/Grok ≈ 12 min, Codex ≈ 8 min, Antigravity ≈ 4 min), overridable.
- CLI model-review ingest sets `evidence_class=judgment`. Deterministic emitters
  (tests, linters, playwright-validator, gen-eval) keep `deterministic`.
- A timed-out, unparseable, or error-classified vendor is `degraded`, not a
  successful empty review. `findings: []` from a vendor that could not read
  artifacts does not count toward quorum.

No change to matching, blocking policy, round structure, or parallel dispatch.
Those are phases 2 and 3.

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| Resilience | Invalid-JSON + timeout share of archived-style fixture dispatches | ≤ 50% of the 2026-09-11 baseline (22+17 of 53 failures) | Evidence: replay harness against recorded manifests |
| Resilience | A 4-vendor panel with 1 timeout still synthesizes | `quorum_lost` is not returned when ≥2 vendors produced valid findings | Unit + fixture test |
| Observability | Raw stdout retained on every dispatch | Sidecar file exists for success and failure | Unit test on dispatcher write path |
| Compatibility | Existing valid findings documents | Still validate without coercion | Schema + synthesizer fixtures |
| Operability | `converge()` timeout is explicit | `dispatch_and_wait` receives a non-default timeout from `converge()` | Unit test |

## Approaches Considered

### Approach 1: Schema-derived prompt, coerce-then-validate, one repair, per-vendor timeout, judgment ingest

Keep the canonical schema strict. Make every prompt a projection of it. Coerce
known aliases, retry once with validator errors, keep raw stdout, give each
vendor a historically honest timeout, and stop treating LLM findings as
deterministic by default.

- **Pros**: Localized to dispatcher / prompt / converge; does not reopen matching
  or the round loop; fails closed after one repair; uses machinery that already
  exists (`vendor_review.py` schema derivation, `evidence_class`, fail-closed
  validation).
- **Cons**: Coercion can hide a vendor that is actually drifting; one retry adds
  latency on the failure path; per-vendor budgets can still be too short for a
  pathological repo walk (phase 3 packs the packet).
- **Effort**: M

### Approach 2: Loosen the schema and raise a global 900s timeout

Make `axis`/`severity` optional again and give every vendor 15 minutes.

- **Pros**: Smallest diff; immediately reduces both failure classes.
- **Cons**: Reverses ri-14 fail-closed validation; 900s × sequential vendors is
  an hour per round; does not fix prompt/schema drift, so vendors still emit
  incomparable documents; empty-success still poisons quorum.
- **Effort**: S

### Approach 3: Abandon CLI review; SDK JSON-mode only

Dispatch reviews only through SDK adapters with response_format/json_schema.

- **Pros**: Structured output is a first-class API feature; no stdout scraping.
- **Cons**: Drops Claude Code / Codex CLI / Grok CLI as reviewers; SDK coverage
  is review-only and incomplete (`build-structured-vendor-result-channel` /
  dg-02 already owns the broader cutover); does not help the CLI path that
  autopilot actually uses.
- **Effort**: L

### Recommended

**Approach 1.** The 2026-08-24 incident and the archive numbers are prompt/schema
and timeout bugs, not evidence that the schema is too strict or that CLI review
should be deleted. Approach 2 trades away the only thing that makes consensus
matchable. Approach 3 is dg-02's job and is too large for the bleeding.

### Selected Approach

Approach 1. Selected by the operator on 2026-09-11 when requesting proposals for
all three phases of the review-robustness plan. No modifications.

## Impact

- **Affected specs**: `skill-workflow` (MODIFIED timeout, dispatcher protocol,
  vendor-failure resilience, review-findings prompt contract; ADDED coercion,
  repair retry, raw-stdout sidecar, judgment ingest, per-vendor timeout budget).
- **Affected code**:
  - `skills/parallel-infrastructure/scripts/review_dispatcher.py`
  - `skills/parallel-infrastructure/scripts/review_findings_schema.py`
  - `skills/autopilot/scripts/convergence_loop.py` (`build_review_prompt`,
    `dispatch_and_wait` timeout)
  - `skills/parallel-review-plan/SKILL.md` and
    `skills/parallel-review-implementation/SKILL.md` (prompt construction)
  - `skills/merge-pull-requests/scripts/vendor_review.py` (already derives the
    prompt; align on the shared helper)
- **Related, not this change**: `ambient-review-ledger` (git-hook sensor),
  `rescope-review-convergence-disagreement-routing` (blocking policy),
  `build-structured-vendor-result-channel` / dg-02 (async regex polling,
  cloud lock release).
- **Breaking behavior**: none for valid findings documents. Invalid documents
  that previously died as `Invalid JSON output` may succeed after coercion or
  one repair. Empty `findings: []` from a classified error no longer counts as
  a successful review (**behavior change**, fail-closed for false consensus).
