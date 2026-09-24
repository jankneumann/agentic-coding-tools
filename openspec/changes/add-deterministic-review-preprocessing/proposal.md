# Change: add-deterministic-review-preprocessing

**Series**: multi-vendor review robustness (phase 4)
**Depends on**: `pack-and-parallelize-vendor-review` (archived; supplies `review_packet.py`) and `ledger-driven-review-convergence` (archived, PR #531; supplies `review_ledger.py` fingerprint and compact)
**Lands before**: `ambient-review-ledger` (planned only, 0/33 tasks, no branch; PR #195 merged its plan, not code. It rebases onto the schema field and ledger fingerprint added here)
**Related, not blocked on**: `build-structured-vendor-result-channel` (dg-02), `rescope-review-convergence-disagreement-routing` (ri-16), `measure-validator-recall-seeded-defects` (ri-06)

## Why

Alibaba's Open Code Review (OCR, `alibaba/open-code-review`, Apache-2.0) gets
its precision from a split we do not have: every review step that must not go
wrong runs as pure, previewable code, and only judgment goes to the model. Our
pipeline has strong deterministic *post*-processing across vendors (consensus,
ledger, evidence class) but almost no deterministic *pre*-processing.
`review_packet.py` ships one whole `git diff`, fits it to a character budget,
and slices the tail when it overflows. The files that get cut are whichever
sort last in git's output, no manifest records them, and a vendor that never
saw a file is indistinguishable from one that reviewed it and found nothing.

Two pains named by the operator triggered this change. On large branches,
truncated packets hide files from every vendor at once. And convergence rounds
burn on judgment findings that a diff-level fact check would have removed
before synthesis: our only false-positive defence today is cross-vendor
agreement, which ri-16 already argues is not a proxy for correctness. OCR's
line-anchoring also attacks a third, quieter loss: our consensus matcher scores
on line overlap, so when vendors cite drifted lines for the same defect, a real
agreement degrades to two "unconfirmed" findings.

## What Changes

- **Deterministic file selection with named exclusion reasons.** A pure
  `select_files(diffs, rules) -> [FileDecision]` gate runs before the packet is
  rendered. Gates in order: binary, user exclude, user include, generated or
  vendored path patterns, per-file token ceiling (`too_large`). Every decision
  carries a reason. The packet meta and the round manifest list excluded files
  with reasons. A `--preview` mode prints the same decisions without dispatch,
  and preview and run consume one function so they cannot drift. The character
  budget tail-slice becomes the last resort, never the first.
- **`existing_code` anchor and ingest-time line resolver.** The findings schema
  gains an optional verbatim-snippet field. At ingest, before synthesis, a pure
  resolver parses the packet's hunks, normalizes whitespace and diff markers,
  and matches the snippet on the new side, then the old side, then the full
  file, filling `line_range`. Zero lines means unanchored, and the finding is
  kept. The ledger fingerprint prefers path plus snippet over the description
  token set, and `compact()` re-verifies an open item by snippet presence.
- **Path-glob rule groups in the packet.** A `review-rules.json` sidecar maps
  globs to checklist text in declaration order, with a project layer over an
  embedded default layer. Files sharing a rule appear under one group in the
  packet. The eight-axis contract stays schema-derived and unchanged; rules add
  focus, they do not replace the contract.
- **Per-vendor coverage as a sealed contract.** Each vendor result carries a
  coverage block: files reviewed, files skipped with reason, coverage rate.
  The dispatcher treats coverage below a threshold the way it treats
  placeholder-only output: the vendor is not eligible for quorum on the
  uncovered files, and the round manifest records it.
- **Fact-check pass before synthesis.** Per vendor, one economy-tier model call
  over the packet diff and that vendor's findings removes only findings the diff
  proves wrong on two grounds: the described code is absent from the subject
  file's diff, or a diff line literally contradicts the central claim. Protected
  subjects (memory safety, concurrency, declaration consistency, behavioral
  change, unused parameters) are never removed. Every removal is logged with the
  disproving line. Its tokens count against the round budget.
- **OCR registered as an optional reviewer vendor.** An `ocr` CLI adapter in
  `agents.yaml` with Tier-1 discovery only when the binary is on PATH; a
  coercion table mapping OCR's category and severity enums onto ours; OCR
  findings arrive with resolved lines and `existing_code` already populated.
  It is a different architecture rather than a different model, which is the
  diversity consensus exists to exploit. Never required on the core path.
- **Labeled fixture set for measurement.** Ten to fifteen findings over real
  diffs from `.review-cache` history, labeled true or false, committed as a
  manifest. The fact-check pass and the resolver report precision against it
  in the change's validation report. This is a floor for archival, not a
  substitute for ri-06.

No **BREAKING** changes. Every schema addition is optional with a default that
leaves existing emitters valid. Existing packets without rule groups or
selection meta still build. Vendors that do not emit coverage are treated as
full coverage with a `coverage: unreported` manifest note, so no vendor is
dropped from quorum by the absence of a field it never had.

Non-goals: LLM-driven file grouping (per-package mode already groups from
`work-packages.yaml`); whole-branch directory grouping and per-group fan-out;
OCR's default test-file exclusions (we review tests); changing the round-two
last-fix-diff scope (recorded as an open question for a follow-up); the
`.review-ledger/` lifecycle owned by `ambient-review-ledger`.

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| Observability | Files excluded from a packet | Every excluded path appears in `review-packet.meta.json` and the round manifest with a reason enum; zero files dropped without a reason | Unit test over a fixture diff whose size forces exclusion |
| Observability | Preview parity | `--preview` and a real build produce byte-identical selection decisions for the same inputs | Unit test asserting both paths call one function and compare equal |
| Correctness | Line resolution | On the labeled fixture set, findings carrying `existing_code` resolve to a non-zero `line_range` at 90% or better; unresolved findings are kept with `line_range` absent | Fixture test in `scripts/tests/` |
| Correctness | Fact-check precision | On the labeled fixture set, zero true findings removed; at least half of the labeled false findings removed | Fixture test plus a recorded validation report |
| Resilience | Fact-check unavailable | Model call error or timeout removes nothing and logs `fact_check.skipped`; synthesis proceeds | Unit test with a failing stub |
| Performance | Round token spend | Fact-check tokens are reported in the round manifest; total round spend on the fixture diff rises by no more than 15% over the pre-change baseline | Timed fixture run recorded in the validation report |
| Compatibility | Existing findings | Findings without `existing_code` or `coverage` validate and synthesize unchanged | Existing dispatcher and synthesizer tests stay green |
| Compatibility | OCR absent | Roster without `ocr` on PATH dispatches exactly as today; no warning beyond the existing Tier-3 skip line | Unit test with PATH stubbed |
| Operability | Rule sidecar drift | `review-rules.json` beside the module and its `install_assets` mirror are byte-identical | `install.sh --check` plus existing mirror parity test |

## Approaches Considered

### Approach 1: Port the deterministic stages as pure Python, register OCR as an optional vendor

Reimplement OCR's five-gate selection, hunk parser and sliding-window resolver,
rule-group resolution, and coverage contract as stdlib-only functions inside
`skills/parallel-infrastructure/scripts/`. Port the review-filter prompt as a
fact-check pass wired into the dispatcher's ingest path. Add an `ocr` adapter
that is discovered only when the binary exists.

- **Pros**: No binary on the core path; preview and run share one function by
  construction; every piece is a pure function with fixture tests; the resolver
  also fixes the ledger fingerprint and compact re-verification, which no
  shell-out could reach; OCR still contributes as an independent architecture
  when installed.
- **Cons**: About 600 lines of ported logic to own and test; the rule-doc
  library is ours to write for our file classes rather than OCR's 45 languages;
  fact-check adds one model call per vendor per round.
- **Effort**: L, decomposed into five M-sized packages that parallelize.

### Approach 2: Shell out to `ocr delegate` for selection and rules, port the rest

Use `ocr delegate preview --format json` and `ocr delegate rule` as the
packet's selection and rule stages. Implement the resolver, coverage, and
fact-check ourselves.

- **Pros**: Selection and 45-language rule library maintained upstream; the
  JSON contract carries `schema_version`; less code to port.
- **Cons**: Puts an npm-installed Go binary on the core review path, which
  cloud harness containers do not carry today; delegate mode does not expose
  the resolver or the review filter, so more than half the change is ported
  anyway; OCR's default test-file exclusions and extension allowlist need
  per-repo overrides to match our conventions; a version skew between the
  installed binary and our parser becomes a new failure class the dispatcher
  already spent a phase eliminating for vendor CLIs.
- **Effort**: M plus an operational dependency.

### Approach 3: Route review through OCR's full engine as the single deterministic reviewer

Run `ocr review --format json` as the review step, ingest its output as the
findings, and retire the packet builder for implementation reviews.

- **Pros**: All of OCR's engineering at once, including grouping, plan phase,
  relocation fallback, and session replay; least code to write.
- **Cons**: Single-vendor by design; abandons consensus, the ledger, evidence
  class, and per-package scope checking that the spec requires; OCR's own
  benchmark trades recall for precision, which is the opposite of what a
  validator gate wants; plan reviews have no diff, so the plan path would need
  a second pipeline.
- **Effort**: M to wire, XL to recover what it removes.

### Recommended

**Approach 1.** The operator's constraint set allows binaries and new
dependencies, but the reasons to port outweigh convenience: the resolver is the
item that pays off three times (matching, fingerprint, compact), and delegate
mode cannot supply it. Approach 2 would still port most of the logic while
adding a runtime dependency. Approach 3 is a different product.

### Selected Approach

Approach 1, selected by the operator on 2026-09-14 at Gate 1, with one
modification to delivery order: the fact-check pass and the OCR vendor adapter
land first because they attack the false-positive pain directly, and the
deterministic ports (selection, resolver, rule groups, coverage) follow. The
work packages and task phases below are ordered accordingly. No change to
scope.

## Impact

- **Affected specs**: `skill-workflow`. MODIFIED: Review Packet As Default
  Input (selection meta and rule groups), Review Findings Schema Extension
  (`existing_code`, `coverage`), Finding Coercion Before Validation (resolver
  and fact-check run at ingest), Cross-Vendor Finding Matching (snippet
  equality band), Gate-Time Review Ledger and Compact Before New Hunt
  (snippet fingerprint and presence check), Review Manifest Generation
  (exclusions, coverage, fact-check removals). ADDED: Deterministic File
  Selection, Ingest-Time Line Resolution, Path-Glob Rule Groups, Per-Vendor
  Coverage Contract, Diff-Grounded Fact Check, Optional OCR Reviewer.
  `review-convergence-safety`: MODIFIED Terminal vendor results are
  checkpointed incrementally (coverage in the manifest).
- **Affected code**:
  - `skills/parallel-infrastructure/scripts/review_packet.py` (selection,
    rule groups, per-file token count, preview)
  - new `skills/parallel-infrastructure/scripts/file_selection.py`,
    `line_resolver.py`, `review_rules.py`, `fact_check.py`
  - `skills/parallel-infrastructure/scripts/review_dispatcher.py` (resolver
    and fact-check at ingest, coverage eligibility, `ocr` adapter)
  - `skills/parallel-infrastructure/scripts/consensus_synthesizer.py`
    (snippet-equality match band)
  - `skills/parallel-infrastructure/scripts/review_ledger.py` (fingerprint,
    compact)
  - `openspec/schemas/review-findings.schema.json` and its
    `install_assets` mirror (`existing_code`, `coverage`)
  - new sidecar `review-rules.json` plus mirror; `finding-coercion.json`
    gains OCR aliases
  - `agent-coordinator/agents.yaml` (`ocr` vendor, review mode only)
  - `skills/autopilot/scripts/convergence_loop.py` (pass fact-check option,
    read coverage from manifest)
  - `skills/tests/parallel-infrastructure/fixtures/review-fixtures/`
    (labeled fixture manifest)
- **Architecture layers**: Execution (packet, dispatcher) and Trust (evidence
  and coverage gating). Governance untouched.
- **Sequencing**: This change lands before `ambient-review-ledger`, which
  rebases its schema edit and `refine_core.py` extraction onto the field and
  fingerprint added here. Additive edits only, so the reverse order also
  merges. `agents.yaml` edits are confined to a new `ocr` block to keep
  textual distance from `add-adaptive-model-router` and
  `cross-vendor-arbitrage-instrument`.
- **Attribution**: Ported algorithms and the fact-check prompt derive from
  `alibaba/open-code-review` (Apache-2.0). Each ported module carries the
  upstream file reference and license notice.
