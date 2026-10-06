# Plan Findings: dispatch-contract

Produced by `/iterate-on-plan` (PLAN_ITERATE phase of autopilot). Threshold: medium.

## Iteration 1

Baseline `openspec validate --strict`: passed (scaffold). The scaffold from
`plan-roadmap` was a placeholder: generic tasks, a placeholder capability, tautological
scenarios.

| # | Type | Criticality | Description | Fix |
|---|------|-------------|-------------|-----|
| 1 | completeness | critical | proposal.md lacked Why / What Changes / Impact sections | Rewrote proposal with all required sections, non-goals, and an Impact table |
| 2 | consistency | critical | Spec delta targeted placeholder capability `multiplayer-collaboration`; real owners are roadmap-orchestration, supervise, skill-workflow, trust-posture, parallel-infrastructure | Removed placeholder; wrote five deltas against existing capabilities |
| 3 | completeness | critical | Outcomes 6-8 (token digest, host-portable isolation, scoped auto) had no requirement at all | Added RO Launch Token Digest, RO Host-Portable Attempt Isolation, TP Roadmap-Approval-Scoped Auto Dispositions |
| 4 | testability | high | Every scenario was "WHEN implemented THEN <outcome>" | Replaced with concrete WHEN/THEN including failure paths, exit codes, error strings |
| 5 | feasibility | high | tasks.md was five generic placeholders (giant tasks, no traceability) | 30 tasks in 9 groups with deps and a requirement traceability table |
| 6 | consistency | high | Existing RO "Durable Delegated Attempt Ledger" requires a stable token re-emitted on resume; digest-only storage makes that impossible | D6 per-generation tokens with `reissue`; MODIFIED the requirement |
| 7 | correctness | high | `ESCALATE --abandoned--> DONE` would be emitted as `success` by a naive DONE->success mapping | D4 maps on `goal_gate.verdict`; scenario "Abandoned work is not reported as success" |
| 8 | completeness | high | No loop-state representation for `permission_blocked`, `capability_unavailable`, or degradations, so `emit-result` had nothing to map | D11 LoopState v6 with `park` / `degradations`, `runner.py park` / `record-degradation` |
| 9 | assumptions | high | "non-auto fallback" is undefined in the posture schema | D8 optional `unscoped` sub-config, default `block` (see session-log decision; no interactive channel in this phase) |
| 10 | assumptions | high | How a child proves it carries a "valid" roadmap_approval_ref was unstated; the child cannot read the roadmap checkpoint | D8/D10a: ref travels in the generation-verified launch marker |
| 11 | consistency | high | Result shape defined three times (two validators plus inline copy in checkpoint.schema.json) | D2: checkpoint schema `$ref`s the result schema; guard test deletes hand validators |
| 12 | testability | medium | Closure over `gate` is impossible while `gate` is a free 128-char string | D3: `gate` becomes the `Gate` enum with per-kind `oneOf` |
| 13 | security | medium | A `launch_*token*` field holding 64-hex would still trip gitleaks generic-api-key (keyword + entropy) | D6: `launch_digest` with `sha256:` prefix; keyword unit test and CI scan of a committed fixture |
| 14 | security | medium | Blocked command in `permission_blocked` could carry a secret | Sanitized with `sanitize_session_log.sanitize()` in child and router; scenario added |
| 15 | feasibility | medium | `dispatch_id` contains `:`; unsafe as a file name for the committed result path | D4 `dispatch-slug` rule |
| 16 | feasibility | medium | Cross-host rebind could hand a post-go attempt to a second owner | D7: rebind only with evidence match; reinitialize only pre-go/prepared/parked; else quarantine |
| 17 | completeness | medium | Version strategy for in-flight v1 workers unstated | D1 v2 writers, v1-tolerant readers; existing fixtures unchanged |
| 18 | completeness | medium | design.md was a scaffold with open questions only | Rewrote with D1-D11, alternatives, risks, package boundaries |
| 19 | parallelizability | medium | No work-packages.yaml | Nine packages, three parallel roots, max width 3; validated |
| 20 | completeness | medium | Narrow fix branch not merged and no task for it | Task 1.1 / wp-merge-narrow-fix |
| 23 | consistency | high | Draft re-evaluation rule ran on both sides, but the child's worktree posture can differ from the supervisor's (the original Issue 1 path), so "which holder is authoritative" stayed open | Gate authority rule: dispatched child applies only `gate_answer`; marker carries supervisor `posture_digest`; drift disables `auto`; only standalone runs self-re-evaluate |
| 21 | scope | low | Raw tokens already in the roadmap branch history still fail full-history gitleaks | Recorded as open question; outside this change's edit scope |
| 22 | scope | low | Degradation rendering in the digest and automatic lane re-routing | Declared non-goals |

Parallelizability: Independent roots: 3 (wp-merge-narrow-fix, wp-dispatch-schemas,
wp-posture) | Sequential chains: schemas -> contract-lib -> {runtime-ledger,
autopilot-child} -> {supervisor, review-honesty} -> integration | Max parallel width: 3.
File overlap between non-ordered packages: none (merge-narrow-fix and supervisor share
files and are ordered).
