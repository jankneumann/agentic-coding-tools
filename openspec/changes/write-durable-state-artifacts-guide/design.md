# Design: Canonical Durable State-Artifact Documentation

## Context

State is intentionally split by altitude and purpose. The split is safe only when readers know which artifact is authoritative for which question and when advisory transport must be verified against canonical files. Today that knowledge is distributed across long skill documents. Ri-07 fixed an analogous ambiguity between `loop-state.json` and the work queue; ri-10 applies the same truth/projection principle across rehydration artifacts.

## Decisions

### D1 — One normative inventory

`docs/guides/state-artifacts.md` owns the shared table of artifact path, scope/holder, writer, authority, consumers, and missing/stale behavior. Skill docs retain only phase-local procedures and link to the guide for shared semantics.

Alternative rejected: keeping full duplicated tables in each skill, because copies have independent release cadence and no reliable conflict signal.

### D2 — Authority is question-scoped

The guide will not name one global state file. `loop-state.json` answers the current Autopilot phase for one change; roadmap `checkpoint.json` answers the current roadmap item/phase and terminal sets; learnings and phase records are historical/advisory; handoffs are discovery and context transport. A handoff can locate work but cannot silently override a canonical loop or roadmap record.

Alternative rejected: treating the newest timestamp across all artifacts as truth, because records describe different scopes and clocks do not establish authority.

### D3 — Bootstrap and verification are separate

A fresh supervisor session may use the newest supervisor handoff or tracked mirror as a bootstrap locator. It then verifies the named roadmap against `checkpoint.json`, verifies every active change against its `loop-state.json`, loads relevant learnings, and finally reads phase records/handoffs for rationale and next-step context. Missing authoritative state is reported as degradation or inconsistency; it is never synthesized from advisory data.

Alternative rejected: loading handoff content last without a bootstrap step, because a fresh session may not otherwise know which roadmaps or changes are active.

### D4 — Documentation drift is tested structurally

A focused pytest suite will parse the guide and relevant skill sources to assert the five required classes, required table fields, canonical order markers, guide links, and supervise alignment. It will avoid pinning full prose so editorial improvements remain possible.

Alternative rejected: exact-file snapshots, because they make harmless wording edits expensive and test typography instead of ownership semantics.

### D5 — No new ADR entry

This change documents an existing architecture rather than making a new long-lived architectural commitment. The OpenSpec decision record and durable guide are sufficient; generating a new capability-timeline entry would duplicate settled authority decisions.

## Rehydration Algorithm

1. Bootstrap: read the newest valid supervisor handoff or tracked supervisor mirror only to identify candidate active roadmaps and changes.
2. Roadmap truth: load and validate each named roadmap `checkpoint.json` and `roadmap.yaml`.
3. Change truth: load and validate each active change's `loop-state.json`; missing or inconsistent state is explicit degradation.
4. Learning context: load direct-dependency learnings plus the bounded recent window.
5. Phase history: read `session-log.md`/phase records for decisions and evidence.
6. Handoff context: merge the newest phase handoff's bounded next actions only when consistent with steps 2–3.
7. Projection: rebuild coordinator/queue views from canonical state; never reverse the edge.

## Scope and Concurrency

The guide, skill links, mirrors, and one test module form a single sequential documentation package because multiple agents editing shared skill files would create avoidable conflicts. The package has an explicit allowlist; repository-wide write globs are forbidden.

## Risks

- **Over-linking removes necessary commands.** Mitigation: replace only shared ownership/replay explanations; keep phase-specific mutation and gate commands in place.
- **The guide becomes another stale copy.** Mitigation: structural tests require links and canonical class/order markers.
- **Bootstrap language elevates handoffs to authority.** Mitigation: distinguish locator use from verification and require fail-loud handling when canonical files disagree or are absent.
- **Runtime mirrors drift.** Mitigation: run `skills/install.sh` and byte-compare every changed skill source with `.agents` and `.claude` mirrors.

## Validation Strategy

- RED/GREEN focused structural tests for inventory, links, and rehydration order.
- Strict change and repository OpenSpec validation.
- Work-package schema, DAG, overlap, and scope checks.
- Changed-skill mirror byte comparisons.
- Documentation-link checks and context-drift gate.
- Security/deploy/browser phases recorded not applicable because no executable or service behavior changes.

