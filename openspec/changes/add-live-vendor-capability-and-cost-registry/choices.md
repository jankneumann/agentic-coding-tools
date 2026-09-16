# Choices Ledger: add-live-vendor-capability-and-cost-registry

<!-- GENERATED from choices.json by the audit-choices skill. Do not hand-edit —
     edits made here are discarded the next time the ledger is rendered.
     choices.json is the source of truth; this file is a rendering of it.
     Produced by an independent, read-only auditor pass — never hand-authored
     during planning or implementation. -->

**Generated**: 2026-09-16T19:42:54Z
**Audited range**: 973fa03434606c1bc87558d9147a4070b44dcdf1..b4f2840d668fe38798fdd5fd291a5456d5f2c90b

<!-- Entries are ordered least-confident first (low, then medium, then high);
     within equal confidence, needs-user before unsound before sound. This is
     a rendering invariant enforced by the renderer, not editable here. -->

## Entries

### Quantize quoted USD to six decimal places using explicit ROUND_HALF_UP, including rounding exact half-microdollar values upward.

**Confidence**: high · **Verdict**: sound

#### The choice

Quantize quoted USD to six decimal places using explicit ROUND_HALF_UP, including rounding exact half-microdollar values upward.

#### Scenario

A request-scoped quote computes a decimal USD value exactly halfway between two six-decimal values.

#### The gap

The design requires decimal arithmetic and six-place rounding but does not specify a tie-breaking mode.

#### The reach

All request-scoped exact-model USD quotes at a six-decimal tie boundary; ordinary non-tie values are unaffected.

#### Verdict

sound — An explicit rounding mode is necessary for deterministic six-place results. ROUND_HALF_UP is a conventional monetary tie rule, preserves the required decimal calculation, and avoids behavior changing with the ambient Decimal context. The choice is narrowly scoped and guarded by a named boundary test. It should be documented as part of the quote contract because clients may observe the final microdollar digit.

#### Confidence

high

#### Provenance

- **Commits**: `b4f2840d668fe38798fdd5fd291a5456d5f2c90b`
- **Files**: `agent-coordinator/src/vendor_registry.py`, `agent-coordinator/tests/test_vendor_registry.py`

#### Self-reported

Not self-reported — the auditor found this decision without a matching `Decisions` entry in `session-log.md`.

---
