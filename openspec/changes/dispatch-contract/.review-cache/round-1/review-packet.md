## Review Round 1

This packet exceeds the size budget and was truncated. You MAY use Read/Grep to recover truncated context.

Review the attached artifacts for correctness, completeness, and adherence to project standards.

### Prompt contract
REQUIRED on every finding — output is REJECTED if any is missing: id, type, criticality, description, disposition, axis, severity
These fields use DIFFERENT vocabularies. Do not reuse one value for another:
  criticality: low|medium|high|critical — how much it matters
  severity: critical|nit|optional|fyi|none — review-gate grading (NOT the same scale as criticality)
  axis: correctness|readability|architecture|security|performance|observability|resilience|compatibility
  type: spec_gap|contract_mismatch|architecture|security|performance|style|correctness|observability|compatibility|resilience|behavioral_failure
  disposition: fix|regenerate|accept|escalate
Use exactly one value from each listed set; do not invent values.
OPTIONAL: report which selected files you actually reviewed as a top-level `coverage` object: `{"reviewed": ["path", ...], "skipped": [{"path": "path", "reason": "why"}, ...]}`. Omitting `coverage` is treated as full coverage, never as a penalty.
Output ONLY a JSON object with a top-level `findings` array.

### Diff
```diff
diff --git a/.gitleaks.toml b/.gitleaks.toml
index 5efaf14..67b0e84 100644
--- a/.gitleaks.toml
+++ b/.gitleaks.toml
@@ -47,4 +47,13 @@ commits = [
     # HEAD with a low-entropy fixture that still matches the sanitizer's
     # pattern without tripping gitleaks' entropy-based generic-api-key rule.
     "e1c52a58e791115023cabe01f1cd027669dba8a9",
+    # multiplayer-collaboration roadmap branch (PR #662): supervised-dispatch
+    # launch nonces (`secrets.token_urlsafe(24)`) committed raw as
+    # `"launch_token"` in openspec/roadmaps/multiplayer-collaboration/
+    # checkpoint.json. They are single-use, run-scoped nonces, not
+    # credentials. dispatch-contract (ri-21) stores only a digest from here
+    # on, so only these introducing commits are exempt.
+    "ddd2c4a8e3fea7cfa7589cb48a5fdfc2016cb281",
+    "c6424d74d6bca96cd632da8f888bf4c5dd512107",
+    "3c06430ace19444a9762ae01b2ff422f08e01ae7",
 ]
diff --git a/TRUST_POSTURE.template.md b/TRUST_POSTURE.template.md
index f2fb949..f90cdf3 100644
--- a/TRUST_POSTURE.template.md
+++ b/TRUST_POSTURE.template.md
@@ -86,6 +86,33 @@ error (it usually means a mis-placed field).
 A gate omitted from `gates:` resolves to `block` (fail-closed). Only an unknown
 gate key or an unknown disposition is a hard validation error.
 
+## Roadmap-approval-scoped `auto` (`proposal_approval`, `replan_required`)
+
+`auto` on `proposal_approval` or `replan_required` applies **only** to a run
+dispatched by `/supervise` under a recorded `roadmap_approval`: the launch marker
+the supervisor writes into the child's worktree carries that approval reference,
+and the approval gate reads it from the marker itself (a reference passed any
+other way is ignored). Every other run — a standalone `/autopilot`, for example —
+uses the gate's `unscoped` fallback instead, which defaults to `block`:
+
+```yaml
+  proposal_approval:
+    disposition: auto
+    unscoped:                       # optional; absent means {disposition: block}
+      disposition: notify_with_timeout
+      timeout_seconds: 600
+      default_action: block
+```
+
+`unscoped` follows the same rules as a gate config except that `auto` is not
+allowed, and it may only appear on these two gates. The decision record names the
+scope that applied (`scope: roadmap_approval` or `scope: unscoped`).
+
+Every gate decision also records its `provenance`: a posture-derived decision
+carries the posture's digest — a SHA-256 over the parsed `gates:` map, so prose
+edits and key order never count as a posture change — and is re-evaluated when
+that digest changes; a human answer is final.
+
 ## Worked example
 
 A posture that auto-creates PRs, notifies-with-a-one-hour-timeout on merge
diff --git a/docs/decisions/roadmap-orchestration.md b/docs/decisions/roadmap-orchestration.md
index fc704e4..970c1cc 100644
--- a/docs/decisions/roadmap-orchestration.md
+++ b/docs/decisions/roadmap-orchestration.md
@@ -5,6 +5,72 @@
 
 ---
 
+## 2026-10-09 — dispatch-contract
+
+### Phase: Plan Review
+
+**Existing v1 contract schemas are given one role each instead of being duplicated** — `openspec/contracts/roadmap-orchestration/schemas/` already published request/result/attempt/context schemas; request/result are frozen as v1 reader schemas, the attempt schema becomes the single attempt definition `$ref`'d by `checkpoint.schema.json`, and the context schema is `$ref`'d by the v2 request.
+
+- Status: `active`
+- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D1)
+
+---
+
+## 2026-10-09 — dispatch-contract
+
+### Phase: Implementation
+
+**Commit order keeps every commit green rather than following package boundaries literally** — The checkpoint/attempt schema $ref switch, models, orchestrator and execution must change together; schemas 2.3-2.4 landed in the ledger commit.
+
+- Status: `active`
+- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D1)
+
+---
+
+## 2026-10-09 — dispatch-contract
+
+### Phase: Implementation
+
+**Cross-host reinitialize keeps a parked attempt's generation** — Its escalate_resume approval is bound to the generation (advisory finding 13).
+
+- Status: `active`
+- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D3)
+
+---
+
+## 2026-10-06 — dispatch-contract
+
+### Phase: Plan Iteration 1
+
+**Spec deltas target existing capabilities, not the placeholder** — multiplayer-collaboration is a roadmap, not a capability; the touched behaviour is owned by roadmap-orchestration, supervise, skill-workflow, trust-posture and parallel-infrastructure.
+
+- Status: `active`
+- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D1)
+
+---
+
+## 2026-10-06 — dispatch-contract
+
+### Phase: Plan Iteration 3
+
+**Attempts persist the verified roadmap_approval_ref** — It is a non-secret gate-decision reference; persisting it lets child_start write it into every generation's marker and lets the supervisor apply the same scope rule from the same fact.
+
+- Status: `active`
+- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D1)
+
+---
+
+## 2026-10-06 — dispatch-contract
+
+### Phase: Plan Iteration 1
+
+**Launch tokens are minted per generation and stored only as sha256 digests** — A digest-only checkpoint cannot re-emit the same token on resume, so the Durable Delegated Attempt Ledger requirement is MODIFIED; reissue is limited to states where takeover is already safe.
+
+- Status: `active`
+- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D2)
+
+---
+
 ## 2026-09-14 — 2026-09-26-route-parked-escalations-through-the-escalate-resume-gate
 
 ### Phase: Plan Iteration 2
diff --git a/docs/decisions/skill-workflow.md b/docs/decisions/skill-workflow.md
index f301b49..5a9f3bb 100644
--- a/docs/decisions/skill-workflow.md
+++ b/docs/decisions/skill-workflow.md
@@ -5,6 +5,17 @@
 
 ---
 
+## 2026-10-09 — dispatch-contract
+
+### Phase: Plan Review
+
+**Quorum park happens in the worker protocol, not convergence_loop** — below quorum the SKILL.md probe skips review entirely, so convergence_loop never runs; `runner.py park` stays the only writer.
+
+- Status: `active`
+- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D4)
+
+---
+
 ## 2026-09-25 — 2026-09-25-restructure-openbao-per-agent-secrets
 
 ### Phase: Implementation
diff --git a/docs/decisions/supervise.md b/docs/decisions/supervise.md
index 6f9134e..a7967b7 100644
--- a/docs/decisions/supervise.md
+++ b/docs/decisions/supervise.md
@@ -5,6 +5,72 @@
 
 ---
 
+## 2026-10-09 — dispatch-contract
+
+### Phase: Plan Review
+
+**Capability-park fan-out writes one escalate_resume record per dispatch** — keeps `require_approval_ref`'s per-dispatch and per-generation checks unchanged.
+
+- Status: `active`
+- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D2)
+
+---
+
+## 2026-10-09 — dispatch-contract
+
+### Phase: Implementation
+
+**Review quorum per environment is data (review_quorum_policy.json) carried as review_requirements.quorum_policy** — Supervisor follow-up 1: a worker gets min_quorum 1 only through data with an explicit sunset; single-lane is detected by failed dispatch.
+
+- Status: `active`
+- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D2)
+
+---
+
+## 2026-10-09 — dispatch-contract
+
+### Phase: Plan Review
+
+**counting_lanes includes unverified roster lanes** — otherwise `missing_lanes` is always empty and distinct capability gaps share one fingerprint.
+
+- Status: `active`
+- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D3)
+
+---
+
+## 2026-10-06 — dispatch-contract
+
+### Phase: Plan Iteration 2
+
+**Review quorum defaults to 2 per review phase with a router-context override** — routing.yaml defines a cost ladder but no quorum; 2 is today's --min-vendors and the ladder orders lanes without excluding tiers. Recorded as a decision because this phase cannot ask the operator.
+
+- Status: `active`
+- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D2)
+
+---
+
+## 2026-10-06 — dispatch-contract
+
+### Phase: Plan Iteration 1
+
+**Dispatched children defer gate authority to the supervisor** — Issue 1 arose because child and supervisor postures differed; the marker carries the supervisor posture digest and drift disables auto, so one holder is authoritative.
+
+- Status: `active`
+- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D3)
+
+---
+
+## 2026-10-06 — dispatch-contract
+
+### Phase: Plan Iteration 2
+
+**Below-quorum availability still launches** — check-vendors exits 2 for both below-quorum and roster failure; only an error field or unparseable JSON blocks prepare, and the child parks capability_unavailable honestly at review.
+
+- Status: `active`
+- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D3)
+
+---
+
 ## 2026-09-16 — 2026-09-26-route-parked-escalations-through-the-escalate-resume-gate
 
 ### Phase: Validation 3
diff --git a/docs/decisions/trust-posture.md b/docs/decisions/trust-posture.md
index e8a5e74..9667a54 100644
--- a/docs/decisions/trust-posture.md
+++ b/docs/decisions/trust-posture.md
@@ -5,6 +5,28 @@
 
 ---
 
+## 2026-10-06 — dispatch-contract
+
+### Phase: Plan Iteration 2
+
+**ApprovalGate reads the launch marker through an injected seam and ignores context refs** — A context value can be set by any caller; the marker is written by child_start after supervisor verification. The seam also keeps wp-posture independent of wp-contract-lib.
+
+- Status: `active`
+- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D1)
+
+---
+
+## 2026-10-06 — dispatch-contract
+
+### Phase: Plan Iteration 1
+
+**Non-auto fallback is an optional `unscoped` posture sub-config defaulting to block** — The outcome names a fallback but the posture schema has none; a declared field keeps operators able to choose notify_with_timeout while failing closed by default. Recorded as a decision rather than asked: this phase sub-agent has no interactive channel to the operator.
+
+- Status: `active`
+- Source: [openspec/changes/dispatch-contract/session-log.md](/openspec/changes/dispatch-contract/session-log.md) (D4)
+
+---
+
 ## 2026-09-03 — 2026-09-03-route-supervise-gates-through-the-approval-gate-service
 
 ### Phase: Plan
diff --git a/openspec/changes/dispatch-contract/.review-ledger/ledger.json b/openspec/changes/dispatch-contract/.review-ledger/ledger.json
new file mode 100644
index 0000000..17b6182
--- /dev/null
+++ b/openspec/changes/dispatch-contract/.review-ledger/ledger.json
@@ -0,0 +1,434 @@
+{
+  "schema_version": 1,
+  "change_id": "dispatch-contract",
+  "items": [
+    {
+      "id": 1,
+      "status": "open",
+      "axis": "architecture",
+      "type": "contract_mismatch",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/dispatch-contract/design.md",
+      "fingerprint": "5ad6e6c7e716b327",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "D2 claims the boundary is defined only by hand validators plus an inline checkpoint copy, but published JSON Schemas already exist at openspec/contracts/roadmap-orchestration/schemas/{supervised-dispatch-request,supervised-dispatch-result,delegated-dispatch-attempt,bounded-dispatch-context}.schema.json (with $id https://agentic-coding-tools.dev/contracts/...), consumed by skills/tests/supervise/test_execution_contract.py, test_execution.py:386, roadmap-runtime/test_dispatch_scheduler.py:34 and autopilot-roadmap/test_supervised_dispatch_e2e.py:42. Adding openspec/schemas/dispatch-*.schema.json without deciding what happens to them creates a fourth definition, the exact root cause the change exists to remove.",
+      "resolution": "compact: claimed fix did not take",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 2,
+      "status": "open",
+      "axis": "architecture",
+      "type": "contract_mismatch",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/dispatch-contract/proposal.md",
+      "fingerprint": "f52608ce043dc53d",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Why states the dispatch request and result 'exist only as three hand-kept validators ... plus test fixtures', and Impact lists only openspec/schemas/ files. openspec/contracts/roadmap-orchestration/schemas/ already publishes request, result, attempt and context schemas (listed in docs/architecture-analysis/contracts-inventory.md). The problem statement and Impact table are factually incomplete.",
+      "resolution": "compact: claimed fix did not take",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 3,
+      "status": "open",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/dispatch-contract/specs/roadmap-orchestration/spec.md",
+      "spec_file": "openspec/changes/dispatch-contract/specs/roadmap-orchestration/spec.md",
+      "fingerprint": "1b0ffb9c419b8a23",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Scenario 'Existing fixtures validate against the published schemas' requires every valid-* fixture under skills/tests/supervise/fixtures/execution/contracts/ to pass validate_request/validate_result, but valid-prepared-attempt.json is a checkpoint attempt (with raw launch_token), and valid-results.json is a map {success, parked} rather than a result. Its v1 success result also carries absolute worktree_path and evidence.loop_state_path under /workspace/.git-worktrees, which the 'cannot be made portable' scenario would reject on any test host. The scenario is unexecutable as worded, and the requirement does not relate the existing openspec/contracts/roadmap-orchestration/schemas/ files to the new single definition.",
+      "resolution": "compact: claimed fix did not take",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 4,
+      "status": "open",
+      "axis": "correctness",
+      "type": "correctness",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/dispatch-contract/tasks.md",
+      "fingerprint": "e6d10986acb9405f",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Making checkpoint.schema.json's attempt result a $ref breaks every existing validator of that schema: roadmap-runtime/scripts/models.py validate_against_schema (lines 956-973) builds a bare Draft202012Validator with no registry, used by resolve_readiness.py:113 and models.py:1135; and tests that copy only checkpoint.schema.json into a tmp repo (supervise/test_execution.py _workspace, test_gate_router.py:54, test_gate_router_e2e.py:57, test_cycle_state.py:115, roadmap-runtime/test_readiness.py:105, autopilot-roadmap/test_supervised_dispatch.py:25, test_supervised_dispatch_e2e.py:95) would then fail with an unresolvable reference. No task updates the loader or those copies. Tasks also omit the existing contract schemas (finding 1), a host_id function in skills/shared/environment_profile.py (D7 cites it; the module has only detect() and its layers), and the install manifest test skills/tests/install_sh/test_openspec_assets.py.",
+      "resolution": "compact: claimed fix did not take",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 5,
+      "status": "open",
+      "axis": "correctness",
+      "type": "correctness",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/dispatch-contract/work-packages.yaml",
+      "fingerprint": "07bf7832b84727c7",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Write scopes omit files the plan must edit: openspec/contracts/roadmap-orchestration/schemas/*.schema.json and skills/tests/supervise/test_execution_contract.py (no package); skills/shared/environment_profile.py (host_id, D7; no package); skills/tests/roadmap-runtime/test_readiness.py, skills/tests/supervise/test_cycle_state.py, skills/tests/autopilot-roadmap/test_supervised_dispatch.py and skills/tests/install_sh/test_openspec_assets.py (schema copy sites broken by the checkpoint $ref; no package). Scope enforcement will reject these edits.",
+      "resolution": "compact: claimed fix did not take",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 6,
+      "status": "open",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/dispatch-contract/design.md",
+      "fingerprint": "d2ab83c894ddee09",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "D9 says one operator answer resumes every attempt sharing a fingerprint, but the resume path verifies a record bound to one dispatch: gate_router.require_approval_ref (gate_router.py:1095-1140) rejects a record whose dispatch_id differs and, for escalate_resume, whose lease_generation differs; ExecutionAdapter.resume rejects any kind other than pending_gate/policy_pause (execution.py:852). D9 never defines the decision-record shape for a fingerprint subject, so the fan-out cannot pass the existing verification.",
+      "resolution": "compact: claimed fix did not take",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 7,
+      "status": "open",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/dispatch-contract/specs/roadmap-orchestration/spec.md",
+      "spec_file": "openspec/changes/dispatch-contract/specs/roadmap-orchestration/spec.md",
+      "fingerprint": "d3f53af13775341a",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Modified scenario 'Resume an authorized parked attempt' requires 'a subject matching the dispatch', replacing the base 'matching dispatch_id' with an undefined term. With D9 fingerprint subjects the verifiable condition is unclear and an implementer could accept a record whose subject lists the dispatch but whose lease_generation is stale.",
+      "resolution": "compact: claimed fix did not take",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 8,
+      "status": "open",
+      "axis": "correctness",
+      "type": "correctness",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/dispatch-contract/tasks.md",
+      "fingerprint": "84c902fc193e17d8",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Honest Review Quorum cannot be met by the tasked edits. Below quorum, skills/autopilot/SKILL.md (lines 175-179) sets CLI_REVIEW_ENABLED=false before run_loop, so PLAN_REVIEW is skipped and convergence_loop never runs; task 7.3 puts the park in convergence_loop.py, which therefore never fires for a dispatched child, and it also contradicts the skill-workflow rule that runner.py park is the only writer of park. The standalone review_skipped degradation likewise cannot come from convergence_loop because no review runs.",
+      "resolution": "compact: claimed fix did not take",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 9,
+      "status": "open",
+      "axis": "correctness",
+      "type": "contract_mismatch",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/dispatch-contract/design.md",
+      "fingerprint": "8f1b25c45703d637",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "D10 defines counting_lanes as 'verified lanes ordered by the cost_policy.tiers ladder'. The skill-workflow scenario requires missing_lanes to name 'the counting lanes not verified', which is always empty under that definition, so every capability_unavailable park fingerprints to sha256(phase, []) and D9's 'different missing lanes are separate escalations' cannot hold.",
+      "resolution": "compact: claimed fix did not take",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 10,
+      "status": "open",
+      "axis": "security",
+      "type": "contract_mismatch",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/dispatch-contract/tasks.md",
+      "fingerprint": "47a3bc29ccd174ea",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Task 6.2 says the gate session 'passes the marker's roadmap_approval_ref into gate context', but D8 and the trust-posture requirement say a context-supplied roadmap_approval_ref is ignored and the gate reads the marker only through its marker_reader seam. Implemented as tasked, either scope never applies or the context path becomes the trust channel D8 forbids.",
+      "resolution": "compact: claimed fix did not take",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 11,
+      "status": "open",
+      "axis": "compatibility",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/dispatch-contract/design.md",
+      "fingerprint": "5610bbaf656f759c",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "D1's v1 upgrade converts only worktree_path, but v1 results also carry an absolute evidence.loop_state_path (see fixtures/execution/contracts/valid-results.json), while Host-Portable Attempt Isolation forbids persisting absolute paths in the result. An upgraded v1 result would still carry an absolute path into checkpoint outcome metadata.",
+      "resolution": "compact: claimed fix did not take",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 12,
+      "status": "open",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/dispatch-contract/design.md",
+      "fingerprint": "41d283d5f025ddc5",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "D9 says the stored command is 'the output of sanitize_session_log.sanitize()', but sanitize() returns a (content, redactions) tuple (sanitize_session_log.py:177).",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 13,
+      "status": "open",
+      "axis": "resilience",
+      "type": "resilience",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/dispatch-contract/design.md",
+      "fingerprint": "f736ba8363a4968c",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "D7 reinitializes a parked attempt on another host by incrementing its generation, which invalidates any already-recorded escalate_resume approval bound to the old lease_generation; the operator would need to answer again.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 14,
+      "status": "open",
+      "axis": "architecture",
+      "type": "contract_mismatch",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/dispatch-contract/design.md",
+      "fingerprint": "078907d34db045e0",
+      "first_seen_round": 2,
+      "last_seen_round": 3,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Round-1 fix introduced an ordering contradiction: D2's last bullet says all four existing contract tests (including skills/tests/supervise/test_execution_contract.py) validate through dispatch_contract, but task 2.3a assigns test_execution_contract.py to wp-dispatch-schemas, a root package that lands before wp-contract-lib creates skills/shared/dispatch_contract.py. Followed literally, wp-dispatch-schemas cannot pass its own edit.",
+      "resolution": "compact: claimed fix did not take",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 15,
+      "status": "open",
+      "axis": "architecture",
+      "type": "architecture",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/dispatch-contract/tasks.md",
+      "fingerprint": "6f79a242a3434e10",
+      "first_seen_round": 2,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Task 5.2 makes roadmap-runtime/scripts/models.py depend on skills/shared/dispatch_contract.schema_registry; models.py has no skills/shared import today. Building the referencing.Registry locally from the schema directories inside models.py would avoid a new cross-skill dependency from the runtime foundation.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 16,
+      "status": "open",
+      "axis": "security",
+      "type": "security",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "skills/autopilot/scripts/runner.py",
+      "fingerprint": "2f8536043bf997ac",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "In a dispatched child, gate-answer compares only --approval-ref with the launch marker's gate_answer.approval_ref. It never checks --gate or --decision against gate_answer.gate/decision, so a child whose marker says {gate: proposal_approval, decision: rejected, approval_ref: R} can run gate-answer --decision approved --approval-ref R (or answer a different pending gate, or clear a park with a pending_gate answer) and record a human-provenance approval the supervisor never made. The spec requires the child to apply a gate decision only from the marker's gate_answer (skill-workflow 'Gate Authority and Re-Evaluation on Resume', design D5).",
+      "resolution": "compact: claimed fix did not take",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 17,
+      "status": "open",
+      "axis": "correctness",
+      "type": "correctness",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "skills/tests/autopilot/test_gate_check_reeval.py",
+      "fingerprint": "fec979559731bf9d",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The dispatched-child gate-answer tests cover only a mismatched approval_ref. No test pins that a matching approval_ref with a different --decision or --gate is refused, which is how finding 1 went unnoticed.",
+      "resolution": "compact: claimed fix did not take",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 18,
+      "status": "open",
+      "axis": "security",
+      "type": "security",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "skills/autopilot-roadmap/scripts/orchestrator.py",
+      "fingerprint": "23ceffe3feec42c8",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "apply_delegated_batch persists a permission_blocked result's parked.command verbatim: _terminal_attempt copies result['parked'] into the checkpoint attempt, and the application journal stores the whole result. Only the router's gate-decision record (parked_commands) is re-sanitized. checkpoint.json is a tracked file on a shared ref, and a result that did not come through runner.py park (hand-written, or from an older worker) can carry an unredacted credential; the apply-time re-derivation compares only the fingerprint (tool, rule, classifier_reason), not the command. Design D9 says the command is 're-sanitized by the router', and the supervise scenario requires the persisted command not to contain the secret. test_a_secret_in_the_blocked_command_is_redacted seeds the checkpoint attempt with the raw 'Bearer abc123...' value and checks only the record.",
+      "resolution": "compact: claimed fix did not take",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 19,
+      "status": "open",
+      "axis": "security",
+      "type": "correctness",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "skills/tests/autopilot-roadmap/test_supervised_dispatch.py",
+      "fingerprint": "4e76f85907b32bb7",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "No test applies a permission_blocked result carrying a secret-bearing command and asserts that the persisted checkpoint (the attempt's parked payload and its application journal) contains no raw secret.",
+      "resolution": "compact: claimed fix did not take",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 20,
+      "status": "open",
+      "axis": "correctness",
+      "type": "correctness",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "skills/shared/dispatch_contract.py",
+      "fingerprint": "98546f72a1f3bf07",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "redact_command is not idempotent for auth headers: backtracking in \\s* defeats the (?!\\[REDACTED:) lookahead, so re-redacting 'Authorization: [REDACTED:auth-header]' rewrites it to 'Authorization:[REDACTED:auth-header]'. Harmless for secrecy, but the router's second pass changes already-redacted text.",
+      "resolution": "compact: claimed fix did not take",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 21,
+      "status": "open",
+      "axis": "correctness",
+      "type": "correctness",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "skills/shared/approval_gate.py",
+      "fingerprint": "f64fc9e8bf4180c1",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Carried from IMPL_ITERATE: in a dispatched child whose posture digest drifted, a notify_with_timeout gate can still take its posture-derived timeout default; the spec forbids only auto there.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 22,
+      "status": "open",
+      "axis": "correctness",
+      "type": "correctness",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "skills/autopilot/scripts/runner.py",
+      "fingerprint": "99566455adc7ab35",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Carried from IMPL_ITERATE: emit-result does not cross-check --dispatch-id/--generation against the launch marker; the supervisor's identity check still rejects a mismatch at apply.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 23,
+      "status": "open",
+      "axis": "correctness",
+      "type": "correctness",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "skills/supervise/scripts/execution.py",
+      "fingerprint": "52493cd6a655e8bd",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "Carried from IMPL_ITERATE: rebind accepts a post-go attempt with no recorded evidence when only a worktree for its branch exists on this host (the evidence conditions hold vacuously).",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 24,
+      "status": "open",
+      "axis": "resilience",
+      "type": "resilience",
+      "criticality": "low",
+      "evidence_class": "judgment",
+      "file_path": "skills/supervise/scripts/gate_router.py",
+      "fingerprint": "a4507d47347e55c8",
+      "first_seen_round": 1,
+      "last_seen_round": 2,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "_resolve_capability_park's proceed path falls back to records[0] when the attempt is not among the fingerprint's parked members (its checkpoint copy moved on); with no members that raises IndexError instead of a GateRefusalError.",
+      "consensus_status": "unconfirmed"
+    }
+  ],
+  "compacted_at": "2026-10-09T13:38:32Z"
+}
diff --git a/openspec/changes/dispatch-contract/design.md b/openspec/changes/dispatch-contract/design.md
index 5779f8b..be13ed5 100644
--- a/openspec/changes/dispatch-contract/design.md
+++ b/openspec/changes/dispatch-contract/design.md
@@ -1,22 +1,479 @@
-<!-- SCAFFOLD: generated by plan-roadmap from roadmap `multiplayer-collaboration`, item `ri-21`.
-     Preliminary. Refine before implementation. -->
-
 # Design: Publish the supervisor-worker dispatch contract
 
 ## Context
 
-Publish versioned dispatch-request and dispatch-result JSON schemas as the single definition of the supervisor-worker boundary; emit results from loop-state via runner.py emit-result; add gate provenance with posture-digest re-evaluation, execution_profile, review_requirements, degradations[], and the parked kinds permission_blocked and capability_unavailable, with a closure contract test so every schema-permitted parked shape has a supervisor answer path.
+The supervisor (`skills/supervise/scripts/execution.py`, `gate_router.py`) prepares
+delegated attempts through the roadmap orchestrator
+(`skills/autopilot-roadmap/scripts/orchestrator.py`), persists them in the roadmap
+`checkpoint.json` (`skills/roadmap-runtime/scripts/models.py`, `checkpoint.py`), and a
+child `/autopilot` run in an isolated worktree drives `loop-state.json` through
+`skills/autopilot/scripts/runner.py`. The request/result shape is defined three times
+by hand and the child-to-result mapping is composed by the worker. This design fixes
+one definition, one mapping, and one answer path per parked shape, and makes the
+persisted state safe to commit to a shared ref.
 
-## Why this item exists
+Existing behaviour this design builds on, not replaces:
 
-Every stall in the first supervised run occurred at an unwritten part of the supervisor-worker boundary; queue-dispatched work (team-work-queue, owner-routed-escalation, queue-dispatch-owner-acceptance) is built on it.
+- The supervisor side already re-evaluates a `posture_block` record when the
+  posture's *disposition* for that gate changes (`gate_router._apply_prior_record`).
+  The child side does not: `runner.py gate-check` prints an existing `pending_gate`
+  without re-evaluating it.
+- `ExecutionAdapter.resume` already requires an `approval_ref` of the form
+  `gate-decision:<decision_id>` resolving to a `proceed` record.
+- `ExecutionAdapter.prepare` already requires a `roadmap_approval_ref` whose
+  fingerprint matches the current roadmap (`gate_router.require_approval_ref`).
 
-## Depends on
+## Decisions
 
-- None
+### D1. Schema versioning: v2 writers, v1-tolerant readers
+
+Both schemas are published at `schema_version` 2. Writers (`orchestrator.py`,
+`execution.py`, `emit-result`) emit only v2. Readers accept v1 requests and results by
+upgrading them in memory through `dispatch_contract.upgrade_v1()`; the existing v1
+fixtures stay byte-unchanged and must pass this way (acceptance outcome 1). A v1
+request gains an empty `execution_profile`/`review_requirements` (which the child
+treats as standalone for D10 purposes). A v1 result gains
+`degradations: []`, its absolute `worktree_path` is converted to `worktree_ref`
+against the current host's managed worktree root or repo root, its absolute
+`evidence.loop_state_path` is rewritten relative to that worktree, and `host_id` is
+set to the current host. A v1 result whose paths cannot be made relative is rejected
+with a named error. `upgrade_v1(doc, *, repo_root, managed_root, host_id)` takes the
+host context explicitly; schema validation of a v1 document (against the frozen v1
+reader schemas, D2) is host-independent, so the existing fixtures validate on any
+host and only the upgrade step is host-bound.
+
+- *Alternative:* bump in place with no v1 support. Rejected: workers already running on
+  `multiplayer-collaboration` return v1 results, and refusing them would strand those
+  attempts.
+- *Alternative:* indefinite dual support. Rejected: v1 reading is removed by a later
+  change once no unresolved v1 attempt exists; the closure test covers v2 only.
+
+### D2. One definition, loaded at runtime
+
+`skills/shared/dispatch_contract.py` locates the schemas the same way
+`review_findings_schema.find_schema_path` does (repo `openspec/schemas/` first, then
+`skills/roadmap-runtime/install_assets/openspec/schemas/`), validates with
+`jsonschema.Draft202012Validator`, and adds only the cross-field checks a schema
+cannot express: result identity matches the attempt, evidence commit and digest match
+the worktree, size of canonical JSON is at most 16 KiB. `_RESULT_REQUIRED`,
+`_RESULT_ALLOWED` and `_validate_result` in `execution.py`, and
+`_validate_dispatch_result` in `orchestrator.py`, are deleted. The inline result
+object in `checkpoint.schema.json` becomes a `$ref` to
+`dispatch-result.schema.json`, resolved through a `referencing.Registry` built from
+the schema directory.
+
+The v1 boundary is also published, but unused at runtime, as JSON Schemas under
+`openspec/contracts/roadmap-orchestration/schemas/` (`supervised-dispatch-request`,
+`supervised-dispatch-result`, `delegated-dispatch-attempt`, `bounded-dispatch-context`,
+each with an `https://agentic-coding-tools.dev/contracts/...` `$id`). They are
+validated today only by tests (`skills/tests/supervise/test_execution_contract.py`,
+`test_execution.py`, `roadmap-runtime/test_dispatch_scheduler.py`,
+`autopilot-roadmap/test_supervised_dispatch_e2e.py`). To end with one definition per
+shape:
+
+- `supervised-dispatch-request.schema.json` and `supervised-dispatch-result.schema.json`
+  are frozen as the **v1 reader schemas**: `upgrade_v1()` validates a v1 document
+  against them before upgrading it, and nothing writes v1. They are deleted with v1
+  reading (Open questions).
+- `delegated-dispatch-attempt.schema.json` becomes the **single attempt definition**:
+  it gains `launch_digest`, `roadmap_approval_ref` and portable isolation, and
+  `checkpoint.schema.json`'s `dispatch_attempts.items` becomes a `$ref` to it (its
+  `result` in turn `$ref`s `dispatch-result.schema.json`).
+- `bounded-dispatch-context.schema.json` is kept and `$ref`'d by the v2 request.
+- The v2 request/result live only at `openspec/schemas/dispatch-*.schema.json`.
+  `dispatch_contract`'s registry loads every schema in `openspec/schemas/` and
+  `openspec/contracts/roadmap-orchestration/schemas/` by `$id`; the four contract
+  files are mirrored under `skills/roadmap-runtime/install_assets/openspec/` at the
+  same relative paths, and the locator's install_assets fallback covers both
+  directories.
+- `test_execution_contract.py` is repointed in `wp-dispatch-schemas` (task 2.3a), which
+  lands before `dispatch_contract` exists, so it keeps building its own
+  `referencing.Registry`, now over both schema directories. `test_execution.py`,
+  `test_dispatch_scheduler.py` and `test_supervised_dispatch_e2e.py` move to
+  `dispatch_contract` in their own later packages (`wp-supervisor`,
+  `wp-runtime-ledger`).
+
+- *Alternative:* generate Python validators from the schema at build time. Rejected:
+  adds a build step that installed copies in consumer repos would not run.
+- *Alternative:* keep the hand validators and add a parity test. Rejected: two
+  definitions are the root cause this item exists to remove.
+
+### D3. Gate field is a closed enum
+
+The v2 result's `parked.gate` is the `Gate` enum (nine values) or `null`, not a free
+string of up to 128 characters. A closure property is only checkable over a finite
+set. Allowed combinations are constrained per kind with `oneOf`:
+
+| `parked.kind` | `parked.gate` | Supervisor answer path |
+|---|---|---|
+| `pending_gate` | any `Gate` except `roadmap_approval` | `resolve_parked` evaluates `Gate(parked.gate)`; `escalate_resume` included via the merged narrow fix |
+| `policy_pause` | `null` or `escalate_resume` | `resolve_parked` evaluates `escalate_resume` for the generation |
+| `permission_blocked` | `null` | escalation subject keyed by rule fingerprint (D9), answered by `escalate_resume` |
+| `capability_unavailable` | `null` | escalation subject keyed by missing-lane set (D9), answered by `escalate_resume` |
+
+`roadmap_approval` is excluded from child parks because a child never evaluates it.
+
+Non-parked outcomes close as today: `success` completes the item, `failed:<reason>`
+goes through `orchestrator._handle_failure`, and `vendor_limit:<vendor>:<reason>` goes
+through `_handle_vendor_limit`. `vendor_limit` is written by the host when the child
+session hits a provider limit, not by `emit-result`. The closure test enumerates
+these outcome classes alongside the parked table.
+
+### D4. Normative loop-state -> result mapping, in code
+
+`skills/shared/dispatch_contract.py` owns `result_from_loop_state(state, attempt_ctx)`;
+`runner.py emit-result` is its only CLI. Precedence, first match wins:
+
+| Loop-state condition | Result |
+|---|---|
+| `park` set (v6) | `parked/<park.kind>` with its payload |
+| `pending_gate` set | `parked/pending_gate`, `gate = pending_gate.gate` |
+| `current_phase == "ESCALATE"` | `parked/policy_pause`, `resume_hint` carries `previous_phase` |
+| `current_phase == "DONE"` and `goal_gate.verdict == "abandoned"` | `failed:abandoned` |
+| `current_phase == "DONE"` and `goal_gate.verdict == "passed"` and `last_handoff_id` set | `success` with `handoff_id = last_handoff_id` |
+| `current_phase == "DONE"` otherwise (verdict missing/refused, or no handoff) | `failed:goal_gate_unverified` |
+| any other phase | no result; exit 5 (`EXIT_NOT_TERMINAL`), nothing written |
+
+`park` precedes `pending_gate` because a park records why the child stopped *before*
+reaching a gate. DONE via `abandoned` is separated because the transition table
+routes `ESCALATE --abandoned--> DONE` (and `_check_done_evidence` stamps
+`goal_gate.verdict = "abandoned"`); mapping every DONE to `success` would complete an
+abandoned roadmap item. Evidence is `{loop_state_path, commit, loop_state_digest}`
+computed from the committed file at `HEAD`, so `emit-result` refuses (exit 2) when
+`loop-state.json` has uncommitted changes.
+
+The result is written to
+`openspec/changes/<id>/dispatch-results/<dispatch-slug>-g<N>.json`, where
+`dispatch-slug` replaces every character outside `[A-Za-z0-9._-]` with `-` (dispatch
+IDs contain `:`), and is also printed to stdout. The worker commits the file; the
+cross-session message carries only its path and commit.
+
+### D5. Gate provenance and the one-way answer
+
+Every gate-decision record (child `loop-state.gate_decisions` and supervisor
+`checkpoint.gate_decisions`) gains `provenance`:
+
+- `{"source": "posture", "posture_digest": "<sha256>"}` for `auto`, `posture_block`
+  and timeout-default resolutions;
+- `{"source": "human", "approval_ref": "gate-decision:<id>" | null}` for
+  console/coordinator approvals and rejections.
+
+`posture_digest` is the SHA-256 of the canonical JSON of the *parsed* `gates` map
+(`trust_posture.posture_digest()`), so prose edits to `TRUST_POSTURE.md` do not count
+as a posture change, and an absent posture has the fixed digest of the all-`block`
+default. `gate-request.schema.json` (`pending_gate.posture`) gains the same
+`posture_digest`.
+
+Authority rule (closes the "two state holders" gap): for a dispatched child the
+supervisor's record is authoritative and its posture (at the roadmap workspace's repo
+root) is the one evaluated. The child never re-evaluates a pending gate itself; it
+applies only the `gate_answer` its marker carries. Because the child's worktree
+posture can differ from the supervisor's (Issue 1 began exactly that way), the marker
+carries the supervisor's `posture_digest`, and a dispatched child whose worktree
+digest differs takes no `auto` disposition and parks `pending_gate` instead, so the
+supervisor decides. Only a standalone run re-evaluates its own pending gate in
+`gate-check`.
+
+Re-evaluation rule (whoever is authoritative): on resume, a `posture`-provenance block
+whose digest differs from the current posture digest is re-evaluated; a
+`human`-provenance record is final for its subject. Comparing the digest instead of only the gate's disposition
+(today's supervisor rule) also catches `notify_with_timeout` parameter changes.
+
+Answer direction: supervisor -> child only. The resume request carries
+`gate_answer: {gate, decision, approval_ref}`. The child applies it with
+`runner.py gate-answer <change> --gate G --decision D --approval-ref R`, which records
+a `human`-provenance (or, for a posture-derived proceed, `posture`-provenance) record
+and clears `pending_gate`. `gate-answer` refuses a `--approval-ref` that does not
+match the one in the current launch marker. The supervisor never writes a child
+worktree file other than the launch marker.
+
+- *Alternative:* the child re-reads the supervisor checkpoint to discover answers.
+  Rejected: the child's worktree may be on another host and branch; the request is the
+  only channel both sides share.
+
+### D6. Launch token digest, minted per generation
+
+`checkpoint.json` stores `launch_digest: "sha256:<64 hex>"` and never the raw token.
+The raw token exists only in the request handed to the host. `child_start` verifies
+`hmac.compare_digest(sha256(token), digest)`.
+
+Because the supervisor cannot re-emit a token it no longer has, a token is minted per
+*launch generation*: `resume` and a new `ExecutionAdapter.reissue(dispatch_id)` mint a
+fresh token, store its digest under the same compare-and-swap that increments or
+re-arms the generation, and return a request carrying it. `reissue` is allowed only
+for `prepared` attempts and pre-go expired claims (the states where a takeover is
+already permitted), so it cannot hand a second owner a post-go generation. The prior
+"same token on resume" clause in Durable Delegated Attempt Ledger is modified
+accordingly.
+
+Field name and format are chosen against the default gitleaks `generic-api-key` rule:
+the key contains none of its keywords (`token`, `key`, `secret`, `auth`, ...) and the
+`sha256:` prefix breaks its value character class. A committed fixture checkpoint with
+live attempts (`skills/tests/roadmap-runtime/fixtures/landable-checkpoint.json`) is
+scanned by the existing CI gitleaks job with no allowlist entry; a unit test asserts
+no serialized checkpoint field name matches the rule's keyword set.
+
+Legacy reader: a stored `launch_token` is converted to `launch_digest` on load and the
+raw value is dropped on the next save. The live roadmap checkpoint is not edited by
+this change; it migrates the next time the supervisor saves it.
+
+### D7. Host-portable isolation
+
+Attempt isolation becomes `{mode, worktree_ref, branch, host_id}`:
+
+- `worktree_ref`: the worktree path relative to the managed worktree root
+  (`managed_worktree` mode) or to the repo root (`harness_provided` mode when it is
+  inside the repo), else `null`.
+- `host_id`: a stable, non-secret host identifier from
+  `skills/shared/environment_profile.py` (cloud session environment ID when present,
+  else a hash of the machine ID). Never a hostname or username.
+
+On reconcile, an attempt whose `host_id` differs from the current host is:
+
+- **rebound** when a worktree for `branch` exists under this host's managed root, its
+  `HEAD` contains the attempt's last recorded evidence commit, and its
+  `loop-state.json` digest matches; the attempt keeps its generation and records a
+  `rebound` history entry with the new `host_id`;
+- **reinitialized** when no such worktree exists and the attempt is `prepared`,
+  `parked`, or pre-go: a managed worktree is created for `branch`, the generation is
+  incremented, and a fresh token is minted (D6);
+- otherwise (post-go with no positive liveness evidence) left in `quarantined`, as the
+  existing liveness rules already require.
+
+`resolve_worktree(attempt)` replaces every direct read of
+`isolation["worktree_path"]` in `execution.py` and `orchestrator.py`; absolute paths
+exist only in memory.
+
+### D8. Roadmap-approval-scoped auto
+
+`TRUST_POSTURE.md` gate configs for `proposal_approval` and `replan_required` gain an
+optional `unscoped` sub-config (same shape as a gate config, `auto` disallowed),
+defaulting to `{disposition: block}`. `approval_gate` resolves those two gates as
+follows: `auto` applies only when the current launch marker (written by `child_start`
+after the supervisor verified the ref with `require_approval_ref`) carries a
+`roadmap_approval_ref`. `ApprovalGate` obtains the marker itself through an injected
+`marker_reader` seam (default: a lazy import of
+`dispatch_contract.read_launch_marker`); a `roadmap_approval_ref` supplied in the
+evaluation context is ignored, so no caller can assert scope by passing a value.
+Without a marker ref, the `unscoped` config applies and the decision's `reason` names
+the fallback. The `scope` used is recorded in the gate-decision record. The seam lets
+`wp-posture` land and test before `wp-contract-lib` exists.
+
+`prepare` persists the verified `roadmap_approval_ref` on each attempt (it is a
+`gate-decision:<uuid>` reference, not a secret) so that `child_start` can write it
+into every generation's marker and so that the supervisor-side evaluation in
+`gate_router.resolve_parked` can supply a `marker_reader` that returns the attempt's
+own ref. Both sides therefore apply the same scope rule from the same recorded fact.
+
+Trust boundary: the marker lives in the child's own worktree (gitignored
+`.supervised-dispatch/`). Anything able to forge it can already act as the child, so
+the marker is trusted to the same degree as the child process; it is not a defence
+against a malicious child.
+
+- *Alternative:* the child re-verifies the ref against the roadmap checkpoint.
+  Rejected: the checkpoint lives on the roadmap branch, not the change branch; the
+  marker is the authenticated channel (its generation and owner are already verified).
+- *Alternative:* hard-code `block` as the fallback with no posture field. Rejected:
+  the acceptance outcome speaks of the gate's "non-auto fallback", and operators may
+  want `notify_with_timeout` for standalone runs.
+
+### D9. One escalation per capability park
+
+`gate_router.resolve_parked` maps `permission_blocked` and `capability_unavailable` to
+an `escalate_resume` subject keyed by a *dedupe fingerprint* instead of by dispatch:
+
+- `permission_blocked`: `sha256(tool, rule, classifier_reason)` where `rule` is the
+  matched permission rule (for example `Bash(env *)`), never the full command.
+- `capability_unavailable`: `sha256(phase, sorted(missing_lanes))`.
+
+N parked attempts with the same fingerprint produce one `pending_gates` entry listing
+all their dispatch IDs, each with the `lease_generation` it had at projection. One
+operator answer resumes every attempt in that entry, each through its own
+generation-checked CAS.
+
+Decision-record shape for the fan-out: answering a fingerprint entry writes **one
+`escalate_resume` record per listed dispatch**, each with that dispatch's own
+`dispatch_id` and projected `lease_generation`, plus the shared `dedupe_fingerprint`
+and the answer's `provenance`. `gate_router.require_approval_ref` therefore keeps its
+existing per-dispatch checks (`dispatch_id` equal, and for `escalate_resume`
+`lease_generation` equal) unchanged; an attempt whose generation moved since
+projection fails that check and is skipped and reported. `ExecutionAdapter.resume`
+accepts parked kinds `permission_blocked` and `capability_unavailable` in addition to
+`pending_gate` and `policy_pause`, with expected gate `escalate_resume`, and also
+requires the record's `dedupe_fingerprint` to equal the fingerprint recomputed from
+the attempt's parked payload.
+
+The redacted command is stored only after passing through
+`skills/session-log/scripts/sanitize_session_log.sanitize()` (secret-pattern and
+high-entropy redaction; the stored value is the first element of its
+`(content, redactions)` return value), truncated to 256 characters; it is redacted by
+`runner.py park` in the child, and re-sanitized by the router.
+
+### D10. Execution profile and honest quorum
+
+The supervisor resolves `execution_profile` once per batch with
+`review_dispatcher.py --check-vendors --json`, which reports, per mode, the lanes for
+which a dry invocation (`<cli> --version`, or for SDK/API lanes the adapter's own
+authenticated no-op, with a 10-second timeout) succeeded. Credentials are touched only
+inside the adapter's existing credential path and never printed; workers never probe. The profile names
+`probe_command`, the only probe a worker may re-run. `review_requirements` holds
+`min_quorum` per review phase (`PLAN_REVIEW`, `IMPL_REVIEW`, `VAL_REVIEW`; default 2,
+today's `--min-vendors` value, overridable by router context key `review_min_quorum`)
+and `counting_lanes`: every lane the roster (`agents.yaml`) configures for mode
+`review`, **verified or not**, ordered by the `cost_policy.tiers` ladder in
+`agent-coordinator/routing.yaml` (subscription-local, subscription-cloud, metered-api).
+`execution_profile.lanes.review` holds the verified subset, so a park's
+`missing_lanes` is `counting_lanes` minus the verified lanes and is non-empty
+whenever quorum is unmet by a configured-but-unverified lane; distinct gaps therefore
+fingerprint differently (D9). The ladder orders lanes; it does not exclude any tier
+from counting. `routing.yaml` itself is not edited.
+
+In a dispatched child (launch marker present), a review phase whose verified lanes are
+fewer than `review_requirements.min_quorum[phase]` records
+`park(kind=capability_unavailable)` and stops; it never lowers the quorum. A
+standalone run keeps today's behaviour (disable CLI review) but appends a
+`single_vendor_review` or `review_skipped` degradation.
+
+Where this happens: today the below-quorum decision is made in the worker protocol
+(`skills/autopilot/SKILL.md` runs `--check-vendors` and sets
+`CLI_REVIEW_ENABLED=false`, so the review phases are skipped and `converge()` never
+runs). In a dispatched child the protocol instead keeps review enabled and, at
+`PLAN_REVIEW` / `IMPL_REVIEW` entry, compares `execution_profile.lanes.review` with
+`review_requirements.min_quorum[phase]` and runs `runner.py park --kind
+capability_unavailable`. A standalone run below quorum runs `runner.py
+record-degradation --code review_skipped` when it disables review.
+`convergence_loop.converge()` gains a pre-dispatch guard that returns
+`reason="capability_unavailable"` when handed fewer verified lanes than `min_quorum`;
+it never writes loop state (`runner.py` stays the only writer of `park` and
+`degradations`, D11).
+
+Per-environment quorum as data. The operator's cloud review-quorum decision
+(TRUST_POSTURE.md "Review quorum in cloud containers (temporary)", 2026-10-09) is
+expressed as data, not as a prompt instruction:
+`skills/parallel-infrastructure/review_quorum_policy.json` holds a default
+`min_quorum` of 2 and an active policy entry for `environment: cloud_container`
+that applies only while fewer than 2 review lanes verify, setting `min_quorum: 1`,
+with its `source` and `sunset` (delete the entry once API-based multi-vendor
+review or the GX10 lane reaches cloud workers). `resolve_quorum_policy()` in
+`review_dispatcher.py` resolves it (environment from
+`environment_profile.detect()`), `--check-vendors --json` reports it as
+`quorum_policy`, and the supervisor copies `min_quorum` plus
+`review_requirements.quorum_policy {environment, policy_id, sunset}` into every
+request. A worker gets `min_quorum` 1 only through that data. A single-lane run is
+detected by lanes failing to dispatch (the dry invocation, or a round's
+`vendor_unavailable`/`auth_required`), never by reading environment variables or
+credentials, and the review records `single_vendor_review` with `phase` and
+`detail: "vendor=<lane>"`. GATEKEEPER `proceed_with_review` now schedules
+VAL_REVIEW on the host-driven `runner.py transition` path too (it was set only by
+`run_loop`).
+
+Degradation codes (closed enum): `single_vendor_review`, `review_skipped`,
+`coordinator_projection_forbidden`, `audit_sink_failed`, `phase_fallback_inline`,
+`handoff_local_fallback`. Each entry is `{code, phase, detail<=512}`, at most 32 per
+result.
+
+### D10a. Launch marker v2 is the child's only view of the request
+
+The child never sees the supervisor checkpoint. `child_start` writes the launch marker
+(`<worktree>/.supervised-dispatch/<change-id>/<item-id>-attempt-<n>.marker`, path
+unchanged) with the request fields the child needs: `dispatch_id`, `generation`,
+`owner_nonce`, optional `continuation`, optional `gate_answer`,
+`roadmap_approval_ref`, `posture_digest` (the supervisor's), `execution_profile`,
+`review_requirements`. The marker carries
+no token. `skills/shared/dispatch_contract.read_launch_marker(change_id)` returns the
+highest-generation marker under `.supervised-dispatch/<change-id>/` whose identity
+fields validate (or `None` for a standalone run); `runner.py` and `approval_gate` call only this function. "Dispatched
+child" in the specs means this function returned a marker.
+
+### D11. Loop state v6
+
+`LoopState` advances to `schema_version` 6 with `park: dict | None` and
+`degradations: list[dict]`. `_apply_transition` refuses while `park` is set (same
+enforcement point as `pending_gate`). `runner.py park` and
+`runner.py record-degradation` are the only writers. The resume continuation clears
+`park` through `gate-answer --gate escalate_resume --approval-ref`.
+
+## Package boundaries and ordering
+
+See `work-packages.yaml`. The DAG is shaped by file ownership:
+
+- Roots (parallel): `wp-merge-narrow-fix` (gate_router/execution/supervise SKILL),
+  `wp-dispatch-schemas` (openspec/schemas dispatch + checkpoint), `wp-posture`
+  (trust_posture, approval_gate, gate schemas).
+- `wp-contract-lib` (shared/dispatch_contract.py) depends on schemas.
+- `wp-runtime-ledger` (models/checkpoint/orchestrator) and `wp-autopilot-child`
+  (runner/autopilot/autopilot SKILL) run in parallel after contract-lib and posture.
+- `wp-review-honesty` (review_dispatcher, convergence_loop) after autopilot-child.
+- `wp-supervisor` (execution/gate_router/supervise SKILL) after merge, runtime-ledger,
+  posture.
+- `wp-integration` (closure, e2e, cross-host, secret-scan fixture) last.
+
+## Risks and trade-offs
+
+- **Schema `$ref` resolution in installed copies.** Consumer repos may only have the
+  `install_assets` mirror. Mitigation: the loader's fallback path and a parity test
+  between the two schema copies.
+- **Token rotation changes resume semantics.** A host still holding an old request
+  after `reissue` gets `launch token mismatch`. Accepted: that is the intended
+  revocation, and it only happens in states where a takeover is already allowed.
+- **Dedupe merges distinct problems.** Two different commands under one permission rule
+  share an escalation. Accepted: the operator fixes rules, not commands; the entry
+  lists every dispatch and its redacted command.
+- **v1 tolerance window.** Kept small and removed later; the closure test does not
+  cover v1.
+- **Scope.** L effort across four skills. Mitigated by eight packages with disjoint
+  write scopes.
+
+## Known constraints
+
+- **Worktree launchpads are rooted at `main`.** `Agent(isolation="worktree")`
+  creates the sub-agent's checkout from the default branch, not from a stacked
+  feature base such as `openspec/dispatch-contract`. The IMPLEMENT phase prompt
+  already tells the sub-agent its launchpad is disposable and to adopt the feature
+  branch through `/implement-feature`; in a cloud harness, where worktree ops
+  short-circuit, the orchestrator must instead name the feature base explicitly
+  (`git switch -c <branch> origin/<feature-branch>`). A cheap in-scope fix did not
+  exist here — the prompt lives in `phase_agent.py` outside this change's packages —
+  so making the prompt carry the resolved feature base is an open follow-up.
+
+## Implementation notes
+
+Recorded during IMPLEMENT (sequential tier):
+
+- `dispatch_contract`'s schema locator falls back to the shipping repository's own
+  `openspec/` before the install_assets mirror, so the test helpers that copy only
+  `checkpoint.schema.json` into a temporary repo resolve its `$ref`s without copying
+  them (task 5.2a needed no helper change).
+- The v2 request keeps `gate_answer` optional next to `continuation`, so an upgraded
+  v1 continuation stays valid; writers always emit both.
+- `redact_command` redacts HTTP auth-scheme and auth-header values before
+  `sanitize_session_log.sanitize()`: the sanitizer alone leaves
+  `Authorization: Bearer <short token>` intact. IMPL_ITERATE added URL-userinfo
+  passwords, `-u/--user user:pass`, and credential-named flags/keys
+  (`--password x`, `--token=x`, `*_secret_access_key x`), which the sanitizer also
+  passes when the value is short.
+- SDK/API review lanes have no authenticated no-op in their adapters yet; they are
+  reported unverified (`probe_unsupported`) rather than counted on importability.
+- `apply` accepts evidence whose commit is an ancestor of the worktree HEAD, because
+  the worker commits the emitted result file after `emit-result`; the loop-state
+  digest still pins the file.
+- Cross-host reinitialize keeps a parked attempt's generation (only its isolation and
+  digest move), so the attempt's bound `escalate_resume` approval stays valid
+  (advisory finding 13); prepared and pre-go claimed attempts get generation + 1.
+- `reissue` launches a reinitialized attempt; `prepare` itself still skips an item
+  with an unresolved attempt.
+- The launch marker also carries the attempt's portable `isolation`, which
+  `emit-result` reads for `worktree_ref` and `host_id`.
+- The landable-fixture keyword test exempts the pre-existing gate-decision field
+  `authorizing_disposition` (contains `auth`; its values are a closed enum below the
+  rule's entropy threshold); every dispatch-attempt field is keyword-free, and a
+  port of the default `generic-api-key` rule finds nothing in the fixture.
 
 ## Open questions
 
-- Which capability do these requirements finally belong to?
-- What are the non-goals for this item?
-- Which decisions here need recording before implementation starts?
+- History rewrite for PR #662: commits already on the roadmap branch contain raw
+  tokens, so gitleaks over full history still fails until those commits are squashed
+  or allowlisted by SHA. This change makes new state clean; the history decision is
+  the operator's (not an edit this change may make).
+- Removal of v1 reading (D1) is a follow-up; the trigger is "no unresolved attempt has
+  a v1 result", which a small check in `/supervise` can report.
diff --git a/openspec/changes/dispatch-contract/handoffs/eeedef7e-c78e-4f7c-a6f5-94cc4a8150f5.json b/openspec/changes/dispatch-contract/handoffs/eeedef7e-c78e-4f7c-a6f5-94cc4a8150f5.json
new file mode 100644
index 0000000..d482996
--- /dev/null
+++ b/openspec/changes/dispatch-contract/handoffs/eeedef7e-c78e-4f7c-a6f5-94cc4a8150f5.json
@@ -0,0 +1,52 @@
+{
+  "handoff_id": "eeedef7e-c78e-4f7c-a6f5-94cc4a8150f5",
+  "agent_name": "autopilot-plan-review",
+  "agent_type": "claude_code",
+  "change_id": "dispatch-contract",
+  "phase": "PLAN_REVIEW",
+  "outcome": "converged",
+  "recorded_at": "2026-10-09T07:25:00Z",
+  "previous_handoff_id": "9b138f6d-f5f3-4a7f-99bb-0d3bb6a5e86e",
+  "summary": "PLAN_REVIEW ran convergence_loop.converge() (review_type=plan, min_quorum=1, max_rounds=3, fix_mode=inline) with a single claude_code lane per the operator's escalate_resume decision. Converged in round 3: blocking trend [11, 1, 0]. Round 1 found 11 blocking plan defects (3 high, 8 medium, all deterministic and verified against the repo); a PLAN_FIX applicator edited only the cited file_paths and the scope check accepted every edit. Round 2 re-verified all 11 as resolved and found 1 new medium defect introduced by the round-1 fix; round 3 re-verified it resolved.",
+  "degradations": [
+    {"code": "single_vendor_review", "phase": "PLAN_REVIEW", "detail": "Only claude_code dispatchable; codex listed by --check-vendors is a known false positive (no codex binary). min_quorum lowered to 1 by recorded operator decision (escalate_resume console_approved 2026-10-09T07:09:10Z). Findings are one vendor's opinion with no cross-vendor confirmation."},
+    {"code": "coordinator_projection_forbidden", "phase": "PLAN_REVIEW", "detail": "No coordinator handoff/memory write available to this trust-2 cloud agent; handoff written to openspec/changes/dispatch-contract/handoffs/ and session-log.md instead."},
+    {"code": "handoff_local_fallback", "phase": "PLAN_REVIEW", "detail": "Handoff persisted locally (this file) rather than through the coordinator."}
+  ],
+  "phase_history_substeps": [
+    {"phase": "PLAN_FIX", "round": 1, "started_at": "2026-10-09T07:17:11Z", "completed_at": "2026-10-09T07:19:57Z", "ledger_items": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], "commit": "refine(plan): PLAN_FIX round 1"},
+    {"phase": "PLAN_FIX", "round": 2, "started_at": "2026-10-09T07:22:31Z", "completed_at": "2026-10-09T07:22:49Z", "ledger_items": [14], "commit": "refine(plan): PLAN_FIX round 2"}
+  ],
+  "completed_work": [
+    "Round 1 review: 13 findings (11 blocking) written to .review-cache/round-1/",
+    "PLAN_FIX round 1: design.md D1/D2/D9/D10, proposal.md Why/Impact, specs/roadmap-orchestration/spec.md, tasks.md (2.3a, 2.4, 4.2, 4.3, 5.2, 5.2a, 6.2, 6.5, 7.3, 8.1-8.3), work-packages.yaml scopes",
+    "Round 2 review: 11 items re-verified resolved, 1 new blocking (item 14), 1 low advisory (item 15)",
+    "PLAN_FIX round 2: design.md D2 test-repointing order",
+    "Round 3 review: item 14 re-verified resolved; 0 blocking",
+    "validate_work_packages.py: VALID; openspec validate dispatch-contract --strict: valid"
+  ],
+  "decisions": [
+    "Existing openspec/contracts/roadmap-orchestration/schemas/ v1 schemas: request/result frozen as v1 reader schemas, delegated-dispatch-attempt becomes the single attempt definition $ref'd by checkpoint.schema.json, bounded-dispatch-context $ref'd by the v2 request (design D2)",
+    "Capability-park fan-out writes one escalate_resume record per listed dispatch (own dispatch_id and lease_generation, shared dedupe_fingerprint) so require_approval_ref keeps per-dispatch checks (design D9)",
+    "counting_lanes = all roster review lanes, verified or not; missing_lanes = counting_lanes minus verified (design D10)",
+    "Dispatched-child quorum park happens in the worker protocol at review-phase entry via runner.py park; convergence_loop gets only a pre-dispatch guard that writes no loop state (design D10, tasks 6.5/7.3)"
+  ],
+  "advisory_open": [
+    "13 (low): D7 reinitializing a parked attempt on another host bumps lease_generation and invalidates an outstanding escalate_resume approval",
+    "15 (low): task 5.2 adds a roadmap-runtime -> skills/shared dependency; building the registry inside models.py would avoid it"
+  ],
+  "next_steps": [
+    "Orchestrator applies outcome 'converged' to move PLAN_REVIEW -> IMPLEMENT"
+  ],
+  "relevant_files": [
+    "openspec/changes/dispatch-contract/design.md",
+    "openspec/changes/dispatch-contract/proposal.md",
+    "openspec/changes/dispatch-contract/tasks.md",
+    "openspec/changes/dispatch-contract/work-packages.yaml",
+    "openspec/changes/dispatch-contract/specs/roadmap-orchestration/spec.md",
+    "openspec/changes/dispatch-contract/.review-ledger/ledger.json",
+    "openspec/changes/dispatch-contract/.review-cache/round-1/",
+    "openspec/changes/dispatch-contract/.review-cache/round-2/",
+    "openspec/changes/dispatch-contract/.review-cache/round-3/"
+  ]
+}
diff --git a/openspec/changes/dispatch-contract/impl-findings.md b/openspec/changes/dispatch-contract/impl-findings.md
new file mode 100644
index 0000000..a43d6d3
--- /dev/null
+++ b/openspec/changes/dispatch-contract/impl-findings.md
@@ -0,0 +1,50 @@
+# Implementation Findings: dispatch-contract
+
+IMPL_ITERATE, threshold `medium`. Review was single-vendor (`claude_code`), under the
+cloud-container quorum policy (`single_vendor_review`).
+
+## Iteration 1
+
+| # | Type | Criticality | Description | Fix | Commit |
+|---|------|-------------|-------------|-----|--------|
+| 1 | security | high | `_resolve_capability_park` re-evaluated the posture whenever a fingerprint's member listing differed from a human rejection's record, so a posture flip to `auto` could clear an operator's rejection | Reuse a human-provenance blocked subject without consulting the posture; the entry lists the current members | 9c52005 |
+| 2 | bug | high | Child `gate-check` treated a human rejection as final forever. After the operator resumed the run, the gate could never be asked again, and a caller outside `ESCALATE` got exit 4 with the loop left where it was | The rejection stays in force until a later human `escalate_resume` proceed (a posture-derived resume does not end it). While it is in force, `gate-check` enters `ESCALATE` | 6892017 |
+| 3 | security | high | `redact_command` kept short credentials that the sanitizer passes: URL userinfo, `curl -u user:pw`, `--password x`, `--token=x`, `*_secret_access_key x` | Added URL-userinfo, user-flag and keyed-secret redaction before `sanitize()` | af0817f |
+| 4 | bug | medium | Cross-host reinitialize took over a pre-go claim whose lease had not expired, bumping the generation while a live child on the other host still held it | Reinitialize a claimed attempt only after its lease has expired, the same rule `child_start`/`reissue` use | a3330ff |
+| 5 | bug | medium | `apply` did not re-derive the result from loop state. A composed v2 result could complete an item whose goal gate was abandoned or refused, or park on the wrong gate or missing-lane set | `apply` re-derives native v2 results through `result_from_loop_state` and refuses any outcome, handoff, kind, gate or fingerprint mismatch (v1 is still tolerated) | 8b76939 |
+| 6 | edge-case | medium | The closure enumeration read any kind/gate node that is not a const or enum as `null` alone, so loosening a gate would still pass the closure test | Non-enumerable nodes raise `DispatchContractError` naming the branch | 609aff1 |
+
+Supervisor-requested follow-ups (tasks 7.6, 7.7): `converge(base_ref=)` pass-through
+(9cdc27d), and converge's own `.review-ledger/` and `.review-cache/` writes left out of the
+post-fix scope check (9805527).
+
+## Iteration 2
+
+| # | Type | Criticality | Description | Fix | Commit |
+|---|------|-------------|-------------|-----|--------|
+| 7 | bug | medium | Regression from fix 1: after the operator approved a rejected fingerprint, the stale rejection was still the latest blocked subject, so a new park on that fingerprint stayed blocked. Members that joined after the rejection were also not resumed by the approval | A subject answered by a later proceed is no longer the prior record. `answer_escalation` resumes current fingerprint members that the subject's listing predates | 4cc15ae |
+
+## IMPL_REVIEW (converge, targeted fixes)
+
+`converge()` ran with `review_type=implementation`, `fix_mode=targeted`, `min_quorum=1`
+from `resolve_quorum_policy` (policy `cloud-container-single-vendor-2026-10-09`), and
+`base_ref=origin/openspec/roadmap-multiplayer-collaboration`. Review was single-vendor
+(`claude_code`), degradation `single_vendor_review`. Blocking trend per round: `[5, 0]`.
+Converged in round 2.
+
+| Ledger | Type | Criticality | Description | Fix | Commit |
+|---|---|---|---|---|---|
+| 16, 17 | security | medium | A dispatched child's `gate-answer` checked only `--approval-ref` against the marker, so a matching reference could record an approval the supervisor had rejected, or answer another gate | `--gate` and `--decision` must also equal the marker's `gate_answer` (exit 2, nothing recorded), with tests | 5b28e32 |
+| 18, 19 | security | medium | `apply_delegated_batch` persisted a `permission_blocked` result's `parked.command` verbatim into the tracked checkpoint (attempt and journal); only the router's record was re-sanitized | The command is passed through `redact_command` right after validation, before binding, journaling and persistence, with an apply-level test | b34c6af |
+| 20 | correctness | low | Auth-header redaction was not idempotent (a second pass rewrote an already-redacted header) | The lookahead skips leading whitespace | bad6de9 |
+
+Advisory (low) added in IMPL_REVIEW: `_resolve_capability_park`'s proceed path indexes
+`records[0]` when the attempt is not among its fingerprint's parked members, which
+raises `IndexError` instead of a `GateRefusalError`.
+
+## Remaining (below threshold)
+
+- low: in a dispatched child whose posture digest has drifted, a `notify_with_timeout` gate can still take its posture-derived timeout default. The spec forbids only `auto` here; parking would follow the supervisor-authority intent more closely.
+- low: `emit-result` does not cross-check `--dispatch-id`/`--generation` against the launch marker. The supervisor's identity check still rejects a mismatch at `apply`.
+- low: rebind accepts a post-go attempt that has no recorded evidence when only a worktree for its branch exists on this host. The evidence conditions hold vacuously.
+- open question: once a human has rejected `escalate_resume` itself, gate-check can never re-ask it. Recovery is the `abandoned` edge or an operator edit.
diff --git a/openspec/changes/dispatch-contract/loop-state.json b/openspec/changes/dispatch-contract/loop-state.json
new file mode 100644
index 0000000..094a7b9
--- /dev/null
+++ b/openspec/changes/dispatch-contract/loop-state.json
@@ -0,0 +1,137 @@
+{
+  "schema_version": 6,
+  "change_id": "dispatch-contract",
+  "current_phase": "VAL_REVIEW",
+  "iteration": 0,
+  "total_iterations": 11,
+  "max_phase_iterations": 3,
+  "findings_trend": [],
+  "blocking_findings": [],
+  "vendor_availability": {},
+  "packages_status": {},
+  "package_authors": {},
+  "implementation_strategy": {},
+  "memory_ids": [],
+  "handoff_ids": [
+    "6166f2e8-de8e-4375-8750-316e09fd34f6",
+    "63b11a2c-616f-4b7a-91a1-c6d1278bde31",
+    "9b138f6d-f5f3-4a7f-99bb-0d3bb6a5e86e",
+    "eeedef7e-c78e-4f7c-a6f5-94cc4a8150f5",
+    "8b3b7d01-452a-498f-9e34-46fdd6ca5e94",
+    "8d309935-3b68-44db-be5c-d6b327ec8c61",
+    "13e77665-feba-4ef3-b28a-a9b61d278135",
+    "8ebe1a5a-c868-49cc-b72d-f6bff31d85e9"
+  ],
+  "phase_history": [
+    {
+      "at": "2026-10-06T09:10:51.641130+00:00",
+      "outcome": "proceed_with_review",
+      "phase": "GATEKEEPER"
+    },
+    {
+      "at": "2026-10-06T09:30:38.405916+00:00",
+      "outcome": "complete",
+      "phase": "PLAN_ITERATE"
+    },
+    {
+      "at": "2026-10-06T11:08:14.058241+00:00",
+      "outcome": "max_iter",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "at": "2026-10-06T11:08:14.233483+00:00",
+      "note": "capability_unavailable: PLAN_REVIEW requires min_quorum=2; only claude_code is dispatchable (codex listed by --check-vendors but no codex CLI/credential). Quorum not lowered; awaiting operator decision on cloud review lane (GX10/policy/credential). handoff 9b138f6d-f5f3-4a7f-99bb-0d3bb6a5e86e",
+      "outcome": "host_escalate",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "at": "2026-10-09T07:24:26.295968+00:00",
+      "outcome": "converged",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "at": "2026-10-09T12:52:59.405442+00:00",
+      "outcome": "complete",
+      "phase": "IMPLEMENT"
+    },
+    {
+      "at": "2026-10-09T13:26:34.431681+00:00",
+      "outcome": "complete",
+      "phase": "IMPL_ITERATE"
+    },
+    {
+      "at": "2026-10-09T13:47:51.835672+00:00",
+      "outcome": "converged",
+      "phase": "IMPL_REVIEW"
+    },
+    {
+      "at": "2026-10-09T13:55:05.532741+00:00",
+      "outcome": "passed",
+      "phase": "VALIDATE"
+    }
+  ],
+  "last_handoff_id": "8ebe1a5a-c868-49cc-b72d-f6bff31d85e9",
+  "started_at": "2026-10-06T09:08:58.470413+00:00",
+  "phase_started_at": "2026-10-09T13:55:08.852195+00:00",
+  "previous_phase": "PLAN_REVIEW",
+  "escalation_reason": "capability_unavailable: PLAN_REVIEW requires min_quorum=2; only claude_code is dispatchable (codex listed by --check-vendors but no codex CLI/credential). Quorum not lowered; awaiting operator decision on cloud review lane (GX10/policy/credential). handoff 9b138f6d-f5f3-4a7f-99bb-0d3bb6a5e86e",
+  "val_review_enabled": true,
+  "cli_review_enabled": true,
+  "error": null,
+  "phase_archetype": "validator",
+  "force": false,
+  "gate_signals": {},
+  "gate_verdict": "proceed_with_review",
+  "gate_decisions": [
+    {
+      "approval_id": null,
+      "authorizing_disposition": "auto",
+      "default_action": null,
+      "disposition": "auto",
+      "gate": "proposal_approval",
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "PLAN",
+      "posture_present": true,
+      "reason": "gate 'proposal_approval' auto-approved by trust posture",
+      "recorded_at": "2026-10-06T09:11:03.554035+00:00",
+      "resolution": "auto",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "notified": null,
+      "outcome": "blocked",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "reason": "gate 'escalate_resume' parked: trust posture disposition is block",
+      "recorded_at": "2026-10-09T07:09:02.414788+00:00",
+      "resolution": "posture_block",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "note": "Operator (in-session, 2026-10-09): allowlist launch-nonce commits by SHA, then continue. Review proceeds single-vendor (claude_code) under the dispatch's accepted single_vendor_review degradation.",
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "reason": "gate 'escalate_resume' approved by the operator \u2014 Operator (in-session, 2026-10-09): allowlist launch-nonce commits by SHA, then continue. Review proceeds single-vendor (claude_code) under the dispatch's accepted single_vendor_review degradation.",
+      "recorded_at": "2026-10-09T07:09:10.123228+00:00",
+      "resolution": "console_approved",
+      "timeout_seconds": null
+    }
+  ],
+  "pending_gate": null,
+  "goal_gate": null,
+  "park": null,
+  "degradations": []
+}
diff --git a/openspec/changes/dispatch-contract/plan-findings.md b/openspec/changes/dispatch-contract/plan-findings.md
new file mode 100644
index 0000000..57d25c7
--- /dev/null
+++ b/openspec/changes/dispatch-contract/plan-findings.md
@@ -0,0 +1,65 @@
+# Plan Findings: dispatch-contract
+
+Produced by `/iterate-on-plan` (PLAN_ITERATE phase of autopilot). Threshold: medium.
+
+## Iteration 1
+
+Baseline `openspec validate --strict`: passed (scaffold). The scaffold from
+`plan-roadmap` was a placeholder: generic tasks, a placeholder capability, tautological
+scenarios.
+
+| # | Type | Criticality | Description | Fix |
+|---|------|-------------|-------------|-----|
+| 1 | completeness | critical | proposal.md lacked Why / What Changes / Impact sections | Rewrote proposal with all required sections, non-goals, and an Impact table |
+| 2 | consistency | critical | Spec delta targeted placeholder capability `multiplayer-collaboration`; real owners are roadmap-orchestration, supervise, skill-workflow, trust-posture, parallel-infrastructure | Removed placeholder; wrote five deltas against existing capabilities |
+| 3 | completeness | critical | Outcomes 6-8 (token digest, host-portable isolation, scoped auto) had no requirement at all | Added RO Launch Token Digest, RO Host-Portable Attempt Isolation, TP Roadmap-Approval-Scoped Auto Dispositions |
+| 4 | testability | high | Every scenario was "WHEN implemented THEN <outcome>" | Replaced with concrete WHEN/THEN including failure paths, exit codes, error strings |
+| 5 | feasibility | high | tasks.md was five generic placeholders (giant tasks, no traceability) | 30 tasks in 9 groups with deps and a requirement traceability table |
+| 6 | consistency | high | Existing RO "Durable Delegated Attempt Ledger" requires a stable token re-emitted on resume; digest-only storage makes that impossible | D6 per-generation tokens with `reissue`; MODIFIED the requirement |
+| 7 | correctness | high | `ESCALATE --abandoned--> DONE` would be emitted as `success` by a naive DONE->success mapping | D4 maps on `goal_gate.verdict`; scenario "Abandoned work is not reported as success" |
+| 8 | completeness | high | No loop-state representation for `permission_blocked`, `capability_unavailable`, or degradations, so `emit-result` had nothing to map | D11 LoopState v6 with `park` / `degradations`, `runner.py park` / `record-degradation` |
+| 9 | assumptions | high | "non-auto fallback" is undefined in the posture schema | D8 optional `unscoped` sub-config, default `block` (see session-log decision; no interactive channel in this phase) |
+| 10 | assumptions | high | How a child proves it carries a "valid" roadmap_approval_ref was unstated; the child cannot read the roadmap checkpoint | D8/D10a: ref travels in the generation-verified launch marker |
+| 11 | consistency | high | Result shape defined three times (two validators plus inline copy in checkpoint.schema.json) | D2: checkpoint schema `$ref`s the result schema; guard test deletes hand validators |
+| 12 | testability | medium | Closure over `gate` is impossible while `gate` is a free 128-char string | D3: `gate` becomes the `Gate` enum with per-kind `oneOf` |
+| 13 | security | medium | A `launch_*token*` field holding 64-hex would still trip gitleaks generic-api-key (keyword + entropy) | D6: `launch_digest` with `sha256:` prefix; keyword unit test and CI scan of a committed fixture |
+| 14 | security | medium | Blocked command in `permission_blocked` could carry a secret | Sanitized with `sanitize_session_log.sanitize()` in child and router; scenario added |
+| 15 | feasibility | medium | `dispatch_id` contains `:`; unsafe as a file name for the committed result path | D4 `dispatch-slug` rule |
+| 16 | feasibility | medium | Cross-host rebind could hand a post-go attempt to a second owner | D7: rebind only with evidence match; reinitialize only pre-go/prepared/parked; else quarantine |
+| 17 | completeness | medium | Version strategy for in-flight v1 workers unstated | D1 v2 writers, v1-tolerant readers; existing fixtures unchanged |
+| 18 | completeness | medium | design.md was a scaffold with open questions only | Rewrote with D1-D11, alternatives, risks, package boundaries |
+| 19 | parallelizability | medium | No work-packages.yaml | Nine packages, three parallel roots, max width 3; validated |
+| 20 | completeness | medium | Narrow fix branch not merged and no task for it | Task 1.1 / wp-merge-narrow-fix |
+| 23 | consistency | high | Draft re-evaluation rule ran on both sides, but the child's worktree posture can differ from the supervisor's (the original Issue 1 path), so "which holder is authoritative" stayed open | Gate authority rule: dispatched child applies only `gate_answer`; marker carries supervisor `posture_digest`; drift disables `auto`; only standalone runs self-re-evaluate |
+| 21 | scope | low | Raw tokens already in the roadmap branch history still fail full-history gitleaks | Recorded as open question; outside this change's edit scope |
+| 22 | scope | low | Degradation rendering in the digest and automatic lane re-routing | Declared non-goals |
+
+Parallelizability: Independent roots: 3 (wp-merge-narrow-fix, wp-dispatch-schemas,
+wp-posture) | Sequential chains: schemas -> contract-lib -> {runtime-ledger,
+autopilot-child} -> {supervisor, review-honesty} -> integration | Max parallel width: 3.
+File overlap between non-ordered packages: none (merge-narrow-fix and supervisor share
+files and are ordered).
+
+## Iteration 2
+
+| # | Type | Criticality | Description | Fix |
+|---|------|-------------|-------------|-----|
+| 1 | security | high | Scoped `auto` trusted a context-supplied `roadmap_approval_ref` plus a `marker_verified` flag, which any caller could set | `ApprovalGate` reads the marker itself via a `marker_reader` seam; context refs ignored; TP scenarios rewritten; trust boundary of the marker stated in D8 |
+| 2 | consistency | medium | SV said prepare blocks on "exit non-zero", but `--check-vendors` exits 2 both below quorum and on roster failure, so a below-quorum batch would never launch | Failure is defined by unparseable JSON or an `error` field; below-quorum launches with an honest profile (new scenario); PI specifies the `error` JSON shape |
+| 3 | testability | medium | PI "no env key read" scenario was unimplementable for SDK/API lanes, whose no-op needs credentials | Credentials only through the adapter's own path; test asserts sentinel secrets never appear in output and no `env`/`printenv` subprocess |
+| 4 | assumptions | medium | "quorum from the routing cost policy" — `routing.yaml` has tiers but no quorum | D10: `min_quorum` default 2 per review phase, router-context override, `counting_lanes` ordered by the tier ladder; `routing.yaml` not edited |
+| 5 | parallelizability | medium | wp-posture (a root) would have needed `read_launch_marker` from wp-contract-lib | `marker_reader` seam with lazy default import keeps wp-posture a root |
+
+Remaining below threshold: none new.
+
+## Iteration 3
+
+| # | Type | Criticality | Description | Fix |
+|---|------|-------------|-------------|-----|
+| 1 | completeness | medium | The marker must carry `roadmap_approval_ref` on every generation, and the supervisor-side scope check needs it too, but no attempt field stored it (prepare verified and discarded it) | Attempt persists the verified ref (D8, RO ledger scenario, tasks 2.3 / 5.3); supervisor `marker_reader` returns the attempt's ref |
+
+Remaining findings (below threshold, for optional review):
+- low: the shared lock key `feature:dispatch-contract:supervisor` on wp-merge-narrow-fix and wp-supervisor is intentional (ordered packages over the same files).
+- low: D10a marker discovery picks the highest valid generation; a stale marker left by a crashed takeover is ignored by the identity check but not cleaned up. Cleanup stays with the existing `_remove_owned_marker` path.
+
+Termination: threshold met (no findings at or above medium after iteration 3 fixes).
diff --git a/openspec/changes/dispatch-contract/proposal.md b/openspec/changes/dispatch-contract/proposal.md
index 7b4e3bd..0bf2507 100644
--- a/openspec/changes/dispatch-contract/proposal.md
+++ b/openspec/changes/dispatch-contract/proposal.md
@@ -5,22 +5,198 @@
 > Effort: L
 > Priority: 1
 
-## Summary
+## Why
 
-Publish versioned dispatch-request and dispatch-result JSON schemas as the single definition of the supervisor-worker boundary; emit results from loop-state via runner.py emit-result; add gate provenance with posture-digest re-evaluation, execution_profile, review_requirements, degradations[], and the parked kinds permission_blocked and capability_unavailable, with a closure contract test so every schema-permitted parked shape has a supervisor answer path.
+The first `/supervise execute` run of `multiplayer-collaboration` (2026-10-05/06)
+dispatched four workers (ri-01, ri-02, ri-05, ri-20) and none reached
+implementation. Every stall traced to the supervisor-worker boundary, whose published
+contract is not the one the runtime enforces: v1 JSON Schemas exist under
+`openspec/contracts/roadmap-orchestration/schemas/` (`supervised-dispatch-request`,
+`supervised-dispatch-result`, `delegated-dispatch-attempt`,
+`bounded-dispatch-context`), but only tests validate against them. At runtime the
+request and result are checked by three hand-kept validators (`execution.py`
+`_validate_result`, `orchestrator.py` `_validate_dispatch_result`, and an inline copy
+inside `checkpoint.schema.json`), none of which reads those schemas. Each worker prompt restated the result shape by hand, and every
+behaviour the prompt left out was decided by the worker. The observed failures:
 
-## Dependencies
+1. A gate parked under a missing posture stayed parked after the operator adopted a
+   posture with `auto` for it, because the child's `pending_gate` is never
+   re-evaluated and nothing says whether the child's or the supervisor's record is
+   authoritative.
+2. Workers probed credentials (`env | grep ...`) to discover vendors, hit `ask`
+   permission rules, and sat in `REQUIRES_ACTION` for hours with no way to report it.
+3. Plan review silently ran below quorum because `--check-vendors` reported a vendor
+   whose CLI was not installed; degradations appeared only in prose.
+4. A child parked as `pending_gate/escalate_resume`, which the supervisor had no
+   answer path for, deadlocking execution.
 
-- None
+Landing the roadmap branch (PR #662) exposed three more defects, all caused by
+host-local, run-local execution state reaching a shared ref: raw launch tokens in a
+tracked `checkpoint.json` (flagged by gitleaks), absolute worktree paths that no
+other host can reconcile, and a repository-global `auto` posture for
+`proposal_approval` that also covers standalone autopilot runs no roadmap approval
+authorized.
+
+Queue-dispatched work (`team-work-queue`, `owner-routed-escalation`,
+`queue-dispatch-owner-acceptance`) is built on this boundary, so it must be fixed
+first.
+
+## What Changes
+
+- **Published schemas.** Add `openspec/schemas/dispatch-request.schema.json` and
+  `dispatch-result.schema.json` (`schema_version` 2) as the only definition of the
+  boundary. The existing v1 contract schemas are frozen as v1 reader schemas
+  (request, result), become the single attempt definition `$ref`'d by
+  `checkpoint.schema.json` (attempt), or are `$ref`'d by the v2 request (context)
+  (design D2). A new `skills/shared/dispatch_contract.py` loads and validates them;
+  `execution.py`, `orchestrator.py` and `checkpoint.schema.json` (via `$ref`) consume
+  that single definition, and their hand-written field sets are deleted. Version-1
+  documents remain readable (D1).
+- **Code-emitted results.** `runner.py emit-result <change-id> --dispatch-id ...
+  --generation ...` derives the result, including its evidence digest, from
+  `loop-state.json` using a normative mapping (D4) and writes it to
+  `openspec/changes/<id>/dispatch-results/<dispatch-slug>-g<N>.json`.
+- **Gate provenance and posture re-evaluation.** Every gate-decision record carries
+  `provenance` (`posture` with `posture_digest`, or `human` with `approval_ref`). On
+  resume, a posture-derived block whose digest differs from the current posture is
+  re-evaluated; a human decision is never overridden. The supervisor answers a child
+  only through a typed `gate_answer` in the resume request, applied by
+  `runner.py gate-answer --approval-ref`.
+- **Execution profile, review requirements, degradations.** The request carries a
+  supervisor-resolved `execution_profile` (verified lanes per mode, location,
+  isolation, sanctioned probe command) and `review_requirements` (quorum per phase,
+  counting lanes). `review_dispatcher.py --check-vendors` reports a lane only when a
+  dry invocation proves it dispatchable. The result carries
+  `degradations[]` with an enumerated code set.
+- **New parked kinds.** `permission_blocked` and `capability_unavailable` are recorded
+  in loop state by `runner.py park`, emitted by `emit-result`, and routed by the
+  supervisor to the operator as one deduplicated escalation each.
+- **Closure contract test.** A test enumerates every `(outcome, parked.kind, gate)`
+  the result schema permits and fails if the supervisor has no answer or resume path;
+  `ExecutionAdapter.apply` refuses an unroutable result at apply time.
+- **Landable dispatch state.** `checkpoint.json` stores `launch_digest`
+  (`sha256:<hex>`) instead of the raw token, and tokens are minted per launch
+  generation (D6). Isolation is recorded as `{mode, worktree_ref, branch, host_id}`
+  so another host can rebind or reinitialize an attempt (D7). A legacy reader
+  migrates raw tokens and absolute paths on load.
+- **Scoped auto dispositions.** `auto` for `proposal_approval` and `replan_required`
+  applies only to a dispatch whose launch marker carries a valid
+  `roadmap_approval_ref`; otherwise the gate uses its declared `unscoped` fallback,
+  `block` by default (D8).
+- **Merged narrow fix.** `openspec/supervise-pending-escalate-answer` (6e6e9a6) is
+  merged into this branch, not re-implemented, and covered by the closure test.
+
+## Non-Goals
+
+- Automatic re-routing of a `capability_unavailable` review to another lane (for
+  example the GX10 review queue). This change makes the park answerable by the
+  operator; automatic re-routing is a follow-up item.
+- Changing how results travel between sessions beyond writing the committed result
+  file. The cross-session message still carries a pointer; no new transport service.
+- Rendering degradations in the supervise digest. They are persisted in the checkpoint
+  and returned by `apply`; the digest is out of scope.
+- Editing `openspec/roadmaps/multiplayer-collaboration/roadmap.yaml`, its
+  `checkpoint.json`, `openspec/supervise/*`, or `.supervised-dispatch/`. The raw tokens
+  already in the roadmap branch's history are not rewritten here (see design Open
+  Questions).
+- New trust-posture gates. The new parked kinds resolve through the existing
+  `escalate_resume` gate.
 
 ## Acceptance Outcomes
 
-- dispatch-request and dispatch-result schemas exist under openspec/schemas and execution.py and orchestrator.py validate against them with existing fixtures passing.
-- runner.py emit-result produces a schema-valid result for every terminal and parked loop-state shape, verified end to end.
-- A closure contract test fails when any schema-permitted parked kind/gate combination lacks a supervisor answer or resume path.
-- A posture-derived gate block clears on resume after a posture change while a human rejection does not.
-- execution_profile, review_requirements, and degradations[] are carried end to end, and permission_blocked and capability_unavailable parks are routed to the operator as single escalations.
+1. dispatch-request and dispatch-result schemas exist under openspec/schemas and
+   execution.py and orchestrator.py validate against them with existing fixtures
+   passing.
+2. runner.py emit-result produces a schema-valid result for every terminal and parked
+   loop-state shape, verified end to end.
+3. A closure contract test fails when any schema-permitted parked kind/gate
+   combination lacks a supervisor answer or resume path.
+4. A posture-derived gate block clears on resume after a posture change while a human
+   rejection does not.
+5. execution_profile, review_requirements, and degradations[] are carried end to end,
+   and permission_blocked and capability_unavailable parks are routed to the operator
+   as single escalations.
+6. checkpoint.json stores no raw launch token (only a digest that child_start
+   verifies) and the default secret-scan passes on a committed checkpoint with live
+   attempts and no allowlist entry.
+7. A checkpoint with live attempts committed on one host can be reconciled on another
+   host, which rebinds or reinitializes attempts instead of failing on absolute
+   isolation paths.
+8. An auto disposition for proposal_approval or replan_required proceeds only for a
+   dispatch carrying a valid roadmap_approval_ref; a standalone autopilot run without
+   one is gated by its non-auto fallback.
 
-## Rationale
+"End to end" in outcomes 2 and 5 means: supervisor request -> child launch marker ->
+child `loop-state.json` -> `emit-result` file -> `ExecutionAdapter.apply` ->
+checkpoint attempt record and `apply` return value.
 
-Every stall in the first supervised run occurred at an unwritten part of the supervisor-worker boundary; queue-dispatched work (team-work-queue, owner-routed-escalation, queue-dispatch-owner-acceptance) is built on it.
+## Impact
+
+Affected specs (deltas under `specs/`):
+
+| Capability | Change |
+|---|---|
+| `roadmap-orchestration` | MODIFIED Durable Delegated Attempt Ledger, Outcome-Only Resume Contract; ADDED Published Dispatch Contract Schemas, Launch Token Digest, Host-Portable Attempt Isolation |
+| `supervise` | ADDED Dispatch Result Closure, Typed Gate Answers With Provenance, Execution Profile and Review Requirements, Single Escalation Per Capability Park |
+| `skill-workflow` | ADDED Code-Emitted Dispatch Result, Loop State Parks and Degradations, Gate Authority and Re-Evaluation on Resume, Honest Review Quorum |
+| `trust-posture` | ADDED Roadmap-Approval-Scoped Auto Dispositions |
+| `parallel-infrastructure` | ADDED Dispatchable Vendor Verification |
+
+Affected code:
+
+- `openspec/schemas/`: new `dispatch-request.schema.json`, `dispatch-result.schema.json`;
+  edited `checkpoint.schema.json`, `gate-decision.schema.json`,
+  `gate-request.schema.json`, `trust-posture.schema.json`; mirrors in
+  `skills/roadmap-runtime/install_assets/openspec/schemas/`.
+- `openspec/contracts/roadmap-orchestration/schemas/`: `delegated-dispatch-attempt`
+  edited (digest, portable isolation); `supervised-dispatch-request`/`-result` frozen
+  as v1 reader schemas; all four mirrored under `install_assets`.
+- `skills/shared/environment_profile.py` (`host_id()`).
+- `skills/shared/`: new `dispatch_contract.py`; `trust_posture.py` (digest, `unscoped`
+  fallback), `approval_gate.py` (provenance, scoped auto).
+- `skills/autopilot/scripts/`: `runner.py` (`emit-result`, `park`,
+  `record-degradation`, `gate-answer --approval-ref`, gate-check re-evaluation),
+  `autopilot.py` (LoopState v6), `convergence_loop.py` (quorum park).
+- `skills/parallel-infrastructure/scripts/review_dispatcher.py` (`--check-vendors --json`).
+- `skills/roadmap-runtime/scripts/models.py`, `checkpoint.py` (attempt shape, legacy
+  migration).
+- `skills/autopilot-roadmap/scripts/orchestrator.py` (prepare, validation via contract).
+- `skills/supervise/scripts/execution.py`, `gate_router.py`, `skills/supervise/SKILL.md`,
+  `skills/autopilot/SKILL.md` (worker protocol: emit-result, park, no env probing).
+- Tests under `skills/tests/{supervise,autopilot,autopilot-roadmap,roadmap-runtime,shared,parallel-infrastructure,install_sh}/`,
+  including `supervise/test_execution_contract.py` and every helper that copies
+  `checkpoint.schema.json` into a temporary repo.
+
+Compatibility: v1 results and legacy checkpoints keep loading (D1, D6, D7). Loop
+state moves to `schema_version` 6 with defaulted new fields. In-flight workers on
+`multiplayer-collaboration` that still return v1 results are accepted until their
+attempts resolve.
+
+## Sources of Truth
+
+- `openspec/roadmaps/multiplayer-collaboration/supervisor-worker-contract.md` (Issues
+  1-4, cross-cutting transport, and the PR #662 addendum).
+- Roadmap item `ri-21` in `openspec/roadmaps/multiplayer-collaboration/roadmap.yaml`.
+
+## Constraints
+
+- Existing `openspec/roadmaps/*/checkpoint.json` files (including the archived
+  `2026-09-26-roadmap-supervisor-orchestration` one) must keep loading; a test covers
+  raw tokens and absolute isolation paths.
+- The narrow fix on `openspec/supervise-pending-escalate-answer` is merged, not
+  re-implemented (task 1.1).
+- Out of scope for edits: `openspec/roadmaps/multiplayer-collaboration/roadmap.yaml`,
+  its `checkpoint.json`, `openspec/supervise/*`, `.supervised-dispatch/`.
+
+## Landing approach for PR #662
+
+The raw launch tokens that the `multiplayer-collaboration` roadmap branch committed
+before this change are allowlisted by commit SHA in `.gitleaks.toml` (commit
+`bf85ea1`: `ddd2c4a`, `c6424d7`, `3c06430`). They are single-use, run-scoped nonces,
+not credentials, and from this change on a checkpoint stores only `launch_digest`.
+
+Land PR #662 on `main` with a **squash merge** (or from a fresh branch cut from the
+roadmap branch's tip), so those introducing commits never enter `main`'s history.
+After landing, the three SHA entries can be removed from `.gitleaks.toml` once no
+branch that still carries those commits is scanned. This change rewrites no
+history; the merge choice is the operator's.
diff --git a/openspec/changes/dispatch-contract/session-log.md b/openspec/changes/dispatch-contract/session-log.md
new file mode 100644
index 0000000..0bb2906
--- /dev/null
+++ b/openspec/changes/dispatch-contract/session-log.md
@@ -0,0 +1,263 @@
+# Session Log: dispatch-contract
+
+> Decision rationale, trade-offs, and alternatives recorded at each workflow phase.
+> Auto-generated by workflow skills. Sanitized before commit.
+
+## Phase: Gatekeeper (2026-10-06)
+
+**Agent**: claude_code | **Session**: N/A
+
+### Next Steps
+- PLAN_ITERATE: concretize WHEN/THEN per parked kind/provenance, replace placeholder tasks, add bounded work-packages.yaml
+
+### Context
+GATEKEEPER verdict proceed_with_review: outcomes verifiable via tests, moderate reversible risk; edits autopilot gate/park logic so VAL_REVIEW enabled.
+
+---
+
+## Phase: Plan Iteration 1 (2026-10-06)
+
+**Agent**: claude_code | **Session**: N/A
+
+### Decisions
+1. **Spec deltas target existing capabilities, not the placeholder** `architectural: roadmap-orchestration` — multiplayer-collaboration is a roadmap, not a capability; the touched behaviour is owned by roadmap-orchestration, supervise, skill-workflow, trust-posture and parallel-infrastructure.
+2. **Launch tokens are minted per generation and stored only as sha256 digests** `architectural: roadmap-orchestration` — A digest-only checkpoint cannot re-emit the same token on resume, so the Durable Delegated Attempt Ledger requirement is MODIFIED; reissue is limited to states where takeover is already safe.
+3. **Dispatched children defer gate authority to the supervisor** `architectural: supervise` — Issue 1 arose because child and supervisor postures differed; the marker carries the supervisor posture digest and drift disables auto, so one holder is authoritative.
+4. **Non-auto fallback is an optional `unscoped` posture sub-config defaulting to block** `architectural: trust-posture` — The outcome names a fallback but the posture schema has none; a declared field keeps operators able to choose notify_with_timeout while failing closed by default. Recorded as a decision rather than asked: this phase sub-agent has no interactive channel to the operator.
+5. **Deviation: assumption findings recorded as decisions instead of AskUserQuestion** `architectural: skill-procedure-deviation` — iterate-on-plan requires surfacing assumptions interactively, but this run is an autopilot phase sub-agent that must return (outcome, handoff_id) without intermediate state; D8 and D10a are recorded with alternatives so PLAN_REVIEW or the operator can overturn them.
+6. **Deviation: analysis run inline rather than via parallel Explore sub-agents** `architectural: skill-procedure-deviation` — The harness exposed no sub-agent dispatch tool to this phase sub-agent; the five analysis dimensions were covered inline in one pass and the findings table records each dimension.
+7. **Deviation: worked in the harness-provided isolated worktree instead of worktree.py setup** `architectural: skill-procedure-deviation` — The feature branch is checked out in the shared checkout and the harness forbids git operations outside this worktree; the worktree branch was reset to the openspec/dispatch-contract tip (8f1f248) so commits fast-forward onto the feature branch.
+
+### Alternatives Considered
+- Keep hand validators with a parity test: rejected because Two definitions are the root cause the item removes
+- Child re-verifies roadmap_approval_ref against the roadmap checkpoint: rejected because Checkpoint lives on the roadmap branch; the generation-verified launch marker is the channel both sides share
+- Map every DONE to success: rejected because ESCALATE --abandoned--> DONE would complete abandoned items
+
+### Trade-offs
+- Accepted v1 request/result tolerance for a migration window over a clean v2-only cut because workers already running on multiplayer-collaboration return v1
+- Accepted one escalation per permission rule fingerprint over one per blocked command because operators fix rules, not commands
+
+### Open Questions
+- [ ] Raw tokens already in the roadmap branch history still fail full-history gitleaks; squash or SHA allowlist is the operator's decision.
+- [ ] When to remove v1 reading (trigger: no unresolved attempt carries a v1 result).
+
+### Completed Work
+- proposal.md rewritten with required sections and Impact table
+- design.md D1-D11 with alternatives and risks
+- specs: roadmap-orchestration (3 ADDED, 2 MODIFIED), supervise (4), skill-workflow (4), trust-posture (1), parallel-infrastructure (1)
+- tasks.md: 30 tasks, dependencies, traceability table
+- work-packages.yaml: 9 packages, validated
+- plan-findings.md iteration 1
+
+### Context
+Replaced the plan-roadmap scaffold with a concrete plan: proposal with Why/What Changes/Non-Goals/Impact, design D1-D11 (plus D10a), five spec deltas against real capabilities covering all eight ri-21 outcomes, 30 traceable tasks and a validated nine-package work-packages.yaml. Addressed 3 critical, 9 high and 9 medium findings, including per-generation launch tokens (digest-only storage made same-token resume impossible), abandoned-DONE mis-mapping, and an explicit gate-authority rule between child and supervisor.
+
+---
+
+## Phase: Plan Iteration 2 (2026-10-06)
+
+**Agent**: claude_code | **Session**: N/A
+
+### Decisions
+1. **ApprovalGate reads the launch marker through an injected seam and ignores context refs** `architectural: trust-posture` — A context value can be set by any caller; the marker is written by child_start after supervisor verification. The seam also keeps wp-posture independent of wp-contract-lib.
+2. **Review quorum defaults to 2 per review phase with a router-context override** `architectural: supervise` — routing.yaml defines a cost ladder but no quorum; 2 is today's --min-vendors and the ladder orders lanes without excluding tiers. Recorded as a decision because this phase cannot ask the operator.
+3. **Below-quorum availability still launches** `architectural: supervise` — check-vendors exits 2 for both below-quorum and roster failure; only an error field or unparseable JSON blocks prepare, and the child parks capability_unavailable honestly at review.
+
+### Alternatives Considered
+- Fail prepare whenever the batch is below quorum: rejected because Plan phases before review still make progress, and the park makes the gap visible as one escalation
+
+### Trade-offs
+- Accepted marker trusted to the child's own trust level over cryptographic marker signing because anything able to forge the marker can already act as the child
+
+### Completed Work
+- TP: marker_reader seam, context refs ignored
+- SV: prepare failure semantics and below-quorum scenario
+- PI: credential-disclosure scenario, error JSON shape
+- D10: review_requirements source defined
+
+### Context
+Second pass found one high and four medium issues: scoped auto trusted a caller-supplied approval ref, the check-vendors exit-code contract contradicted prepare's failure rule, the credential-probe test was unimplementable for API lanes, and the quorum source was unstated. All fixed in design D8/D10 and the supervise, trust-posture and parallel-infrastructure deltas.
+
+---
+
+## Phase: Plan Iteration 3 (2026-10-06)
+
+**Agent**: claude_code | **Session**: N/A
+
+### Decisions
+1. **Attempts persist the verified roadmap_approval_ref** `architectural: roadmap-orchestration` — It is a non-secret gate-decision reference; persisting it lets child_start write it into every generation's marker and lets the supervisor apply the same scope rule from the same fact.
+2. **Deviation: skipped iterate-on-plan step 10 multi-vendor review** `architectural: skill-procedure-deviation` — In this autopilot run the next phase is PLAN_REVIEW (cli_review_enabled=true), which performs the multi-vendor plan review and convergence; dispatching it here as well would duplicate that phase and spend vendor quota twice.
+
+### Alternatives Considered
+- Re-verify the ref at every child_start against the roadmap checkpoint: rejected because child_start already runs supervisor-side with the checkpoint loaded; persisting the verified ref is sufficient and avoids re-fingerprinting the roadmap per generation
+
+### Open Questions
+- [ ] Raw tokens already in the roadmap branch history still fail full-history gitleaks; squash or SHA allowlist is the operator's decision.
+
+### Completed Work
+- D8 persistence of roadmap_approval_ref; RO ledger scenario; tasks 2.3 and 5.3
+- plan-findings iteration 3 with termination reason
+
+### Context
+Third pass found one medium gap: the verified roadmap_approval_ref was not persisted on attempts, so neither the per-generation marker nor the supervisor-side scope check could carry it. Fixed in D8, the RO ledger scenario and tasks 2.3/5.3; refinement converged with only low findings left.
+
+---
+
+## Phase: Plan Review (parked) (2026-10-06)
+
+**Agent**: claude_code | **Session**: N/A
+
+### Next Steps
+- Operator decides how cloud review quorum is satisfied (GX10 review lane, policy, or credential); then answer escalate_resume to re-enter PLAN_REVIEW
+
+### Context
+PLAN_REVIEW parked before any review round: min_quorum=2 is unmeetable in this cloud environment. review_dispatcher --check-vendors reports claude_code+codex, but codex is a known false positive (no codex binary on PATH, no credential). Per supervisor resume instructions (contract Issue 3) quorum was not lowered; loop escalated with capability_unavailable (missing lane: codex / any second review vendor). Coordinator projection forbidden (expected for trust-2 cloud agents).
+
+
+---
+
+## Phase: Plan Review (2026-10-09)
+
+**Agent**: claude_code | **Session**: N/A | **Handoff**: eeedef7e-c78e-4f7c-a6f5-94cc4a8150f5
+
+### Decisions
+1. **Existing v1 contract schemas are given one role each instead of being duplicated** `architectural: roadmap-orchestration` — `openspec/contracts/roadmap-orchestration/schemas/` already published request/result/attempt/context schemas; request/result are frozen as v1 reader schemas, the attempt schema becomes the single attempt definition `$ref`'d by `checkpoint.schema.json`, and the context schema is `$ref`'d by the v2 request.
+2. **Capability-park fan-out writes one escalate_resume record per dispatch** `architectural: supervise` — keeps `require_approval_ref`'s per-dispatch and per-generation checks unchanged.
+3. **counting_lanes includes unverified roster lanes** `architectural: supervise` — otherwise `missing_lanes` is always empty and distinct capability gaps share one fingerprint.
+4. **Quorum park happens in the worker protocol, not convergence_loop** `architectural: skill-workflow` — below quorum the SKILL.md probe skips review entirely, so convergence_loop never runs; `runner.py park` stays the only writer.
+
+### Trade-offs
+- Accepted single-vendor review (`single_vendor_review`, min_quorum=1) by recorded operator decision over waiting for a second lane; findings carry no cross-vendor confirmation.
+
+### Completed Work
+- converge() for PLAN_REVIEW: 3 rounds, blocking trend [11, 1, 0], converged
+- PLAN_FIX round 1 (items 1-11) and round 2 (item 14), inline edits to cited files only; scope check passed both rounds
+- Advisory (non-blocking) left open: 13 (cross-host reinitialize of a parked attempt invalidates its approval), 15 (roadmap-runtime -> shared dependency)
+
+### Context
+PLAN_REVIEW resumed after the operator's escalate_resume approval and ran the convergence loop with the claude_code lane only. Round 1 found 11 blocking defects verified against the repository, most importantly that published v1 dispatch schemas already exist under `openspec/contracts/roadmap-orchestration/schemas/`, that a `$ref` in `checkpoint.schema.json` breaks the registry-less validator in `models.py`, and that the D9 fan-out could not pass `require_approval_ref`. All were fixed and re-verified; one ordering contradiction introduced by the fix was caught and fixed in round 2. Degradations: `single_vendor_review`, `coordinator_projection_forbidden`, `handoff_local_fallback`.
+
+---
+
+## Phase: Implementation (2026-10-09)
+
+**Agent**: claude_code | **Session**: N/A
+
+### Decisions
+1. **Commit order keeps every commit green rather than following package boundaries literally** `architectural: roadmap-orchestration` — The checkpoint/attempt schema $ref switch, models, orchestrator and execution must change together; schemas 2.3-2.4 landed in the ledger commit.
+2. **Review quorum per environment is data (review_quorum_policy.json) carried as review_requirements.quorum_policy** `architectural: supervise` — Supervisor follow-up 1: a worker gets min_quorum 1 only through data with an explicit sunset; single-lane is detected by failed dispatch.
+3. **Cross-host reinitialize keeps a parked attempt's generation** `architectural: roadmap-orchestration` — Its escalate_resume approval is bound to the generation (advisory finding 13).
+
+### Alternatives Considered
+- Rename authorizing_disposition / lock_keys to satisfy a literal keyword test: rejected because Breaking rename outside scope; a port of the default generic-api-key rule proves the fixture clean.
+
+### Trade-offs
+- Accepted SDK/API review lanes reported unverified (probe_unsupported) over counting them on importability because no authenticated no-op exists in their adapters; fail closed
+
+### Open Questions
+- [ ] IMPLEMENT phase prompt should name the stacked feature base (worktree launchpads are rooted at main).
+- [ ] Removal of v1 reading once no unresolved attempt carries a v1 result.
+
+### Completed Work
+- Tasks 1.1-9.7 ticked in tasks.md (9.6 = full suites + openspec validate --strict).
+- Degradations: coordinator_projection_forbidden not exercised (local handoff fallback used).
+
+### Next Steps
+- IMPL_REVIEW: start with skills/supervise/scripts/gate_router.py (fingerprint escalation) and execution.py (reconcile).
+- Pre-existing env-only failures: test_workflow_contract canonical-source (.claude worktree path), two project-context-refresh shared-checkout tests (fail at bdb0048 too).
+
+### Relevant Files
+- `skills/shared/dispatch_contract.py` — single runtime definition of the boundary
+- `openspec/schemas/dispatch-result.schema.json` — v2 result
+- `openspec/schemas/dispatch-request.schema.json` — v2 request
+- `skills/supervise/scripts/gate_router.py` — ANSWER_PATHS, provenance, fingerprint escalations
+- `skills/supervise/scripts/execution.py` — profile, digests, reissue, cross-host reconcile
+- `skills/autopilot/scripts/runner.py` — emit-result, park, record-degradation, gate authority
+
+### Context
+Implemented all nine work packages sequentially (tier: sequential, no sub-agents): v2 dispatch schemas and the shared dispatch_contract library, digest-only and host-portable checkpoint attempts with legacy migration, LoopState v6 with emit-result/park/record-degradation and gate authority, dispatchable-lane verification with a data-driven per-environment quorum, the supervisor's profile resolution, provenance re-evaluation, fingerprint escalations and cross-host reconcile, plus closure, end-to-end, cross-host and landable-fixture tests. Supervisor follow-ups (a)-(e) are folded in.
+
+---
+
+## Phase: Implementation Iteration 1 (2026-10-09)
+
+**Agent**: claude_code | **Session**: N/A
+
+### Decisions
+1. **A child human rejection ends only at a later human escalate_resume proceed** — Keeps 'a posture change never reopens a human rejection' while removing the permanent deadlock after an operator resume; a posture-derived resume does not end it.
+2. **apply re-derives only native v2 results** — v1 results predate the normative mapping and keep the D1 tolerance window.
+3. **A fingerprint subject ends at a later proceed for that fingerprint** — The fan-out writes per-dispatch proceed records without dispatch_ids, so the prior blocked subject would otherwise outlive its own answer.
+
+### Alternatives Considered
+- Re-ask a human-rejected gate as a fresh pending_gate: rejected because The spec scenario requires gate-check to record nothing while the rejection is in force.
+- Snapshot after the ledger write in converge(): rejected because Excluding the bookkeeping paths also covers .review-cache writes and is order-independent.
+
+### Trade-offs
+- Accepted Keyed-secret redaction over-redacts words like 'token' followed by a value over Leaving short credentials in park.command because The stored command is diagnostic only; it is not part of the dedupe fingerprint.
+
+### Open Questions
+- [ ] Should a dispatched child with a drifted posture also refuse notify_with_timeout timeout defaults?
+- [ ] How is a human rejection of escalate_resume itself recovered other than via abandoned?
+
+### Completed Work
+- Human-rejected capability escalation stays final when membership changes (9c52005)
+- Child human rejection ends at an operator resume and parks in ESCALATE (6892017)
+- redact_command drops URL, -u and keyed short credentials (af0817f)
+- Cross-host reinitialize respects an unexpired pre-go lease (a3330ff)
+- apply re-derives v2 results via result_from_loop_state (8b76939)
+- Closure enumeration refuses non-enumerable kind/gate nodes (609aff1)
+- Operator answer ends a fingerprint subject and covers late members (4cc15ae)
+- converge(base_ref=) pass-through, task 7.6 (9cdc27d)
+- converge bookkeeping excluded from post-fix scope check, task 7.7 (9805527)
+
+### Context
+Two iterations fixed seven findings at medium or above: human-rejection finality on both sides of the gate boundary, short-credential redaction, cross-host takeover of live pre-go claims, supervisor re-derivation of v2 results through the normative mapping, and a closure enumeration that no longer reads non-enumerable gates as null. The two supervisor-requested converge() fixes (base_ref pass-through, bookkeeping excluded from the post-fix scope check) also landed as tasks 7.6 and 7.7.
+
+---
+
+## Phase: Implementation Review (2026-10-09)
+
+**Agent**: claude_code | **Session**: N/A
+
+### Decisions
+1. **A launch marker's gate_answer authorizes exactly its gate and decision** — The approval reference names a supervisor record but does not carry its content; gate-answer now also requires --gate and --decision to equal the marker's answer.
+2. **The supervisor redacts a blocked command at apply, not only in the router record** — checkpoint.json is tracked; a result that did not come through runner.py park could otherwise commit a credential in the attempt or its journal.
+
+### Alternatives Considered
+- Re-derive the whole parked payload, command included, from loop state at apply: rejected because The supervisor's checkpoint must be safe even for v1 results, which are not re-derived.
+
+### Trade-offs
+- Accepted single-vendor review (claude_code) at quorum 1 over parking IMPL_REVIEW as capability_unavailable because cloud-container quorum policy cloud-container-single-vendor-2026-10-09; degradation single_vendor_review
+
+### Open Questions
+- [ ] Once a human has rejected escalate_resume itself, gate-check can never re-ask it (carried from IMPL_ITERATE).
+
+### Completed Work
+- Fixes: 5b28e32 (gate-answer gate/decision), b34c6af (apply-time command redaction), bad6de9 (idempotent header redaction).
+- Degradations: single_vendor_review (IMPL_REVIEW, claude_code); coordinator_projection_forbidden if the handoff write falls back locally.
+
+### Next Steps
+- VAL_REVIEW / VALIDATE: low advisories remain (notify_with_timeout under posture drift, emit-result identity cross-check, vacuous rebind evidence, records[0] fallback in _resolve_capability_park).
+
+### Relevant Files
+- `skills/autopilot/scripts/runner.py` — gate-answer marker authority
+- `skills/autopilot-roadmap/scripts/orchestrator.py` — apply-time command redaction
+- `skills/shared/dispatch_contract.py` — redact_command
+- `openspec/changes/dispatch-contract/impl-findings.md` — IMPL_REVIEW findings table
+
+### Context
+converge() ran IMPL_REVIEW (review_type=implementation, fix_mode=targeted, min_quorum=1 from resolve_quorum_policy, base_ref=origin/openspec/roadmap-multiplayer-collaboration) and converged in round 2 with blocking trend [5, 0]. Round 1 found two medium security defects, each with a test gap: a dispatched child's gate-answer accepted any gate or decision as long as the approval reference matched the marker, and apply persisted a permission_blocked result's command unredacted into the tracked checkpoint. A low redaction idempotency issue was also fixed. IMPL_FIX ran inline (claude_code) and was scoped to the cited paths, which lie inside wp-autopilot-child, wp-runtime-ledger and wp-contract-lib.
+
+---
+
+## Phase: Validate (2026-10-09)
+
+**Agent**: claude_code | **Session**: N/A
+
+### Next Steps
+- VAL_REVIEW single-vendor over validation evidence
+- SUBMIT_PR against openspec/roadmap-multiplayer-collaboration
+
+### Context
+VALIDATE passed: spec compliance pass, 0 open tasks, openspec strict valid, ruff clean, suites green except known env-only failures; deploy/smoke/security/e2e N/A (non-deployable, declared); CI DEGRADED (no runs yet, no PR). All eight ri-21 outcomes mapped to passing tests; real gitleaks binary not run locally (CI only). Degradations: single_vendor_review (PLAN_REVIEW, IMPL_REVIEW), coordinator_projection_forbidden.
+
diff --git a/openspec/changes/dispatch-contract/specs/parallel-infrastructure/spec.md b/openspec/changes/dispatch-contract/specs/parallel-infrastructure/spec.md
new file mode 100644
index 0000000..b69b6cc
--- /dev/null
+++ b/openspec/changes/dispatch-contract/specs/parallel-infrastructure/spec.md
@@ -0,0 +1,17 @@
+## ADDED Requirements
+
+### Requirement: Dispatchable Vendor Verification
+
+`review_dispatcher.py --check-vendors` SHALL count a vendor lane as available for a mode only after a dry invocation for that mode succeeds: the adapter's declared no-op command (for a CLI lane, `<cli> --version`; for an SDK or API lane, the adapter's own authenticated no-op such as a model-list call) run with a 10-second timeout. Credentials MAY be read only inside the adapter's existing credential path, and the probe SHALL NOT print, log, or return any environment value or credential. With `--json` it SHALL print `{"modes": {<mode>: {"verified": [...], "unverified": [{"vendor", "reason"}]}}, "probe_command": "<argv>"}` and keep its existing exit codes (0 at quorum, 2 below quorum or on probe failure); when the roster cannot be resolved it SHALL print `{"error": "<reason>", "modes": {}}` and exit 2.
+
+#### Scenario: A listed vendor without its CLI is unverified
+- **WHEN** `agents.yaml` lists `codex` for mode `review` and no `codex` executable is on `PATH`
+- **THEN** `--check-vendors --json` SHALL list `codex` under `unverified` with reason `cli_not_found`, and SHALL NOT count it toward `--min-vendors`
+
+#### Scenario: A hanging dry invocation is unverified
+- **WHEN** a lane's dry invocation does not exit within 10 seconds
+- **THEN** the lane SHALL be `unverified` with reason `probe_timeout`
+
+#### Scenario: The probe never discloses credentials
+- **WHEN** the test sets `ANTHROPIC_API_KEY=sk-test-SENTINEL-1234567890` and `OPENAI_API_KEY=sk-test-SENTINEL-0987654321` and runs `--check-vendors --json`
+- **THEN** neither sentinel value SHALL appear in stdout, stderr, or the JSON, and no `env` or `printenv` subprocess SHALL have been spawned
diff --git a/openspec/changes/dispatch-contract/specs/roadmap-orchestration/spec.md b/openspec/changes/dispatch-contract/specs/roadmap-orchestration/spec.md
new file mode 100644
index 0000000..75d8fd0
--- /dev/null
+++ b/openspec/changes/dispatch-contract/specs/roadmap-orchestration/spec.md
@@ -0,0 +1,138 @@
+## ADDED Requirements
+
+### Requirement: Published Dispatch Contract Schemas
+
+The repository SHALL publish `openspec/schemas/dispatch-request.schema.json` and `openspec/schemas/dispatch-result.schema.json` at `schema_version` 2 as the only definition of the supervisor-worker dispatch boundary, mirrored byte-identically under `skills/roadmap-runtime/install_assets/openspec/schemas/`. `skills/shared/dispatch_contract.py` SHALL load and validate both with JSON Schema Draft 2020-12, and the roadmap orchestrator, the supervise execution adapter, and `checkpoint.schema.json` (through `$ref`) SHALL validate against that definition and SHALL NOT keep their own field sets for the request or result. Readers SHALL accept a `schema_version` 1 result by upgrading it in memory; writers SHALL emit only version 2. The existing `openspec/contracts/roadmap-orchestration/schemas/supervised-dispatch-request.schema.json` and `supervised-dispatch-result.schema.json` SHALL be kept unchanged as the version-1 reader schemas that a version-1 document is validated against before upgrade, `delegated-dispatch-attempt.schema.json` SHALL be the only definition of a checkpoint attempt (`checkpoint.schema.json` SHALL `$ref` it), and `bounded-dispatch-context.schema.json` SHALL be `$ref`'d by the version-2 request. Schema validation of a version-1 document SHALL be host-independent; only the upgrade step, which takes `repo_root`, `managed_root`, and `host_id` explicitly, depends on the host.
+
+#### Scenario: Existing fixtures validate against the published schemas
+- **WHEN** the test suite validates the byte-unchanged fixtures under `skills/tests/supervise/fixtures/execution/contracts/` with this mapping: `valid-request.json` and `invalid-continuation-without-kind.json` through `dispatch_contract.validate_request`; each entry (`success`, `parked`) of `valid-results.json` through `dispatch_contract.validate_result`; `valid-prepared-attempt.json` through the checkpoint attempt validator after the legacy reader converts its `launch_token`
+- **THEN** every `valid-*` document SHALL validate and every `invalid-*` document SHALL be rejected with a `DispatchContractError` naming the failing JSON pointer, on any host and without a managed worktree root existing at the fixtures' `/workspace/...` paths
+
+#### Scenario: No hand-written result field set remains
+- **WHEN** a guard test scans `skills/supervise/scripts/execution.py` and `skills/autopilot-roadmap/scripts/orchestrator.py`
+- **THEN** neither file SHALL define `_RESULT_REQUIRED`, `_RESULT_ALLOWED`, `_validate_result`, or `_validate_dispatch_result`
+- **AND** `checkpoint.schema.json`'s attempt `result` property SHALL be a `$ref` to `dispatch-result.schema.json`
+
+#### Scenario: Schema mirrors stay identical
+- **WHEN** the parity test compares `openspec/schemas/dispatch-*.schema.json` and `checkpoint.schema.json` with their `install_assets` copies
+- **THEN** the bytes SHALL be identical, and a difference SHALL fail the test naming the file
+
+#### Scenario: A version-1 result is upgraded, not rejected
+- **WHEN** `ExecutionAdapter.apply` receives a schema-valid version-1 `success` result whose absolute `worktree_path` lies inside the current host's managed worktree root
+- **THEN** the result SHALL be upgraded to version 2 with `degradations: []`, a relative `worktree_ref`, an `evidence.loop_state_path` relative to that worktree, and the current `host_id`, and applied
+
+#### Scenario: A version-1 result that cannot be made portable is rejected
+- **WHEN** a version-1 result's `worktree_path` lies outside both the managed worktree root and the repo root
+- **THEN** validation SHALL fail with `DispatchContractError("v1 result worktree_path is not repo-relative")` and the attempt SHALL be left unchanged
+
+### Requirement: Launch Token Digest
+
+The roadmap checkpoint SHALL store, for each delegated attempt, `launch_digest` with the form `sha256:<64 lowercase hex>` and SHALL NOT store a raw launch token in any field. The raw token SHALL appear only in the request returned to the host. `ExecutionAdapter.child_start` SHALL verify a presented token by constant-time comparison of its SHA-256 digest with `launch_digest`. A token SHALL be minted per launch generation: `ExecutionAdapter.resume` and `ExecutionAdapter.reissue` SHALL mint a fresh token and replace `launch_digest` under the same compare-and-swap that changes the generation. `reissue` SHALL be refused for any attempt that is not `prepared` and not a pre-go expired claim. Loading a checkpoint whose attempt carries a legacy `launch_token` SHALL convert it to `launch_digest` in memory, and the next save SHALL drop the raw value.
+
+#### Scenario: No raw token is persisted
+- **WHEN** `prepare_delegated_batch` persists a batch and the checkpoint is read back from disk
+- **THEN** no attempt SHALL contain a `launch_token` field, every attempt SHALL contain a `launch_digest` matching `^sha256:[0-9a-f]{64}$`, and the token in each returned request SHALL hash to its attempt's digest
+
+#### Scenario: child_start rejects a wrong token
+- **WHEN** `child_start` is called with a token whose digest differs from `launch_digest`
+- **THEN** it SHALL raise `ExecutionStateError("launch token mismatch")` and the checkpoint SHALL be byte-identical before and after the call
+
+#### Scenario: Resume rotates the token
+- **WHEN** an authorized parked attempt is resumed
+- **THEN** the returned continuation request SHALL carry a token different from the previous generation's, `launch_digest` SHALL equal its digest, and `child_start` with the previous token SHALL raise `launch token mismatch`
+
+#### Scenario: Reissue is refused after go
+- **WHEN** `reissue` is called for an attempt whose launch gate has released go
+- **THEN** it SHALL raise `ExecutionStateError` and SHALL NOT change `launch_digest` or the generation
+
+#### Scenario: Legacy checkpoint loads and migrates
+- **WHEN** the archived `openspec/roadmaps/archive/2026-09-26-roadmap-supervisor-orchestration/checkpoint.json` (raw tokens, absolute paths) is copied to a temp workspace, loaded, and saved
+- **THEN** load SHALL succeed, and the saved file SHALL contain `launch_digest` values equal to the SHA-256 of the former tokens and no `launch_token` field
+
+#### Scenario: A committed checkpoint with live attempts passes the default secret scan
+- **WHEN** the fixture `skills/tests/roadmap-runtime/fixtures/landable-checkpoint.json`, produced by `prepare` plus `child_start` and `acknowledge`, is scanned by the CI gitleaks job using `.gitleaks.toml`
+- **THEN** gitleaks SHALL report no finding, and `.gitleaks.toml` SHALL contain no path, regex, or commit entry referring to that fixture or to `launch_digest`
+- **AND** a unit test SHALL assert that no field name in the serialized checkpoint matches the default `generic-api-key` keyword set (`access`, `auth`, `api`, `credential`, `creds`, `key`, `passw`, `secret`, `token`)
+
+### Requirement: Host-Portable Attempt Isolation
+
+Each delegated attempt SHALL record isolation as `{mode, worktree_ref, branch, host_id}`, where `worktree_ref` is the worktree path relative to the managed worktree root (`managed_worktree`) or to the repo root (`harness_provided` inside the repo), or `null` otherwise, and `host_id` is the non-secret identifier from `skills/shared/environment_profile.py`. Absolute worktree paths SHALL exist only in memory and SHALL NOT be persisted in the checkpoint, the request, or the result. When reconciling an attempt whose `host_id` differs from the current host, the adapter SHALL rebind it when a worktree for its branch exists under the current managed root whose `HEAD` contains the last recorded evidence commit and whose `loop-state.json` digest matches; otherwise it SHALL reinitialize it (create a managed worktree for the branch, increment the generation, mint a new token) when the attempt is `prepared`, `parked`, or a pre-go claim whose lease has expired (an unexpired claim is not taken over); otherwise it SHALL leave the attempt subject to the existing quarantine rules. Legacy absolute `worktree_path` values SHALL be converted to `worktree_ref` on load when they lie inside the managed root or repo root, and SHALL otherwise mark the attempt `needs_rebind`.
+
+#### Scenario: Persisted isolation has no absolute path
+- **WHEN** a batch is prepared and the checkpoint is read back
+- **THEN** every attempt's `isolation` SHALL have exactly the keys `mode`, `worktree_ref`, `branch`, `host_id`, and no persisted string in the attempt SHALL start with `/` or a drive letter
+
+#### Scenario: Reconcile on another host rebinds a matching worktree
+- **GIVEN** a checkpoint with a `parked` attempt committed on host A with evidence commit C
+- **WHEN** host B, which has a managed worktree for the attempt's branch whose `HEAD` contains C and whose loop-state digest matches, reconciles the checkpoint
+- **THEN** the attempt SHALL keep its generation, gain a `rebound` history entry, and record host B's `host_id`
+
+#### Scenario: Reconcile on another host reinitializes when no worktree exists
+- **GIVEN** the same committed checkpoint and a `prepared` attempt
+- **WHEN** host B has no worktree for the branch and reconciles
+- **THEN** a managed worktree SHALL be created for the branch, the generation SHALL increase by one, a new `launch_digest` SHALL be stored, and `prepare` on host B SHALL NOT skip the item
+
+#### Scenario: A post-go attempt of unknown liveness is not rebound
+- **WHEN** host B reconciles a post-go `launched` attempt from host A and the durable task handle cannot establish live or dead status
+- **THEN** the attempt SHALL become `quarantined` and no worktree SHALL be created
+
+#### Scenario: Rebind refuses a diverged worktree
+- **WHEN** host B's worktree for the branch does not contain the evidence commit, or its loop-state digest differs
+- **THEN** the attempt SHALL NOT be rebound and reconciliation SHALL report `rebind_refused:evidence_mismatch` for it
+
+## MODIFIED Requirements
+
+### Requirement: Outcome-Only Resume Contract
+
+The roadmap orchestrator SHALL persist only structured dispatch outcomes and handoff identifiers needed to resume; it MUST NOT persist a child transcript in roadmap state or dispatch context.
+
+#### Scenario: Apply a successful child outcome
+- **WHEN** a child returns a schema-valid success result correlated to the current dispatch identifier and change identifier
+- **THEN** the item is completed and its learning entry is written once only after the result's `worktree_ref`, `branch`, `host_id`, and loop-state evidence exactly match the prepared attempt and the worktree resolved from `worktree_ref` on the current host remains contained by its verified root
+- **AND** contradictory status/outcome pairs are schema-invalid and the checkpoint records bounded outcome metadata, including the result's `degradations`, without transcript content
+
+#### Scenario: Reject stale or mismatched child outcome
+- **WHEN** a result carries a different dispatch identifier, change identifier, or already-applied attempt
+- **THEN** the result is rejected without advancing the item
+- **AND** a resumed run can safely redispatch or reconcile the current attempt
+
+#### Scenario: Preserve a parked child
+- **WHEN** a child Autopilot run returns a schema-valid parked result of kind `pending_gate`, `policy_pause`, `permission_blocked`, or `capability_unavailable`
+- **THEN** the attempt is recorded as parked and the roadmap item is not marked failed or completed
+- **AND** dependents are not failure-blocked while the parked snapshot's bounded metadata (`kind`, `reason`, and the nullable `gate`, `deadline`, `resume_hint`, plus the kind's typed payload the result contract permits — never an `approval_id`, which lives only in the supervise gate router's own ledger) remains available to that router, which is the only consumer permitted to resume it
+
+#### Scenario: Refuse an unroutable parked result at apply time
+- **WHEN** `apply` receives a parked result whose `(kind, gate)` pair has no entry in the supervisor's answer-path table
+- **THEN** apply SHALL reject it with `DispatchContractError("unroutable parked result")` before any callback runs, and the attempt SHALL remain in its pre-apply state
+
+### Requirement: Durable Delegated Attempt Ledger
+
+The roadmap checkpoint SHALL record every delegated dispatch attempt before its request is returned to the host and SHALL preserve unresolved attempts across session restart.
+
+#### Scenario: Persist a prepared batch before launch
+- **WHEN** the scheduler prepares a safe batch of delegated item requests
+- **THEN** each request's identity, exact host-portable isolation/scope/context envelope, launch digest, verified `roadmap_approval_ref`, marker path, attempt, phase, and prepared status are saved in `checkpoint.json` before the requests are emitted
+- **AND** a crash after preparation loses agent launch work rather than losing the identity of potentially running work
+
+#### Scenario: Resume with an unresolved attempt
+- **WHEN** a fresh supervisor loads a checkpoint containing a prepared attempt without a correlated result
+- **THEN** it reconciles a persisted host launch acknowledgement, an atomic child-start marker, and worktree Autopilot state before deciding whether work launched
+- **AND** pre-go stale claims may be reclaimed by generation compare-and-swap through `reissue`, which mints a new token; after go, takeover requires positive task-death evidence, and unknown liveness becomes non-resumable quarantine
+
+#### Scenario: Reconcile lease crash windows
+- **WHEN** a crash occurs before marker creation, after marker but before Autopilot entry, before host acknowledgement, or while a child is active
+- **THEN** the generation-specific ack/go barrier prevents Autopilot entry before durable handle acknowledgement, while markers, heartbeats, handle status, exact worktree loop-state, and terminal handoff/result evidence classify the generation
+- **AND** a pre-go expired claim may be reclaimed safely, but a post-go generation may be reclaimed only after positive task-death evidence; mere absence or expiry enters quarantine
+- **AND** duplicate owners, presentation of a superseded generation's token, and stale owners that fail compare-and-swap are refused
+
+#### Scenario: Resume an authorized parked attempt
+- **WHEN** the supervise gate router supplies an `approval_ref` of the form `gate-decision:<decision_id>` for a parked dispatch of any kind
+- **THEN** the resume command verifies the reference resolves to a `gate_decisions` record in the same checkpoint with outcome `proceed`, a gate equal to the parked gate (or `escalate_resume` for `policy_pause`, `permission_blocked`, and `capability_unavailable`), a `dispatch_id` equal to the parked dispatch, for `escalate_resume` a `lease_generation` equal to the attempt's current generation, and for `permission_blocked` and `capability_unavailable` a `dedupe_fingerprint` equal to the one recomputed from the attempt's parked payload, then compare-and-swaps parked to prepared, increments the lease generation, mints a new launch token, and emits one continuation with the same dispatch ID, attempt, worktree reference, and loop-state, carrying a typed `gate_answer`
+- **AND** a reference that does not resolve, resolves to a `blocked` decision, or names a different gate, dispatch, lease generation, or fingerprint is rejected without mutating the attempt
+- **AND** the normal child-start protocol transitions it to launched while duplicate or unauthorized resumes are rejected
+- **AND** `ExecutionAdapter.prepare` likewise requires a `roadmap_approval_ref` resolving to a `proceed` `roadmap_approval` decision for the checkpoint's roadmap before any attempt is written
+
+#### Scenario: Quarantine unknown post-go liveness
+- **WHEN** a post-go generation has no terminal result and its durable task handle cannot positively establish live or dead status
+- **THEN** the attempt becomes `quarantined` with its uncertain lease unreleased and no takeover or duplicate Autopilot entry occurs
+- **AND** approval-gate resume is forbidden until reconciliation positively proves the prior task dead or terminal
diff --git a/openspec/changes/dispatch-contract/specs/skill-workflow/spec.md b/openspec/changes/dispatch-contract/specs/skill-workflow/spec.md
new file mode 100644
index 0000000..790422f
--- /dev/null
+++ b/openspec/changes/dispatch-contract/specs/skill-workflow/spec.md
@@ -0,0 +1,97 @@
+## ADDED Requirements
+
+### Requirement: Code-Emitted Dispatch Result
+
+`skills/autopilot/scripts/runner.py` SHALL provide `emit-result <change-id> --dispatch-id ID --generation N --attempt A` that derives a `dispatch-result.schema.json` version-2 result from the committed `loop-state.json` through `dispatch_contract.result_from_loop_state`, writes it to `openspec/changes/<change-id>/dispatch-results/<dispatch-slug>-g<N>.json` (where `dispatch-slug` replaces each character outside `[A-Za-z0-9._-]` with `-`), and prints it to stdout. The mapping SHALL be, first match wins: `park` set -> `parked/<park.kind>`; `pending_gate` set -> `parked/pending_gate` with the pending gate; `ESCALATE` -> `parked/policy_pause` with `previous_phase` in `resume_hint`; `DONE` with `goal_gate.verdict` `abandoned` -> `failed:abandoned`; `DONE` with verdict `passed` and a `last_handoff_id` -> `success`; any other `DONE` -> `failed:goal_gate_unverified`. Evidence SHALL be the loop-state path, the `HEAD` commit, and the SHA-256 of `loop-state.json` at `HEAD`. Worker prompts and SKILL.md files SHALL instruct workers to return only the path and commit of this file, never a hand-composed result.
+
+#### Scenario: Every terminal and parked shape maps to a schema-valid result
+- **WHEN** the end-to-end test builds a committed loop state for each of: `DONE`/passed, `DONE`/abandoned, `DONE`/refused, `ESCALATE`, `pending_gate` for each gate the result schema permits, `park` of kind `permission_blocked`, and `park` of kind `capability_unavailable`, and runs `emit-result` for each
+- **THEN** each written file SHALL validate against `dispatch-result.schema.json`, its outcome and kind SHALL equal the mapping above, and `ExecutionAdapter.apply` SHALL accept it for a matching prepared attempt
+
+#### Scenario: A non-terminal phase produces no result
+- **WHEN** `emit-result` runs while `current_phase` is `IMPLEMENT` with no `pending_gate` or `park`
+- **THEN** it SHALL exit 5, write no file, and print `runner: loop state is not terminal or parked`
+
+#### Scenario: Uncommitted loop state is refused
+- **WHEN** `loop-state.json` differs from its `HEAD` version
+- **THEN** `emit-result` SHALL exit 2 and write no file
+
+#### Scenario: Abandoned work is not reported as success
+- **WHEN** the loop reached `DONE` through `ESCALATE --abandoned-->`
+- **THEN** the result outcome SHALL be `failed:abandoned`
+
+### Requirement: Loop State Parks and Degradations
+
+`LoopState` SHALL advance to `schema_version` 6, adding `park: dict | None` and `degradations: list[dict]`, and `load_state()` SHALL migrate a version-5 file by defaulting both. `runner.py park <change-id> --kind permission_blocked --tool T --rule R --command C --reason X` and `runner.py park <change-id> --kind capability_unavailable --phase P --missing-lane L ...` SHALL be the only writers of `park`; `runner.py record-degradation <change-id> --code CODE --phase P --detail D` SHALL be the only writer of `degradations`, accepting only the enumerated codes of `dispatch-result.schema.json`. `_apply_transition` SHALL refuse to move a phase while `park` is set, and `runner.py gate-answer --gate escalate_resume --approval-ref R` SHALL clear it.
+
+#### Scenario: Version-5 state migrates
+- **WHEN** `load_state()` reads a `schema_version` 5 file
+- **THEN** the result SHALL have `schema_version` 6, `park` None, `degradations` [], and every v5 field unchanged
+
+#### Scenario: A park blocks transitions
+- **WHEN** `park` is set and `runner.py apply-outcome` is called
+- **THEN** it SHALL exit non-zero naming the park kind, and `current_phase` SHALL be unchanged
+
+#### Scenario: An unknown degradation code is rejected
+- **WHEN** `record-degradation` is called with `--code made_up`
+- **THEN** it SHALL exit 2 and `degradations` SHALL be unchanged
+
+#### Scenario: The park command is redacted before it is stored
+- **WHEN** `park --kind permission_blocked --command 'curl -H "Authorization: Bearer abc123def456ghi789"'` runs
+- **THEN** the stored `park.command` SHALL not contain `abc123def456ghi789`
+
+### Requirement: Gate Authority and Re-Evaluation on Resume
+
+Gate authority SHALL depend on whether the child is dispatched (a launch marker is returned by `dispatch_contract.read_launch_marker`). In a dispatched child the supervisor SHALL be authoritative: the child SHALL apply a gate decision only from the marker's `gate_answer` through `runner.py gate-answer --approval-ref`, SHALL NOT re-evaluate an existing `pending_gate` itself, and, when its worktree posture digest differs from the marker's `posture_digest`, SHALL NOT take an `auto` disposition for any gate but SHALL park `pending_gate` with `posture`-provenance instead. In a standalone run, `runner.py gate-check` SHALL, when a `pending_gate` has a `posture.posture_digest` different from the worktree's current posture digest, re-evaluate that gate before printing it: a `proceed` SHALL clear `pending_gate`, record a `posture`-provenance decision, apply the pending edge, and exit 3; a block SHALL replace `pending_gate` with one carrying the new digest; a gate whose last decision has `human` provenance SHALL NOT be re-evaluated. A human rejection of a gate SHALL stay in force until a later `human`-provenance `proceed` on `escalate_resume` (the operator resuming the run); while it is in force, `gate-check --gate` for that gate SHALL record nothing, SHALL enter `ESCALATE` if the loop is not already there, and SHALL exit 4, and a `posture`-provenance resume SHALL NOT end it. `gate-answer` SHALL record `--approval-ref gate-decision:<id>` in the decision's `provenance` and SHALL refuse (exit 2, nothing recorded) a dispatched child's reference that differs from the marker's `gate_answer.approval_ref`.
+
+#### Scenario: A dispatched child applies the supervisor's answer
+- **GIVEN** a dispatched child parked at `pending_gate/proposal_approval` and a resumed marker whose `gate_answer` is `{gate: proposal_approval, decision: approved, approval_ref: gate-decision:Y}`
+- **WHEN** the child runs `gate-answer --gate proposal_approval --decision approved --approval-ref gate-decision:Y`
+- **THEN** `pending_gate` SHALL be None, the last decision SHALL carry `provenance: {source: human, approval_ref: gate-decision:Y}` or, when the supervisor's decision was posture-derived, `{source: posture, posture_digest}` copied from the answer, and the pending edge SHALL have been applied
+
+#### Scenario: A dispatched child does not self-re-evaluate
+- **WHEN** a dispatched child with a `pending_gate` and no `gate_answer` in its marker runs `gate-check` after its worktree posture changed
+- **THEN** `pending_gate` SHALL be printed unchanged and exit 0, and no decision SHALL be recorded
+
+#### Scenario: Posture drift between child and supervisor blocks auto
+- **WHEN** a dispatched child's worktree posture has `proposal_approval: auto` but its digest differs from the marker's `posture_digest`
+- **THEN** the gate SHALL park as `pending_gate` with reason containing `posture digest differs from dispatch`, and the child SHALL NOT proceed
+
+#### Scenario: A standalone stale posture block clears without an answer
+- **GIVEN** a standalone run with `pending_gate` for `pr_creation` recorded under posture digest D1 (gate `block`)
+- **WHEN** the worktree posture changes `pr_creation` to `auto` and `gate-check` runs
+- **THEN** `pending_gate` SHALL be None, the last decision SHALL have `outcome: proceed` and `provenance.source: posture`, and the exit code SHALL be 3
+
+#### Scenario: A human rejection is not re-evaluated
+- **WHEN** the last decision for the gate has `provenance.source: human` and outcome `blocked`, and the posture changes to `auto`
+- **THEN** `gate-check` SHALL NOT record a new decision and the loop SHALL remain in `ESCALATE`
+
+#### Scenario: An operator resume ends a human rejection
+- **GIVEN** a human rejection of `merge` followed by a `human`-provenance `escalate_resume` `proceed`
+- **WHEN** the resumed phase runs `gate-check --gate merge`
+- **THEN** the gate SHALL be evaluated again under the current posture
+
+#### Scenario: A mismatched approval reference is refused
+- **WHEN** a dispatched child runs `gate-answer --approval-ref gate-decision:X` and the marker's `gate_answer.approval_ref` is `gate-decision:Y`
+- **THEN** it SHALL exit 2 and loop state SHALL be byte-identical
+
+### Requirement: Honest Review Quorum
+
+When the launch marker of a dispatched child carries `review_requirements`, a review phase whose verified lanes from `execution_profile` are fewer than `review_requirements.min_quorum[phase]` SHALL record `park(kind=capability_unavailable, phase, missing_lanes)` and stop, and SHALL NOT run the review with a lower quorum. A standalone run (no launch marker) SHALL keep disabling CLI review below quorum and SHALL record a `review_skipped` degradation, or a `single_vendor_review` degradation when exactly one lane reviewed.
+
+#### Scenario: Dispatched child below quorum parks
+- **WHEN** `review_requirements.min_quorum.PLAN_REVIEW` is 2 and only `claude_code` is verified
+- **THEN** the loop SHALL have `park.kind == capability_unavailable` with `missing_lanes` naming the counting lanes not verified, no review dispatch SHALL have run, and `emit-result` SHALL return `parked/capability_unavailable`
+
+#### Scenario: A single-lane review under a quorum-1 policy is recorded
+- **WHEN** a dispatched child's `review_requirements.min_quorum.PLAN_REVIEW` is 1 by policy data and exactly one review lane dispatches, the others having failed to dispatch
+- **THEN** the review SHALL run and `degradations` SHALL contain a `single_vendor_review` entry for `PLAN_REVIEW` whose detail names the vendor
+- **AND** the child SHALL NOT have read environment variables or credentials to decide that only one lane exists
+
+#### Scenario: GATEKEEPER review scheduling on the host-driven path
+- **WHEN** `runner.py transition --outcome proceed_with_review` is applied in `GATEKEEPER`
+- **THEN** `val_review_enabled` SHALL be True and `gate_verdict` SHALL be `proceed_with_review`
+
+#### Scenario: Standalone run below quorum records a degradation
+- **WHEN** no launch marker exists and `--check-vendors` reports one vendor
+- **THEN** `cli_review_enabled` SHALL be False and `degradations` SHALL contain one `review_skipped` entry for `PLAN_REVIEW`
diff --git a/openspec/changes/dispatch-contract/specs/supervise/spec.md b/openspec/changes/dispatch-contract/specs/supervise/spec.md
new file mode 100644
index 0000000..3bfa8aa
--- /dev/null
+++ b/openspec/changes/dispatch-contract/specs/supervise/spec.md
@@ -0,0 +1,93 @@
+## ADDED Requirements
+
+### Requirement: Dispatch Result Closure
+
+For every `(outcome class, parked.kind, parked.gate)` combination that `dispatch-result.schema.json` permits, the supervisor SHALL have exactly one answer or resume path, declared in a single table `gate_router.ANSWER_PATHS`. A contract test SHALL derive the permitted combinations from the schema itself (not from a hand-written list) and SHALL fail when any combination lacks an entry or an entry names a combination the schema forbids. A parked branch whose `kind` or `gate` is not a `const` or `enum` SHALL fail the enumeration rather than be read as `null`. The table SHALL include the `pending_gate` / `escalate_resume` path merged from `openspec/supervise-pending-escalate-answer`. Before applying a version-2 `success` or `parked` result, `ExecutionAdapter.apply` SHALL re-derive the result from its evidenced loop state through `dispatch_contract.result_from_loop_state` and SHALL refuse the batch when the outcome, the success `handoff_id`, the parked `kind`, a `pending_gate`'s `gate`, or a capability park's dedupe fingerprint differs.
+
+#### Scenario: A result the loop state does not map to is refused
+- **WHEN** a version-2 result claims `success` but its evidenced loop state is `DONE` with `goal_gate.verdict: abandoned`
+- **THEN** `apply` SHALL raise naming the expected outcome, and the attempt SHALL be unchanged
+
+#### Scenario: Every permitted combination has a path
+- **WHEN** the closure test enumerates the schema's `parked` `oneOf` branches and their `kind` / `gate` enums, plus the `success`, `failed:*`, and `vendor_limit:*` outcome classes
+- **THEN** each combination SHALL map to an entry in `ANSWER_PATHS`, and the test SHALL report the full list of missing combinations when any is absent
+
+#### Scenario: Adding a kind without a path fails the test
+- **WHEN** a test fixture copy of the result schema adds a parked kind `example_kind` with no `ANSWER_PATHS` entry and the closure check runs against that copy
+- **THEN** the check SHALL fail naming `("parked", "example_kind", null)`
+
+#### Scenario: pending_gate with escalate_resume is answerable
+- **WHEN** a child returns `parked/pending_gate` with `gate: escalate_resume`
+- **THEN** `resolve_parked` SHALL evaluate `escalate_resume` for that dispatch generation and, on `proceed`, resume it
+
+### Requirement: Typed Gate Answers With Provenance
+
+Every gate-decision record the router writes SHALL carry `provenance`, either `{source: "posture", posture_digest}` or `{source: "human", approval_ref}`. When resolving a parked attempt, the router SHALL re-evaluate a prior `posture`-provenance block whose `posture_digest` differs from the current posture digest, and SHALL treat a `human`-provenance decision as final for its subject. A resume request SHALL carry the decision to the child only as `gate_answer: {gate, decision, approval_ref}`; the supervisor SHALL NOT write any file in a child worktree other than the launch marker.
+
+#### Scenario: A posture-derived block clears after a posture change
+- **GIVEN** an attempt parked `pending_gate/proposal_approval` whose supervisor record has `resolution: posture_block` and `provenance.posture_digest` D1
+- **WHEN** the operator changes `TRUST_POSTURE.md` so `proposal_approval` is `auto` (digest D2) and `resolve_parked` runs for the attempt, whose persisted `roadmap_approval_ref` was verified at prepare
+- **THEN** a new `proceed` record with `provenance: {source: posture, posture_digest: D2}` SHALL be written and the attempt SHALL be resumed with `gate_answer.decision: approved`
+- **AND** the child applying that answer SHALL leave `PLAN` without parking again
+
+#### Scenario: A human rejection survives a posture change
+- **GIVEN** a prior record for the same subject with `resolution: console_rejected` and `provenance.source: human`
+- **WHEN** the posture changes the gate to `auto` and `resolve_parked` runs
+- **THEN** no new record SHALL be written, the attempt SHALL stay parked, and the router SHALL return the existing blocked entry
+
+#### Scenario: An unchanged posture does not re-evaluate
+- **WHEN** `resolve_parked` runs for a `posture_block` record whose `posture_digest` equals the current digest
+- **THEN** the prior record SHALL be reused and no approval SHALL be filed
+
+#### Scenario: A prose-only posture edit is not a posture change
+- **WHEN** only the Markdown body of `TRUST_POSTURE.md` changes and its front matter is unchanged
+- **THEN** the posture digest SHALL be unchanged
+
+### Requirement: Execution Profile and Review Requirements
+
+Before launching a batch, the supervisor SHALL resolve an `execution_profile` (verified lanes per mode `review`, `alternative`, `quick`; `location`; isolation mode; and `probe_command`, the only probe a worker may run) by invoking `review_dispatcher.py --check-vendors --json`, and `review_requirements` (`min_quorum` per review phase, default 2 and overridable by router context `review_min_quorum`, and `counting_lanes` ordered by the `cost_policy.tiers` ladder of `agent-coordinator/routing.yaml`), and SHALL place both in every request. The worker protocol in `skills/autopilot/SKILL.md` SHALL forbid reading environment variables or credentials to discover capabilities. `ExecutionAdapter.apply` SHALL persist the result's `degradations` on the checkpoint attempt and SHALL return them in its summary.
+
+#### Scenario: Request carries a resolved profile
+- **WHEN** `prepare` returns a batch
+- **THEN** every request SHALL validate against `dispatch-request.schema.json` with non-empty `execution_profile.lanes.review`, `execution_profile.probe_command`, and `review_requirements.min_quorum` keyed by review phase
+
+#### Scenario: Profile resolution failure blocks launch
+- **WHEN** `--check-vendors --json` prints output that does not parse as JSON, or JSON carrying an `error` field
+- **THEN** `prepare` SHALL raise without writing any attempt, and the error SHALL name the probe failure
+
+#### Scenario: Below-quorum availability still launches with an honest profile
+- **WHEN** `--check-vendors --json` exits 2 (below quorum) with valid JSON and no `error` field
+- **THEN** `prepare` SHALL succeed, and each request's `execution_profile.lanes.review` SHALL list only the verified lanes, so the child parks `capability_unavailable` at its first review phase
+
+#### Scenario: The per-environment quorum is resolved from data
+- **WHEN** the quorum policy data declares an active `cloud_container` entry with `min_quorum` 1 that applies below 2 verified review lanes, and `prepare` runs in a cloud container where one review lane verifies
+- **THEN** every request's `review_requirements.min_quorum` SHALL be 1 for each review phase and `review_requirements.quorum_policy` SHALL name the environment, the policy entry, and its sunset condition
+- **AND** on a host, or in a container where two or more review lanes verify, `min_quorum` SHALL stay 2
+
+#### Scenario: Degradations reach the checkpoint
+- **WHEN** a success result carries `degradations: [{code: single_vendor_review, phase: PLAN_REVIEW, detail: "codex not dispatchable"}]`
+- **THEN** after `apply` the checkpoint attempt's outcome metadata and the `apply` return value SHALL both contain that entry unchanged
+
+#### Scenario: Worker protocol forbids env probing
+- **WHEN** a guard test scans `skills/autopilot/SKILL.md` and `skills/supervise/SKILL.md`
+- **THEN** neither SHALL contain an instruction to run `env`, `printenv`, or to read API key variables for vendor discovery
+
+### Requirement: Single Escalation Per Capability Park
+
+The router SHALL map `permission_blocked` and `capability_unavailable` parks to an `escalate_resume` subject keyed by a dedupe fingerprint — `sha256(tool, rule, classifier_reason)` for `permission_blocked`, `sha256(phase, sorted(missing_lanes))` for `capability_unavailable` — and SHALL project exactly one `pending_gates` entry per fingerprint listing every parked dispatch that shares it. One `proceed` answer SHALL resume each listed attempt through its own generation-checked compare-and-swap. The stored redacted command SHALL be the output of `sanitize_session_log.sanitize()` (secret-pattern and high-entropy redaction) truncated to 256 characters.
+
+#### Scenario: Three workers blocked on one rule produce one escalation
+- **WHEN** three attempts park `permission_blocked` with tool `Bash`, rule `Bash(env *)`, and the same classifier reason
+- **THEN** the supervisor record SHALL contain one `pending_gates` entry whose dispatch list has all three IDs
+
+#### Scenario: One answer resumes every attempt in the entry
+- **WHEN** the operator answers that entry `approved`
+- **THEN** each of the three attempts SHALL be resumed once with a distinct new generation, and an attempt whose generation changed since projection SHALL be skipped and reported, not resumed
+
+#### Scenario: Different missing lanes are separate escalations
+- **WHEN** one attempt parks `capability_unavailable` missing `{codex}` and another missing `{codex, gemini}` for the same phase
+- **THEN** two `pending_gates` entries SHALL exist
+
+#### Scenario: A secret in the blocked command is redacted
+- **WHEN** a `permission_blocked` park reports command `curl -H "Authorization: Bearer abc123..."`
+- **THEN** the persisted command SHALL not contain `abc123` and SHALL contain a `[REDACTED:` marker
diff --git a/openspec/changes/dispatch-contract/specs/trust-posture/spec.md b/openspec/changes/dispatch-contract/specs/trust-posture/spec.md
new file mode 100644
index 0000000..2d3db68
--- /dev/null
+++ b/openspec/changes/dispatch-contract/specs/trust-posture/spec.md
@@ -0,0 +1,29 @@
+## ADDED Requirements
+
+### Requirement: Roadmap-Approval-Scoped Auto Dispositions
+
+The trust posture SHALL let the `proposal_approval` and `replan_required` gate configs declare an optional `unscoped` sub-config (`disposition` of `notify_with_timeout` or `block`, with the same `timeout_seconds` / `default_action` rules as a gate config), defaulting to `{disposition: block}` when absent. When either gate's disposition is `auto`, the approval gate SHALL apply `auto` only if the current launch marker, obtained by the gate through its `marker_reader` seam, carries a `roadmap_approval_ref`, and SHALL ignore any `roadmap_approval_ref` supplied in the evaluation context; otherwise it SHALL apply the `unscoped` config and record `scope: unscoped` and a reason naming the fallback in the decision. `unscoped` with disposition `auto`, or on any other gate, SHALL be a validation error. The loader SHALL also expose `posture_digest(posture)`: the SHA-256 of the canonical JSON of the parsed `gates` map, with a fixed value for the absent-posture default.
+
+#### Scenario: Dispatched run with a valid approval reference proceeds
+- **WHEN** `proposal_approval` is `auto` and `marker_reader` returns a marker carrying `roadmap_approval_ref`
+- **THEN** the decision SHALL be `proceed` with `resolution: auto` and `scope: roadmap_approval`
+
+#### Scenario: Standalone run falls back to the unscoped disposition
+- **WHEN** `proposal_approval` is `auto`, no `unscoped` is declared, and `marker_reader` returns None
+- **THEN** the decision SHALL be `blocked` with `resolution: posture_block`, `scope: unscoped`, and a reason containing `unscoped fallback`
+
+#### Scenario: Declared notify fallback is used
+- **WHEN** `replan_required` is `auto` with `unscoped: {disposition: notify_with_timeout, timeout_seconds: 600, default_action: block}` and no reference is present
+- **THEN** the approval gate SHALL file an approval and apply `block` on timeout
+
+#### Scenario: A reference not from the launch marker is ignored
+- **WHEN** the evaluation context carries `roadmap_approval_ref: gate-decision:Z` but `marker_reader` returns None
+- **THEN** the unscoped fallback SHALL apply and the record's `scope` SHALL be `unscoped`
+
+#### Scenario: Invalid unscoped config is rejected
+- **WHEN** `TRUST_POSTURE.md` declares `unscoped: {disposition: auto}` or declares `unscoped` on `merge`
+- **THEN** `validate_posture_file` SHALL return an error naming the gate and field
+
+#### Scenario: Digest ignores prose and key order
+- **WHEN** two posture files differ only in Markdown body text and front-matter key order
+- **THEN** `posture_digest` SHALL return the same value for both
diff --git a/openspec/changes/dispatch-contract/tasks.md b/openspec/changes/dispatch-contract/tasks.md
index b82d273..e834294 100644
--- a/openspec/changes/dispatch-contract/tasks.md
+++ b/openspec/changes/dispatch-contract/tasks.md
@@ -1,19 +1,245 @@
 # Tasks: Publish the supervisor-worker dispatch contract
 
 > Change ID: `dispatch-contract`
+> Packages and write scopes: `work-packages.yaml`. Each task names its package
+> (`[wp-*]`), its dependencies, and the requirement(s) it implements
+> (RO = roadmap-orchestration, SV = supervise, SW = skill-workflow,
+> TP = trust-posture, PI = parallel-infrastructure).
 
-## Status
+## 1. Merge the narrow fix  `[wp-merge-narrow-fix]` (no deps)
 
-- [ ] Planning
-- [ ] Implementation
-- [ ] Testing
-- [ ] Review
-- [ ] Done
+- [x] 1.1 Merge `origin/openspec/supervise-pending-escalate-answer` (6e6e9a6) into
+  `openspec/dispatch-contract`; resolve nothing by re-implementing. Run
+  `skills/tests/supervise/test_gate_router.py`. — SV Dispatch Result Closure
+  (pending_gate/escalate_resume path)
 
-## Tasks
+## 2. Schemas  `[wp-dispatch-schemas]` (no deps)
 
-- [ ] Define detailed requirements
-- [ ] Implement core functionality
-- [ ] Write tests
-- [ ] Update documentation
-- [ ] Review and merge
+- [x] 2.1 Write `openspec/schemas/dispatch-result.schema.json` v2: outcome classes,
+  `parked` `oneOf` per kind (D3), `gate` as the `Gate` enum, `degradations` code enum
+  (D10), isolation echo `{worktree_ref, branch, host_id}`, evidence. — RO Published
+  Dispatch Contract Schemas
+- [x] 2.2 Write `openspec/schemas/dispatch-request.schema.json` v2: identity, raw
+  `launch_token`, host-portable `isolation`, `execution_profile`,
+  `review_requirements`, optional `continuation` and `gate_answer`,
+  `roadmap_approval_ref`. — RO Published Dispatch Contract Schemas; SV Execution
+  Profile and Review Requirements
+- [x] 2.3 Edit `checkpoint.schema.json`: attempt `result` -> `$ref`; `launch_token` ->
+  `launch_digest` (`^sha256:[0-9a-f]{64}$`); attempt `roadmap_approval_ref`; isolation
+  `{mode, worktree_ref, branch, host_id}`; parked kinds extended; `rebound` history state. — RO Launch Token Digest,
+  Host-Portable Attempt Isolation
+- [x] 2.3a Existing contract schemas (design D2): edit
+  `openspec/contracts/roadmap-orchestration/schemas/delegated-dispatch-attempt.schema.json`
+  to the new attempt shape and make `checkpoint.schema.json` `dispatch_attempts.items`
+  `$ref` it; keep `supervised-dispatch-request`/`-result.schema.json` byte-unchanged as
+  v1 reader schemas; `$ref` `bounded-dispatch-context.schema.json` from the v2
+  request. Repoint `skills/tests/supervise/test_execution_contract.py` at the v2/v1
+  schemas through a registry. (dep 2.1-2.3) — RO Published Dispatch Contract Schemas
+- [x] 2.4 Mirror 2.1-2.3a into `skills/roadmap-runtime/install_assets/openspec/`
+  (`schemas/` and `contracts/roadmap-orchestration/schemas/`) and add the byte-parity
+  test; add the new installed paths to
+  `skills/tests/install_sh/test_openspec_assets.py`. (dep 2.1-2.3a) — RO Published
+  Dispatch Contract Schemas
+
+## 3. Posture provenance and scope  `[wp-posture]` (no deps)
+
+- [x] 3.1 Test first: `skills/tests/shared/test_trust_posture_scope.py` covering every
+  TP scenario (digest stability, `unscoped` validation). — TP
+- [x] 3.2 `trust_posture.py`: `posture_digest()`, `unscoped` sub-config parse and
+  validation; `trust-posture.schema.json` and `TRUST_POSTURE.template.md` document it.
+  (dep 3.1) — TP Roadmap-Approval-Scoped Auto Dispositions
+- [x] 3.3 `approval_gate.py`: `provenance` on every decision record; scoped `auto` for
+  `proposal_approval` / `replan_required` using a `marker_reader` seam (context-supplied
+  refs ignored); `scope` recorded. `gate-decision.schema.json` and
+  `gate-request.schema.json` gain `provenance`, `scope`, `posture.posture_digest`.
+  (dep 3.2) — TP; SV Typed Gate Answers With Provenance
+
+## 4. Contract library  `[wp-contract-lib]` (deps: 2.4)
+
+- [x] 4.1 Test first: `skills/tests/shared/test_dispatch_contract.py` — fixture
+  validation, v1 upgrade (both scenarios), mapping table rows from D4, slug rule,
+  marker reader. — RO Published Dispatch Contract Schemas; SW Code-Emitted Dispatch
+  Result
+- [x] 4.2 `skills/shared/dispatch_contract.py`: schema locator with install_assets
+  fallback, `validate_request`, `validate_result`, `upgrade_v1`,
+  `result_from_loop_state`, `dispatch_slug`, `read_launch_marker`,
+  `DispatchContractError`; a `referencing.Registry` built from every schema under
+  `openspec/schemas/` and `openspec/contracts/roadmap-orchestration/schemas/`
+  (`$id`-keyed) and exported as `schema_registry(repo_root)`. (dep 4.1)
+- [x] 4.3 `skills/shared/environment_profile.py`: add `host_id()` (cloud session
+  environment ID when present, else a hash of the machine ID; never a hostname or
+  username) with a unit test. — RO Host-Portable Attempt Isolation (D7)
+
+## 5. Runtime ledger  `[wp-runtime-ledger]` (deps: 4.2)
+
+- [x] 5.1 Test first: legacy-load tests that copy the archived checkpoint and the live
+  `multiplayer-collaboration` checkpoint into `tmp_path` at test time (never commit a
+  copy: both contain raw tokens); persisted-shape tests (no raw token, no absolute
+  path). Update `test_delegated_checkpoint.py` and `test_dispatch_scheduler.py`,
+  which pin `launch_token` today. — RO Launch Token Digest, Host-Portable Attempt Isolation
+- [x] 5.2 `roadmap-runtime/scripts/models.py` + `checkpoint.py`: attempt fields
+  `launch_digest` and portable isolation; legacy migration on load; `needs_rebind`;
+  `validate_against_schema` builds its `Draft202012Validator` with
+  `dispatch_contract.schema_registry(repo_root)` so the checkpoint's `$ref`s resolve
+  (today it uses a bare validator, so `resolve_readiness.py` and checkpoint load would
+  fail on an unresolvable reference). (dep 5.1)
+- [x] 5.2a Update every test helper that copies only `checkpoint.schema.json` into a
+  temporary repo to also copy the schemas it `$ref`s: `roadmap-runtime/test_readiness.py`,
+  `autopilot-roadmap/test_supervised_dispatch.py`, `test_supervised_dispatch_e2e.py`
+  (this package), and `supervise/test_execution.py`, `test_gate_router.py`,
+  `test_gate_router_e2e.py`, `test_cycle_state.py` (in 8.1). (dep 5.2)
+- [x] 5.3 `autopilot-roadmap/scripts/orchestrator.py`: mint token, store digest,
+  take and persist the verified `roadmap_approval_ref` from `ExecutionAdapter.prepare`,
+  emit v2 request; replace `_validate_dispatch_result` with `dispatch_contract`;
+  `resolve_worktree()` for every path read; persist `degradations` in outcome
+  metadata; refuse unroutable parked results at apply (calls the answer-path predicate
+  injected by the adapter). (dep 5.2) — RO Outcome-Only Resume Contract, Durable
+  Delegated Attempt Ledger
+
+## 6. Autopilot child  `[wp-autopilot-child]` (deps: 3.3, 4.2)
+
+- [x] 6.1 Test first: `skills/tests/autopilot/test_emit_result.py`,
+  `test_loop_state_v6.py`, `test_gate_check_reeval.py`. — SW all four requirements
+- [x] 6.2 `autopilot.py`: LoopState v6 (`park`, `degradations`), v5 migration,
+  `_apply_transition` refuses while parked; the gate session constructs
+  `ApprovalGate` with its default `marker_reader`
+  (`dispatch_contract.read_launch_marker`) and passes no `roadmap_approval_ref` or
+  other scope value through the gate context, which D8 ignores. (dep 6.1) — SW Loop
+  State Parks and Degradations; TP
+- [x] 6.3 `runner.py`: `emit-result`, `park`, `record-degradation`. (dep 6.2) — SW
+  Code-Emitted Dispatch Result, Loop State Parks and Degradations
+- [x] 6.4 `runner.py` + gate session: dispatched-vs-standalone authority (marker
+  present => apply only `gate_answer`; worktree/marker posture-digest drift => no
+  `auto`, park `pending_gate`); standalone `gate-check` re-evaluation on digest change;
+  `gate-answer --approval-ref` with marker check; clears `park` for `escalate_resume`.
+  (dep 6.3)
+  — SW Gate Authority and Re-Evaluation on Resume
+- [x] 6.5 `skills/autopilot/SKILL.md`: worker protocol — `emit-result` + commit, `park`
+  on permission denial, `probe_command` only, no env probing. Replace the
+  below-quorum `CLI_REVIEW_ENABLED=false` step: in a dispatched child (marker present)
+  keep review enabled and, at `PLAN_REVIEW` / `IMPL_REVIEW` entry, compare
+  `execution_profile.lanes.review` with `review_requirements.min_quorum[phase]` and run
+  `runner.py park --kind capability_unavailable --phase P --missing-lane ...` when
+  short; in a standalone run keep disabling review and run `runner.py
+  record-degradation --code review_skipped --phase PLAN_REVIEW`. Resync mirrors with
+  `install.sh`. (dep 6.4) — SV Execution Profile and Review Requirements; SW
+  Code-Emitted Dispatch Result, Honest Review Quorum
+- [x] 6.6 Supervisor follow-up (a): `autopilot._apply_transition` applies GATEKEEPER
+  `proceed_with_review` (sets `val_review_enabled`, records `gate_verdict`) so the
+  host-driven `runner.py transition` path schedules VAL_REVIEW like `run_loop`; tests in
+  `test_loop_state_v6.py`. — SV Execution Profile and Review Requirements
+- [x] 6.7 Supervisor follow-up (b): `emit-result` derives `parked` only from `park`,
+  `pending_gate` or `ESCALATE`, so a parked result without that loop-state evidence is
+  unproducible; `apply` accepts `park` evidence for the two new kinds. Covered in the
+  `test_emit_result.py` matrix. — SW Code-Emitted Dispatch Result
+
+## 7. Review honesty  `[wp-review-honesty]` (deps: 6.3)
+
+- [x] 7.1 Test first: `skills/tests/parallel-infrastructure/test_check_vendors_dispatchable.py`
+  and `skills/tests/autopilot/test_quorum_park.py`. — PI; SW Honest Review Quorum
+- [x] 7.2 `review_dispatcher.py`: dry-invocation verification, `--json` output,
+  env-free probe. (dep 7.1) — PI Dispatchable Vendor Verification
+- [x] 7.3 `convergence_loop.py`: pre-dispatch guard that returns
+  `ConvergenceResult(reason="capability_unavailable")` with the missing lanes when it
+  is handed fewer verified lanes than `min_quorum`, before any dispatch; it writes no
+  loop state (the caller runs `runner.py park`, the only writer of `park`). (dep 7.1,
+  6.3) — SW Honest Review Quorum
+- [x] 7.4 Supervisor follow-up 1: per-environment review quorum as data —
+  `skills/parallel-infrastructure/review_quorum_policy.json` (cloud container below 2
+  verified lanes -> `min_quorum` 1, with the sunset from the operator's TRUST_POSTURE.md
+  decision of 2026-10-09; any other host keeps 2), resolved by
+  `review_dispatcher.resolve_quorum_policy()` into `--check-vendors --json`
+  `quorum_policy`, carried as `review_requirements.quorum_policy`
+  (`dispatch-request.schema.json`). A single-lane review is detected by failed dispatch
+  only and records `single_vendor_review` (phase, vendor). — SV Execution Profile and
+  Review Requirements; SW Honest Review Quorum
+
+- [x] 7.5 Supervisor follow-up (d): `review_packet._git_diff` resolves its base ref
+  robustly (`main`, else `origin/main`), so a checkout with only the remote-tracking
+  base no longer produces an empty review packet; test in `test_review_packet.py`
+  (one-file scope extension to `review_packet.py`). — SW Honest Review Quorum
+- [x] 7.6 Supervisor follow-up (d), IMPL_ITERATE: `converge(..., base_ref=None)`
+  passes `base_ref` through to `build_review_packet`, so a stacked branch diffs
+  against its PR base; `None` keeps `DEFAULT_BASE_REF`. Tests in
+  `skills/tests/autopilot/test_convergence_loop.py`. — SW Honest Review Quorum
+- [x] 7.7 Supervisor follow-up (d), IMPL_ITERATE: the post-fix scope check in
+  `converge()` excludes converge's own `artifacts_dir` bookkeeping
+  (`.review-ledger/`, `.review-cache/`), so a fix that edits only an allowed path is
+  not rejected by `reject_out_of_scope_fix`. Regression test in
+  `skills/tests/autopilot/test_convergence_loop.py`. — SW Honest Review Quorum
+
+## 8. Supervisor  `[wp-supervisor]` (deps: 1.1, 3.3, 5.3)
+
+- [x] 8.1 Test first: extend `skills/tests/supervise/test_execution.py` and
+  `test_gate_router.py` for token verify/rotate/reissue, cross-host reconcile,
+  provenance re-evaluation, dedupe escalation (one `escalate_resume` record per
+  listed dispatch, design D9), degradations persistence. Update
+  `test_gate_router_e2e.py` and `test_cycle_state.py` (schema copies, 5.2a); leave the existing `fixtures/execution/contracts/` v1
+  fixtures byte-unchanged (outcome 1: they must pass through the v1 reader) and add
+  v2 fixtures beside them. — RO, SV
+- [x] 8.2 `execution.py`: delete hand validators; `child_start` digest verify;
+  `reissue`; token rotation in `resume`; `resume` accepts parked kinds
+  `permission_blocked` / `capability_unavailable` (expected gate `escalate_resume`,
+  `dedupe_fingerprint` recomputed and compared); marker v2 contents including the supervisor's
+  `posture_digest` (D10a);
+  `execution_profile` / `review_requirements` resolution in `prepare`; host-portable
+  verify, rebind and reinitialize in `reconcile`. (dep 8.1) — RO Launch Token Digest,
+  Host-Portable Attempt Isolation; SV Execution Profile and Review Requirements
+- [x] 8.3 `gate_router.py`: `ANSWER_PATHS` table; provenance-aware
+  `_apply_prior_record` (digest, human-final); `resolve_parked` for the two new kinds
+  with fingerprint dedupe and fan-out resume (one per-dispatch `escalate_resume`
+  record carrying its own `lease_generation` and the shared `dedupe_fingerprint`, so
+  `require_approval_ref` keeps its per-dispatch checks); typed `gate_answer` in continuation.
+  (dep 8.2) — SV Dispatch Result Closure, Typed Gate Answers With Provenance, Single
+  Escalation Per Capability Park
+- [x] 8.4 `skills/supervise/SKILL.md`: collect results by committed file path, profile
+  resolution, new park kinds; resync mirrors. (dep 8.3)
+
+## 9. Integration  `[wp-integration]` (deps: 6.5, 7.3, 8.4)
+
+- [x] 9.1 Closure contract test `skills/tests/supervise/test_dispatch_closure.py`,
+  schema-derived enumeration plus the mutated-schema negative case. — SV Dispatch
+  Result Closure (outcome 3)
+- [x] 9.2 End-to-end test `skills/tests/autopilot-roadmap/test_dispatch_contract_e2e.py`:
+  prepare -> child_start -> loop-state shapes -> `emit-result` -> `apply` for every
+  shape; includes posture flip vs human rejection and the two single-escalation
+  cases. — outcomes 2, 4, 5
+- [x] 9.3 Cross-host test: commit a checkpoint on host id A, reconcile with host id B
+  (rebind, reinitialize, quarantine, evidence mismatch). — outcome 7
+- [x] 9.4 Landable fixture `skills/tests/roadmap-runtime/fixtures/landable-checkpoint.json`
+  generated by the e2e harness with live attempts, plus the keyword unit test; confirm
+  no `.gitleaks.toml` change. Run `gitleaks detect --no-git --source
+  skills/tests/roadmap-runtime/fixtures` locally when the binary is present. —
+  outcome 6
+- [x] 9.5 Scoped-auto e2e: dispatched child with marker ref proceeds; standalone run
+  blocks with `scope: unscoped`. — outcome 8
+- [x] 9.6 Full suites: `skills/.venv/bin/python -m pytest skills/tests/{supervise,autopilot,autopilot-roadmap,roadmap-runtime,shared,parallel-infrastructure}`,
+  `openspec validate dispatch-contract --strict`, existing fixtures unchanged. —
+  outcome 1
+
+- [x] 9.7 Supervisor follow-ups (c), (e) and plan sync: design.md records the
+  per-environment quorum policy as data (D10), the `main`-rooted worktree launchpad as
+  a known constraint with an open follow-up, and the implementation notes; the
+  supervise and skill-workflow spec deltas gain the quorum-policy, single-lane and
+  GATEKEEPER scenarios; proposal.md gains "Landing approach for PR #662" (squash merge
+  so the SHA-allowlisted token commits never enter `main`; no history rewritten).
+
+## Traceability
+
+| Requirement | Tasks |
+|---|---|
+| RO Published Dispatch Contract Schemas | 2.1, 2.2, 2.3a, 2.4, 4.1, 4.2, 5.2, 5.2a, 5.3, 8.2, 9.6 |
+| RO Launch Token Digest | 2.3, 5.1, 5.2, 5.3, 8.2, 9.4 |
+| RO Host-Portable Attempt Isolation | 2.3, 4.3, 5.1, 5.2, 8.2, 9.3 |
+| RO Outcome-Only Resume Contract (MOD) | 5.3, 8.3, 9.2 |
+| RO Durable Delegated Attempt Ledger (MOD) | 5.3, 8.2, 9.2 |
+| SV Dispatch Result Closure | 1.1, 8.3, 9.1 |
+| SV Typed Gate Answers With Provenance | 3.3, 8.3, 9.2 |
+| SV Execution Profile and Review Requirements | 2.2, 6.5, 8.2, 9.2 |
+| SV Single Escalation Per Capability Park | 8.3, 9.2 |
+| SW Code-Emitted Dispatch Result | 4.2, 6.3, 6.5, 9.2 |
+| SW Loop State Parks and Degradations | 6.2, 6.3 |
+| SW Gate Authority and Re-Evaluation on Resume | 6.4, 9.2 |
+| SW Honest Review Quorum | 6.5, 7.3 |
+| TP Roadmap-Approval-Scoped Auto Dispositions | 3.1, 3.2, 3.3, 6.2, 9.5 |
+| PI Dispatchable Vendor Verification | 7.1, 7.2 |
diff --git a/openspec/changes/dispatch-contract/validation-report.md b/openspec/changes/dispatch-contract/validation-report.md
new file mode 100644
index 0000000..0619eca
--- /dev/null
+++ b/openspec/changes/dispatch-contract/validation-report.md
@@ -0,0 +1,116 @@
+# Validation Report: dispatch-contract
+
+**Date**: 2026-10-09
+**Commit**: 7cc9180c3ea49a0a9b08618d376bf0c2793bdccc
+**Branch**: openspec/dispatch-contract
+
+Scope: skills scripts, shared libraries, and JSON schemas only. There is no deployable
+service (no docker-compose, agent-coordinator/, packages/ or apps/ path changed; the only
+non-skills/openspec/docs path is the root `TRUST_POSTURE.template.md`). Container-dependent
+phases are therefore not applicable, not skipped.
+
+## Phase Results
+
+- Deploy: not applicable (no deployable surface)
+- Smoke: not applicable (no live service)
+- Gen-Eval: not applicable (no descriptors touched; no service)
+- Security: not applicable for live scanners (no service); secret scan evidence under Spec Compliance outcome 6
+- E2E: not applicable (no browser-facing surface)
+- Architecture: not run (advisory; no service/graph consumer touched)
+- Task drift: pass (0 unchecked boxes in tasks.md)
+- OpenSpec: pass (`openspec validate dispatch-contract --strict`: valid)
+- Lint: pass (`ruff check` on every changed Python file/dir: all checks passed)
+- Test suites: pass except the known environment-only failure (see Spec Compliance)
+- CI/CD: DEGRADED (not checked; GitHub MCP lists zero workflow runs for branch openspec/dispatch-contract and no PR exists yet)
+- Choices: no ledger
+
+## Spec Compliance
+
+**Status**: pass
+
+Per-directory results (each `skills/tests/<dir>` run in its own process, base-independent):
+
+| Suite | Result |
+|---|---|
+| skills/tests/autopilot | 533 passed, 6 skipped |
+| skills/tests/autopilot-roadmap | 144 passed |
+| skills/tests/install_sh | 18 passed, 14 skipped |
+| skills/tests/parallel-infrastructure | 292 passed, 2 skipped |
+| skills/tests/roadmap-runtime | 181 passed, 1 skipped |
+| skills/tests/shared | 134 passed, 1 skipped |
+| skills/tests/supervise | 459 passed, 1 failed (known) |
+| skills/autopilot/scripts/tests/test_autopilot.py | 48 passed |
+
+The single failure is the documented environment-only
+`test_workflow_contract.py::test_contract_inspects_the_canonical_source_contribution`
+(fails identically at base bdb0048 when run under a `.claude/` path). No other failures.
+
+### Acceptance outcome to test mapping (proposal.md, ri-21)
+
+1. Schemas exist and execution.py / orchestrator.py validate against them, fixtures pass: pass.
+   `shared/test_dispatch_contract.py`, `roadmap-runtime/test_dispatch_schema_parity.py`,
+   `supervise/test_execution_contract.py`, `supervise/test_execution.py`,
+   `autopilot-roadmap/test_supervised_dispatch.py`. Legacy loading: every
+   `openspec/roadmaps/**/checkpoint.json` (archived 2026-09-26, dispatch-governance,
+   multiplayer-collaboration with 4 raw-token attempts, principal-credential-architecture,
+   roadmap-jev-system-one-integration-assessment) loaded through `models.load_checkpoint`
+   from a tmp copy (5/5 LOAD OK; real files untouched), and
+   `roadmap-runtime/test_checkpoint_legacy_migration.py` (archived + live, 5 tests) passes.
+2. emit-result produces a schema-valid result for every terminal/parked shape, end to end: pass.
+   `autopilot/test_emit_result.py`, `autopilot-roadmap/test_dispatch_contract_e2e.py::test_every_shape_round_trips_through_emit_result_and_apply`,
+   `::test_apply_refuses_a_result_the_loop_state_does_not_map_to`.
+3. Closure contract test fails on any unrouted parked kind/gate: pass.
+   `supervise/test_dispatch_closure.py` (`test_every_permitted_combination_has_exactly_one_path`,
+   `test_adding_a_kind_without_a_path_fails_naming_it`, `test_pending_gate_with_escalate_resume_is_answerable`, apply-time predicate table).
+4. Posture-derived block clears on resume after posture change, human rejection does not: pass.
+   `autopilot/test_gate_check_reeval.py` (`test_a_standalone_stale_posture_block_clears_without_an_answer`,
+   `test_a_human_rejection_is_not_re_evaluated`), `autopilot-roadmap/test_dispatch_contract_e2e.py`
+   (`test_a_posture_flip_resumes_the_child_which_leaves_plan`, `test_a_human_rejection_survives_the_posture_flip`),
+   `shared/test_approval_gate_provenance.py`.
+5. execution_profile, review_requirements, degradations[] carried end to end; capability parks routed as single escalations: pass.
+   `autopilot-roadmap/test_dispatch_contract_e2e.py::test_a_capability_park_is_one_operator_escalation_that_resumes_the_child`,
+   `autopilot/test_quorum_park.py`, `autopilot/test_convergence_loop.py`,
+   `parallel-infrastructure/test_check_vendors_dispatchable.py`, `parallel-infrastructure/test_review_packet.py`.
+6. checkpoint.json stores no raw launch token; default secret scan passes with no allowlist entry: pass (with one sub-check not run).
+   `roadmap-runtime/test_landable_checkpoint.py`: `test_the_fixture_has_live_attempts_and_no_raw_token`,
+   `test_the_default_generic_api_key_rule_finds_nothing` (Python port of the default gitleaks
+   generic-api-key rule: keyword prefilter, regex, entropy > 3.5, applied to the committed-shape
+   fixture with 2 live attempts), `test_the_rule_port_catches_a_raw_launch_token` (calibration),
+   `test_no_scalar_field_name_matches_the_generic_api_key_keywords`,
+   `test_gitleaks_config_has_no_entry_for_the_fixture` (no allowlist help),
+   `test_the_builder_reproduces_the_fixture_shape` (fixture produced by real prepare/child_start/acknowledge).
+   child_start digest verification: `roadmap-runtime/test_delegated_checkpoint.py`, `autopilot-roadmap/test_supervised_dispatch*.py`.
+   NOT RUN: `test_gitleaks_scan_of_the_fixture_directory_is_clean` (skipped: gitleaks binary not
+   installed; binaries must not be downloaded). The CI gitleaks job remains the real-binary check.
+7. Checkpoint with live attempts committed on one host reconciles on another: pass.
+   `roadmap-runtime/test_cross_host_reconcile.py` (7 tests: rebind of matching worktree, refusal on diverged worktree / digest mismatch,
+   reinitialize of prepared attempt, unexpired vs expired pre-go claim, post-go unknown liveness quarantined).
+8. auto for proposal_approval / replan_required proceeds only with valid roadmap_approval_ref: pass.
+   `shared/test_trust_posture_scope.py` (valid ref proceeds; standalone falls back to unscoped; marker-sourced refs only),
+   `autopilot-roadmap/test_dispatch_contract_e2e.py::test_a_dispatched_child_with_a_marker_ref_takes_scoped_auto`,
+   `::test_a_standalone_run_blocks_with_scope_unscoped`.
+
+## Smoke Tests
+
+**Status**: not applicable
+Reason: skills/schemas-only change, no running service to smoke test.
+
+## Security
+
+**Status**: not applicable
+Reason: no deployable surface for ZAP/dependency-check. Secret-scan evidence for the changed checkpoint shape is in Spec Compliance outcome 6; the real gitleaks binary was not available locally (CI covers it).
+
+## E2E Tests
+
+**Status**: not applicable
+Reason: no browser or service surface.
+
+## Review Degradations
+
+- single_vendor_review: PLAN_REVIEW and IMPL_REVIEW ran claude_code only (cloud-container policy, min_quorum=1).
+- coordinator_projection_forbidden: coordinator queue projection returned forbidden (expected in this environment).
+- GATEKEEPER ran via a real judge (no degradation).
+
+## Result
+
+**PASS** — All eight acceptance outcomes are covered by passing tests. Not-run items are recorded above (gitleaks binary, CI status, live-service phases). Ready for `/cleanup-feature dispatch-contract`.
diff --git a/openspec/changes/dispatch-contract/work-packages.yaml b/openspec/changes/dispatch-contract/work-packages.yaml
new file mode 100644
index 0000000..0a87a84
--- /dev/null
+++ b/openspec/changes/dispatch-contract/work-packages.yaml
@@ -0,0 +1,565 @@
+# Packages are shaped by file ownership; see design.md "Package boundaries and ordering".
+schema_version: 1
+feature:
+  id: dispatch-contract
+  title: Publish the supervisor-worker dispatch contract
+  plan_revision: 2
+  created_by: claude-code
+  deployable: false  # skills scripts + JSON schemas only; no service surface
+contracts:
+  revision: 1
+  openapi:
+    primary: openspec/schemas/dispatch-result.schema.json
+    files:
+    - openspec/schemas/dispatch-request.schema.json
+    - openspec/schemas/dispatch-result.schema.json
+    - openspec/contracts/roadmap-orchestration/schemas/delegated-dispatch-attempt.schema.json
+    - openspec/contracts/roadmap-orchestration/schemas/bounded-dispatch-context.schema.json
+    - openspec/contracts/roadmap-orchestration/schemas/supervised-dispatch-request.schema.json
+    - openspec/contracts/roadmap-orchestration/schemas/supervised-dispatch-result.schema.json
+defaults:
+  priority: 5
+  lock_ttl_minutes: 120
+  timeout_minutes: 60
+  retry_budget: 2
+  verification_tier_required: B
+  min_trust_level: 2
+packages:
+- package_id: wp-merge-narrow-fix
+  title: Merge supervise-pending-escalate-answer
+  task_type: integration
+  description: Task 1.1. Merge origin/openspec/supervise-pending-escalate-answer (6e6e9a6) unchanged.
+  role: integrator
+  priority: 1
+  depends_on: []
+  locks:
+    files:
+    - skills/supervise/SKILL.md
+    - skills/supervise/scripts/execution.py
+    - skills/supervise/scripts/gate_router.py
+    - skills/tests/supervise/test_gate_router.py
+    keys:
+    - feature:dispatch-contract:supervisor
+    ttl_minutes: 120
+    reason: Merge supervise-pending-escalate-answer
+  scope:
+    write_allow:
+    - skills/supervise/SKILL.md
+    - skills/supervise/scripts/execution.py
+    - skills/supervise/scripts/gate_router.py
+    - skills/tests/supervise/test_gate_router.py
+    read_allow:
+    - '**'
+  worktree:
+    name: dispatch-contract-wp-merge-narrow-fix
+    mode: isolated
+  timeout_minutes: 60
+  retry_budget: 2
+  min_trust_level: 2
+  verification:
+    tier_required: B
+    steps:
+    - name: wp-merge-narrow-fix tests
+      kind: command
+      command: skills/.venv/bin/python -m pytest skills/tests/supervise/test_gate_router.py -q
+      cwd: .
+      expect_exit_code: 0
+      evidence:
+        artifacts: []
+        result_keys:
+        - wp_merge_narrow_fix_pass
+  metadata:
+    loc_estimate: 260
+    complexity: low
+    package_kind: integration
+  inputs: {}
+  outputs:
+    result_keys:
+    - wp_merge_narrow_fix_pass
+    artifacts: []
+- package_id: wp-dispatch-schemas
+  title: Dispatch request/result and checkpoint schemas
+  task_type: contracts
+  description: Tasks 2.1-2.4. Publish dispatch-request/result v2, edit checkpoint schema, mirror to install_assets,
+    parity test.
+  role: contracts-author
+  priority: 1
+  depends_on: []
+  locks:
+    files:
+    - openspec/schemas/dispatch-request.schema.json
+    - openspec/schemas/dispatch-result.schema.json
+    - openspec/schemas/checkpoint.schema.json
+    - skills/roadmap-runtime/install_assets/openspec/schemas/dispatch-request.schema.json
+    - skills/roadmap-runtime/install_assets/openspec/schemas/dispatch-result.schema.json
+    - skills/roadmap-runtime/install_assets/openspec/schemas/checkpoint.schema.json
+    - skills/tests/roadmap-runtime/test_dispatch_schema_parity.py
+    - openspec/contracts/roadmap-orchestration/schemas/delegated-dispatch-attempt.schema.json
+    - skills/roadmap-runtime/install_assets/openspec/contracts/roadmap-orchestration/schemas/**
+    - skills/tests/supervise/test_execution_contract.py
+    - skills/tests/install_sh/test_openspec_assets.py
+    keys:
+    - contract:dispatch-request
+    - contract:dispatch-result
+    - contract:checkpoint
+    ttl_minutes: 120
+    reason: Dispatch request/result and checkpoint schemas
+  scope:
+    write_allow:
+    - openspec/schemas/dispatch-request.schema.json
+    - openspec/schemas/dispatch-result.schema.json
+    - openspec/schemas/checkpoint.schema.json
+    - skills/roadmap-runtime/install_assets/openspec/schemas/dispatch-request.schema.json
+    - skills/roadmap-runtime/install_assets/openspec/schemas/dispatch-result.schema.json
+    - skills/roadmap-runtime/install_assets/openspec/schemas/checkpoint.schema.json
+    - skills/tests/roadmap-runtime/test_dispatch_schema_parity.py
+    - openspec/contracts/roadmap-orchestration/schemas/delegated-dispatch-attempt.schema.json
+    - skills/roadmap-runtime/install_assets/openspec/contracts/roadmap-orchestration/schemas/**
+    - skills/tests/supervise/test_execution_contract.py
+    - skills/tests/install_sh/test_openspec_assets.py
+    read_allow:
+    - '**'
+  worktree:
+    name: dispatch-contract-wp-dispatch-schemas
+    mode: isolated
+  timeout_minutes: 90
+  retry_budget: 2
+  min_trust_level: 2
+  verification:
+    tier_required: C
+    steps:
+    - name: wp-dispatch-schemas tests
+      kind: command
+      command: skills/.venv/bin/python -m pytest skills/tests/roadmap-runtime/test_dispatch_schema_parity.py
+        -q
+      cwd: .
+      expect_exit_code: 0
+      evidence:
+        artifacts: []
+        result_keys:
+        - wp_dispatch_schemas_pass
+  metadata:
+    loc_estimate: 450
+    complexity: medium
+    package_kind: config
+  inputs: {}
+  outputs:
+    result_keys:
+    - wp_dispatch_schemas_pass
+    artifacts: []
+- package_id: wp-posture
+  title: Posture digest, provenance, scoped auto
+  task_type: implementation
+  description: Tasks 3.1-3.3. posture_digest, unscoped fallback, provenance and scope on gate decisions;
+    gate-decision/gate-request/trust-posture schemas.
+  role: implementer
+  priority: 1
+  depends_on: []
+  locks:
+    files:
+    - skills/shared/trust_posture.py
+    - skills/shared/approval_gate.py
+    - openspec/schemas/trust-posture.schema.json
+    - openspec/schemas/gate-decision.schema.json
+    - openspec/schemas/gate-request.schema.json
+    - TRUST_POSTURE.template.md
+    - skills/tests/shared/test_trust_posture_scope.py
+    - skills/tests/shared/test_approval_gate_provenance.py
+    keys:
+    - contract:gate-decision
+    - contract:trust-posture
+    - feature:dispatch-contract:posture
+    ttl_minutes: 120
+    reason: Posture digest, provenance, scoped auto
+  scope:
+    write_allow:
+    - skills/shared/trust_posture.py
+    - skills/shared/approval_gate.py
+    - openspec/schemas/trust-posture.schema.json
+    - openspec/schemas/gate-decision.schema.json
+    - openspec/schemas/gate-request.schema.json
+    - TRUST_POSTURE.template.md
+    - skills/tests/shared/test_trust_posture_scope.py
+    - skills/tests/shared/test_approval_gate_provenance.py
+    read_allow:
+    - '**'
+  worktree:
+    name: dispatch-contract-wp-posture
+    mode: isolated
+  timeout_minutes: 90
+  retry_budget: 2
+  min_trust_level: 2
+  verification:
+    tier_required: B
+    steps:
+    - name: wp-posture tests
+      kind: command
+      command: skills/.venv/bin/python -m pytest skills/tests/shared/test_trust_posture_scope.py skills/tests/shared/test_approval_gate_provenance.py
+        skills/shared/tests -q
+      cwd: .
+      expect_exit_code: 0
+      evidence:
+        artifacts: []
+        result_keys:
+        - wp_posture_pass
+  metadata:
+    loc_estimate: 350
+    complexity: medium
+    package_kind: algorithm
+  inputs: {}
+  outputs:
+    result_keys:
+    - wp_posture_pass
+    artifacts: []
+- package_id: wp-contract-lib
+  title: shared/dispatch_contract.py
+  task_type: implementation
+  description: Tasks 4.1-4.2. Schema loader/validator, v1 upgrade, loop-state mapping, slug, launch-marker
+    reader.
+  role: implementer
+  priority: 2
+  depends_on:
+  - wp-dispatch-schemas
+  locks:
+    files:
+    - skills/shared/dispatch_contract.py
+    - skills/shared/environment_profile.py
+    - skills/tests/shared/test_dispatch_contract.py
+    - skills/tests/shared/test_environment_profile_host_id.py
+    keys:
+    - feature:dispatch-contract:contractlib
+    ttl_minutes: 120
+    reason: shared/dispatch_contract.py
+  scope:
+    write_allow:
+    - skills/shared/dispatch_contract.py
+    - skills/shared/environment_profile.py
+    - skills/tests/shared/test_dispatch_contract.py
+    - skills/tests/shared/test_environment_profile_host_id.py
+    - skills/tests/shared/fixtures/dispatch_contract/**
+    read_allow:
+    - '**'
+  worktree:
+    name: dispatch-contract-wp-contract-lib
+    mode: isolated
+  timeout_minutes: 90
+  retry_budget: 2
+  min_trust_level: 2
+  verification:
+    tier_required: B
+    steps:
+    - name: wp-contract-lib tests
+      kind: command
+      command: skills/.venv/bin/python -m pytest skills/tests/shared/test_dispatch_contract.py skills/tests/shared/test_environment_profile_host_id.py
+        -q
+      cwd: .
+      expect_exit_code: 0
+      evidence:
+        artifacts: []
+        result_keys:
+        - wp_contract_lib_pass
+  metadata:
+    loc_estimate: 400
+    complexity: medium
+    package_kind: algorithm
+  inputs: {}
+  outputs:
+    result_keys:
+    - wp_contract_lib_pass
+    artifacts: []
+- package_id: wp-runtime-ledger
+  title: Checkpoint attempt shape and orchestrator
+  task_type: implementation
+  description: Tasks 5.1-5.3. launch_digest, host-portable isolation, legacy migration, orchestrator prepare/apply
+    on the contract.
+  role: implementer
+  priority: 3
+  depends_on:
+  - wp-contract-lib
+  locks:
+    files:
+    - skills/roadmap-runtime/scripts/models.py
+    - skills/roadmap-runtime/scripts/checkpoint.py
+    - skills/autopilot-roadmap/scripts/orchestrator.py
+    - skills/tests/roadmap-runtime/test_delegated_checkpoint.py
+    - skills/tests/roadmap-runtime/test_checkpoint_legacy_migration.py
+    - skills/tests/roadmap-runtime/test_dispatch_scheduler.py
+    - skills/tests/autopilot-roadmap/test_supervised_dispatch_e2e.py
+    - skills/tests/roadmap-runtime/test_readiness.py
+    - skills/tests/autopilot-roadmap/test_supervised_dispatch.py
+    keys:
+    - feature:dispatch-contract:ledger
+    ttl_minutes: 120
+    reason: Checkpoint attempt shape and orchestrator
+  scope:
+    write_allow:
+    - skills/roadmap-runtime/scripts/models.py
+    - skills/roadmap-runtime/scripts/checkpoint.py
+    - skills/autopilot-roadmap/scripts/orchestrator.py
+    - skills/tests/roadmap-runtime/test_delegated_checkpoint.py
+    - skills/tests/roadmap-runtime/test_checkpoint_legacy_migration.py
+    - skills/tests/roadmap-runtime/test_dispatch_scheduler.py
+    - skills/tests/autopilot-roadmap/test_supervised_dispatch_e2e.py
+    - skills/tests/roadmap-runtime/test_readiness.py
+    - skills/tests/autopilot-roadmap/test_supervised_dispatch.py
+    read_allow:
+    - '**'
+  worktree:
+    name: dispatch-contract-wp-runtime-ledger
+    mode: isolated
+  timeout_minutes: 90
+  retry_budget: 2
+  min_trust_level: 2
+  verification:
+    tier_required: B
+    steps:
+    - name: wp-runtime-ledger tests
+      kind: command
+      command: skills/.venv/bin/python -m pytest skills/tests/roadmap-runtime skills/tests/autopilot-roadmap
+        -q
+      cwd: .
+      expect_exit_code: 0
+      evidence:
+        artifacts: []
+        result_keys:
+        - wp_runtime_ledger_pass
+  metadata:
+    loc_estimate: 500
+    complexity: high
+    package_kind: migration
+  inputs: {}
+  outputs:
+    result_keys:
+    - wp_runtime_ledger_pass
+    artifacts: []
+- package_id: wp-autopilot-child
+  title: Loop state v6, emit-result, park, gate re-evaluation
+  task_type: implementation
+  description: Tasks 6.1-6.5. runner.py emit-result/park/record-degradation/gate-answer --approval-ref,
+    gate-check re-evaluation, LoopState v6, autopilot SKILL worker protocol.
+  role: implementer
+  priority: 3
+  depends_on:
+  - wp-contract-lib
+  - wp-posture
+  locks:
+    files:
+    - skills/autopilot/scripts/runner.py
+    - skills/autopilot/scripts/autopilot.py
+    - skills/autopilot/SKILL.md
+    - skills/tests/autopilot/test_emit_result.py
+    - skills/tests/autopilot/test_loop_state_v6.py
+    - skills/tests/autopilot/test_gate_check_reeval.py
+    keys:
+    - feature:dispatch-contract:autopilot
+    ttl_minutes: 120
+    reason: Loop state v6, emit-result, park, gate re-evaluation
+  scope:
+    write_allow:
+    - skills/autopilot/scripts/runner.py
+    - skills/autopilot/scripts/autopilot.py
+    - skills/autopilot/SKILL.md
+    - skills/tests/autopilot/test_emit_result.py
+    - skills/tests/autopilot/test_loop_state_v6.py
+    - skills/tests/autopilot/test_gate_check_reeval.py
+    read_allow:
+    - '**'
+  worktree:
+    name: dispatch-contract-wp-autopilot-child
+    mode: isolated
+  timeout_minutes: 90
+  retry_budget: 2
+  min_trust_level: 2
+  verification:
+    tier_required: B
+    steps:
+    - name: wp-autopilot-child tests
+      kind: command
+      command: skills/.venv/bin/python -m pytest skills/tests/autopilot -q
+      cwd: .
+      expect_exit_code: 0
+      evidence:
+        artifacts: []
+        result_keys:
+        - wp_autopilot_child_pass
+  metadata:
+    loc_estimate: 550
+    complexity: high
+    package_kind: algorithm
+  inputs: {}
+  outputs:
+    result_keys:
+    - wp_autopilot_child_pass
+    artifacts: []
+- package_id: wp-review-honesty
+  title: Dispatchable vendor verification and quorum park
+  task_type: implementation
+  description: Tasks 7.1-7.3. --check-vendors dry invocation and --json; capability_unavailable park in
+    convergence loop.
+  role: implementer
+  priority: 4
+  depends_on:
+  - wp-autopilot-child
+  locks:
+    files:
+    - skills/parallel-infrastructure/scripts/review_dispatcher.py
+    - skills/autopilot/scripts/convergence_loop.py
+    - skills/tests/parallel-infrastructure/test_check_vendors_dispatchable.py
+    - skills/tests/autopilot/test_quorum_park.py
+    keys:
+    - feature:dispatch-contract:review
+    ttl_minutes: 120
+    reason: Dispatchable vendor verification and quorum park
+  scope:
+    write_allow:
+    - skills/parallel-infrastructure/scripts/review_dispatcher.py
+    - skills/autopilot/scripts/convergence_loop.py
+    - skills/tests/parallel-infrastructure/test_check_vendors_dispatchable.py
+    - skills/tests/autopilot/test_quorum_park.py
+    read_allow:
+    - '**'
+  worktree:
+    name: dispatch-contract-wp-review-honesty
+    mode: isolated
+  timeout_minutes: 90
+  retry_budget: 2
+  min_trust_level: 2
+  verification:
+    tier_required: B
+    steps:
+    - name: wp-review-honesty tests
+      kind: command
+      command: skills/.venv/bin/python -m pytest skills/tests/parallel-infrastructure/test_check_vendors_dispatchable.py
+        skills/tests/autopilot/test_quorum_park.py -q
+      cwd: .
+      expect_exit_code: 0
+      evidence:
+        artifacts: []
+        result_keys:
+        - wp_review_honesty_pass
+  metadata:
+    loc_estimate: 300
+    complexity: medium
+    package_kind: algorithm
+  inputs: {}
+  outputs:
+    result_keys:
+    - wp_review_honesty_pass
+    artifacts: []
+- package_id: wp-supervisor
+  title: Execution adapter and gate router
+  task_type: implementation
+  description: Tasks 8.1-8.4. Token verify/rotate/reissue, rebind/reinitialize, execution profile, ANSWER_PATHS,
+    provenance re-evaluation, dedupe escalation, supervise SKILL.
+  role: implementer
+  priority: 4
+  depends_on:
+  - wp-merge-narrow-fix
+  - wp-posture
+  - wp-runtime-ledger
+  locks:
+    files:
+    - skills/supervise/scripts/execution.py
+    - skills/supervise/scripts/gate_router.py
+    - skills/supervise/SKILL.md
+    keys:
+    - feature:dispatch-contract:supervisor
+    ttl_minutes: 120
+    reason: Execution adapter and gate router
+  scope:
+    write_allow:
+    - skills/supervise/scripts/execution.py
+    - skills/supervise/scripts/gate_router.py
+    - skills/supervise/SKILL.md
+    - skills/tests/supervise/test_execution.py
+    - skills/tests/supervise/test_gate_router.py
+    - skills/tests/supervise/test_gate_router_e2e.py
+    - skills/tests/supervise/test_cycle_state.py
+    - skills/tests/supervise/fixtures/execution/**
+    read_allow:
+    - '**'
+  worktree:
+    name: dispatch-contract-wp-supervisor
+    mode: isolated
+  timeout_minutes: 90
+  retry_budget: 2
+  min_trust_level: 2
+  verification:
+    tier_required: B
+    steps:
+    - name: wp-supervisor tests
+      kind: command
+      command: skills/.venv/bin/python -m pytest skills/tests/supervise -q
+      cwd: .
+      expect_exit_code: 0
+      evidence:
+        artifacts: []
+        result_keys:
+        - wp_supervisor_pass
+  metadata:
+    loc_estimate: 700
+    complexity: high
+    package_kind: algorithm
+  inputs: {}
+  outputs:
+    result_keys:
+    - wp_supervisor_pass
+    artifacts: []
+- package_id: wp-integration
+  title: Closure, end-to-end, cross-host, landable fixture
+  task_type: integration
+  description: Tasks 9.1-9.6. Acceptance-outcome tests across packages.
+  role: integrator
+  priority: 5
+  depends_on:
+  - wp-autopilot-child
+  - wp-review-honesty
+  - wp-supervisor
+  locks:
+    files:
+    - skills/tests/supervise/test_dispatch_closure.py
+    - skills/tests/autopilot-roadmap/test_dispatch_contract_e2e.py
+    - skills/tests/roadmap-runtime/test_cross_host_reconcile.py
+    - skills/tests/roadmap-runtime/test_landable_checkpoint.py
+    - skills/tests/roadmap-runtime/fixtures/landable-checkpoint.json
+    keys:
+    - feature:dispatch-contract:integration
+    ttl_minutes: 120
+    reason: Closure, end-to-end, cross-host, landable fixture
+  scope:
+    write_allow:
+    - skills/tests/supervise/test_dispatch_closure.py
+    - skills/tests/autopilot-roadmap/test_dispatch_contract_e2e.py
+    - skills/tests/roadmap-runtime/test_cross_host_reconcile.py
+    - skills/tests/roadmap-runtime/test_landable_checkpoint.py
+    - skills/tests/roadmap-runtime/fixtures/landable-checkpoint.json
+    read_allow:
+    - '**'
+  worktree:
+    name: dispatch-contract-wp-integration
+    mode: isolated
+  timeout_minutes: 90
+  retry_budget: 2
+  min_trust_level: 2
+  verification:
+    tier_required: A
+    steps:
+    - name: wp-integration tests
+      kind: command
+      command: skills/.venv/bin/python -m pytest skills/tests/supervise skills/tests/autopilot skills/tests/autopilot-roadmap
+        skills/tests/roadmap-runtime skills/tests/shared skills/tests/parallel-infrastructure -q
+      cwd: .
+      expect_exit_code: 0
+      evidence:
+        artifacts: []
+        result_keys:
+        - wp_integration_pass
+  metadata:
+    loc_estimate: 500
+    complexity: high
+    package_kind: integration
+  inputs: {}
+  outputs:
+    result_keys:
+    - wp_integration_pass
+    artifacts: []
diff --git a/openspec/contracts/roadmap-orchestration/schemas/delegated-dispatch-attempt.schema.json b/openspec/contracts/roadmap-orchestration/schemas/delegated-dispatch-attempt.schema.json
index 8426404..a3c1b55 100644
--- a/openspec/contracts/roadmap-orchestration/schemas/delegated-dispatch-attempt.schema.json
+++ b/openspec/contracts/roadmap-orchestration/schemas/delegated-dispatch-attempt.schema.json
@@ -2,6 +2,7 @@
   "$schema": "https://json-schema.org/draft/2020-12/schema",
   "$id": "https://agentic-coding-tools.dev/contracts/delegated-dispatch-attempt.schema.json",
   "title": "Delegated Dispatch Attempt",
+  "description": "The single definition of a checkpoint delegated dispatch attempt (dispatch-contract D2); openspec/schemas/checkpoint.schema.json dispatch_attempts.items $refs it.",
   "type": "object",
   "additionalProperties": false,
   "required": [
@@ -12,7 +13,7 @@
     "attempt",
     "status",
     "prepared_at",
-    "launch_token",
+    "launch_digest",
     "launch_marker_path",
     "lease_generation",
     "launch_history",
@@ -55,14 +56,13 @@
         "failed"
       ]
     },
-    "launch_token": {
+    "launch_digest": {
       "type": "string",
-      "minLength": 16,
-      "maxLength": 256
+      "pattern": "^sha256:[0-9a-f]{64}$",
+      "description": "sha256 of the current generation's raw launch token; the raw token is never persisted (D6)."
     },
     "launch_marker_path": {
-      "type": "string",
-      "minLength": 1
+      "$ref": "https://agentic-coding-tools.dev/schemas/dispatch-result.schema.json#/$defs/RelativePath"
     },
     "lease_generation": {
       "type": "integer",
@@ -102,29 +102,8 @@
       }
     },
     "isolation": {
-      "type": "object",
-      "additionalProperties": false,
-      "required": [
-        "mode",
-        "worktree_path",
-        "branch"
-      ],
-      "properties": {
-        "mode": {
-          "enum": [
-            "managed_worktree",
-            "harness_provided"
-          ]
-        },
-        "worktree_path": {
-          "type": "string",
-          "minLength": 1
-        },
-        "branch": {
-          "type": "string",
-          "minLength": 1
-        }
-      }
+      "$ref": "https://agentic-coding-tools.dev/schemas/dispatch-request.schema.json#/$defs/Isolation",
+      "description": "Host-portable isolation {mode, worktree_ref, branch, host_id} (D7). Absolute paths exist only in memory."
     },
     "context": {
       "$ref": "./bounded-dispatch-context.schema.json",
@@ -154,7 +133,7 @@
           ]
         },
         "result": {
-          "$ref": "./supervised-dispatch-result.schema.json"
+          "$ref": "https://agentic-coding-tools.dev/schemas/dispatch-result.schema.json"
         },
         "result_digest": {
           "type": "string",
@@ -200,7 +179,9 @@
         "kind": {
           "enum": [
             "pending_gate",
-            "policy_pause"
+            "policy_pause",
+            "permission_blocked",
+            "capability_unavailable"
           ]
         }
       }
@@ -281,12 +262,12 @@
               "parked",
               "quarantined",
               "terminal",
-              "stale_takeover"
+              "stale_takeover",
+              "rebound"
             ]
           },
           "marker_path": {
-            "type": "string",
-            "minLength": 1
+            "$ref": "https://agentic-coding-tools.dev/schemas/dispatch-result.schema.json#/$defs/RelativePath"
           },
           "handle": {
             "type": [
@@ -298,6 +279,9 @@
           "observed_at": {
             "type": "string",
             "format": "date-time"
+          },
+          "host_id": {
+            "$ref": "https://agentic-coding-tools.dev/schemas/dispatch-result.schema.json#/$defs/HostId"
           }
         }
       }
@@ -350,8 +334,7 @@
               "minimum": 1
             },
             "marker_path": {
-              "type": "string",
-              "minLength": 1
+              "$ref": "https://agentic-coding-tools.dev/schemas/dispatch-result.schema.json#/$defs/RelativePath"
             },
             "observed_at": {
               "type": "string",
@@ -362,39 +345,7 @@
       ]
     },
     "parked": {
-      "type": "object",
-      "additionalProperties": false,
-      "required": [
-        "kind",
-        "reason"
-      ],
-      "properties": {
-        "kind": {
-          "enum": [
-            "pending_gate",
-            "policy_pause"
-          ]
-        },
-        "reason": {
-          "type": "string",
-          "minLength": 1,
-          "maxLength": 1024
-        },
-        "gate": {
-          "type": [
-            "string",
-            "null"
-          ],
-          "maxLength": 128
-        },
-        "deadline": {
-          "type": [
-            "string",
-            "null"
-          ],
-          "format": "date-time"
-        }
-      }
+      "$ref": "https://agentic-coding-tools.dev/schemas/dispatch-result.schema.json#/$defs/Parked"
     },
     "handoff_id": {
       "type": [
@@ -485,6 +436,30 @@
           "format": "date-time"
         }
       }
+    },
+    "roadmap_approval_ref": {
+      "$ref": "https://agentic-coding-tools.dev/schemas/dispatch-request.schema.json#/$defs/ApprovalRef",
+      "description": "The roadmap_approval decision prepare verified for this attempt (D8); not a secret."
+    },
+    "needs_rebind": {
+      "type": "boolean",
+      "description": "Set by the legacy reader when an absolute worktree_path lay outside the managed and repo roots (D7)."
+    },
+    "degradations": {
+      "type": "array",
+      "maxItems": 32,
+      "items": {
+        "$ref": "https://agentic-coding-tools.dev/schemas/dispatch-result.schema.json#/$defs/Degradation"
+      },
+      "description": "The applied result's degradations, persisted as outcome metadata (D10)."
+    },
+    "execution_profile": {
+      "$ref": "https://agentic-coding-tools.dev/schemas/dispatch-request.schema.json#/$defs/ExecutionProfile",
+      "description": "The supervisor-resolved execution profile carried by every generation's request and marker (D10)."
+    },
+    "review_requirements": {
+      "$ref": "https://agentic-coding-tools.dev/schemas/dispatch-request.schema.json#/$defs/ReviewRequirements",
+      "description": "Review quorum requirements carried by every generation's request and marker (D10)."
     }
   },
   "allOf": [
diff --git a/openspec/schemas/checkpoint.schema.json b/openspec/schemas/checkpoint.schema.json
index 8d0f3d1..18dc77b 100644
--- a/openspec/schemas/checkpoint.schema.json
+++ b/openspec/schemas/checkpoint.schema.json
@@ -186,1461 +186,9 @@
     "dispatch_attempts": {
       "type": "array",
       "items": {
-        "$ref": "#/$defs/delegated_dispatch_attempt"
+        "$ref": "https://agentic-coding-tools.dev/contracts/delegated-dispatch-attempt.schema.json"
       },
       "default": []
     }
-  },
-  "$defs": {
-    "delegated_dispatch_attempt": {
-      "type": "object",
-      "additionalProperties": false,
-      "required": [
-        "dispatch_id",
-        "item_id",
-        "change_id",
-        "phase",
-        "attempt",
-        "status",
-        "prepared_at",
-        "launch_token",
-        "launch_marker_path",
-        "lease_generation",
-        "launch_history",
-        "scope",
-        "isolation",
-        "context"
-      ],
-      "properties": {
-        "dispatch_id": {
-          "type": "string",
-          "minLength": 1,
-          "maxLength": 256
-        },
-        "item_id": {
-          "type": "string",
-          "minLength": 1,
-          "maxLength": 128
-        },
-        "change_id": {
-          "type": "string",
-          "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$",
-          "maxLength": 160
-        },
-        "phase": {
-          "const": "autopilot"
-        },
-        "attempt": {
-          "type": "integer",
-          "minimum": 1
-        },
-        "status": {
-          "enum": [
-            "prepared",
-            "claimed",
-            "acknowledged",
-            "launched",
-            "quarantined",
-            "parked",
-            "completed",
-            "failed"
-          ]
-        },
-        "launch_token": {
-          "type": "string",
-          "minLength": 16,
-          "maxLength": 256
-        },
-        "launch_marker_path": {
-          "type": "string",
-          "minLength": 1
-        },
-        "lease_generation": {
-          "type": "integer",
-          "minimum": 1
-        },
-        "scope": {
-          "type": "object",
-          "additionalProperties": false,
-          "required": [
-            "proof",
-            "write_allow",
-            "lock_keys"
-          ],
-          "properties": {
-            "proof": {
-              "enum": [
-                "proven_disjoint",
-                "serial_indeterminate"
-              ]
-            },
-            "write_allow": {
-              "type": "array",
-              "uniqueItems": true,
-              "items": {
-                "type": "string",
-                "minLength": 1
-              }
-            },
-            "lock_keys": {
-              "type": "array",
-              "uniqueItems": true,
-              "items": {
-                "type": "string",
-                "minLength": 1
-              }
-            }
-          }
-        },
-        "isolation": {
-          "type": "object",
-          "additionalProperties": false,
-          "required": [
-            "mode",
-            "worktree_path",
-            "branch"
-          ],
-          "properties": {
-            "mode": {
-              "enum": [
-                "managed_worktree",
-                "harness_provided"
-              ]
-            },
-            "worktree_path": {
-              "type": "string",
-              "minLength": 1
-            },
-            "branch": {
-              "type": "string",
-              "minLength": 1
-            }
-          }
-        },
-        "context": {
-          "$ref": "#/$defs/contextLevel1"
-        },
-        "application_journal": {
-          "type": "object",
-          "additionalProperties": false,
-          "required": [
-            "schema_version",
-            "state",
-            "result",
-            "result_digest",
-            "bound_at"
-          ],
-          "properties": {
-            "schema_version": {
-              "const": 1
-            },
-            "state": {
-              "enum": [
-                "result_bound",
-                "callback_started",
-                "callback_acknowledged",
-                "terminal_persisted",
-                "effects_applied"
-              ]
-            },
-            "result": {
-              "type": "object",
-              "additionalProperties": false,
-              "required": [
-                "schema_version",
-                "dispatch_id",
-                "change_id",
-                "attempt",
-                "lease_generation",
-                "outcome"
-              ],
-              "properties": {
-                "schema_version": {
-                  "const": 1
-                },
-                "dispatch_id": {
-                  "type": "string",
-                  "minLength": 1,
-                  "maxLength": 256
-                },
-                "change_id": {
-                  "type": "string",
-                  "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$",
-                  "maxLength": 160
-                },
-                "outcome": {
-                  "type": "string",
-                  "pattern": "^(success|failed:.+|vendor_limit:[^:]+:.+|parked)$",
-                  "maxLength": 1024
-                },
-                "replan": {
-                  "type": "boolean",
-                  "default": false
-                },
-                "handoff_id": {
-                  "type": [
-                    "string",
-                    "null"
-                  ],
-                  "maxLength": 256
-                },
-                "worktree_path": {
-                  "type": "string",
-                  "minLength": 1
-                },
-                "branch": {
-                  "type": "string",
-                  "minLength": 1
-                },
-                "parked": {
-                  "type": "object",
-                  "additionalProperties": false,
-                  "required": [
-                    "kind",
-                    "reason"
-                  ],
-                  "properties": {
-                    "kind": {
-                      "enum": [
-                        "pending_gate",
-                        "policy_pause"
-                      ]
-                    },
-                    "reason": {
-                      "type": "string",
-                      "minLength": 1,
-                      "maxLength": 1024
-                    },
-                    "gate": {
-                      "type": [
-                        "string",
-                        "null"
-                      ],
-                      "maxLength": 128
-                    },
-                    "deadline": {
-                      "type": [
-                        "string",
-                        "null"
-                      ],
-                      "format": "date-time"
-                    },
-                    "resume_hint": {
-                      "type": [
-                        "string",
-                        "null"
-                      ],
-                      "maxLength": 512
-                    }
-                  }
-                },
-                "evidence": {
-                  "type": "object",
-                  "additionalProperties": false,
-                  "properties": {
-                    "loop_state_path": {
-                      "type": "string",
-                      "minLength": 1
-                    },
-                    "commit": {
-                      "type": "string",
-                      "pattern": "^[0-9a-f]{40}$"
-                    },
-                    "loop_state_digest": {
-                      "type": "string",
-                      "pattern": "^[0-9a-f]{64}$"
-                    }
-                  },
-                  "required": [
-                    "loop_state_path",
-                    "commit",
-                    "loop_state_digest"
-                  ]
-                },
-                "attempt": {
-                  "type": "integer",
-                  "minimum": 1
-                },
-                "lease_generation": {
-                  "type": "integer",
-                  "minimum": 1
-                }
-              },
-              "allOf": [
-                {
-                  "if": {
-                    "properties": {
-                      "outcome": {
-                        "const": "success"
-                      }
-                    },
-                    "required": [
-                      "outcome"
-                    ]
-                  },
-                  "then": {
-                    "required": [
-                      "handoff_id",
-                      "worktree_path",
-                      "branch",
-                      "evidence"
-                    ],
-                    "properties": {
-                      "handoff_id": {
-                        "type": "string",
-                        "minLength": 1,
-                        "maxLength": 256
-                      }
-                    }
-                  }
-                },
-                {
-                  "if": {
-                    "properties": {
-                      "outcome": {
-                        "const": "parked"
-                      }
-                    },
-                    "required": [
-                      "outcome"
-                    ]
-                  },
-                  "then": {
-                    "required": [
-                      "parked",
-                      "worktree_path",
-                      "branch",
-                      "evidence"
-                    ]
-                  }
-                },
-                {
-                  "if": {
-                    "properties": {
-                      "outcome": {
-                        "not": {
-                          "const": "parked"
-                        }
-                      }
-                    },
-                    "required": [
-                      "outcome"
-                    ]
-                  },
-                  "then": {
-                    "not": {
-                      "required": [
-                        "parked"
-                      ]
-                    }
-                  }
-                }
-              ]
-            },
-            "result_digest": {
-              "type": "string",
-              "pattern": "^[0-9a-f]{64}$"
-            },
-            "bound_at": {
-              "type": "string",
-              "format": "date-time"
-            },
-            "callback_started_at": {
-              "type": "string",
-              "format": "date-time"
-            },
-            "callback_acknowledged_at": {
-              "type": "string",
-              "format": "date-time"
-            },
-            "terminal_persisted_at": {
-              "type": "string",
-              "format": "date-time"
-            },
-            "effects_applied_at": {
-              "type": "string",
-              "format": "date-time"
-            }
-          }
-        },
-        "continuation": {
-          "type": "object",
-          "additionalProperties": false,
-          "required": [
-            "kind",
-            "approval_ref"
-          ],
-          "properties": {
-            "approval_ref": {
-              "type": "string",
-              "minLength": 1,
-              "maxLength": 256
-            },
-            "kind": {
-              "enum": [
-                "pending_gate",
-                "policy_pause"
-              ]
-            }
-          }
-        },
-        "lease": {
-          "type": "object",
-          "additionalProperties": false,
-          "required": [
-            "generation",
-            "owner_nonce",
-            "state",
-            "acquired_at",
-            "heartbeat_at",
-            "expires_at"
-          ],
-          "properties": {
-            "generation": {
-              "type": "integer",
-              "minimum": 1
-            },
-            "owner_nonce": {
-              "type": "string",
-              "minLength": 16,
-              "maxLength": 256
-            },
-            "state": {
-              "enum": [
-                "active",
-                "released",
-                "expired",
-                "uncertain"
-              ]
-            },
-            "acquired_at": {
-              "type": "string",
-              "format": "date-time"
-            },
-            "heartbeat_at": {
-              "type": "string",
-              "format": "date-time"
-            },
-            "expires_at": {
-              "type": "string",
-              "format": "date-time"
-            }
-          }
-        },
-        "launch_history": {
-          "type": "array",
-          "maxItems": 64,
-          "items": {
-            "type": "object",
-            "additionalProperties": false,
-            "required": [
-              "generation",
-              "owner_nonce",
-              "state",
-              "marker_path",
-              "observed_at"
-            ],
-            "properties": {
-              "generation": {
-                "type": "integer",
-                "minimum": 1
-              },
-              "owner_nonce": {
-                "type": "string",
-                "minLength": 16,
-                "maxLength": 256
-              },
-              "state": {
-                "enum": [
-                  "claimed",
-                  "acknowledged",
-                  "go_released",
-                  "entered",
-                  "heartbeat",
-                  "parked",
-                  "quarantined",
-                  "terminal",
-                  "stale_takeover"
-                ]
-              },
-              "marker_path": {
-                "type": "string",
-                "minLength": 1
-              },
-              "handle": {
-                "type": [
-                  "string",
-                  "null"
-                ],
-                "maxLength": 256
-              },
-              "observed_at": {
-                "type": "string",
-                "format": "date-time"
-              }
-            }
-          }
-        },
-        "launch_evidence": {
-          "oneOf": [
-            {
-              "type": "object",
-              "additionalProperties": false,
-              "required": [
-                "kind",
-                "generation",
-                "handle",
-                "observed_at"
-              ],
-              "properties": {
-                "kind": {
-                  "const": "host_ack"
-                },
-                "generation": {
-                  "type": "integer",
-                  "minimum": 1
-                },
-                "handle": {
-                  "type": "string",
-                  "minLength": 1,
-                  "maxLength": 256
-                },
-                "observed_at": {
-                  "type": "string",
-                  "format": "date-time"
-                }
-              }
-            },
-            {
-              "type": "object",
-              "additionalProperties": false,
-              "required": [
-                "kind",
-                "generation",
-                "marker_path",
-                "observed_at"
-              ],
-              "properties": {
-                "kind": {
-                  "const": "child_marker"
-                },
-                "generation": {
-                  "type": "integer",
-                  "minimum": 1
-                },
-                "marker_path": {
-                  "type": "string",
-                  "minLength": 1
-                },
-                "observed_at": {
-                  "type": "string",
-                  "format": "date-time"
-                }
-              }
-            }
-          ]
-        },
-        "parked": {
-          "type": "object",
-          "additionalProperties": false,
-          "required": [
-            "kind",
-            "reason"
-          ],
-          "properties": {
-            "kind": {
-              "enum": [
-                "pending_gate",
-                "policy_pause"
-              ]
-            },
-            "reason": {
-              "type": "string",
-              "minLength": 1,
-              "maxLength": 1024
-            },
-            "gate": {
-              "type": [
-                "string",
-                "null"
-              ],
-              "maxLength": 128
-            },
-            "deadline": {
-              "type": [
-                "string",
-                "null"
-              ],
-              "format": "date-time"
-            },
-            "resume_hint": {
-              "type": [
-                "string",
-                "null"
-              ],
-              "maxLength": 512
-            }
-          }
-        },
-        "handoff_id": {
-          "type": [
-            "string",
-            "null"
-          ],
-          "maxLength": 256
-        },
-        "outcome": {
-          "type": [
-            "string",
-            "null"
-          ],
-          "pattern": "^(success|failed:.+|vendor_limit:[^:]+:.+|parked)$",
-          "maxLength": 1024
-        },
-        "prepared_at": {
-          "type": "string",
-          "format": "date-time"
-        },
-        "resolved_at": {
-          "type": [
-            "string",
-            "null"
-          ],
-          "format": "date-time"
-        },
-        "quarantine": {
-          "type": "object",
-          "additionalProperties": false,
-          "required": [
-            "kind",
-            "reason"
-          ],
-          "properties": {
-            "kind": {
-              "const": "unknown_liveness"
-            },
-            "reason": {
-              "type": "string",
-              "minLength": 1,
-              "maxLength": 1024
-            },
-            "observed_at": {
-              "type": "string",
-              "format": "date-time"
-            }
-          }
-        },
-        "launch_gate": {
-          "type": "object",
-          "additionalProperties": false,
-          "required": [
-            "generation",
-            "state"
-          ],
-          "properties": {
-            "generation": {
-              "type": "integer",
-              "minimum": 1
-            },
-            "state": {
-              "enum": [
-                "waiting_ack",
-                "go_released",
-                "entered"
-              ]
-            },
-            "handle": {
-              "type": [
-                "string",
-                "null"
-              ],
-              "maxLength": 256
-            },
-            "go_released_at": {
-              "type": [
-                "string",
-                "null"
-              ],
-              "format": "date-time"
-            },
-            "entered_at": {
-              "type": [
-                "string",
-                "null"
-              ],
-              "format": "date-time"
-            }
-          }
-        }
-      },
-      "allOf": [
-        {
-          "if": {
-            "properties": {
-              "scope": {
-                "properties": {
-                  "proof": {
-                    "const": "proven_disjoint"
-                  }
-                },
-                "required": [
-                  "proof"
-                ]
-              }
-            },
-            "required": [
-              "scope"
-            ]
-          },
-          "then": {
-            "properties": {
-              "scope": {
-                "properties": {
-                  "write_allow": {
-                    "minItems": 1
-                  }
-                }
-              }
-            }
-          }
-        },
-        {
-          "if": {
-            "properties": {
-              "status": {
-                "const": "prepared"
-              }
-            },
-            "required": [
-              "status"
-            ]
-          },
-          "then": {
-            "properties": {
-              "outcome": {
-                "type": "null"
-              },
-              "resolved_at": {
-                "type": "null"
-              }
-            },
-            "not": {
-              "anyOf": [
-                {
-                  "required": [
-                    "parked"
-                  ]
-                },
-                {
-                  "required": [
-                    "lease"
-                  ]
-                },
-                {
-                  "required": [
-                    "launch_evidence"
-                  ]
-                },
-                {
-                  "required": [
-                    "launch_gate"
-                  ]
-                }
-              ]
-            }
-          }
-        },
-        {
-          "if": {
-            "properties": {
-              "status": {
-                "const": "claimed"
-              }
-            },
-            "required": [
-              "status"
-            ]
-          },
-          "then": {
-            "required": [
-              "launch_evidence",
-              "lease",
-              "launch_gate"
-            ],
-            "properties": {
-              "lease": {
-                "properties": {
-                  "state": {
-                    "const": "active"
-                  }
-                }
-              },
-              "launch_gate": {
-                "properties": {
-                  "state": {
-                    "const": "waiting_ack"
-                  },
-                  "handle": {
-                    "type": "null"
-                  },
-                  "go_released_at": {
-                    "type": "null"
-                  },
-                  "entered_at": {
-                    "type": "null"
-                  }
-                }
-              },
-              "outcome": {
-                "type": "null"
-              },
-              "resolved_at": {
-                "type": "null"
-              },
-              "launch_evidence": {
-                "properties": {
-                  "kind": {
-                    "const": "child_marker"
-                  }
-                }
-              }
-            },
-            "not": {
-              "anyOf": [
-                {
-                  "required": [
-                    "parked"
-                  ]
-                },
-                {
-                  "required": [
-                    "quarantine"
-                  ]
-                }
-              ]
-            }
-          }
-        },
-        {
-          "if": {
-            "properties": {
-              "status": {
-                "const": "launched"
-              }
-            },
-            "required": [
-              "status"
-            ]
-          },
-          "then": {
-            "required": [
-              "launch_evidence",
-              "lease",
-              "launch_gate"
-            ],
-            "properties": {
-              "lease": {
-                "properties": {
-                  "state": {
-                    "const": "active"
-                  }
-                }
-              },
-              "launch_gate": {
-                "properties": {
-                  "state": {
-                    "const": "entered"
-                  },
-                  "handle": {
-                    "type": "string",
-                    "minLength": 1,
-                    "maxLength": 256
-                  },
-                  "go_released_at": {
-                    "type": "string",
-                    "format": "date-time"
-                  },
-                  "entered_at": {
-                    "type": "string",
-                    "format": "date-time"
-                  }
-                },
-                "required": [
-                  "handle",
-                  "go_released_at",
-                  "entered_at"
-                ]
-              },
-              "outcome": {
-                "type": "null"
-              },
-              "resolved_at": {
-                "type": "null"
-              },
-              "launch_evidence": {
-                "properties": {
-                  "kind": {
-                    "const": "host_ack"
-                  }
-                }
-              }
-            },
-            "not": {
-              "anyOf": [
-                {
-                  "required": [
-                    "parked"
-                  ]
-                },
-                {
-                  "required": [
-                    "quarantine"
-                  ]
-                }
-              ]
-            }
-          }
-        },
-        {
-          "if": {
-            "properties": {
-              "status": {
-                "const": "quarantined"
-              }
-            },
-            "required": [
-              "status"
-            ]
-          },
-          "then": {
-            "required": [
-              "launch_evidence",
-              "lease",
-              "launch_gate",
-              "quarantine"
-            ],
-            "properties": {
-              "lease": {
-                "properties": {
-                  "state": {
-                    "const": "uncertain"
-                  }
-                }
-              },
-              "outcome": {
-                "type": "null"
-              },
-              "resolved_at": {
-                "type": "null"
-              },
-              "launch_evidence": {
-                "properties": {
-                  "kind": {
-                    "const": "host_ack"
-                  }
-                }
-              },
-              "launch_gate": {
-                "required": [
-                  "handle",
-                  "go_released_at"
-                ],
-                "properties": {
-                  "state": {
-                    "enum": [
-                      "go_released",
-                      "entered"
-                    ]
-                  },
-                  "handle": {
-                    "type": "string",
-                    "minLength": 1,
-                    "maxLength": 256
-                  },
-                  "go_released_at": {
-                    "type": "string",
-                    "format": "date-time"
-                  }
-                }
-              }
-            },
-            "not": {
-              "required": [
-                "parked"
-              ]
-            }
-          }
-        },
-        {
-          "if": {
-            "properties": {
-              "status": {
-                "const": "parked"
-              }
-            },
-            "required": [
-              "status"
-            ]
-          },
-          "then": {
-            "required": [
-              "parked",
-              "outcome",
-              "resolved_at",
-              "launch_evidence",
-              "lease",
-              "launch_gate"
-            ],
-            "properties": {
-              "outcome": {
-                "const": "parked"
-              },
-              "lease": {
-                "properties": {
-                  "state": {
-                    "const": "released"
-                  }
-                }
-              },
-              "launch_gate": {
-                "properties": {
-                  "state": {
-                    "const": "entered"
-                  },
-                  "handle": {
-                    "type": "string",
-                    "minLength": 1,
-                    "maxLength": 256
-                  },
-                  "go_released_at": {
-                    "type": "string",
-                    "format": "date-time"
-                  },
-                  "entered_at": {
-                    "type": "string",
-                    "format": "date-time"
-                  }
-                },
-                "required": [
-                  "handle",
-                  "go_released_at",
-                  "entered_at"
-                ]
-              },
-              "launch_evidence": {
-                "properties": {
-                  "kind": {
-                    "const": "host_ack"
-                  }
-                }
-              }
-            },
-            "not": {
-              "required": [
-                "quarantine"
-              ]
-            }
-          }
-        },
-        {
-          "if": {
-            "properties": {
-              "status": {
-                "const": "completed"
-              }
-            },
-            "required": [
-              "status"
-            ]
-          },
-          "then": {
-            "required": [
-              "outcome",
-              "resolved_at",
-              "handoff_id",
-              "launch_evidence",
-              "lease",
-              "launch_gate"
-            ],
-            "properties": {
-              "outcome": {
-                "const": "success"
-              },
-              "handoff_id": {
-                "type": "string",
-                "minLength": 1,
-                "maxLength": 256
-              },
-              "lease": {
-                "properties": {
-                  "state": {
-                    "const": "released"
-                  }
-                }
-              },
-              "launch_gate": {
-                "properties": {
-                  "state": {
-                    "const": "entered"
-                  },
-                  "handle": {
-                    "type": "string",
-                    "minLength": 1,
-                    "maxLength": 256
-                  },
-                  "go_released_at": {
-                    "type": "string",
-                    "format": "date-time"
-                  },
-                  "entered_at": {
-                    "type": "string",
-                    "format": "date-time"
-                  }
-                },
-                "required": [
-                  "handle",
-                  "go_released_at",
-                  "entered_at"
-                ]
-              },
-              "launch_evidence": {
-                "properties": {
-                  "kind": {
-                    "const": "host_ack"
-                  }
-                }
-              }
-            },
-            "not": {
-              "anyOf": [
-                {
-                  "required": [
-                    "parked"
-                  ]
-                },
-                {
-                  "required": [
-                    "quarantine"
-                  ]
-                }
-              ]
-            }
-          }
-        },
-        {
-          "if": {
-            "properties": {
-              "status": {
-                "const": "failed"
-              }
-            },
-            "required": [
-              "status"
-            ]
-          },
-          "then": {
-            "required": [
-              "outcome",
-              "resolved_at"
-            ],
-            "properties": {
-              "outcome": {
-                "type": "string",
-                "pattern": "^(failed:.+|vendor_limit:[^:]+:.+)$"
-              },
-              "lease": {
-                "properties": {
-                  "state": {
-                    "enum": [
-                      "released",
-                      "expired"
-                    ]
-                  }
-                }
-              }
-            },
-            "not": {
-              "anyOf": [
-                {
-                  "required": [
-                    "parked"
-                  ]
-                },
-                {
-                  "required": [
-                    "quarantine"
-                  ]
-                }
-              ]
-            }
-          }
-        },
-        {
-          "if": {
-            "required": [
-              "continuation"
-            ]
-          },
-          "then": {
-            "properties": {
-              "status": {
-                "enum": [
-                  "prepared",
-                  "claimed",
-                  "acknowledged",
-                  "launched",
-                  "quarantined"
-                ]
-              },
-              "lease_generation": {
-                "minimum": 2
-              }
-            }
-          }
-        },
-        {
-          "if": {
-            "properties": {
-              "status": {
-                "not": {
-                  "const": "quarantined"
-                }
-              }
-            },
-            "required": [
-              "status"
-            ]
-          },
-          "then": {
-            "not": {
-              "required": [
-                "quarantine"
-              ]
-            }
-          }
-        },
-        {
-          "if": {
-            "properties": {
-              "status": {
-                "const": "acknowledged"
-              }
-            },
-            "required": [
-              "status"
-            ]
-          },
-          "then": {
-            "required": [
-              "launch_evidence",
-              "lease",
-              "launch_gate"
-            ],
-            "properties": {
-              "launch_evidence": {
-                "properties": {
-                  "kind": {
-                    "const": "host_ack"
-                  }
-                }
-              },
-              "lease": {
-                "properties": {
-                  "state": {
-                    "const": "active"
-                  }
-                }
-              },
-              "launch_gate": {
-                "required": [
-                  "handle",
-                  "go_released_at"
-                ],
-                "properties": {
-                  "state": {
-                    "const": "go_released"
-                  },
-                  "handle": {
-                    "type": "string",
-                    "minLength": 1,
-                    "maxLength": 256
-                  },
-                  "go_released_at": {
-                    "type": "string",
-                    "format": "date-time"
-                  },
-                  "entered_at": {
-                    "type": "null"
-                  }
-                }
-              },
-              "outcome": {
-                "type": "null"
-              },
-              "resolved_at": {
-                "type": "null"
-              }
-            },
-            "not": {
-              "anyOf": [
-                {
-                  "required": [
-                    "parked"
-                  ]
-                },
-                {
-                  "required": [
-                    "quarantine"
-                  ]
-                }
-              ]
-            }
-          }
-        },
-        {
-          "if": {
-            "properties": {
-              "launch_gate": {
-                "properties": {
-                  "state": {
-                    "const": "entered"
-                  }
-                },
-                "required": [
-                  "state"
-                ]
-              }
-            },
-            "required": [
-              "launch_gate"
-            ]
-          },
-          "then": {
-            "properties": {
-              "launch_gate": {
-                "required": [
-                  "entered_at"
-                ],
-                "properties": {
-                  "entered_at": {
-                    "type": "string",
-                    "format": "date-time"
-                  }
-                }
-              }
-            }
-          }
-        }
-      ]
-    },
-    "key": {
-      "type": "string",
-      "minLength": 1,
-      "maxLength": 64,
-      "not": {
-        "pattern": "([Ss][Ee][Cc][Rr][Ee][Tt]|[Tt][Oo][Kk][Ee][Nn]|[Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]|[Cc][Rr][Ee][Dd][Ee][Nn][Tt][Ii][Aa][Ll]|[Aa][Pp][Ii][_-]?[Kk][Ee][Yy]|[Pp][Rr][Ii][Vv][Aa][Tt][Ee][_-]?[Kk][Ee][Yy]|[Aa][Uu][Tt][Hh]|[Cc][Oo][Oo][Kk][Ii][Ee]|[Rr][Aa][Ww][_-]?[Rr][Ee][Ss][Pp][Oo][Nn][Ss][Ee]|[Tt][Rr][Aa][Nn][Ss][Cc][Rr][Ii][Pp][Tt])"
-      }
-    },
-    "scalar": {
-      "oneOf": [
-        {
-          "type": "string",
-          "maxLength": 4096
-        },
-        {
-          "type": "number"
-        },
-        {
-          "type": "boolean"
-        },
-        {
-          "type": "null"
-        }
-      ]
-    },
-    "scalarArray": {
-      "type": "array",
-      "maxItems": 64,
-      "items": {
-        "$ref": "#/$defs/scalar"
-      }
-    },
-    "contextLevel4": {
-      "type": "object",
-      "maxProperties": 32,
-      "propertyNames": {
-        "$ref": "#/$defs/key"
-      },
-      "additionalProperties": {
-        "oneOf": [
-          {
-            "$ref": "#/$defs/scalar"
-          },
-          {
-            "$ref": "#/$defs/scalarArray"
-          }
-        ]
-      }
-    },
-    "contextLevel3": {
-      "type": "object",
-      "maxProperties": 32,
-      "propertyNames": {
-        "$ref": "#/$defs/key"
-      },
-      "additionalProperties": {
-        "oneOf": [
-          {
-            "$ref": "#/$defs/scalar"
-          },
-          {
-            "$ref": "#/$defs/scalarArray"
-          },
-          {
-            "$ref": "#/$defs/contextLevel4"
-          }
-        ]
-      }
-    },
-    "contextLevel2": {
-      "type": "object",
-      "maxProperties": 32,
-      "propertyNames": {
-        "$ref": "#/$defs/key"
-      },
-      "additionalProperties": {
-        "oneOf": [
-          {
-            "$ref": "#/$defs/scalar"
-          },
-          {
-            "$ref": "#/$defs/scalarArray"
-          },
-          {
-            "$ref": "#/$defs/contextLevel3"
-          }
-        ]
-      }
-    },
-    "contextLevel1": {
-      "type": "object",
-      "maxProperties": 32,
-      "propertyNames": {
-        "$ref": "#/$defs/key"
-      },
-      "additionalProperties": {
-        "oneOf": [
-          {
-            "$ref": "#/$defs/scalar"
-          },
-          {
-            "$ref": "#/$defs/scalarArray"
-          },
-          {
-            "$ref": "#/$defs/contextLevel2"
-          }
-        ]
-      }
-    }
   }
 }
diff --git a/openspec/schemas/dispatch-request.schema.json b/openspec/schemas/dispatch-request.schema.json
new file mode 100644
index 0000000..6267f2a
--- /dev/null
+++ b/openspec/schemas/dispatch-request.schema.json
@@ -0,0 +1,226 @@
+{
+  "$schema": "https://json-schema.org/draft/2020-12/schema",
+  "$id": "https://agentic-coding-tools.dev/schemas/dispatch-request.schema.json",
+  "title": "Dispatch Request (v2)",
+  "description": "The only definition of the request the supervisor hands a host to launch one delegated child Autopilot generation (dispatch-contract D1, D6, D7, D8, D10). The raw launch_token exists only here; the checkpoint stores its launch_digest. Version-1 requests are validated against openspec/contracts/roadmap-orchestration/schemas/supervised-dispatch-request.schema.json and upgraded in memory.",
+  "type": "object",
+  "additionalProperties": false,
+  "required": [
+    "schema_version",
+    "dispatch_id",
+    "roadmap_id",
+    "item_id",
+    "change_id",
+    "phase",
+    "attempt",
+    "launch_token",
+    "lease_generation",
+    "launch_marker_path",
+    "scope",
+    "isolation",
+    "context",
+    "execution_profile",
+    "review_requirements",
+    "roadmap_approval_ref"
+  ],
+  "properties": {
+    "schema_version": {"const": 2},
+    "dispatch_id": {"type": "string", "minLength": 1, "maxLength": 256},
+    "roadmap_id": {"type": "string", "minLength": 1, "maxLength": 128},
+    "item_id": {"type": "string", "minLength": 1, "maxLength": 128},
+    "change_id": {
+      "type": "string",
+      "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$",
+      "maxLength": 160
+    },
+    "phase": {"const": "autopilot"},
+    "attempt": {"type": "integer", "minimum": 1},
+    "launch_token": {
+      "type": "string",
+      "minLength": 16,
+      "maxLength": 256,
+      "description": "Raw per-generation launch nonce. Never persisted; child_start compares sha256(token) with the checkpoint's launch_digest."
+    },
+    "lease_generation": {"type": "integer", "minimum": 1},
+    "launch_marker_path": {
+      "$ref": "https://agentic-coding-tools.dev/schemas/dispatch-result.schema.json#/$defs/RelativePath"
+    },
+    "scope": {
+      "type": "object",
+      "additionalProperties": false,
+      "required": ["proof", "write_allow", "lock_keys"],
+      "properties": {
+        "proof": {"enum": ["proven_disjoint", "serial_indeterminate"]},
+        "write_allow": {
+          "type": "array",
+          "uniqueItems": true,
+          "items": {"type": "string", "minLength": 1}
+        },
+        "lock_keys": {
+          "type": "array",
+          "uniqueItems": true,
+          "items": {"type": "string", "minLength": 1}
+        }
+      }
+    },
+    "isolation": {"$ref": "#/$defs/Isolation"},
+    "context": {
+      "$ref": "https://agentic-coding-tools.dev/contracts/bounded-dispatch-context.schema.json",
+      "description": "Shared recursively bounded secret-free context; runtime also enforces canonical JSON at most 16 KiB."
+    },
+    "execution_profile": {"$ref": "#/$defs/ExecutionProfile"},
+    "review_requirements": {"$ref": "#/$defs/ReviewRequirements"},
+    "roadmap_approval_ref": {
+      "oneOf": [
+        {"$ref": "#/$defs/ApprovalRef"},
+        {"type": "null"}
+      ],
+      "description": "The roadmap_approval decision prepare verified; null only for an upgraded version-1 request."
+    },
+    "continuation": {
+      "type": "object",
+      "additionalProperties": false,
+      "required": ["kind", "approval_ref"],
+      "properties": {
+        "approval_ref": {"$ref": "#/$defs/ApprovalRef"},
+        "kind": {
+          "enum": ["pending_gate", "policy_pause", "permission_blocked", "capability_unavailable"]
+        }
+      }
+    },
+    "gate_answer": {"$ref": "#/$defs/GateAnswer"}
+  },
+  "allOf": [
+    {
+      "if": {
+        "properties": {"scope": {"properties": {"proof": {"const": "proven_disjoint"}}, "required": ["proof"]}},
+        "required": ["scope"]
+      },
+      "then": {"properties": {"scope": {"properties": {"write_allow": {"minItems": 1}}}}}
+    },
+    {
+      "if": {"required": ["continuation"]},
+      "then": {"properties": {"lease_generation": {"minimum": 2}}}
+    },
+    {
+      "if": {"required": ["gate_answer"]},
+      "then": {"required": ["continuation"]}
+    }
+  ],
+  "$defs": {
+    "ApprovalRef": {
+      "type": "string",
+      "maxLength": 256,
+      "pattern": "^gate-decision:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
+    },
+    "Isolation": {
+      "type": "object",
+      "additionalProperties": false,
+      "required": ["mode", "worktree_ref", "branch", "host_id"],
+      "properties": {
+        "mode": {"enum": ["managed_worktree", "harness_provided"]},
+        "worktree_ref": {
+          "$ref": "https://agentic-coding-tools.dev/schemas/dispatch-result.schema.json#/$defs/WorktreeRef"
+        },
+        "branch": {"type": "string", "minLength": 1, "maxLength": 256},
+        "host_id": {
+          "$ref": "https://agentic-coding-tools.dev/schemas/dispatch-result.schema.json#/$defs/HostId"
+        }
+      }
+    },
+    "Lanes": {
+      "type": "array",
+      "maxItems": 32,
+      "uniqueItems": true,
+      "items": {"type": "string", "minLength": 1, "maxLength": 128}
+    },
+    "ExecutionProfile": {
+      "type": "object",
+      "additionalProperties": false,
+      "description": "Supervisor-resolved capabilities (D10). Empty only for an upgraded version-1 request.",
+      "properties": {
+        "lanes": {
+          "type": "object",
+          "additionalProperties": false,
+          "properties": {
+            "review": {"$ref": "#/$defs/Lanes"},
+            "alternative": {"$ref": "#/$defs/Lanes"},
+            "quick": {"$ref": "#/$defs/Lanes"}
+          }
+        },
+        "location": {"type": "string", "minLength": 1, "maxLength": 64},
+        "isolation": {"enum": ["managed_worktree", "harness_provided"]},
+        "probe_command": {
+          "type": "string",
+          "minLength": 1,
+          "maxLength": 512,
+          "description": "The only probe a worker may re-run."
+        }
+      }
+    },
+    "ReviewRequirements": {
+      "type": "object",
+      "additionalProperties": false,
+      "properties": {
+        "min_quorum": {
+          "type": "object",
+          "additionalProperties": false,
+          "properties": {
+            "PLAN_REVIEW": {"type": "integer", "minimum": 1},
+            "IMPL_REVIEW": {"type": "integer", "minimum": 1},
+            "VAL_REVIEW": {"type": "integer", "minimum": 1}
+          }
+        },
+        "counting_lanes": {"$ref": "#/$defs/Lanes"},
+        "quorum_policy": {
+          "type": "object",
+          "additionalProperties": false,
+          "description": "The per-environment quorum policy min_quorum was resolved from, as data (D10): which environment, which policy entry (null for the default quorum) and its sunset condition.",
+          "required": ["environment", "policy_id", "sunset"],
+          "properties": {
+            "environment": {"enum": ["cloud_container", "host"]},
+            "policy_id": {"type": ["string", "null"], "maxLength": 128},
+            "sunset": {"type": ["string", "null"], "maxLength": 512}
+          }
+        }
+      }
+    },
+    "GateAnswer": {
+      "type": "object",
+      "additionalProperties": false,
+      "required": ["gate", "decision", "approval_ref"],
+      "properties": {
+        "gate": {
+          "$ref": "https://agentic-coding-tools.dev/schemas/dispatch-result.schema.json#/$defs/ChildGate"
+        },
+        "decision": {"enum": ["approved", "rejected"]},
+        "approval_ref": {"$ref": "#/$defs/ApprovalRef"},
+        "provenance": {"$ref": "#/$defs/Provenance"}
+      }
+    },
+    "Provenance": {
+      "oneOf": [
+        {
+          "type": "object",
+          "additionalProperties": false,
+          "required": ["source", "posture_digest"],
+          "properties": {
+            "source": {"const": "posture"},
+            "posture_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"}
+          }
+        },
+        {
+          "type": "object",
+          "additionalProperties": false,
+          "required": ["source", "approval_ref"],
+          "properties": {
+            "source": {"const": "human"},
+            "approval_ref": {
+              "oneOf": [{"$ref": "#/$defs/ApprovalRef"}, {"type": "null"}]
+            }
+          }
+        }
+      ]
+    }
+  }
+}
diff --git a/openspec/schemas/dispatch-result.schema.json b/openspec/schemas/dispatch-result.schema.json
new file mode 100644
index 0000000..e7168bc
--- /dev/null
+++ b/openspec/schemas/dispatch-result.schema.json
@@ -0,0 +1,250 @@
+{
+  "$schema": "https://json-schema.org/draft/2020-12/schema",
+  "$id": "https://agentic-coding-tools.dev/schemas/dispatch-result.schema.json",
+  "title": "Dispatch Result (v2)",
+  "description": "The only definition of the result a delegated child Autopilot run returns to the supervisor (dispatch-contract D1-D4, D10). Emitted by `runner.py emit-result` from the committed loop-state.json; version-1 results are validated against openspec/contracts/roadmap-orchestration/schemas/supervised-dispatch-result.schema.json and upgraded in memory by the shared dispatch_contract.upgrade_v1(). Paths are host-portable: no field carries an absolute path.",
+  "type": "object",
+  "additionalProperties": false,
+  "required": [
+    "schema_version",
+    "dispatch_id",
+    "change_id",
+    "attempt",
+    "lease_generation",
+    "outcome",
+    "degradations"
+  ],
+  "properties": {
+    "schema_version": {
+      "const": 2
+    },
+    "dispatch_id": {
+      "type": "string",
+      "minLength": 1,
+      "maxLength": 256
+    },
+    "change_id": {
+      "type": "string",
+      "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$",
+      "maxLength": 160
+    },
+    "attempt": {
+      "type": "integer",
+      "minimum": 1
+    },
+    "lease_generation": {
+      "type": "integer",
+      "minimum": 1
+    },
+    "outcome": {
+      "type": "string",
+      "maxLength": 1024,
+      "description": "Outcome class. Each oneOf branch names its class in x-outcome-class; the closure contract test enumerates them.",
+      "oneOf": [
+        {"x-outcome-class": "success", "const": "success"},
+        {"x-outcome-class": "failed", "pattern": "^failed:.+$"},
+        {"x-outcome-class": "vendor_limit", "pattern": "^vendor_limit:[^:]+:.+$"},
+        {"x-outcome-class": "parked", "const": "parked"}
+      ]
+    },
+    "replan": {
+      "type": "boolean",
+      "default": false
+    },
+    "handoff_id": {
+      "type": ["string", "null"],
+      "maxLength": 256
+    },
+    "worktree_ref": {
+      "$ref": "#/$defs/WorktreeRef"
+    },
+    "branch": {
+      "type": "string",
+      "minLength": 1,
+      "maxLength": 256
+    },
+    "host_id": {
+      "$ref": "#/$defs/HostId"
+    },
+    "parked": {
+      "$ref": "#/$defs/Parked"
+    },
+    "evidence": {
+      "type": "object",
+      "additionalProperties": false,
+      "required": ["loop_state_path", "commit", "loop_state_digest"],
+      "properties": {
+        "loop_state_path": {
+          "$ref": "#/$defs/RelativePath",
+          "description": "loop-state.json path relative to the worktree root."
+        },
+        "commit": {
+          "type": "string",
+          "pattern": "^[0-9a-f]{40}$"
+        },
+        "loop_state_digest": {
+          "type": "string",
+          "pattern": "^[0-9a-f]{64}$"
+        }
+      }
+    },
+    "degradations": {
+      "type": "array",
+      "maxItems": 32,
+      "items": {"$ref": "#/$defs/Degradation"}
+    }
+  },
+  "allOf": [
+    {
+      "if": {"properties": {"outcome": {"const": "success"}}, "required": ["outcome"]},
+      "then": {
+        "required": ["handoff_id", "worktree_ref", "branch", "host_id", "evidence"],
+        "properties": {
+          "handoff_id": {"type": "string", "minLength": 1, "maxLength": 256}
+        }
+      }
+    },
+    {
+      "if": {"properties": {"outcome": {"const": "parked"}}, "required": ["outcome"]},
+      "then": {"required": ["parked", "worktree_ref", "branch", "host_id", "evidence"]}
+    },
+    {
+      "if": {"properties": {"outcome": {"not": {"const": "parked"}}}, "required": ["outcome"]},
+      "then": {"not": {"required": ["parked"]}}
+    }
+  ],
+  "$defs": {
+    "HostId": {
+      "type": "string",
+      "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
+      "description": "Non-secret host identifier from the shared environment_profile.host_id(); never a hostname or username."
+    },
+    "RelativePath": {
+      "type": "string",
+      "minLength": 1,
+      "maxLength": 1024,
+      "pattern": "^(?![/\\\\])(?![A-Za-z]:)(?!\\.\\.(?:[/\\\\]|$))(?!.*[/\\\\]\\.\\.(?:[/\\\\]|$)).+$"
+    },
+    "WorktreeRef": {
+      "description": "Worktree path relative to the managed worktree root (managed_worktree) or the repo root (harness_provided inside the repo); null otherwise.",
+      "oneOf": [
+        {"$ref": "#/$defs/RelativePath"},
+        {"type": "null"}
+      ]
+    },
+    "ChildGate": {
+      "description": "Every Gate a child can park on: the Gate enum minus roadmap_approval, which a child never evaluates (D3).",
+      "enum": [
+        "gatekeeper_escalation",
+        "proposal_approval",
+        "plan_review_convergence_failure",
+        "validation_failure",
+        "escalate_resume",
+        "replan_required",
+        "pr_creation",
+        "merge"
+      ]
+    },
+    "ParkedCommon": {
+      "type": "object",
+      "required": ["kind", "reason"],
+      "properties": {
+        "reason": {"type": "string", "minLength": 1, "maxLength": 1024},
+        "deadline": {"type": ["string", "null"], "format": "date-time"},
+        "resume_hint": {"type": ["string", "null"], "maxLength": 512}
+      }
+    },
+    "ParkedPendingGate": {
+      "allOf": [{"$ref": "#/$defs/ParkedCommon"}],
+      "type": "object",
+      "additionalProperties": false,
+      "required": ["kind", "reason", "gate"],
+      "properties": {
+        "kind": {"const": "pending_gate"},
+        "gate": {"$ref": "#/$defs/ChildGate"},
+        "reason": true,
+        "deadline": true,
+        "resume_hint": true
+      }
+    },
+    "ParkedPolicyPause": {
+      "allOf": [{"$ref": "#/$defs/ParkedCommon"}],
+      "type": "object",
+      "additionalProperties": false,
+      "required": ["kind", "reason"],
+      "properties": {
+        "kind": {"const": "policy_pause"},
+        "gate": {"enum": [null, "escalate_resume"]},
+        "reason": true,
+        "deadline": true,
+        "resume_hint": true
+      }
+    },
+    "ParkedPermissionBlocked": {
+      "allOf": [{"$ref": "#/$defs/ParkedCommon"}],
+      "type": "object",
+      "additionalProperties": false,
+      "required": ["kind", "reason", "tool", "rule", "classifier_reason"],
+      "properties": {
+        "kind": {"const": "permission_blocked"},
+        "gate": {"enum": [null]},
+        "tool": {"type": "string", "minLength": 1, "maxLength": 128},
+        "rule": {"type": "string", "minLength": 1, "maxLength": 512, "description": "The matched permission rule (e.g. Bash(env *)), never the full command."},
+        "classifier_reason": {"type": "string", "minLength": 1, "maxLength": 512},
+        "command": {"type": ["string", "null"], "maxLength": 256, "description": "Redacted through sanitize_session_log.sanitize() and truncated to 256 characters."},
+        "reason": true,
+        "deadline": true,
+        "resume_hint": true
+      }
+    },
+    "ParkedCapabilityUnavailable": {
+      "allOf": [{"$ref": "#/$defs/ParkedCommon"}],
+      "type": "object",
+      "additionalProperties": false,
+      "required": ["kind", "reason", "phase", "missing_lanes"],
+      "properties": {
+        "kind": {"const": "capability_unavailable"},
+        "gate": {"enum": [null]},
+        "phase": {"enum": ["PLAN_REVIEW", "IMPL_REVIEW", "VAL_REVIEW"]},
+        "missing_lanes": {
+          "type": "array",
+          "minItems": 1,
+          "maxItems": 32,
+          "uniqueItems": true,
+          "items": {"type": "string", "minLength": 1, "maxLength": 128}
+        },
+        "reason": true,
+        "deadline": true,
+        "resume_hint": true
+      }
+    },
+    "Parked": {
+      "description": "Parked snapshot. One branch per kind; each branch constrains its allowed gate values (D3).",
+      "oneOf": [
+        {"$ref": "#/$defs/ParkedPendingGate"},
+        {"$ref": "#/$defs/ParkedPolicyPause"},
+        {"$ref": "#/$defs/ParkedPermissionBlocked"},
+        {"$ref": "#/$defs/ParkedCapabilityUnavailable"}
+      ]
+    },
+    "Degradation": {
+      "type": "object",
+      "additionalProperties": false,
+      "required": ["code", "phase", "detail"],
+      "properties": {
+        "code": {
+          "enum": [
+            "single_vendor_review",
+            "review_skipped",
+            "coordinator_projection_forbidden",
+            "audit_sink_failed",
+            "phase_fallback_inline",
+            "handoff_local_fallback"
+          ]
+        },
+        "phase": {"type": "string", "minLength": 1, "maxLength": 64},
+        "detail": {"type": "string", "maxLength": 512}
+      }
+    }
+  }
+}
diff --git a/openspec/schemas/gate-decision.schema.json b/openspec/schemas/gate-decision.schema.json
index 5edbb07..48189f2 100644
--- a/openspec/schemas/gate-decision.schema.json
+++ b/openspec/schemas/gate-decision.schema.json
@@ -154,6 +154,42 @@
       "pattern": "^[0-9a-f]{64}$",
       "description": "sha256 of the roadmap's authorized DAG shape; stamped on every roadmap_approval record. Absent (not null) on every other gate."
     },
+    "provenance": {
+      "description": "Who decided (dispatch-contract D5). A posture-provenance block is re-evaluated when the posture digest changes; a human-provenance decision is final for its subject.",
+      "oneOf": [
+        {
+          "type": "object",
+          "additionalProperties": false,
+          "required": ["source", "posture_digest"],
+          "properties": {
+            "source": {"const": "posture"},
+            "posture_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"}
+          }
+        },
+        {
+          "type": "object",
+          "additionalProperties": false,
+          "required": ["source", "approval_ref"],
+          "properties": {
+            "source": {"const": "human"},
+            "approval_ref": {
+              "type": ["string", "null"],
+              "pattern": "^gate-decision:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
+            }
+          }
+        }
+      ]
+    },
+    "scope": {
+      "type": "string",
+      "enum": ["roadmap_approval", "unscoped"],
+      "description": "For an auto proposal_approval / replan_required gate: whether a launch-marker roadmap_approval_ref scoped the auto, or the unscoped fallback applied (D8)."
+    },
+    "dedupe_fingerprint": {
+      "type": "string",
+      "pattern": "^[0-9a-f]{64}$",
+      "description": "Shared escalation subject of a permission_blocked / capability_unavailable fan-out answer (D9)."
+    },
     "timeout_seconds": {
       "type": [
         "integer",
diff --git a/openspec/schemas/gate-request.schema.json b/openspec/schemas/gate-request.schema.json
index 9e33e10..c099dca 100644
--- a/openspec/schemas/gate-request.schema.json
+++ b/openspec/schemas/gate-request.schema.json
@@ -40,7 +40,12 @@
       "required": ["disposition", "posture_present"],
       "properties": {
         "disposition": {"type": "string", "enum": ["auto", "notify_with_timeout", "block"]},
-        "posture_present": {"type": "boolean"}
+        "posture_present": {"type": "boolean"},
+        "posture_digest": {
+          "type": "string",
+          "pattern": "^[0-9a-f]{64}$",
+          "description": "trust_posture.posture_digest() of the posture this gate was evaluated under; a standalone gate-check re-evaluates when it differs (dispatch-contract D5)."
+        }
       }
     }
   }
diff --git a/openspec/schemas/supervisor-record-mirror.schema.json b/openspec/schemas/supervisor-record-mirror.schema.json
index 9d1156a..c62a6fa 100644
--- a/openspec/schemas/supervisor-record-mirror.schema.json
+++ b/openspec/schemas/supervisor-record-mirror.schema.json
@@ -46,7 +46,9 @@
         "disposition": {"type": ["string", "null"], "enum": ["auto", "notify_with_timeout", "block", null]},
         "approval_id": {"type": ["string", "null"]},
         "source": {"type": "string", "enum": ["autopilot", "supervise", "escalation"], "default": "supervise"},
-        "decision_id": {"type": ["string", "null"], "description": "The router's gate-decision record id this pending entry projects, so a rehydrated session can resolve `gate-decision:<decision_id>` back to its record."}
+        "decision_id": {"type": ["string", "null"], "description": "The router's gate-decision record id this pending entry projects, so a rehydrated session can resolve `gate-decision:<decision_id>` back to its record."},
+        "dedupe_fingerprint": {"type": "string", "pattern": "^[0-9a-f]{64}$", "description": "Shared escalation subject of a permission_blocked / capability_unavailable park (dispatch-contract D9)."},
+        "dispatch_ids": {"type": "array", "maxItems": 64, "description": "Every parked dispatch one escalation answer resumes, each with the lease_generation it had at projection (D9).", "items": {"type": "object", "additionalProperties": false, "required": ["dispatch_id", "lease_generation"], "properties": {"dispatch_id": {"type": "string", "minLength": 1, "maxLength": 256}, "lease_generation": {"type": "integer", "minimum": 1}}}}
       }
     },
     "standingDecision": {
diff --git a/openspec/schemas/supervisor-record.schema.json b/openspec/schemas/supervisor-record.schema.json
index 6c813c0..25e6051 100644
--- a/openspec/schemas/supervisor-record.schema.json
+++ b/openspec/schemas/supervisor-record.schema.json
@@ -46,7 +46,9 @@
         "disposition": {"type": ["string", "null"], "enum": ["auto", "notify_with_timeout", "block", null]},
         "approval_id": {"type": ["string", "null"]},
         "source": {"type": "string", "enum": ["autopilot", "supervise", "escalation"], "default": "supervise"},
-        "decision_id": {"type": ["string", "null"], "description": "The router's gate-decision record id this pending entry projects, so a rehydrated session can resolve `gate-decision:<decision_id>` back to its record."}
+        "decision_id": {"type": ["string", "null"], "description": "The router's gate-decision record id this pending entry projects, so a rehydrated session can resolve `gate-decision:<decision_id>` back to its record."},
+        "dedupe_fingerprint": {"type": "string", "pattern": "^[0-9a-f]{64}$", "description": "Shared escalation subject of a permission_blocked / capability_unavailable park (dispatch-contract D9)."},
+        "dispatch_ids": {"type": "array", "maxItems": 64, "description": "Every parked dispatch one escalation answer resumes, each with the lease_generation it had at projection (D9).", "items": {"type": "object", "additionalProperties": false, "required": ["dispatch_id", "lease_generation"], "properties": {"dispatch_id": {"type": "string", "minLength": 1, "maxLength": 256}, "lease_generation": {"type": "integer", "minimum": 1}}}}
       }
     },
     "standingDecision": {
diff --git a/openspec/schemas/trust-posture.schema.json b/openspec/schemas/trust-posture.schema.json
index 14d5ab8..1aa25c9 100644
--- a/openspec/schemas/trust-posture.schema.json
+++ b/openspec/schemas/trust-posture.schema.json
@@ -5,7 +5,10 @@
   "description": "Schema for the YAML front matter of the repo-owned trust posture contract (TRUST_POSTURE.md). Declared at repo root; resolved by skills/shared/trust_posture.py (which performs the authoritative runtime validation — this schema is the declarative mirror, following the flags.yaml / feature_flags.py pattern). When the contract file is absent, every gate resolves to 'block' (backward-compatible default); the loader also fails closed to 'block' for any gate omitted here.",
   "type": "object",
   "additionalProperties": false,
-  "required": ["schema_version", "gates"],
+  "required": [
+    "schema_version",
+    "gates"
+  ],
   "properties": {
     "schema_version": {
       "type": "integer",
@@ -17,15 +20,33 @@
       "description": "Per-gate disposition map. Keys are restricted to the nine enumerated gates; an unknown gate key is a validation error. A gate omitted here resolves to 'block' (fail-closed).",
       "additionalProperties": false,
       "properties": {
-        "gatekeeper_escalation": { "$ref": "#/$defs/GateConfig" },
-        "proposal_approval": { "$ref": "#/$defs/GateConfig" },
-        "plan_review_convergence_failure": { "$ref": "#/$defs/GateConfig" },
-        "validation_failure": { "$ref": "#/$defs/GateConfig" },
-        "escalate_resume": { "$ref": "#/$defs/GateConfig" },
-        "replan_required": { "$ref": "#/$defs/GateConfig" },
-        "pr_creation": { "$ref": "#/$defs/GateConfig" },
-        "merge": { "$ref": "#/$defs/GateConfig" },
-        "roadmap_approval": { "$ref": "#/$defs/GateConfig" }
+        "gatekeeper_escalation": {
+          "$ref": "#/$defs/GateConfig"
+        },
+        "proposal_approval": {
+          "$ref": "#/$defs/ScopedGateConfig"
+        },
+        "plan_review_convergence_failure": {
+          "$ref": "#/$defs/GateConfig"
+        },
+        "validation_failure": {
+          "$ref": "#/$defs/GateConfig"
+        },
+        "escalate_resume": {
+          "$ref": "#/$defs/GateConfig"
+        },
+        "replan_required": {
+          "$ref": "#/$defs/ScopedGateConfig"
+        },
+        "pr_creation": {
+          "$ref": "#/$defs/GateConfig"
+        },
+        "merge": {
+          "$ref": "#/$defs/GateConfig"
+        },
+        "roadmap_approval": {
+          "$ref": "#/$defs/GateConfig"
+        }
       }
     }
   },
@@ -33,11 +54,17 @@
     "GateConfig": {
       "type": "object",
       "additionalProperties": false,
-      "required": ["disposition"],
+      "required": [
+        "disposition"
+      ],
       "properties": {
         "disposition": {
           "type": "string",
-          "enum": ["auto", "notify_with_timeout", "block"],
+          "enum": [
+            "auto",
+            "notify_with_timeout",
+            "block"
+          ],
           "description": "auto = proceed unattended and log; notify_with_timeout = file an approval, notify, poll until timeout, then apply default_action; block = park the loop for a human (today's behavior)."
         },
         "timeout_seconds": {
@@ -47,24 +74,177 @@
         },
         "default_action": {
           "type": "string",
-          "enum": ["proceed", "block"],
+          "enum": [
+            "proceed",
+            "block"
+          ],
           "description": "Required for notify_with_timeout: what to do when the timer expires. Must NOT be present for auto or block."
         }
       },
       "allOf": [
         {
-          "if": { "properties": { "disposition": { "const": "notify_with_timeout" } } },
-          "then": { "required": ["timeout_seconds", "default_action"] },
+          "if": {
+            "properties": {
+              "disposition": {
+                "const": "notify_with_timeout"
+              }
+            }
+          },
+          "then": {
+            "required": [
+              "timeout_seconds",
+              "default_action"
+            ]
+          },
           "else": {
             "not": {
               "anyOf": [
-                { "required": ["timeout_seconds"] },
-                { "required": ["default_action"] }
+                {
+                  "required": [
+                    "timeout_seconds"
+                  ]
+                },
+                {
+                  "required": [
+                    "default_action"
+                  ]
+                }
               ]
             }
           }
         }
       ]
+    },
+    "ScopedGateConfig": {
+      "type": "object",
+      "additionalProperties": false,
+      "required": [
+        "disposition"
+      ],
+      "properties": {
+        "disposition": {
+          "type": "string",
+          "enum": [
+            "auto",
+            "notify_with_timeout",
+            "block"
+          ],
+          "description": "auto = proceed unattended and log; notify_with_timeout = file an approval, notify, poll until timeout, then apply default_action; block = park the loop for a human (today's behavior)."
+        },
+        "timeout_seconds": {
+          "type": "integer",
+          "exclusiveMinimum": 0,
+          "description": "Required for notify_with_timeout: seconds to wait for a human before applying default_action. Must NOT be present for auto or block."
+        },
+        "default_action": {
+          "type": "string",
+          "enum": [
+            "proceed",
+            "block"
+          ],
+          "description": "Required for notify_with_timeout: what to do when the timer expires. Must NOT be present for auto or block."
+        },
+        "unscoped": {
+          "$ref": "#/$defs/UnscopedConfig"
+        }
+      },
+      "allOf": [
+        {
+          "if": {
+            "properties": {
+              "disposition": {
+                "const": "notify_with_timeout"
+              }
+            }
+          },
+          "then": {
+            "required": [
+              "timeout_seconds",
+              "default_action"
+            ]
+          },
+          "else": {
+            "not": {
+              "anyOf": [
+                {
+                  "required": [
+                    "timeout_seconds"
+                  ]
+                },
+                {
+                  "required": [
+                    "default_action"
+                  ]
+                }
+              ]
+            }
+          }
+        }
+      ],
+      "description": "A gate config whose auto disposition is scoped to a roadmap approval (dispatch-contract D8): auto applies only when the launch marker carries a roadmap_approval_ref; otherwise unscoped applies (default block)."
+    },
+    "UnscopedConfig": {
+      "type": "object",
+      "additionalProperties": false,
+      "required": [
+        "disposition"
+      ],
+      "properties": {
+        "disposition": {
+          "type": "string",
+          "enum": [
+            "notify_with_timeout",
+            "block"
+          ]
+        },
+        "timeout_seconds": {
+          "type": "integer",
+          "exclusiveMinimum": 0,
+          "description": "Required for notify_with_timeout: seconds to wait for a human before applying default_action. Must NOT be present for auto or block."
+        },
+        "default_action": {
+          "type": "string",
+          "enum": [
+            "proceed",
+            "block"
+          ],
+          "description": "Required for notify_with_timeout: what to do when the timer expires. Must NOT be present for auto or block."
+        }
+      },
+      "allOf": [
+        {
+          "if": {
+            "properties": {
+              "disposition": {
+                "const": "notify_with_timeout"
+              }
+            }
+          },
+          "then": {
+            "required": [
+              "timeout_seconds",
+              "default_action"
+            ]
+          },
+          "else": {
+            "not": {
+              "anyOf": [
+                {
+                  "required": [
+                    "timeout_seconds"
+                  ]
+                },
+                {
+                  "required": [
+                    "default_action"
+                  ]
+                }
+              ]
+            }
+          }
+        }
+      ],
+      "description": "Fallback for a scoped gate evaluated without a roadmap approval. Same rules as a gate config, except auto is not allowed."
     }
   }
 }
diff --git a/skills/autopilot-roadmap/scripts/orchestrator.py b/skills/autopilot-roadmap/scripts/orchestrator.py
index 3d5d790..da57d2f 100644
--- a/skills/autopilot-roadmap/scripts/orchestrator.py
+++ b/skills/autopilot-roadmap/scripts/orchestrator.py
@@ -72,8 +72,14 @@ from policy import (  # type: ignore[import-untyped]
 )
 from replanner import replan  # type: ignore[import-untyped]
 from sanitizer import sanitize_dict  # type: ignore[import-untyped]
+from shared import dispatch_contract  # noqa: E402
+from shared.environment_profile import host_id as current_host_id  # noqa: E402
 from shared.trust_posture import Gate  # noqa: E402
 
+#: Answers whether the supervisor has an answer path for a parked ``(kind,
+#: gate)`` pair; injected by the supervise execution adapter (D3, closure).
+ParkedRoute = Callable[[str, Any], bool]
+
 logger = logging.getLogger(__name__)
 
 #: Filename of the replan handoff written into the workspace on a proceed.
@@ -125,30 +131,7 @@ def _normalize_outcome(result: DispatchResult) -> tuple[str, bool]:
 
 
 IsolationResolver = Callable[[RoadmapItem], Mapping[str, Any]]
-_RESULT_REQUIRED = {
-    "schema_version",
-    "dispatch_id",
-    "change_id",
-    "attempt",
-    "lease_generation",
-    "outcome",
-}
-_RESULT_ALLOWED = _RESULT_REQUIRED | {
-    "replan",
-    "handoff_id",
-    "worktree_path",
-    "branch",
-    "parked",
-    "evidence",
-}
-_EXACT_CHANGE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
 _BATCH_ID = re.compile(r"^batch-[0-9a-f]{24}$")
-_RESULT_OUTCOME = re.compile(r"^(success|failed:.+|vendor_limit:[^:]+:.+|parked)$")
-_DATE_TIME = re.compile(
-    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$"
-)
-_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
-_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
 _TERMINAL_ATTEMPT_STATUSES = {"completed", "failed", "parked"}
 _RESERVED_DISPATCH_CONTEXT_KEYS = frozenset(
     {
@@ -201,17 +184,37 @@ def _copy_context(context: Mapping[str, Any] | None) -> dict[str, Any]:
     return value
 
 
-def _validated_isolation(value: Mapping[str, Any]) -> dict[str, str]:
+def _portable_isolation(
+    value: Mapping[str, Any],
+    *,
+    repo_root: Path,
+    managed_root: Path,
+    host_id: str,
+) -> dict[str, Any]:
+    """Convert a resolver's absolute isolation to the persisted portable shape (D7).
+
+    The absolute path exists only here, in memory; a path outside the root its
+    mode is relative to is refused.
+    """
     isolation = dict(value)
     if set(isolation) != {"mode", "worktree_path", "branch"}:
         raise ValueError("isolation must contain exactly mode, worktree_path, and branch")
-    if isolation["mode"] not in {"managed_worktree", "harness_provided"}:
+    mode = isolation["mode"]
+    if mode not in {"managed_worktree", "harness_provided"}:
         raise ValueError("unsupported isolation mode")
     if not isinstance(isolation["worktree_path"], str) or not isolation["worktree_path"]:
         raise ValueError("isolation worktree_path must be non-empty")
     if not isinstance(isolation["branch"], str) or not isolation["branch"]:
         raise ValueError("isolation branch must be non-empty")
-    return isolation  # type: ignore[return-value]
+    ref = dispatch_contract.portable_ref(
+        Path(isolation["worktree_path"]).resolve(),
+        mode=mode,
+        repo_root=Path(repo_root).resolve(),
+        managed_root=Path(managed_root).resolve(),
+    )
+    if ref is None and mode == "managed_worktree":
+        raise ValueError("managed worktree is not inside the managed worktree root")
+    return {"mode": mode, "worktree_ref": ref, "branch": isolation["branch"], "host_id": host_id}
 
 
 def _next_attempt_number(checkpoint: Any, item_id: str) -> int:
@@ -225,25 +228,51 @@ def _next_attempt_number(checkpoint: Any, item_id: str) -> int:
     )
 
 
-def _request_from_attempt(
+def request_from_attempt(
     roadmap_id: str,
     attempt: Mapping[str, Any],
+    *,
+    launch_token: str | None,
+    gate_answer: Mapping[str, Any] | None = None,
 ) -> dict[str, Any]:
-    return {
-        "schema_version": 1,
+    """The version-2 request for an attempt's current generation (D1, D6).
+
+    ``launch_token`` is the raw per-generation token, held only in memory by the
+    caller that just minted it; it is never read back from the checkpoint. With
+    ``launch_token=None`` the returned entry view omits it and is not a full
+    request.
+    """
+    request: dict[str, Any] = {
+        "schema_version": 2,
         "dispatch_id": attempt["dispatch_id"],
         "roadmap_id": roadmap_id,
         "item_id": attempt["item_id"],
         "change_id": attempt["change_id"],
         "phase": attempt["phase"],
         "attempt": attempt["attempt"],
-        "launch_token": attempt["launch_token"],
         "lease_generation": attempt["lease_generation"],
         "launch_marker_path": attempt["launch_marker_path"],
         "scope": copy.deepcopy(attempt["scope"]),
         "isolation": copy.deepcopy(attempt["isolation"]),
         "context": copy.deepcopy(attempt["context"]),
+        "execution_profile": copy.deepcopy(attempt.get("execution_profile") or {}),
+        "review_requirements": copy.deepcopy(attempt.get("review_requirements") or {}),
+        "roadmap_approval_ref": attempt.get("roadmap_approval_ref"),
     }
+    if "continuation" in attempt:
+        request["continuation"] = copy.deepcopy(attempt["continuation"])
+    if gate_answer is not None:
+        request["gate_answer"] = copy.deepcopy(dict(gate_answer))
+    if launch_token is None:
+        return request
+    request["launch_token"] = launch_token
+    return dispatch_contract.validate_request(request)
+
+
+def mint_launch_token() -> tuple[str, str]:
+    """A fresh raw launch token and its persisted digest (D6)."""
+    token = secrets.token_urlsafe(24)
+    return token, dispatch_contract.launch_digest(token)
 
 
 def prepare_delegated_batch(
@@ -252,9 +281,24 @@ def prepare_delegated_batch(
     repo_root: Path,
     isolation_resolver: IsolationResolver,
     context: Mapping[str, Any] | None = None,
+    managed_root: Path | None = None,
+    host_id: str | None = None,
+    roadmap_approval_ref: str | None = None,
+    execution_profile: Mapping[str, Any] | None = None,
+    review_requirements: Mapping[str, Any] | None = None,
 ) -> dict[str, Any]:
-    """Persist one scope-safe generation batch without invoking ``dispatch_fn``."""
+    """Persist one scope-safe generation batch without invoking ``dispatch_fn``.
+
+    Each attempt stores only the launch digest; the raw token of each
+    generation is minted here and returned in its request alone (D6).
+    Isolation is persisted host-portably (D7), and the verified
+    ``roadmap_approval_ref`` plus the resolved execution profile and review
+    requirements are persisted so every generation's request and marker carry
+    them (D8, D10).
+    """
     base_context = _copy_context(context)
+    managed = Path(managed_root) if managed_root is not None else Path(repo_root) / ".git-worktrees"
+    host = host_id or current_host_id()
     roadmap, manager, checkpoint = _load_or_create_execution_state(workspace, repo_root)
     unresolved_items = {
         attempt["item_id"]
@@ -298,7 +342,9 @@ def prepare_delegated_batch(
     for selected in plan.items:
         item = by_id[selected.item_id]
         try:
-            isolation = _validated_isolation(isolation_resolver(item))
+            isolation = _portable_isolation(
+                isolation_resolver(item), repo_root=repo_root, managed_root=managed, host_id=host
+            )
         except Exception as exc:
             failures.append(
                 {
@@ -334,12 +380,14 @@ def prepare_delegated_batch(
     )
     batch_id = f"batch-{hashlib.sha256(digest_input.encode()).hexdigest()[:24]}"
     prepared: list[dict[str, Any]] = []
+    tokens: dict[str, str] = {}
     dispatch_ids: list[str] = []
     for selected, item, attempt_number, isolation in generation_specs:
         dispatch_id = f"{batch_id}:{item.item_id}:attempt-{attempt_number}"
         dispatch_ids.append(dispatch_id)
-        prepared.append(
-            {
+        token, digest = mint_launch_token()
+        tokens[dispatch_id] = token
+        attempt_record: dict[str, Any] = {
                 "dispatch_id": dispatch_id,
                 "item_id": item.item_id,
                 "change_id": selected.change_id,
@@ -347,7 +395,7 @@ def prepare_delegated_batch(
                 "attempt": attempt_number,
                 "status": "prepared",
                 "prepared_at": datetime.now(timezone.utc).isoformat(),
-                "launch_token": secrets.token_urlsafe(24),
+                "launch_digest": digest,
                 "launch_marker_path": (
                     f".supervised-dispatch/{item.change_id}/"
                     f"{item.item_id}-attempt-{attempt_number}.marker"
@@ -357,8 +405,12 @@ def prepare_delegated_batch(
                 "scope": selected.scope.to_request_scope(),
                 "isolation": isolation,
                 "context": copy.deepcopy(base_context),
-            }
-        )
+                "execution_profile": copy.deepcopy(dict(execution_profile or {})),
+                "review_requirements": copy.deepcopy(dict(review_requirements or {})),
+        }
+        if roadmap_approval_ref is not None:
+            attempt_record["roadmap_approval_ref"] = roadmap_approval_ref
+        prepared.append(attempt_record)
 
     for attempt in prepared:
         validate_delegated_dispatch_attempt(attempt)
@@ -375,126 +427,16 @@ def prepare_delegated_batch(
     return {
         "batch_id": batch_id,
         "requests": [
-            _request_from_attempt(roadmap.roadmap_id, attempt) for attempt in prepared
+            request_from_attempt(
+                roadmap.roadmap_id, attempt, launch_token=tokens[attempt["dispatch_id"]]
+            )
+            for attempt in prepared
         ],
         "failures": failures,
         "deferred_item_ids": list(plan.deferred_item_ids),
     }
 
 
-def _validate_dispatch_result(result: Mapping[str, Any]) -> dict[str, Any]:
-    value = copy.deepcopy(dict(result))
-    missing = _RESULT_REQUIRED - value.keys()
-    extra = value.keys() - _RESULT_ALLOWED
-    if missing or extra:
-        raise ValueError(
-            "invalid supervised dispatch result fields: "
-            f"missing={sorted(missing)} extra={sorted(extra)}"
-        )
-    if isinstance(value["schema_version"], bool) or value["schema_version"] != 1:
-        raise ValueError("invalid supervised dispatch result schema_version")
-    if not isinstance(value["dispatch_id"], str) or not 1 <= len(value["dispatch_id"]) <= 256:
-        raise ValueError("invalid supervised dispatch result dispatch_id")
-    change_id = value["change_id"]
-    if (
-        not isinstance(change_id, str)
-        or len(change_id) > 160
-        or _EXACT_CHANGE_ID.fullmatch(change_id) is None
-    ):
-        raise ValueError("invalid supervised dispatch result change_id")
-    for field in ("attempt", "lease_generation"):
-        number = value[field]
-        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
-            raise ValueError(f"invalid supervised dispatch result {field}")
-    outcome = value["outcome"]
-    if (
-        not isinstance(outcome, str)
-        or len(outcome) > 1024
-        or _RESULT_OUTCOME.fullmatch(outcome) is None
-    ):
-        raise ValueError("invalid supervised dispatch result outcome")
-    if "replan" in value and not isinstance(value["replan"], bool):
-        raise ValueError("invalid supervised dispatch result replan")
-    if "handoff_id" in value and (
-        value["handoff_id"] is not None
-        and (
-            not isinstance(value["handoff_id"], str)
-            or len(value["handoff_id"]) > 256
-        )
-    ):
-        raise ValueError("invalid supervised dispatch result handoff_id")
-    for field in ("worktree_path", "branch"):
-        if field in value and (
-            not isinstance(value[field], str) or not value[field]
-        ):
-            raise ValueError(f"invalid supervised dispatch result {field}")
-    if "evidence" in value:
-        evidence = value["evidence"]
-        if not isinstance(evidence, dict) or set(evidence) - {
-            "loop_state_path",
-            "commit",
-            "loop_state_digest",
-        }:
-            raise ValueError("invalid supervised dispatch result evidence")
-        if not isinstance(evidence.get("loop_state_path"), str) or not evidence["loop_state_path"]:
-            raise ValueError("invalid supervised dispatch result loop_state_path")
-        if (
-            not isinstance(evidence.get("commit"), str)
-            or _HEX_40.fullmatch(evidence["commit"]) is None
-        ):
-            raise ValueError("invalid supervised dispatch result commit")
-        if (
-            not isinstance(evidence.get("loop_state_digest"), str)
-            or _HEX_64.fullmatch(evidence["loop_state_digest"]) is None
-        ):
-            raise ValueError("invalid supervised dispatch result loop_state_digest")
-    if outcome in {"success", "parked"}:
-        required = {"worktree_path", "branch", "evidence"}
-        if not required <= value.keys():
-            raise ValueError(f"invalid {outcome} dispatch result evidence")
-    if outcome == "success" and (
-        not isinstance(value.get("handoff_id"), str) or not value["handoff_id"]
-    ):
-        raise ValueError("invalid success dispatch result handoff_id")
-    if outcome == "parked":
-        parked = val

[diff truncated to fit packet budget; use Read/Grep for the remainder]

```

### Rule groups

#### Group 1 (default: `(default)`)
Applies to:
- .gitleaks.toml
- TRUST_POSTURE.template.md
- docs/decisions/roadmap-orchestration.md
- docs/decisions/skill-workflow.md
- docs/decisions/supervise.md
- docs/decisions/trust-posture.md
- openspec/changes/dispatch-contract/.review-ledger/ledger.json
- openspec/changes/dispatch-contract/design.md
- openspec/changes/dispatch-contract/handoffs/eeedef7e-c78e-4f7c-a6f5-94cc4a8150f5.json
- openspec/changes/dispatch-contract/impl-findings.md
- openspec/changes/dispatch-contract/loop-state.json
- openspec/changes/dispatch-contract/plan-findings.md
- openspec/changes/dispatch-contract/proposal.md
- openspec/changes/dispatch-contract/session-log.md
- openspec/changes/dispatch-contract/tasks.md
- openspec/changes/dispatch-contract/validation-report.md
- openspec/changes/dispatch-contract/work-packages.yaml
- openspec/contracts/roadmap-orchestration/schemas/delegated-dispatch-attempt.schema.json
- skills/parallel-infrastructure/review_quorum_policy.json
- skills/roadmap-runtime/install_assets/openspec/contracts/roadmap-orchestration/schemas/bounded-dispatch-context.schema.json
- skills/roadmap-runtime/install_assets/openspec/contracts/roadmap-orchestration/schemas/delegated-dispatch-attempt.schema.json
- skills/roadmap-runtime/install_assets/openspec/contracts/roadmap-orchestration/schemas/supervised-dispatch-request.schema.json
- skills/roadmap-runtime/install_assets/openspec/contracts/roadmap-orchestration/schemas/supervised-dispatch-result.schema.json
- skills/roadmap-runtime/install_assets/openspec/schemas/checkpoint.schema.json
- skills/roadmap-runtime/install_assets/openspec/schemas/dispatch-request.schema.json
- skills/roadmap-runtime/install_assets/openspec/schemas/dispatch-result.schema.json

Review for correctness, security, and adherence to this repository's conventions.

#### Group 2 (default: `openspec/changes/*/specs/**/spec.md`)
Applies to:
- openspec/changes/dispatch-contract/specs/parallel-infrastructure/spec.md
- openspec/changes/dispatch-contract/specs/roadmap-orchestration/spec.md
- openspec/changes/dispatch-contract/specs/skill-workflow/spec.md
- openspec/changes/dispatch-contract/specs/supervise/spec.md
- openspec/changes/dispatch-contract/specs/trust-posture/spec.md

Verify every SHALL/MUST has at least one Scenario with WHEN/THEN. Check that a MODIFIED requirement's unchanged scenarios were preserved, not silently dropped.

#### Group 3 (default: `openspec/schemas/*.schema.json`)
Applies to:
- openspec/schemas/checkpoint.schema.json
- openspec/schemas/dispatch-request.schema.json
- openspec/schemas/dispatch-result.schema.json
- openspec/schemas/gate-decision.schema.json
- openspec/schemas/gate-request.schema.json
- openspec/schemas/supervisor-record-mirror.schema.json
- openspec/schemas/supervisor-record.schema.json
- openspec/schemas/trust-posture.schema.json

Verify the schema is valid Draft 2020-12, that required fields were not silently dropped, and that any mirrored copy (install_assets, sentinel-injected) is checked for the same change.

#### Group 4 (default: `skills/*/scripts/*.py`)
Applies to:
- skills/autopilot-roadmap/scripts/orchestrator.py
- skills/autopilot/scripts/autopilot.py
- skills/autopilot/scripts/convergence_loop.py
- skills/autopilot/scripts/runner.py
- skills/parallel-infrastructure/scripts/review_dispatcher.py
- skills/parallel-infrastructure/scripts/review_packet.py
- skills/roadmap-runtime/scripts/models.py
- skills/supervise/scripts/cycle_state.py
- skills/supervise/scripts/execution.py
- skills/supervise/scripts/gate_router.py

Check for unhandled exceptions on the failure paths this module is meant to guard (network, subprocess, file I/O). Verify a function documented as "never raises" actually catches every exception class it claims to. Flag silent behavior changes to existing callers.

#### Group 5 (default: `skills/*/SKILL.md`)
Applies to:
- skills/autopilot/SKILL.md
- skills/supervise/SKILL.md

Check that the workflow steps match what the referenced scripts actually accept (flags, return shapes). Verify examples are runnable as written. Flag instructions that silently assume coordinator, tier, or environment state without stating the fallback.

#### Group 6 (default: `**/scripts/tests/**`)
Applies to:
- skills/autopilot/scripts/tests/test_autopilot.py

Check that tests exercise real behavior, not just shape — mocks should stand in for I/O and external calls, not for the logic under test. Flag a test that would pass even if the implementation were reverted to a no-op.

#### Group 7 (default: `**/*.py`)
Applies to:
- skills/shared/approval_gate.py
- skills/shared/dispatch_contract.py
- skills/shared/environment_profile.py
- skills/shared/trust_posture.py

Check for unhandled exceptions, resource leaks (files/sockets/locks not in a context manager), and mutable default arguments. Flag a docstring claim ("never raises", "pure function") the code does not actually satisfy.

#### Group 8 (default: `skills/tests/**`)
Applies to:
- skills/tests/autopilot-roadmap/test_dispatch_contract_e2e.py
- skills/tests/autopilot-roadmap/test_supervised_dispatch.py
- skills/tests/autopilot-roadmap/test_supervised_dispatch_e2e.py
- skills/tests/autopilot/test_apply_outcome_contract.py
- skills/tests/autopilot/test_convergence_loop.py
- skills/tests/autopilot/test_emit_result.py
- skills/tests/autopilot/test_gate_check_reeval.py
- skills/tests/autopilot/test_gate_e2e.py
- skills/tests/autopilot/test_gate_evaluate_cli.py
- skills/tests/autopilot/test_loop_state.py
- skills/tests/autopilot/test_loop_state_v6.py
- skills/tests/autopilot/test_quorum_park.py
- skills/tests/install_sh/test_openspec_assets.py
- skills/tests/parallel-infrastructure/test_check_vendors.py
- skills/tests/parallel-infrastructure/test_check_vendors_dispatchable.py
- skills/tests/parallel-infrastructure/test_review_packet.py
- skills/tests/roadmap-runtime/fixtures/landable-checkpoint.json
- skills/tests/roadmap-runtime/test_checkpoint_legacy_migration.py
- skills/tests/roadmap-runtime/test_cross_host_reconcile.py
- skills/tests/roadmap-runtime/test_delegated_checkpoint.py
- skills/tests/roadmap-runtime/test_dispatch_scheduler.py
- skills/tests/roadmap-runtime/test_dispatch_schema_parity.py
- skills/tests/roadmap-runtime/test_landable_checkpoint.py
- skills/tests/shared/test_approval_gate_provenance.py
- skills/tests/shared/test_dispatch_contract.py
- skills/tests/shared/test_environment_profile_host_id.py
- skills/tests/shared/test_trust_posture_scope.py
- skills/tests/supervise/test_dispatch_closure.py
- skills/tests/supervise/test_execution.py
- skills/tests/supervise/test_execution_contract.py
- skills/tests/supervise/test_gate_router.py
- skills/tests/supervise/test_gate_router_e2e.py
- skills/tests/supervise/test_workflow_contract.py

Same standard as scripts/tests/: verify the test would fail if the behavior it targets were broken. Check that fixture paths use openspec_paths.change_dir rather than a literal openspec/changes/<id>/ path where the guide requires it.

### Spec excerpts
#### specs/parallel-infrastructure/spec.md
(excerpt dropped — over packet budget; Read this path if needed)

#### specs/roadmap-orchestration/spec.md
(excerpt dropped — over packet budget; Read this path if needed)

#### specs/skill-workflow/spec.md
(excerpt dropped — over packet budget; Read this path if needed)

#### specs/supervise/spec.md
(excerpt dropped — over packet budget; Read this path if needed)

#### specs/trust-posture/spec.md
(excerpt dropped — over packet budget; Read this path if needed)

### Open ledger items
- [1] D2 claims the boundary is defined only by hand validators plus an inline checkpoint copy, but published JSON Schemas already exist at openspec/contracts/roadmap-orchestration/schemas/{supervised-dispatch-request,supervised-dispatch-result,delegated-dispatch-attempt,bounded-dispatch-context}.schema.json (with $id https://agentic-coding-tools.dev/contracts/...), consumed by skills/tests/supervise/test_execution_contract.py, test_execution.py:386, roadmap-runtime/test_dispatch_scheduler.py:34 and autopilot-roadmap/test_supervised_dispatch_e2e.py:42. Adding openspec/schemas/dispatch-*.schema.json without deciding what happens to them creates a fourth definition, the exact root cause the change exists to remove.
- [2] Why states the dispatch request and result 'exist only as three hand-kept validators ... plus test fixtures', and Impact lists only openspec/schemas/ files. openspec/contracts/roadmap-orchestration/schemas/ already publishes request, result, attempt and context schemas (listed in docs/architecture-analysis/contracts-inventory.md). The problem statement and Impact table are factually incomplete.
- [3] Scenario 'Existing fixtures validate against the published schemas' requires every valid-* fixture under skills/tests/supervise/fixtures/execution/contracts/ to pass validate_request/validate_result, but valid-prepared-attempt.json is a checkpoint attempt (with raw launch_token), and valid-results.json is a map {success, parked} rather than a result. Its v1 success result also carries absolute worktree_path and evidence.loop_state_path under /workspace/.git-worktrees, which the 'cannot be made portable' scenario would reject on any test host. The scenario is unexecutable as worded, and the requirement does not relate the existing openspec/contracts/roadmap-orchestration/schemas/ files to the new single definition.
- [4] Making checkpoint.schema.json's attempt result a $ref breaks every existing validator of that schema: roadmap-runtime/scripts/models.py validate_against_schema (lines 956-973) builds a bare Draft202012Validator with no registry, used by resolve_readiness.py:113 and models.py:1135; and tests that copy only checkpoint.schema.json into a tmp repo (supervise/test_execution.py _workspace, test_gate_router.py:54, test_gate_router_e2e.py:57, test_cycle_state.py:115, roadmap-runtime/test_readiness.py:105, autopilot-roadmap/test_supervised_dispatch.py:25, test_supervised_dispatch_e2e.py:95) would then fail with an unresolvable reference. No task updates the loader or those copies. Tasks also omit the existing contract schemas (finding 1), a host_id function in skills/shared/environment_profile.py (D7 cites it; the module has only detect() and its layers), and the install manifest test skills/tests/install_sh/test_openspec_assets.py.
- [5] Write scopes omit files the plan must edit: openspec/contracts/roadmap-orchestration/schemas/*.schema.json and skills/tests/supervise/test_execution_contract.py (no package); skills/shared/environment_profile.py (host_id, D7; no package); skills/tests/roadmap-runtime/test_readiness.py, skills/tests/supervise/test_cycle_state.py, skills/tests/autopilot-roadmap/test_supervised_dispatch.py and skills/tests/install_sh/test_openspec_assets.py (schema copy sites broken by the checkpoint $ref; no package). Scope enforcement will reject these edits.
- [6] D9 says one operator answer resumes every attempt sharing a fingerprint, but the resume path verifies a record bound to one dispatch: gate_router.require_approval_ref (gate_router.py:1095-1140) rejects a record whose dispatch_id differs and, for escalate_resume, whose lease_generation differs; ExecutionAdapter.resume rejects any kind other than pending_gate/policy_pause (execution.py:852). D9 never defines the decision-record shape for a fingerprint subject, so the fan-out cannot pass the existing verification.
- [7] Modified scenario 'Resume an authorized parked attempt' requires 'a subject matching the dispatch', replacing the base 'matching dispatch_id' with an undefined term. With D9 fingerprint subjects the verifiable condition is unclear and an implementer could accept a record whose subject lists the dispatch but whose lease_generation is stale.
- [8] Honest Review Quorum cannot be met by the tasked edits. Below quorum, skills/autopilot/SKILL.md (lines 175-179) sets CLI_REVIEW_ENABLED=false before run_loop, so PLAN_REVIEW is skipped and convergence_loop never runs; task 7.3 puts the park in convergence_loop.py, which therefore never fires for a dispatched child, and it also contradicts the skill-workflow rule that runner.py park is the only writer of park. The standalone review_skipped degradation likewise cannot come from convergence_loop because no review runs.
- [9] D10 defines counting_lanes as 'verified lanes ordered by the cost_policy.tiers ladder'. The skill-workflow scenario requires missing_lanes to name 'the counting lanes not verified', which is always empty under that definition, so every capability_unavailable park fingerprints to sha256(phase, []) and D9's 'different missing lanes are separate escalations' cannot hold.
- [10] Task 6.2 says the gate session 'passes the marker's roadmap_approval_ref into gate context', but D8 and the trust-posture requirement say a context-supplied roadmap_approval_ref is ignored and the gate reads the marker only through its marker_reader seam. Implemented as tasked, either scope never applies or the context path becomes the trust channel D8 forbids.
- [11] D1's v1 upgrade converts only worktree_path, but v1 results also carry an absolute evidence.loop_state_path (see fixtures/execution/contracts/valid-results.json), while Host-Portable Attempt Isolation forbids persisting absolute paths in the result. An upgraded v1 result would still carry an absolute path into checkpoint outcome metadata.
- [12] D9 says the stored command is 'the output of sanitize_session_log.sanitize()', but sanitize() returns a (content, redactions) tuple (sanitize_session_log.py:177).
- [13] D7 reinitializes a parked attempt on another host by incrementing its generation, which invalidates any already-recorded escalate_resume approval bound to the old lease_generation; the operator would need to answer again.
- [14] Round-1 fix introduced an ordering contradiction: D2's last bullet says all four existing contract tests (including skills/tests/supervise/test_execution_contract.py) validate through dispatch_contract, but task 2.3a assigns test_execution_contract.py to wp-dispatch-schemas, a root package that lands before wp-contract-lib creates skills/shared/dispatch_contract.py. Followed literally, wp-dispatch-schemas cannot pass its own edit.
- [15] Task 5.2 makes roadmap-runtime/scripts/models.py depend on skills/shared/dispatch_contract.schema_registry; models.py has no skills/shared import today. Building the referencing.Registry locally from the schema directories inside models.py would avoid a new cross-skill dependency from the runtime foundation.
- [16] In a dispatched child, gate-answer compares only --approval-ref with the launch marker's gate_answer.approval_ref. It never checks --gate or --decision against gate_answer.gate/decision, so a child whose marker says {gate: proposal_approval, decision: rejected, approval_ref: R} can run gate-answer --decision approved --approval-ref R (or answer a different pending gate, or clear a park with a pending_gate answer) and record a human-provenance approval the supervisor never made. The spec requires the child to apply a gate decision only from the marker's gate_answer (skill-workflow 'Gate Authority and Re-Evaluation on Resume', design D5).
- [17] The dispatched-child gate-answer tests cover only a mismatched approval_ref. No test pins that a matching approval_ref with a different --decision or --gate is refused, which is how finding 1 went unnoticed.
- [18] apply_delegated_batch persists a permission_blocked result's parked.command verbatim: _terminal_attempt copies result['parked'] into the checkpoint attempt, and the application journal stores the whole result. Only the router's gate-decision record (parked_commands) is re-sanitized. checkpoint.json is a tracked file on a shared ref, and a result that did not come through runner.py park (hand-written, or from an older worker) can carry an unredacted credential; the apply-time re-derivation compares only the fingerprint (tool, rule, classifier_reason), not the command. Design D9 says the command is 're-sanitized by the router', and the supervise scenario requires the persisted command not to contain the secret. test_a_secret_in_the_blocked_command_is_redacted seeds the checkpoint attempt with the raw 'Bearer abc123...' value and checks only the record.
- [19] No test applies a permission_blocked result carrying a secret-bearing command and asserts that the persisted checkpoint (the attempt's parked payload and its application journal) contains no raw secret.
- [20] redact_command is not idempotent for auth headers: backtracking in \s* defeats the (?!\[REDACTED:) lookahead, so re-redacting 'Authorization: [REDACTED:auth-header]' rewrites it to 'Authorization:[REDACTED:auth-header]'. Harmless for secrecy, but the router's second pass changes already-redacted text.
- [21] Carried from IMPL_ITERATE: in a dispatched child whose posture digest drifted, a notify_with_timeout gate can still take its posture-derived timeout default; the spec forbids only auto there.
- [22] Carried from IMPL_ITERATE: emit-result does not cross-check --dispatch-id/--generation against the launch marker; the supervisor's identity check still rejects a mismatch at apply.
- [23] Carried from IMPL_ITERATE: rebind accepts a post-go attempt with no recorded evidence when only a worktree for its branch exists on this host (the evidence conditions hold vacuously).
- [24] _resolve_capability_park's proceed path falls back to records[0] when the attempt is not among the fingerprint's parked members (its checkpoint copy moved on); with no members that raises IndexError instead of a GateRefusalError.

Do not emit findings for issues already in the ledger except to re-verify the open items listed above.

### Instructions
Return findings as JSON with a top-level `findings` array.

This is round 1. Focus on remaining issues.