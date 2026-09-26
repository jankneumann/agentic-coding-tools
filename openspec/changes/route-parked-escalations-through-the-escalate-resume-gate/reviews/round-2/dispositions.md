# Plan Review Round 2 Dispositions

Real quorum: 4/4 schema-valid reviewers (Antigravity, Claude Code, Codex, Grok).

- Generation-scoped lookup/console-answer disagreement: fixed by recording generation, resolving the newest blocked dispatch generation for the backward-compatible console path, adding optional explicit generation input, and testing answer-then-route reuse.
- Partial-apply/resume blocker: fixed by allowing evaluation/projection but deferring resume until every batch member is terminal with `effects_applied`; partial apply is replayed idempotently before route-only retry semantics begin.
- Stale older-generation mirror entry: fixed by retiring earlier decision IDs for the same gate/roadmap/dispatch when projecting the new generation.
- Stale approval reference: fixed by requiring resume authorization to match the current parked lease generation.
- Notification context ambiguity: fixed with an exact key allowlist and one literal reason value.
- Workspace lock hold-time disagreement: fixed by centralizing a per-subject lock in `gate_router` across evaluate/answer/optional resume, while workspace locks remain short state-CAS sections.
- Response generation ambiguity: fixed with distinct `decided_lease_generation` and `resumed_lease_generation` fields.
- Missing cycle-state/schema scope and validation evidence: fixed by expanding scope and adding Ruff, all-OpenSpec, package/DAG, context-drift, and explicit scope verification steps.
- Prepared continuation scan ambiguity and late-answer correlation: fixed explicitly in D1/D3 and tasks.

Positive findings were accepted. No blocking or disagreement finding was waived. Round 3 must independently confirm zero blockers and disagreements.
