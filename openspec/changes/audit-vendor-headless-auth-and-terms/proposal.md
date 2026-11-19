# Audit vendor headless auth and terms

> Parent roadmap: `sandboxed-flow`
> Change ID: `audit-vendor-headless-auth-and-terms`
> Effort: S
> Priority: 1

## Why

The roadmap moves vendor CLIs (`claude`, `codex`, `agy`, `grok`) into
sandboxes and wants them to keep using subscription logins where that is
allowed. Two later items depend on facts nobody has written down: the
credential profile (`add-per-vendor-credential-profile`, ri-03) needs to know
which file each CLI reads, whether refresh rewrites it and which hosts it
contacts; the lane decisions need to know what each vendor's terms say about
unattended use.

The repository holds one statement on the subject and it is wrong.
`docs/proposals/factory-local-cloud-split.md` says the Claude review lane uses
an API key "in line with the subscription terms", and that Codex, Gemini and
opencode "permit programmatic CLI use", without a source for either.
`openspec/roadmaps/sandboxed-flow/claude-auth-strategy.md` replaced the Claude
half with quoted terms, but its quotes came through a summarising fetch tool
and were never checked against the pages.

## What Changes

- Add `docs/guides/vendor-auth-audit.yaml`: one record per vendor with a
  verdict per lane (interactive, attended headless dispatch, unattended
  daemon, CI), the governing sentence, its source and retrieval date, and the
  four mechanics fields (credential material, refresh-write requirement,
  inference and auth hosts, proxy or base-URL override). Each mechanics field
  carries an evidence level: `observed`, `documented` or `not_observed`.
- Add `docs/guides/vendor-auth-audit.md`: the same content for a reader, the
  method, and what is still unverified.
- Re-verify every quote in `claude-auth-strategy.md` against the live page and
  correct those that differ.
- Add `skills/vendor-status/scripts/observe_vendor_auth.py`: run on an
  operator host, it reports which credential paths exist, their modes and
  modification times around a CLI run, and never reads their content. Its
  output is what turns a `documented` field into an `observed` one.
- Correct the Claude review-lane statement and the subscription-terms risk in
  `docs/proposals/factory-local-cloud-split.md`.
- Add tests that hold the table to its invariants.

## Assumptions

- **Observation cannot happen where this change is written.** The cloud
  container has `claude` only; `codex`, `agy` and `grok` are not installed, no
  CLI is logged in with a subscription, and no operator machine is attached.
  Mechanics fields are therefore recorded from vendor documentation with
  evidence `documented`, and the acceptance outcome "recorded from an observed
  run" stays open until the operator runs the observation script on a host.
  The roadmap item is not marked completed before that.
- Vendor terms are read as published on the retrieval date. The table records
  that date; it is not legal advice and the terms change.
- "Unaddressed" is a finding, not a gap to fill by inference. A lane the terms
  do not mention is recorded as `unaddressed` with the pages searched.

## Approaches Considered

### A. Prose document only

One markdown guide with a table per vendor.

- Pros: least work; easy to read.
- Cons: ri-03 would parse prose or copy values by hand; nothing stops a lane
  from being marked permitted without a quote.
- Effort: S

### B. Machine-readable table plus guide, with evidence levels (Recommended)

A YAML table is the source; the guide explains it; tests enforce that every
verdict has a quote and source, that unattended lanes without a `permitted`
verdict name an API-key or gateway-key lane, and that `observed` is claimed
only with a host and date.

- Pros: ri-03 and the token-injection spike read one file; the difference
  between documented and observed is explicit and testable; partial
  completion is honest.
- Cons: two files to keep in step (a test checks the guide names every
  vendor and lane).
- Effort: S

### C. Extend `agent-coordinator/agents.yaml`

Put terms and mechanics on each agent entry.

- Pros: one place for vendor facts.
- Cons: `agents.yaml` is runtime configuration loaded by the coordinator; the
  audit is evidence with quotes and dates, and changing the schema is ri-03's
  job once it knows what it needs.
- Effort: M

**Selected: B.** The operator approved this item with the roadmap; the choice
between A and B does not change its outcomes.

## Impact

- New: `docs/guides/vendor-auth-audit.yaml`, `docs/guides/vendor-auth-audit.md`,
  `skills/vendor-status/scripts/observe_vendor_auth.py`, tests under
  `skills/tests/vendor-status/`.
- Changed: `openspec/roadmaps/sandboxed-flow/claude-auth-strategy.md`,
  `docs/proposals/factory-local-cloud-split.md`, `docs/guides/documentation.md`.
- No coordinator code, no runtime behaviour.

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by |
|---|---|---|---|
| Confidentiality | Credential bytes read by the observation script | 0 | Unit test with a file whose content must not appear in output |
| Traceability | Verdicts with a quote and source, or a list of pages searched | 100% | Table test |
