# Design: add-decision-choices-ledger

## Context

All existing decision capture is self-reported by the implementing agent
(session-log `Decisions` bullets → `docs/decisions/` index) or finding-shaped
(review/consensus schemas, keyed on `axis`/`severity`/file location). Neither
can represent "a choice made where the spec was silent, judged independently."
This change adds that artifact and the auditor that produces it, following the
house precedent of a new schema per new record shape
(`validate-feature-findings-gate`) and the read-only reviewer posture
(`parallel-review-implementation`).

## Goals / Non-Goals

**Goals**

- An independent, read-only audit pass producing a per-change choices ledger.
- Human triage experience: one ranked file, least-confident first, standalone
  entries.
- Machine compatibility: schema-valid JSON with the codeviz artifact header,
  ingestible later by codeviz without rework.
- Zero perturbation of existing decision infrastructure (session-log format,
  `docs/decisions/` generation, drift gates).

**Non-Goals**

- No lifecycle machinery (open/addressed/retired) — a verdict is a judgment at
  a point in time, not a defect that auto-retires.
- No multi-vendor consensus over verdicts in v1 (single independent auditor;
  consensus is a natural follow-up if verdict quality warrants it).
- No GitHub issue sync, no kanban lane, no SSE events (compose with
  `ambient-review-ledger` later if both land).
- No write-back into session-log or the decision index.

## Decisions

- **D1: Separate `decision-choices.schema.json`, not an extension of
  `review-findings.schema.json`.** The review-findings validator requires
  `axis` and `severity` and its consumers (consensus synthesizer, review
  gates) assume code-anchored defects. Decision entries are intent-anchored.
  Precedent: `validate-feature-findings-gate` reached the same conclusion for
  validation findings.
- **D2: `choices.json` is the source of truth; `choices.md` is rendered from
  it.** A single writer makes the ranking invariant and header requirements
  unit-testable, and re-rendering is idempotent. The renderer is pure Python
  (no LLM), keeping the host-assisted invariant.
- **D3: Content-derived `stable_id`** — hash of (normalized choice headline +
  primary file set + gap text), mirroring the `ambient-review-ledger` wrapper
  pattern, so re-audits are idempotent and entries can be referenced stably
  from gate presentations.
- **D4: Artifact header copied verbatim from
  `skills/prioritize-proposals/scripts/artifact_header.py`** (module docstring
  sanctions this) with `generator: "audit-choices@1.0"`,
  `event_kind: "choices-ledger"`. When `skills/shared/artifact_header.py`
  ships (codeviz roadmap item `artifact-header-schema`), migration is a
  no-op on the on-disk format.
- **D5: Cross-reference-only linkage to self-reported decisions.** The auditor
  resolves `session-log.md` `Decisions` bullets (and `handoffs/*.json`
  payloads when present) to `<change-id>#D<n>` refs; unmatched audit entries
  get `self_reported: false`. The auditor never writes to session-log or
  `docs/decisions/` — those files are producer-owned and CI-diff-enforced;
  writing there breaks the deterministic drift gates.
- **D6: Non-blocking by construction.** The auditor exits 0 always; workflow
  hooks wrap the invocation in a warn-and-continue guard. `needs-user`
  verdicts reach humans only through existing gates (`validate-feature`,
  `cleanup-feature`), reusing the deferred-tasks surfacing pattern — no new
  gate is introduced.
- **D7: Auditor dispatched as a read-only reviewer archetype.** The SKILL
  dispatches one independent sub-agent (provider-neutral dispatch path where
  available) whose prompt receives the evidence bundle (commit log, diff
  stats, artifact excerpts) and whose contract forbids file modification;
  the harness-side writer script — not the sub-agent — persists the ledger
  after validating the returned entries. This keeps LLM calls out of skill
  Python (host-assisted invariant) and file writes out of the LLM's hands.
- **D8: The artifact is registered as `optional: true`** in
  `feature-workflow/schema.yaml` with `requires: [tasks]`, matching
  `session-log`'s posture: valuable when present, never load-bearing for
  validation or archive.

## Fitness Functions

| NFR | Verifying check | Status |
|-----|-----------------|--------|
| `make decisions` zero-diff after audit run | existing CI decisions freshness gate | existing |
| Auditor writes confined to ledger pair | new skill test using working-tree snapshot diff | new |
| Exit 0 with adverse verdicts | new unit test on the audit driver | new |
| Header completeness in `choices.json` | new jsonschema validation test | new |
| Ascending-confidence ordering in `choices.md` | new renderer unit test | new |

## Alternatives Considered

- **Annotate session-log decisions in place** — rejected: cannot represent
  unreported decisions (the highest-value signal) and churns the
  parser/sanitizer contract every workflow skill depends on.
- **Store choices in the planned `.review-ledger/` substrate** — rejected:
  blocks on a 0/33 change; lifecycle semantics mismatch (choices do not
  auto-retire).
- **Multi-vendor consensus on verdicts in v1** — deferred: triples audit cost
  before we know single-auditor verdict quality; the schema's `stable_id` and
  per-entry structure leave room for a `vendor_verdicts` extension later.

## Risks / Trade-offs

- **Fourth decision-adjacent store.** Mitigated by mandatory cross-refs /
  `self_reported` flags and a positioning note in the generated decision-index
  README (edited at its producer, not the generated file).
- **Nominal lock overlap with `ambient-review-ledger`'s planned packages.**
  That change reserved `contract:review-findings`; we do not touch that file.
  Our namespace is `contract:decision-choices` and `.` — flagged here so the
  eventual implementer of ambient-review-ledger sees no surprise.
- **Auditor hallucinating decisions.** The writer script validates every entry
  against the schema and drops entries whose cited commits/files do not exist
  in the range; the ledger records the evidence pointers so a human can verify
  each claim in one click.
- **Prompt-injection via audited diff content.** The auditor is read-only and
  its output passes through schema validation before persistence; entries are
  data, never executed instructions.

## Migration Plan

Purely additive. No existing artifact changes shape. Rollout: land schema +
skill, run `/audit-choices` against one recently archived change as a fixture
check, then enable the `iterate-on-implementation` hook (a one-line step
addition that is trivially revertable). Rollback is deleting the hook lines;
ledger files already written remain valid standalone artifacts.
