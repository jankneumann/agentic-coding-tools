# Design: add-deterministic-review-preprocessing

## Context

`review_packet.py` renders one markdown body from a full `git diff`, spec
excerpts, the schema-derived prompt contract, and open ledger items, then fits
it to a 320k-character budget by dropping excerpts, slicing the diff tail, and
finally hard-slicing. Nothing upstream decides which files deserve to be in the
packet, nothing records what fell off the end, and every vendor gets the same
blind spot. At ingest, `_ingest_stdout` parses, coerces, validates, stamps
`judgment`, and rejects placeholder-only output. Consensus scores line overlap
at 0.95 and falls back to description Jaccard; the ledger fingerprints on a
description token set and `compact()` re-verifies by token presence.

Open Code Review (OCR) solves the same problems with pure code: a five-gate
selection with reasons, a preview that shares the selection function, glob rule
resolution, a verbatim `existing_code` anchor resolved by a hunk-side sliding
window, a fact-check pass that removes only diff-disproven comments with
protected subjects, and a coverage manifest. All of it is Apache-2.0.

Constraints that shape this design: the coordinated tier means packages must
have non-overlapping `write_allow` unless ordered by `depends_on`; the ruff rule
set in `skills/pyproject.toml` is pinned; sidecars carry `schema_version` and a
byte-identical `install_assets` mirror; new tests under `scripts/tests/` are
already in the CI isolated-process loop; `ambient-review-ledger` is planned but
unstarted and rebases onto this change.

## Goals / Non-Goals

**Goals**

- No changed file leaves the packet without a recorded reason.
- Findings anchor on a verbatim snippet, resolved by code, not by the model.
- Provably wrong findings are removed before synthesis, never silently.
- Vendor coverage is visible and limits quorum where it is partial.
- OCR contributes as an optional, independently architected reviewer.
- Every effect is measurable on a committed fixture set before archival.

**Non-goals**

- LLM-driven or directory-based file grouping and per-group fan-out.
- OCR's default test-file exclusions or its extension allowlist as-is.
- Changing round-two packet scope from last-fix diff.
- Model-based relocation of unmatched snippets (OCR's `RE_LOCATION_TASK`).
- The `.review-ledger/` lifecycle, hooks, and `refine_core.py` extraction.

## Decisions

### D1: Selection is one pure function with an ordered reason enum

`file_selection.select_files(diffs, rules, *, per_file_token_ceiling)` returns
one `FileDecision(path, status, reason, gate, est_tokens)` per input diff, in
input order. Gate order is fixed: `binary`, `user_exclude`, `user_include`
(keep and stop), `generated_path`, `deleted`, `too_large`. Reason enum:
`none, binary, user_exclude, generated_path, deleted, too_large`. Deleted files
stay in the change-file list shown to reviewers but carry no diff. The default
generated-path list lives in `review-rules.json` beside the code so a project
can extend it; the embedded list covers lockfiles, `vendor/`, `node_modules/`,
`__snapshots__/`, `*.generated.*`, `*.pb.*`, minified bundles, and
`.review-cache/`. It deliberately omits test-file patterns: this repository
reviews tests.

Why one function: OCR's `--preview` drifted from its run until the two were
forced through `selectFiles` (their issue #782). Preview parity is a test here,
not a convention.

### D2: Token estimate is a stdlib heuristic, applied per file

`est_tokens = ceil(len(text) / 4)` for the diff body, with a documented note
that it is a floor. The per-file ceiling is 80% of `BUDGET_CHARS / 4`. Exact
tokenization would need a dependency and vendor-specific tables; the estimate
only has to decide "this one file cannot fit" and is reported, so a reviewer of
the manifest sees the number the gate used. Truncation of the remaining set
keeps today's ladder but records `selection.truncated` paths in the meta.

### D3: Snippet resolver ported from `resolver.go`, no model fallback

`line_resolver.resolve(finding, packet_diff, file_text=None)` parses hunks
with the `@@ -a,b +c,d @@` regex, builds new-side and old-side indexed line
lists, normalizes each line by stripping whitespace and a leading `+` or `-`,
drops blank lines from the target, and scans for a consecutive run. Order:
new side per hunk, old side per hunk, then full file with blank lines skipped.
Result sets `line_range` and `line_resolution` in
`{hunk_new, hunk_old, file, unresolved}`; a vendor-supplied non-zero range is
kept with `line_resolution: vendor`. Unresolved findings stay in the payload.
OCR's model-based relocation is not ported: it costs a call per miss and the
fixture set will tell us whether the miss rate justifies it later.

### D4: Rule layers and grouping key

`review_rules.resolve(path)` walks two layers: `<repo>/.review-rules.json`
then the embedded default. Entries are `{path: glob, rule: text}` in
declaration order; first match wins within a layer; a project match beats any
default match. Globs use `fnmatch` with `**` support from the existing
`scope_overlap` primitives, case-insensitive on the lowercased path. Files are
grouped by `(source, pattern, text)` so provenance is exact per group. The
sidecar also carries the `include`, `exclude`, and `generated_paths` lists the
selection gate reads, so one file configures pre-processing.

The embedded default ships rules for this repository's file classes: skill
markdown, skill scripts, coordinator YAML, OpenSpec artifacts, GitHub
workflows, JSON schemas, and a fallback. Rule text is short and points at the
axis contract rather than restating it.

### D5: Coverage is advisory on the payload, binding in the manifest

Vendors are asked in the prompt contract to emit `coverage`, but the field is
optional. The dispatcher computes `coverage_rate = |reviewed ∩ selected| /
|selected|`. Below `0.8` (contracted in the sidecar as
`coverage_quorum_threshold`) the vendor is marked `coverage_eligibility:
partial` and the synthesizer skips it in the quorum count for findings whose
`file_path` is not in its `reviewed` list. Absent coverage is full coverage
with `coverage: unreported`, so no existing vendor loses quorum because of a
field it never emitted. This mirrors the placeholder-only rule: the dispatcher
decides eligibility, the synthesizer honors it.

### D6: Fact-check runs after checkpoint, before synthesis, on the economy tier

`fact_check.run(vendor, findings, packet_diff, *, model_spec, timeout)`
renders the ported review-filter prompt with the packet diff and the vendor's
validated findings, calls the vendor's economy tier resolved through
`resolve_tier_for_provider(vendor, "economy")` using the same CLI or SDK
adapter as review mode, and parses a single tool-style answer: either
`approve_all` or a list of `{finding_id, ground, evidence_line}`. The pass
then applies the protected-subject veto by keyword class on the finding's
description and axis before honoring any removal, and writes
`fact-check-decisions.json` in the round directory with every candidate,
the verdict, and `vetoed` where applicable. Any error, timeout, or unparsable
answer removes nothing and records `fact_check: skipped`.

Sequencing in `converge()`: dispatch → `_checkpoint_result` (raw) →
fact-check per successful result → filtered results into `synthesize()`.
The checkpointed vendor file is never rewritten. Tokens from the pass are added
to the round budget and to the vendor's manifest entry as `fact_check_tokens`.
The pass is on by default with `fact_check=False` available on `converge()`
for A/B runs against the fixture set.

### D7: OCR enters through an adapter script, not a dispatcher branch

`agents.yaml` gains an `ocr-local` agent whose review-mode command is
`python3 skills/parallel-infrastructure/scripts/ocr_adapter.py`. The adapter
runs `ocr review --format json --audience agent --output <tmp> --from <base>
--to <head>` with base and head taken from the packet meta, then rewrites
OCR's `comments[]` into a review-findings payload: `path` to `file_path`,
`content` to `description`, `existing_code` carried through, `start_line` and
`end_line` to `line_range` unless both are zero, `category` and `severity`
left for the coercion sidecar. It exits non-zero with OCR's stderr when the
binary or its LLM config is missing so discovery classifies it as unavailable.
`can_dispatch` for the agent checks the binary on PATH and `OCR_LLM_URL` or
an `ocr config` file. No branch is added to `CliVendorAdapter`; the generic
stdout path ingests the adapter's JSON. Coercion aliases added:
`maintainability → architecture`, `test → correctness`,
`documentation → style`, `other → style`, and OCR severities
`critical/high → critical`, `medium → nit`, `low → optional` with the
reverse criticality fill.

### D8: Fixture set is real diffs with hand labels

`skills/tests/parallel-infrastructure/fixtures/review-fixtures/manifest.json`
lists cases: a diff file, a findings payload with `existing_code`, and per
finding `label: true|false` with a justification. Sources are past
`.review-cache` rounds and archived changes, scrubbed of paths outside the
repo. Two tests consume it: `test_fact_check_fixture.py` asserts zero
labeled-true removals and at least half of labeled-false removals when the
pass runs against a recorded fact-check transcript (so CI needs no model), and
`test_line_resolver_fixture.py` asserts the 90% resolution floor. A recorded
transcript, not a live call, keeps CI deterministic; the live run is a
validation-phase step whose output is committed to the validation report.

### D9: Delivery order follows the operator's Gate 1 choice

Fact-check and the OCR vendor are the first implementation packages because
they attack the false-positive pain directly and touch no file the ports
touch. Packet selection and rules run in parallel with them. The resolver,
matching and ledger, and coverage follow in a dependency chain on the shared
dispatcher and synthesizer files.

### D10: Attribution

Each ported module opens with a comment naming the upstream file in
`alibaba/open-code-review`, its Apache-2.0 license, and the commit read on
2026-09-14. The fact-check prompt file carries the same header. No upstream
code is vendored verbatim; the algorithms are re-expressed in Python.

### Fitness Functions

| NFR (from proposal.md) | Verifying check | Status |
|------------------------|-----------------|--------|
| Observability: every excluded path in meta and manifest with a reason; zero unrecorded drops | `scripts/tests/test_file_selection.py::test_no_file_without_reason` over a fixture diff whose size forces exclusion | new |
| Observability: preview parity, byte-identical decisions | `skills/tests/parallel-infrastructure/test_review_packet.py::test_preview_matches_build` | new |
| Correctness: line resolution 90% or better on fixtures; unresolved kept | `skills/tests/parallel-infrastructure/test_line_resolver_fixture.py` | new |
| Correctness: fact-check precision, zero true removed, half of false removed | `skills/tests/parallel-infrastructure/test_fact_check_fixture.py` against recorded transcript; live figure in validation report | new |
| Resilience: fact-check failure removes nothing | `scripts/tests/test_fact_check.py::test_error_removes_nothing` with a failing stub adapter | new |
| Performance: round token spend rises at most 15% on the fixture diff | Validation-phase timed run, both `fact_check` on and off, recorded in `validation-report.md` | new, deferred to validation phase because it needs live vendors |
| Compatibility: findings without new fields validate and synthesize unchanged | Existing `test_review_findings_schema*.py`, `test_consensus_synthesizer.py`, `test_review_ledger.py` stay green | existing |
| Compatibility: OCR absent leaves dispatch unchanged | `scripts/tests/test_review_dispatcher.py::test_ocr_absent_is_tier3` with PATH stubbed | new |
| Operability: sidecar and mirror byte-identical | `skills/install.sh --check` in CI plus `skills/tests/install_sh/test_openspec_assets.py` | existing |

## Alternatives Considered

- **Shell out to `ocr delegate preview` and `ocr delegate rule`** for selection
  and rules. Rejected: puts a Go binary on the core path that cloud containers
  lack, delegate mode does not expose the resolver or the review filter, and
  OCR's defaults exclude tests.
- **Model-based relocation on resolver miss.** Deferred: one call per miss;
  measure the miss rate on fixtures first.
- **Coverage as a hard gate that fails the vendor.** Rejected: a vendor that
  reviewed eight of ten files still has eight files of signal; partial
  eligibility keeps it.
- **Fact-check on the premium tier.** Rejected by the operator: economy tier,
  counted in the round budget.
- **Bump the packet metadata contract in place.** Rejected: the archived
  contract has `additionalProperties: false` and `schema_version const 1`; a
  new contract with `schema_version: 2` supersedes it and the existing contract
  test is repointed.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Token heuristic under-counts and a file that should be `too_large` slips through, then gets tail-truncated | Truncated paths are recorded in `selection.truncated`; the heuristic is a documented floor; ceiling is 80% of budget |
| Fact-check removes a true finding on a subject outside the protected list | Decision file records every removal with the disproving line; fixture test fails on any labeled-true removal; `fact_check=False` switch for A/B |
| Snippet fingerprint changes ids for existing ledgers | Fingerprint falls back to the token set when no snippet is present; existing items have none, so ids are unchanged |
| `ambient-review-ledger` starts before this lands and edits the same schema | Additive fields only; its plan is rebased, per the operator's sequencing decision |
| OCR needs an LLM endpoint the operator has not configured | Vendor is Tier-1 only when config is present; absence is a skip, not a failure |
| Vendors ignore the `coverage` request | Absent coverage is full coverage; the field is a prompt-contract request, not a schema requirement |
| Existing `test_review_packet_schema.py` resolves the archived contract with `additionalProperties: false` | The test is repointed to this change's contract via `openspec_paths.change_dir` in the packet package |
| Dispatcher and synthesizer edited by three packages | Chained by `depends_on`; the validator permits overlap only along dependency edges |

## Migration Plan

Rollout is additive and switchable. Order of landing: contracts; fact-check
and OCR vendor and packet selection in parallel; resolver; matching and
ledger; coverage; fixtures; integration. Each package leaves the suite green.
`converge(fact_check=True)` is the default once the fixture test passes; the
validation phase records the live precision figure and the token delta.

Rollback: set `fact_check=False`, remove the `ocr-local` block from
`agents.yaml`, and the pipeline behaves as before except that packets carry
selection meta and findings may carry `existing_code`, both of which every
consumer ignores when absent. No data migration: ledgers without snippets keep
their fingerprints.
