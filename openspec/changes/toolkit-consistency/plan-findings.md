# Plan Findings

> Change ID: `toolkit-consistency`

## Iteration 1 — 2026-10-05T07:15Z

Baseline: `openspec validate toolkit-consistency --strict` passed on the roadmap scaffold, so no
validation failures seeded this iteration. Analysis ran sequentially (scaffold had 5
placeholder tasks and 1 spec delta, below the parallel-dispatch threshold).

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | testability | critical | All four scaffold scenarios were circular (`WHEN toolkit-consistency is implemented THEN <acceptance outcome>`); nothing was verifiable. | Replaced with 7 requirements and 26 concrete WHEN/THEN scenarios in `specs/toolkit-distribution/spec.md`, each with success and failure/edge paths (count corrected from 25 in Iteration 2, review finding 11). |
| 2 | completeness | critical | `proposal.md` lacked Why / What Changes / Impact; `tasks.md` had five generic placeholder tasks traceable to no requirement. | Rewrote `proposal.md` with the required sections and non-goals; rewrote `tasks.md` as 7 requirement-traced, single-commit tasks with file scopes and dependencies. |
| 3 | consistency | high | Spec delta sat under the placeholder capability `multiplayer-collaboration`, which has no spec; the real owner of install/portability requirements is `skill-workflow` (Cross-Repo Portability, Canonical Skill Distribution). | Decided D1: new capability `toolkit-distribution`; existing `skill-workflow` requirements referenced as constraints, not modified. Flagged for human approval in `proposal.md`. |
| 4 | clarity | high | Roadmap text says "add `install.sh --check`", but `--check` already exists (mirror parity vs source). The scaffold did not say what changes about it, which could be implemented as a parallel checker or a rewrite. | Proposal and Drift check requirement now say the existing check is kept unchanged and the stamp comparison is additive (D7), with distinct checkout-drift and runtime-drift messages. |
| 5 | assumptions | high | Where the "tracked file" lives and what it contains was undecided (per-agent dir vs `openspec/` vs root). Mirror dirs are often gitignored, so a per-agent stamp would not be tracked. | Decided D2/D3: `.agentic-toolkit/stamp.json` at the consumer root, the stamp *is* the pin. Could not use AskUserQuestion (non-interactive sub-agent); recorded as a decision needing approval in `proposal.md` and `design.md`. |
| 6 | assumptions | high | "Repository-scoped learnings" had no store, writer, format or consumer; the roadmap forbids a parallel learning store. | Decided D8/D9: one-way JSONL projection from episodic memory written by `improve-harness`, consumed by `analyze_failures.py`, never written back; explicit human-owned `config.json` opt-in. Flagged for approval. |
| 7 | completeness | high | No failure or edge scenarios: aborted install, invalid stamp, unpinned repo, self-install, disabled opt-in, transcript-mined entries, secrets in lessons. | Added a scenario for each under the corresponding requirement. |
| 8 | scope | medium | Acceptance outcome 4 (no private coordinator source in payloads) is already enforced by `validate_install_manifest.py` and `test_consumer_portability.py`; re-stating it would duplicate `skill-workflow` Cross-Repo Portability. | Treated as a regression constraint: portability scenarios under Payload hash and Exported learning privacy; T7 runs the existing gate. Noted in Impact. |
| 9 | feasibility | medium | "Payload hash" was unspecified; a non-deterministic or subset hash would give false drift or miss installed files. | D4 fixes the algorithm (installed file set, excludes, sorted `relpath\0sha256\n`, follows symlinks) and places the helper in `shared/` so it is portable. |
| 10 | scope | medium | No non-goals; the item could grow into auto-update, consumer CI enforcement or coordinator team memory. | Added Non-goals to `proposal.md`; coordinator-side sharing explicitly deferred to `closed-loop-learning`. |
| 11 | completeness | medium | Acceptance outcome 1 requires registration in `docs/guides/state-artifacts.md`; nothing planned it or defined writer/authority/missing-stale behaviour. | Added the State-artifact registration requirement, task T6 and a guard test; D6–D8 define the behaviours. |
| 12 | security | medium | Exported learnings could carry transcript excerpts (memory `details`), identities (`agent_id`, `session_id`) or secrets. | Exported learning privacy requirement: field allowlist, transcript-mined exclusion, session-log sanitizer, deterministic output. |
| 13 | parallelizability | medium | Placeholder tasks had no dependencies or file scopes; `install.sh` and `install-manifest.json` would be touched by several tasks. | Tasks now carry Files/Depends on; `install.sh` edits sequenced T2→T3; manifest edits owned solely by T7. |
| 14 | consistency | medium | Self-install (this repository, CI `install.sh --check` step) would churn a tracked stamp on every sync and could break CI. | D6: self-install writes no stamp and skips the stamp comparison; Impact notes CI is unaffected. |
| 15 | assumptions | low | Which version string is "the toolkit version" (`VERSION` 0.2.0 vs `skills/pyproject.toml` 0.2.0). | D5: `VERSION` + `source_commit`; informational only, hash decides drift. |
| 16 | clarity | low | Scaffold design.md open questions (capability, non-goals, decisions to record) were unanswered. | All three answered in `design.md` (D1, Non-goals, D1–D9). |

### Parallelizability assessment

- Independent tasks at start: 3 (T1, T4, T6)
- Sequential chains: T1→T2→T3; T4→T5; {T1, T4}→T7
- Max parallel width: 3
- File-overlap conflicts: `skills/install.sh` (T2, T3 — sequenced), `skills/install-manifest.json` (T7 only); none between independent tasks

### Deferred / out of scope

- Source-free installed checker, auto re-install, consumer CI wiring, coordinator team memory — recorded as non-goals; new proposals if wanted.

### Termination

Remaining findings after fixes: none at or above `medium`. Findings 15–16 (low) were fixed opportunistically. Iteration 2 not required; `openspec validate --strict` passes.

## Iteration 2 — PLAN_REVIEW convergence round 1 — 2026-10-09T08:21Z

Autopilot PLAN_REVIEW ran `converge(review_type="plan", min_quorum=1)` under the cloud
single-vendor review policy (`TRUST_POSTURE.md` "Review quorum in cloud containers
(temporary)", commit 479dcd9). Dispatch evidence (`.review-ledger/ledger.json`,
`.review-cache/round-1/review-manifest.json`): `claude_code` (claude-local CLI, model
`fable`, 194 s) succeeded with 16 findings; the `codex` lane (codex-remote, SDK tier) failed
with `auth_required` ("No API key available for SDK dispatch"); grok, pi, antigravity and ocr
had no CLI, SDK or endpoint. Degradation recorded: `single_vendor_review`. Diff-grounded
fact-check kept all 16. Every finding is `judgment` class and single-vendor `unconfirmed`,
so none is blocking under ledger rule D3 (open + deterministic, or confirmed high/critical)
and the loop converged in round 1 with 0 blocking items. Because a single vendor can never
confirm its own judgment findings, the conductor applied the in-scope medium/low findings
below inline as a PLAN_FIX sub-step rather than let the degraded quorum silently pass them.

Ledger ids below are `.review-ledger/ledger.json` ids. The review packet was the full
`main...HEAD` diff, so most findings cite files outside this change; those are recorded for
their owners and were not edited (change-scoped commits only).

| Ledger | Type | Criticality | Cited file | Disposition |
|---|---|---|---|---|
| 1 | spec_gap | medium | other changes' `specs/multiplayer-collaboration/spec.md` | Out of scope: roadmap scaffolds with circular scenarios; each item's PLAN_ITERATE owns the rewrite (this change already did its own, Iteration 1 row 1). Flagged to the roadmap owner so no scaffold reaches IMPLEMENT unrefined. |
| 2 | style | low | `reviewer-shaped-prs/specs/.../spec.md` | Out of scope: `plan-roadmap` scaffold generator truncates requirement headings (`pRs created by`). Follow-up for the generator; headings are the ri-06 collision identity. |
| 3 | security | medium | `TRUST_POSTURE.md` | Out of scope, escalated: `proposal_approval: auto` is justified by a recorded `roadmap_approval`, but the gate also fires for standalone changes with no roadmap. Operator decision needed. |
| 4 | style | low | `TRUST_POSTURE.md` | Out of scope: header comment says every failure path waits for a human while `replan_required` is `auto`; table is right, comment is stale. |
| 5 | observability | medium | `loop-state.json` | Verified, not editable here: commit 479dcd9 (the cited policy) exists on `openspec/roadmap-multiplayer-collaboration` but not on this branch, so the citation does not resolve from this checkout. Orchestrator should bring 479dcd9 onto the change branch. `loop-state.json` is orchestrator-owned. |
| 6 | correctness | medium | `roadmaps/multiplayer-collaboration/roadmap.yaml` | Out of scope, escalated: roadmap.yaml shows ri-20 `approved` and `current_item_id: ri-01` while this change's loop-state shows GATEKEEPER/PLAN_ITERATE done and two PLAN_REVIEW parks; a queue projection would re-dispatch. Needs `autopilot-roadmap` reconciliation. |
| 7 | security | low | `roadmaps/multiplayer-collaboration/checkpoint.json` | Out of scope: consumed `launch_token` / `owner_nonce` committed in a tracked file; low exposure, will trip secret scanners. Roadmap owner. |
| 8 | contract_mismatch | medium | `specs/toolkit-distribution/spec.md` | **Fixed.** Exported learning privacy now states `capability_gap` and `affected_skill` are the retained `capability_gap:` / `affected_skill:` tag values (the tags `analyze_failures.py` already reads), so the exporter's dedupe key is satisfiable from the allowlist; One-way consumption now dedupes shared records on `(capability_gap, affected_skill, summary)` instead of the local `session_id` key that exported records cannot carry. |
| 9 | security | medium | `specs/toolkit-distribution/spec.md` | **Fixed.** `tags` are filtered to the D4 namespaces (`failure_type:`, `capability_gap:`, `affected_skill:`, `severity:`, `source:`); `agent:`, `session:`, `change:`, `vendor:`, `model:` and all other tags are dropped. New scenario "Identity-bearing tags are dropped". |
| 10 | spec_gap | low | `specs/toolkit-distribution/spec.md` | Deferred, open question: D3 makes every successful install move the pin, so an install from an un-pinned checkout silently rewrites the stamp. A notice when the new hash differs from the existing stamp is a cheap follow-up; not added here to keep T2 single-commit. |
| 11 | style | low | `plan-findings.md` | **Fixed.** Scenario count corrected to 26 (now 27 with the finding-9 scenario). `session-log.md` Plan Iteration 1 is left as the historical record; the correction is in the Plan Review entry. |
| 12 | observability | low | `openspec/supervise/supervisor-record.json` | Out of scope: `written_at` precedes `decided_at` by 35 ms and two timestamp formats are mixed. Supervisor skill follow-up. |
| 13 | architecture | low | `roadmaps/multiplayer-collaboration/roadmap.yaml` | Out of scope: ri-13 (priority 2) depends on ri-12 (priority 3). Roadmap owner. |
| 14 | style | low | `specs/toolkit-distribution/spec.md` | **Fixed.** `<project-root>` replaced by `<target-root>` in the opt-in and one-way requirements, with one sentence defining it as the consumer root the Install stamp names. |
| 15 | observability | low | `loop-state.json` | Orchestrator-owned: stale `escalation_reason`, `previous_phase == current_phase`, `iteration 0 / total_iterations 8` after resume. Reported in the phase handoff. |
| 16 | spec_gap | low | `owner-routed-escalation/proposal.md` | Out of scope: scaffold proposals cite `ri-NN` instead of change ids. `plan-roadmap` follow-up. |

### Termination

Blocking ledger items after round 1: 0 (converged). In-scope findings 8, 9, 11, 14 fixed
inline and marked addressed in the ledger; 10 deferred as an open question; 1–7, 12, 13, 15,
16 recorded for their owners. `openspec validate toolkit-consistency --strict` passes after
the fixes. A verification run of `converge()` over the committed fix follows (see the Plan
Review entry in `session-log.md` for its result).
