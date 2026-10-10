## Review Round 1

The packet is complete; do not explore the repo for missing artifacts.

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
diff --git a/openspec/changes/dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g3.json b/openspec/changes/dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g3.json
new file mode 100644
index 0000000..b11c55f
--- /dev/null
+++ b/openspec/changes/dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g3.json
@@ -0,0 +1,50 @@
+{
+  "attempt": 1,
+  "branch": "openspec/dispatch-contract",
+  "change_id": "dispatch-contract",
+  "degradations": [
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "IMPL_REVIEW"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "VAL_REVIEW"
+    },
+    {
+      "code": "coordinator_projection_forbidden",
+      "detail": "every project-state submit returned forbidden (trust-2 cloud agent)",
+      "phase": "SUBMIT_PR"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "audit sink failed for proposal_approval, escalate_resume, pr_creation, merge gate decisions",
+      "phase": "SUBMIT_PR"
+    }
+  ],
+  "dispatch_id": "batch-1199bf07b6cb5035d4c22472:ri-21:attempt-1",
+  "evidence": {
+    "commit": "45f9195322bc3f52fc4c18bbb5ce5c98e7a011fd",
+    "loop_state_digest": "b55ce362b3fcfcaf304c6770f1708b4946aed1e852a38c1ae8853a4ab893fb35",
+    "loop_state_path": "openspec/changes/dispatch-contract/loop-state.json"
+  },
+  "host_id": "machine-801452e4fd3b9a26",
+  "lease_generation": 3,
+  "outcome": "parked",
+  "parked": {
+    "deadline": null,
+    "gate": null,
+    "kind": "policy_pause",
+    "reason": "goal gate refused: validate record predates report",
+    "resume_hint": "previous_phase=SUBMIT_PR; answer escalate_resume to resume"
+  },
+  "schema_version": 2,
+  "worktree_ref": null
+}
diff --git a/openspec/changes/dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g4.json b/openspec/changes/dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g4.json
new file mode 100644
index 0000000..292e7ff
--- /dev/null
+++ b/openspec/changes/dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g4.json
@@ -0,0 +1,50 @@
+{
+  "attempt": 1,
+  "branch": "openspec/dispatch-contract",
+  "change_id": "dispatch-contract",
+  "degradations": [
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "IMPL_REVIEW"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "VAL_REVIEW"
+    },
+    {
+      "code": "coordinator_projection_forbidden",
+      "detail": "every project-state submit returned forbidden (trust-2 cloud agent)",
+      "phase": "SUBMIT_PR"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "audit sink failed for proposal_approval, escalate_resume, pr_creation, merge gate decisions",
+      "phase": "SUBMIT_PR"
+    }
+  ],
+  "dispatch_id": "batch-1199bf07b6cb5035d4c22472:ri-21:attempt-1",
+  "evidence": {
+    "commit": "bf613c97b74333336b11927489a1fe51c2d2f136",
+    "loop_state_digest": "20e8fa624f44682cf4064082a5b09393f6b7d09d6f25723024135295a645a2ee",
+    "loop_state_path": "openspec/changes/dispatch-contract/loop-state.json"
+  },
+  "host_id": "machine-dc39bf1e25efdf45",
+  "lease_generation": 4,
+  "outcome": "parked",
+  "parked": {
+    "deadline": null,
+    "gate": null,
+    "kind": "policy_pause",
+    "reason": "goal gate refused: required section not passed: Validation Review (missing)",
+    "resume_hint": "previous_phase=SUBMIT_PR; answer escalate_resume to resume"
+  },
+  "schema_version": 2,
+  "worktree_ref": "dispatch-contract"
+}
diff --git a/openspec/changes/dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g5.json b/openspec/changes/dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g5.json
new file mode 100644
index 0000000..2b3f4ab
--- /dev/null
+++ b/openspec/changes/dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g5.json
@@ -0,0 +1,54 @@
+{
+  "attempt": 1,
+  "branch": "openspec/dispatch-contract",
+  "change_id": "dispatch-contract",
+  "degradations": [
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "PLAN_REVIEW"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "IMPL_REVIEW"
+    },
+    {
+      "code": "single_vendor_review",
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "VAL_REVIEW"
+    },
+    {
+      "code": "coordinator_projection_forbidden",
+      "detail": "every project-state submit returned forbidden (trust-2 cloud agent)",
+      "phase": "SUBMIT_PR"
+    },
+    {
+      "code": "audit_sink_failed",
+      "detail": "audit sink failed for proposal_approval, escalate_resume, pr_creation, merge gate decisions",
+      "phase": "SUBMIT_PR"
+    }
+  ],
+  "dispatch_id": "batch-1199bf07b6cb5035d4c22472:ri-21:attempt-1",
+  "evidence": {
+    "commit": "ce23762b97c16ef4c1a6847584853e3794af2630",
+    "loop_state_digest": "bbede1b04fad897db34a3e1c77ade71745a334c50e83cf499ba60e86c6310b12",
+    "loop_state_path": "openspec/changes/dispatch-contract/loop-state.json"
+  },
+  "host_id": "machine-dc39bf1e25efdf45",
+  "lease_generation": 5,
+  "outcome": "parked",
+  "parked": {
+    "classifier_reason": "auto-mode classifier denied running the scratchpad converge() driver for VAL_REVIEW (Code from External)",
+    "command": "skills/.venv/bin/python <scratchpad>/vr5d/run_converge.py <worktree> <scratchpad>/vr5d/proto",
+    "deadline": null,
+    "gate": null,
+    "kind": "permission_blocked",
+    "reason": "permission denied for Bash under rule auto-mode-classifier:Code from External",
+    "resume_hint": null,
+    "rule": "auto-mode-classifier:Code from External",
+    "tool": "Bash"
+  },
+  "schema_version": 2,
+  "worktree_ref": "dispatch-contract"
+}
diff --git a/openspec/changes/dispatch-contract/loop-state.json b/openspec/changes/dispatch-contract/loop-state.json
index b606892..73f69fc 100644
--- a/openspec/changes/dispatch-contract/loop-state.json
+++ b/openspec/changes/dispatch-contract/loop-state.json
@@ -1,9 +1,9 @@
 {
   "schema_version": 6,
   "change_id": "dispatch-contract",
-  "current_phase": "SUBMIT_PR",
+  "current_phase": "VAL_REVIEW",
   "iteration": 0,
-  "total_iterations": 12,
+  "total_iterations": 17,
   "max_phase_iterations": 3,
   "findings_trend": [],
   "blocking_findings": [],
@@ -21,7 +21,8 @@
     "8d309935-3b68-44db-be5c-d6b327ec8c61",
     "13e77665-feba-4ef3-b28a-a9b61d278135",
     "8ebe1a5a-c868-49cc-b72d-f6bff31d85e9",
-    "c832cb1d-c7ab-48cb-9285-4f4b037d029a"
+    "c832cb1d-c7ab-48cb-9285-4f4b037d029a",
+    "c44fffaa-5096-400f-826a-c499391bb89e"
   ],
   "phase_history": [
     {
@@ -74,17 +75,28 @@
       "at": "2026-10-09T14:08:06.250432+00:00",
       "outcome": "converged",
       "phase": "VAL_REVIEW"
+    },
+    {
+      "at": "2026-10-10T09:52:41.398847+00:00",
+      "note": "Invalid outcome 'created' for phase 'ESCALATE'",
+      "outcome": "transition_failed",
+      "phase": "ESCALATE"
+    },
+    {
+      "at": "2026-10-10T10:06:25.827106+00:00",
+      "outcome": "passed",
+      "phase": "VALIDATE"
     }
   ],
-  "last_handoff_id": "c832cb1d-c7ab-48cb-9285-4f4b037d029a",
+  "last_handoff_id": "c44fffaa-5096-400f-826a-c499391bb89e",
   "started_at": "2026-10-06T09:08:58.470413+00:00",
-  "phase_started_at": "2026-10-09T14:08:09.206576+00:00",
-  "previous_phase": "PLAN_REVIEW",
-  "escalation_reason": "capability_unavailable: PLAN_REVIEW requires min_quorum=2; only claude_code is dispatchable (codex listed by --check-vendors but no codex CLI/credential). Quorum not lowered; awaiting operator decision on cloud review lane (GX10/policy/credential). handoff 9b138f6d-f5f3-4a7f-99bb-0d3bb6a5e86e",
+  "phase_started_at": "2026-10-10T10:06:28.528280+00:00",
+  "previous_phase": "SUBMIT_PR",
+  "escalation_reason": "goal gate refused: required section not passed: Validation Review (missing)",
   "val_review_enabled": true,
   "cli_review_enabled": true,
   "error": null,
-  "phase_archetype": "runner",
+  "phase_archetype": "validator",
   "force": false,
   "gate_signals": {},
   "gate_verdict": "proceed_with_review",
@@ -136,89 +148,214 @@
       "timeout_seconds": null
     },
     {
-      "gate": "pr_creation",
-      "outcome": "proceed",
-      "resolution": "auto",
-      "authorizing_disposition": "auto",
-      "reason": "gate 'pr_creation' auto-approved by trust posture",
       "approval_id": null,
+      "authorizing_disposition": "auto",
       "default_action": null,
-      "posture_present": true,
-      "notified": null,
-      "timeout_seconds": null,
-      "provenance": {
-        "source": "posture",
-        "posture_digest": "e8262346bb6004a61154ca0832650ed5ec4fa6a4d9b5cde30302333c0f067a24"
-      },
       "disposition": "auto",
+      "gate": "pr_creation",
+      "notified": null,
+      "outcome": "proceed",
       "phase": "SUBMIT_PR",
-      "recorded_at": "2026-10-09T14:08:17.017603+00:00"
+      "posture_present": true,
+      "provenance": {
+        "posture_digest": "e8262346bb6004a61154ca0832650ed5ec4fa6a4d9b5cde30302333c0f067a24",
+        "source": "posture"
+      },
+      "reason": "gate 'pr_creation' auto-approved by trust posture",
+      "recorded_at": "2026-10-09T14:08:17.017603+00:00",
+      "resolution": "auto",
+      "timeout_seconds": null
     },
     {
-      "gate": "merge",
-      "outcome": "blocked",
-      "resolution": "posture_block",
+      "approval_id": null,
       "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "merge",
+      "notified": null,
+      "outcome": "blocked",
+      "phase": "SUBMIT_PR",
+      "posture_present": true,
+      "provenance": {
+        "posture_digest": "e8262346bb6004a61154ca0832650ed5ec4fa6a4d9b5cde30302333c0f067a24",
+        "source": "posture"
+      },
       "reason": "gate 'merge' parked: trust posture disposition is block",
+      "recorded_at": "2026-10-09T14:09:04.031160+00:00",
+      "resolution": "posture_block",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "merge",
+      "note": "Operator approved merge in supervisor session 2026-10-09 ('merge both 662, 667, 666'); PR #667 merged as 0d078ff by the operator.",
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "SUBMIT_PR",
+      "posture_present": true,
+      "provenance": {
+        "approval_ref": "gate-decision:d2c8df05-dcfb-4133-a9d4-239e812c5620",
+        "source": "human"
+      },
+      "reason": "gate 'merge' approved by the operator \u2014 Operator approved merge in supervisor session 2026-10-09 ('merge both 662, 667, 666'); PR #667 merged as 0d078ff by the operator.",
+      "recorded_at": "2026-10-10T03:10:34.221320+00:00",
+      "resolution": "console_approved",
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
+      "provenance": {
+        "posture_digest": "e8262346bb6004a61154ca0832650ed5ec4fa6a4d9b5cde30302333c0f067a24",
+        "source": "posture"
+      },
+      "reason": "gate 'escalate_resume' parked: trust posture disposition is block",
+      "recorded_at": "2026-10-10T09:52:54.591188+00:00",
+      "resolution": "posture_block",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "note": "Operator resumed merged item ri-21 in supervisor session 2026-10-10 (decision fb5a1364, a4948ea); goal gate fixed in 1d79737 (VAL_REVIEW binds after VALIDATE).",
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "provenance": {
+        "approval_ref": "gate-decision:fb5a1364-f4d7-41ce-b1fb-f385d2261d4d",
+        "source": "human"
+      },
+      "reason": "gate 'escalate_resume' approved by the operator \u2014 Operator resumed merged item ri-21 in supervisor session 2026-10-10 (decision fb5a1364, a4948ea); goal gate fixed in 1d79737 (VAL_REVIEW binds after VALIDATE).",
+      "recorded_at": "2026-10-10T09:52:57.428960+00:00",
+      "resolution": "console_approved",
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
+      "provenance": {
+        "posture_digest": "e8262346bb6004a61154ca0832650ed5ec4fa6a4d9b5cde30302333c0f067a24",
+        "source": "posture"
+      },
+      "reason": "gate 'escalate_resume' parked: trust posture disposition is block",
+      "recorded_at": "2026-10-10T10:03:19.475199+00:00",
+      "resolution": "posture_block",
+      "timeout_seconds": null
+    },
+    {
+      "approval_id": null,
+      "authorizing_disposition": "block",
+      "default_action": null,
+      "disposition": "block",
+      "gate": "escalate_resume",
+      "note": "Operator re-validate decision 724eaee2 (supervisor, 2026-10-10): resume at VALIDATE so VALIDATE + VAL_REVIEW regenerate the report and its Validation Review section.",
+      "notified": null,
+      "outcome": "proceed",
+      "phase": "ESCALATE",
+      "posture_present": true,
+      "provenance": {
+        "approval_ref": "gate-decision:724eaee2-ea65-4edc-a891-f9ece3964707",
+        "source": "human"
+      },
+      "reason": "gate 'escalate_resume' approved by the operator \u2014 Operator re-validate decision 724eaee2 (supervisor, 2026-10-10): resume at VALIDATE so VALIDATE + VAL_REVIEW regenerate the report and its Validation Review section.",
+      "recorded_at": "2026-10-10T10:03:22.135499+00:00",
+      "resolution": "console_approved",
+      "timeout_seconds": null
+    },
+    {
+      "gate": "escalate_resume",
+      "outcome": "proceed",
+      "resolution": "console_approved",
+      "authorizing_disposition": "block",
+      "reason": "gate 'escalate_resume' approved by the operator \u2014 Operator chose 'Both' (supervisor 2026-10-10): unblock now; committed converge driver to follow.",
       "approval_id": null,
       "default_action": null,
-      "posture_present": true,
+      "posture_present": false,
       "notified": null,
       "timeout_seconds": null,
       "provenance": {
-        "source": "posture",
-        "posture_digest": "e8262346bb6004a61154ca0832650ed5ec4fa6a4d9b5cde30302333c0f067a24"
+        "source": "human",
+        "approval_ref": "gate-decision:1469b3d5-5478-4ab7-9bbd-dd6993bb998e"
       },
       "disposition": "block",
-      "phase": "SUBMIT_PR",
-      "recorded_at": "2026-10-09T14:09:04.031160+00:00"
+      "phase": "VAL_REVIEW",
+      "recorded_at": "2026-10-10T10:19:22.012039+00:00",
+      "note": "Operator chose 'Both' (supervisor 2026-10-10): unblock now; committed converge driver to follow."
     }
   ],
-  "pending_gate": {
-    "schema_version": 1,
-    "change_id": "dispatch-contract",
-    "gate": "merge",
-    "phase": "SUBMIT_PR",
-    "requested_at": "2026-10-09T14:09:04.032176+00:00",
-    "prompt": "Authorize merging this pull request? (autopilot records the authorization only; /cleanup-feature merges)",
-    "context": {
+  "pending_gate": null,
+  "goal_gate": {
+    "evidence": {
+      "bound_by": "VAL_REVIEW",
+      "checked_at": "2026-10-10T09:53:00.161786+00:00",
+      "merge_authorized": true,
+      "phase_statuses": {
+        "Spec Compliance": "pass",
+        "Validation Review": "missing"
+      },
       "pr_url": "https://github.com/jankneumann/agentic-coding-tools/pull/667",
-      "branch": "openspec/dispatch-contract",
-      "change_id": "dispatch-contract"
+      "report_mtime": "2026-10-09T14:08:04.183909+00:00",
+      "report_path": "openspec/changes/dispatch-contract/validation-report.md",
+      "report_time": "2026-10-09T14:06:06+00:00",
+      "report_time_source": "commit",
+      "required_sections": [
+        "Spec Compliance",
+        "Validation Review"
+      ],
+      "val_review_at": "2026-10-09T14:08:06.250432+00:00",
+      "validate_at": "2026-10-09T13:55:05.532741+00:00",
+      "validate_outcome": "passed"
     },
-    "posture": {
-      "disposition": "block",
-      "posture_present": true,
-      "posture_digest": "e8262346bb6004a61154ca0832650ed5ec4fa6a4d9b5cde30302333c0f067a24"
-    }
+    "reason": "required section not passed: Validation Review (missing)",
+    "verdict": "refused"
   },
-  "goal_gate": null,
   "park": null,
   "degradations": [
     {
       "code": "single_vendor_review",
-      "phase": "PLAN_REVIEW",
-      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)"
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "PLAN_REVIEW"
     },
     {
       "code": "single_vendor_review",
-      "phase": "IMPL_REVIEW",
-      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)"
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "IMPL_REVIEW"
     },
     {
       "code": "single_vendor_review",
-      "phase": "VAL_REVIEW",
-      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)"
+      "detail": "claude_code only; min_quorum=1 under cloud-container policy (TRUST_POSTURE.md 479dcd9)",
+      "phase": "VAL_REVIEW"
     },
     {
       "code": "coordinator_projection_forbidden",
-      "phase": "SUBMIT_PR",
-      "detail": "every project-state submit returned forbidden (trust-2 cloud agent)"
+      "detail": "every project-state submit returned forbidden (trust-2 cloud agent)",
+      "phase": "SUBMIT_PR"
     },
     {
       "code": "audit_sink_failed",
-      "phase": "SUBMIT_PR",
-      "detail": "audit sink failed for proposal_approval, escalate_resume, pr_creation, merge gate decisions"
+      "detail": "audit sink failed for proposal_approval, escalate_resume, pr_creation, merge gate decisions",
+      "phase": "SUBMIT_PR"
     }
   ]
 }
diff --git a/openspec/changes/dispatch-contract/session-log.md b/openspec/changes/dispatch-contract/session-log.md
index c14fcc1..d876b27 100644
--- a/openspec/changes/dispatch-contract/session-log.md
+++ b/openspec/changes/dispatch-contract/session-log.md
@@ -299,3 +299,27 @@ VALIDATE passed: spec compliance pass, 0 open tasks, openspec strict valid, ruff
 ### Context
 converge() ran VAL_REVIEW (review_type=implementation, fix_mode=targeted, min_quorum=1 from resolve_quorum_policy, base_ref=origin/openspec/roadmap-multiplayer-collaboration) and converged in round 2 with blocking trend [5, 0]. The critique checked whether validation-report.md proves each ri-21 outcome. Four medium gaps: outcome 6 overstated CI coverage (security.yml runs gitleaks only for main, so this change's PR never triggers it); outcome 4 had no test clearing a posture-derived capability-fingerprint block after a posture flip; outcome 7's cross-host tests shared one repo root; outcome 5 was proven only piecewise. VAL_FIX (inline, claude_code) added three tests and corrected the report. No production code changed. The closure test (outcome 3) was confirmed to enumerate every schema-permitted kind/gate from the schema, independently of ANSWER_PATHS, which is built from the Gate enum.
 
+---
+
+## Phase: Validate (re-validation) (2026-10-10)
+
+**Agent**: claude_code | **Session**: N/A
+
+### Decisions
+1. **Report regenerated, no Validation Review section** `architectural: validation` — VAL_REVIEW writes it next; goal gate binds after VALIDATE
+
+### Completed Work
+- Ran 8 suites in separate processes
+- ruff on 51 changed files
+- openspec validate --strict
+- regenerated validation-report.md
+
+### Next Steps
+- VAL_REVIEW appends ## Validation Review
+
+### Relevant Files
+- `openspec/changes/dispatch-contract/validation-report.md` — regenerated report
+
+### Context
+Re-validation at c83cf40 (gate-decision 724eaee2, gen 5): passed. Spec Compliance pass; 1,747 passed/24 skipped/1 known env-only failure; ruff clean; openspec strict valid; gate_logic action=continue. Outcome 6 caveat stands: only a Python port of gitleaks generic-api-key ran; first real full-ruleset scan is PR #662 Security job. CI DEGRADED (no run for head).
+
diff --git a/openspec/changes/dispatch-contract/validation-report.md b/openspec/changes/dispatch-contract/validation-report.md
index 8e6e543..b0bbe81 100644
--- a/openspec/changes/dispatch-contract/validation-report.md
+++ b/openspec/changes/dispatch-contract/validation-report.md
@@ -1,8 +1,17 @@
 # Validation Report: dispatch-contract
 
-**Date**: 2026-10-09
-**Commit**: 7cc9180c3ea49a0a9b08618d376bf0c2793bdccc (VALIDATE); counts and evidence refreshed in VAL_REVIEW at df3b98e
-**Branch**: openspec/dispatch-contract
+**Date**: 2026-10-10
+**Commit**: c83cf40 (branch head on origin; re-validation, operator gate-decision 724eaee2, lease generation 5)
+**Branch**: openspec/dispatch-contract (merged via PR #667 as 0d078ff)
+
+This report was regenerated against the current head. It supersedes the 2026-10-09 report (VALIDATE at 7cc9180,
+VAL_REVIEW at df3b98e). Code under test now includes the PR #667 review fixes (765f9d8 resume only the recorded
+escalation subject's dispatches; b35e544 keep a repo-root harness isolation as the portable ref "."; 43a9b11
+single-flight capability/permission park resolution; 6a0a096 records them), the post-merge fixes 4955e24
+(digest-only launch tokens in the live checkpoint), c04a1a8 (accept an already-migrated live checkpoint),
+789705a (verified isolation mode in the attempt profile), and the cherry-picked goal-gate fix f44bbd6 (goal gate binds
+to the report's last writer and commit time, so VAL_REVIEW binds after VALIDATE) and resume-at-VALIDATE commits
+(3a29785, c83cf40).
 
 Scope: skills scripts, shared libraries, and JSON schemas only. There is no deployable
 service (no docker-compose, agent-coordinator/, packages/ or apps/ path changed; the only
@@ -19,9 +28,9 @@ phases are therefore not applicable, not skipped.
 - Architecture: not run (advisory; no service/graph consumer touched)
 - Task drift: pass (0 unchecked boxes in tasks.md)
 - OpenSpec: pass (`openspec validate dispatch-contract --strict`: valid)
-- Lint: pass (`ruff check` on every changed Python file/dir: all checks passed)
-- Test suites: pass except the known environment-only failure (see Spec Compliance)
-- CI/CD: DEGRADED (not checked; GitHub MCP lists zero workflow runs for branch openspec/dispatch-contract and no PR exists yet)
+- Lint: pass (`ruff check` on all 51 Python files changed since base bdb0048: all checks passed)
+- Test suites: pass except the known environment-only failure (see Spec Compliance); worktree, cleanup-feature and validate-feature suites not run (not touched; environment-only failures identical at base)
+- CI/CD: DEGRADED (not applicable to this head: GitHub lists exactly one run for branch openspec/dispatch-contract, CI #2056 on 2e45ea7, the pre-merge PR head, conclusion success; no run exists for c83cf40)
 - Choices: no ledger
 
 ## Spec Compliance
@@ -32,18 +41,21 @@ Per-directory results (each `skills/tests/<dir>` run in its own process, base-in
 
 | Suite | Result |
 |---|---|
-| skills/tests/autopilot | 533 passed, 6 skipped |
-| skills/tests/autopilot-roadmap | 146 passed |
+| skills/tests/autopilot | 544 passed, 6 skipped |
+| skills/tests/autopilot-roadmap | 147 passed |
 | skills/tests/install_sh | 18 passed, 14 skipped |
 | skills/tests/parallel-infrastructure | 292 passed, 2 skipped |
 | skills/tests/roadmap-runtime | 182 passed, 1 skipped |
-| skills/tests/shared | 134 passed, 1 skipped |
-| skills/tests/supervise | 459 passed, 1 failed (known) |
-| skills/autopilot/scripts/tests/test_autopilot.py | 48 passed |
+| skills/tests/shared | 136 passed, 1 skipped |
+| skills/tests/supervise | 469 passed, 1 failed (known) |
+| skills/autopilot/scripts/tests | 227 passed |
+
+Totals: 1,747 passed, 24 skipped, 1 failed (known environment-only). The two project-context-refresh
+shared-checkout tests are outside the touched suites and were not run. `openspec validate dispatch-contract --strict`: valid.
 
 The single failure is the documented environment-only
 `test_workflow_contract.py::test_contract_inspects_the_canonical_source_contribution`
-(fails identically at base bdb0048 when run under a `.claude/` path). No other failures.
+(fails identically at base bdb0048 when run under a `.claude/` path; this run is under `.claude/worktrees/`). No other failures.
 
 ### Acceptance outcome to test mapping (proposal.md, ri-21)
 
@@ -85,7 +97,7 @@ The single failure is the documented environment-only
      `test_an_operator_approval_ends_a_human_rejected_escalation`, `test_an_approval_resumes_a_member_that_joined_after_the_rejection`).
 5. execution_profile, review_requirements, degradations[] carried end to end; capability parks routed as single escalations: pass.
    End to end: `autopilot-roadmap/test_dispatch_contract_e2e.py::test_profile_and_degradations_travel_the_whole_chain`
-   (added in VAL_REVIEW: request, launch marker, `runner.py record-degradation`, emit-result, apply, attempt record and
+   (request, launch marker, `runner.py record-degradation`, emit-result, apply, attempt record and
    apply return value) and `::test_a_capability_park_is_one_operator_escalation_that_resumes_the_child`.
    Units: `autopilot/test_emit_result.py::test_degradations_travel_into_the_result`,
    `supervise/test_execution.py` (`test_a_marker_carries_the_supervisor_view_but_no_token`, `test_apply_persists_degradations_on_the_attempt`,
@@ -122,6 +134,16 @@ The single failure is the documented environment-only
    `autopilot-roadmap/test_dispatch_contract_e2e.py::test_a_dispatched_child_with_a_marker_ref_takes_scoped_auto`,
    `::test_a_standalone_run_blocks_with_scope_unscoped`.
 
+## Deploy
+
+**Status**: N/A
+Reason: work-packages.yaml `feature.deployable: false`; no service to deploy.
+
+## CI/CD
+
+**Status**: DEGRADED
+Reason: no CI run exists for branch head c83cf40. The only run for the branch is CI #2056 on 2e45ea7 (success, pre-merge PR head). Local suites above are the evidence.
+
 ## Smoke Tests
 
 **Status**: not applicable
@@ -141,8 +163,10 @@ Reason: no browser or service surface.
 
 - single_vendor_review: PLAN_REVIEW, IMPL_REVIEW and VAL_REVIEW ran claude_code only (cloud-container policy, min_quorum=1).
 - coordinator_projection_forbidden: coordinator queue projection returned forbidden (expected in this environment).
+- audit_sink_failed: audit sink failed for the proposal_approval, escalate_resume, pr_creation and merge gate decisions (SUBMIT_PR).
 - GATEKEEPER ran via a real judge (no degradation).
+- Re-validation: no new reviewer was dispatched in this VALIDATE run; VAL_REVIEW runs next and appends its own section.
 
 ## Result
 
-**PASS** — All eight acceptance outcomes are covered by passing tests. Outcome 6's secret-scan claim rests on a one-rule port locally; the real default-ruleset gitleaks scan first runs in PR #662's Security job and must pass there before the claim is confirmed. Other not-run items are recorded above (CI status, live-service phases). Ready for `/cleanup-feature dispatch-contract`.
+**PASS** (re-validation at c83cf40) — All eight acceptance outcomes are covered by passing tests. Outcome 6's secret-scan claim rests on a one-rule port locally; the real default-ruleset gitleaks scan first runs in PR #662's Security job and must pass there before the claim is confirmed. Other not-run items are recorded above (CI status, live-service phases). The change is already merged (PR #667, 0d078ff); this report exists so the goal gate can bind VAL_REVIEW after VALIDATE.
diff --git a/openspec/schemas/dispatch-request.schema.json b/openspec/schemas/dispatch-request.schema.json
index 6267f2a..0645d57 100644
--- a/openspec/schemas/dispatch-request.schema.json
+++ b/openspec/schemas/dispatch-request.schema.json
@@ -195,7 +195,11 @@
         },
         "decision": {"enum": ["approved", "rejected"]},
         "approval_ref": {"$ref": "#/$defs/ApprovalRef"},
-        "provenance": {"$ref": "#/$defs/Provenance"}
+        "provenance": {"$ref": "#/$defs/Provenance"},
+        "resume_at": {
+          "enum": ["VALIDATE"],
+          "description": "Operator-approved escalate_resume target: re-run VALIDATE instead of resuming the parked phase."
+        }
       }
     },
     "Provenance": {
diff --git a/skills/autopilot/scripts/autopilot.py b/skills/autopilot/scripts/autopilot.py
index 23dbaa3..bd7d8e7 100644
--- a/skills/autopilot/scripts/autopilot.py
+++ b/skills/autopilot/scripts/autopilot.py
@@ -272,7 +272,10 @@ TRANSITIONS: dict[str, dict[str, str]] = {
     "VAL_REVIEW": {"converged": "SUBMIT_PR", "not_converged": "VAL_FIX", "max_iter": "ESCALATE"},
     "VAL_FIX": {"fixed": "VALIDATE", "stuck": "ESCALATE"},
     "SUBMIT_PR": {"created": "DONE"},
-    "ESCALATE": {"resolved": "_previous_phase", "abandoned": "DONE"},
+    # "revalidate" exists only for an operator-approved escalate_resume that
+    # names resume_at=VALIDATE: evidence the goal gate refused is regenerated
+    # by this run instead of being edited after the fact.
+    "ESCALATE": {"resolved": "_previous_phase", "revalidate": "VALIDATE", "abandoned": "DONE"},
 }
 
 
diff --git a/skills/autopilot/scripts/goal_gate.py b/skills/autopilot/scripts/goal_gate.py
index e0ede0c..6f44b2d 100644
--- a/skills/autopilot/scripts/goal_gate.py
+++ b/skills/autopilot/scripts/goal_gate.py
@@ -14,6 +14,13 @@ the same change; the history entry alone is only the sub-agent's self-report wit
 no artifact behind it. Requiring the history entry to postdate the report is what
 binds the artifact to this run.
 
+The binding record is the report's last legitimate writer: the latest VALIDATE
+``passed`` entry, or, when VAL_REVIEW is enabled, a VAL_REVIEW ``converged`` entry
+after it (VAL_REVIEW appends its own required section to the same report). The
+report's time is its last commit when the committed copy is unmodified (a
+checkout resets mtime, so mtime would make every fresh clone look stale), and its
+mtime otherwise.
+
 The module deliberately imports nothing from ``autopilot.py``: ``state`` is used
 structurally (``.phase_history``, ``.val_review_enabled``) so that ``autopilot``
 can import this module without a cycle.
@@ -21,6 +28,7 @@ can import this module without a cycle.
 
 from __future__ import annotations
 
+import subprocess
 import sys
 from dataclasses import dataclass, field
 from datetime import datetime, timezone
@@ -77,6 +85,52 @@ def _latest_validate_entry(history: Any) -> dict[str, Any] | None:
     return None
 
 
+def _binding_entry(history: Any, *, val_review_enabled: bool) -> dict[str, Any] | None:
+    """The record that must postdate the report: the latest VAL_REVIEW
+    ``converged`` entry after the latest VALIDATE when VAL_REVIEW is enabled,
+    else the latest VALIDATE entry. ``None`` when VAL_REVIEW is enabled but has
+    not converged since that VALIDATE (the VALIDATE entry then binds)."""
+    if not val_review_enabled or not isinstance(history, list):
+        return None
+    for entry in reversed(history):
+        if not isinstance(entry, dict):
+            continue
+        if entry.get("phase") == "VALIDATE":
+            return None
+        if entry.get("phase") == "VAL_REVIEW" and entry.get("outcome") == "converged":
+            return entry
+    return None
+
+
+def _git(change_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
+    return subprocess.run(
+        ["git", "-C", str(change_dir), *args],
+        capture_output=True,
+        text=True,
+        check=False,
+        timeout=30,
+    )
+
+
+def _report_time(report_path: Path) -> tuple[datetime, str]:
+    """``(time, source)``: the last commit touching the report when the working
+    copy matches it, else the file's mtime."""
+    name = report_path.name
+    cwd = report_path.parent
+    try:
+        tracked = _git(cwd, "ls-files", "--error-unmatch", "--", name).returncode == 0
+        clean = tracked and _git(cwd, "diff", "--quiet", "HEAD", "--", name).returncode == 0
+        if clean:
+            stamp = _git(cwd, "log", "-1", "--format=%cI", "--", name).stdout.strip()
+            parsed = _parse_timestamp(stamp)
+            if parsed is not None:
+                return parsed, "commit"
+    except (OSError, subprocess.SubprocessError):
+        pass
+    mtime = datetime.fromtimestamp(report_path.stat().st_mtime, tz=timezone.utc)
+    return mtime, "mtime"
+
+
 def _parse_timestamp(raw: Any) -> datetime | None:
     if not isinstance(raw, str):
         return None
@@ -108,8 +162,8 @@ def check_goal_gate(
     """Decide whether the loop has earned DONE.
 
     Returns ``passed`` only when every required report section reads ``pass``
-    AND the latest VALIDATE history entry is ``passed`` and not older than the
-    report file. Any other outcome is ``refused`` with a reason naming the one
+    AND the latest VALIDATE history entry is ``passed`` and its binding record
+    (that entry, or a later converged VAL_REVIEW) is not older than the report. Any other outcome is ``refused`` with a reason naming the one
     condition that failed. ``now`` is injectable so the recorded ``checked_at``
     is deterministic under test.
     """
@@ -139,13 +193,24 @@ def check_goal_gate(
     if not report_path.is_file():
         return GoalGateVerdict("refused", REASON_REPORT_MISSING, evidence)
 
-    # mtime, not a git timestamp: validate-feature writes the report inside an
-    # ephemeral worktree and copies it back, so mtime is the moment the report
-    # became visible to this loop — the comparison that proves the report is
-    # this run's, and one that does not require the report to be committed.
-    report_mtime = datetime.fromtimestamp(report_path.stat().st_mtime, tz=timezone.utc)
-    evidence["report_mtime"] = report_mtime.isoformat()
-    if validated_at < report_mtime:
+    # An uncommitted or untracked report (validate-feature writes it inside an
+    # ephemeral worktree and copies it back) is timed by mtime, the moment it
+    # became visible to this loop; a committed, unmodified one by its commit.
+    report_time, source = _report_time(report_path)
+    evidence["report_time"] = report_time.isoformat()
+    evidence["report_time_source"] = source
+    bound_at = validated_at
+    evidence["bound_by"] = "VALIDATE"
+    review = _binding_entry(
+        getattr(state, "phase_history", None),
+        val_review_enabled=getattr(state, "val_review_enabled", False),
+    )
+    reviewed_at = _parse_timestamp(review.get("at")) if review else None
+    if reviewed_at is not None and reviewed_at > bound_at:
+        bound_at = reviewed_at
+        evidence["bound_by"] = "VAL_REVIEW"
+        evidence["val_review_at"] = review.get("at") if review else None
+    if bound_at < report_time:
         return GoalGateVerdict("refused", REASON_STALE_REPORT, evidence)
 
     required = _required_sections(state, change_dir)
diff --git a/skills/autopilot/scripts/runner.py b/skills/autopilot/scripts/runner.py
index 4803f23..51202ec 100644
--- a/skills/autopilot/scripts/runner.py
+++ b/skills/autopilot/scripts/runner.py
@@ -431,6 +431,22 @@ def _cmd_gate_answer(args: argparse.Namespace) -> int:
             "nothing was recorded\n"
         )
         return 2
+    resume_at = getattr(args, "resume_at", None)
+    if resume_at is not None and (
+        args.gate != Gate.ESCALATE_RESUME.value or args.decision != "approved"
+    ):
+        sys.stderr.write(
+            "runner: --resume-at applies only to an approved escalate_resume; "
+            "nothing was recorded\n"
+        )
+        return 2
+    if marker is not None and resume_at != marker_answer.get("resume_at"):
+        # The resume target is part of the supervisor's answer, never the child's.
+        sys.stderr.write(
+            "runner: --resume-at does not match the launch marker's gate_answer "
+            f"({marker_answer.get('resume_at')!r}); nothing was recorded\n"
+        )
+        return 2
     if marker is not None and (
         args.gate != marker_answer.get("gate") or args.decision != marker_answer.get("decision")
     ):
@@ -500,6 +516,8 @@ def _cmd_gate_answer(args: argparse.Namespace) -> int:
         return 0
 
     outcome = str(edge.get("outcome", ""))
+    if resume_at == "VALIDATE" and outcome == "resolved":
+        outcome = "revalidate"
     if edge.get("target") == "ESCALATE":
         # enter_escalate (not the bare table edge) so previous_phase and
         # escalation_reason are populated for the resume path.
@@ -1093,6 +1111,16 @@ def _build_parser() -> argparse.ArgumentParser:
             "that differs from its launch marker's."
         ),
     )
+    ga.add_argument(
+        "--resume-at",
+        default=None,
+        choices=["VALIDATE"],
+        help=(
+            "Resume an approved escalate_resume at VALIDATE instead of the parked "
+            "phase, so validation evidence is regenerated by this run. Must match "
+            "the launch marker's gate_answer when one is present."
+        ),
+    )
     ga.set_defaults(func=_cmd_gate_answer)
 
     pk = sub.add_parser(
diff --git a/skills/roadmap-runtime/install_assets/openspec/schemas/dispatch-request.schema.json b/skills/roadmap-runtime/install_assets/openspec/schemas/dispatch-request.schema.json
index 6267f2a..0645d57 100644
--- a/skills/roadmap-runtime/install_assets/openspec/schemas/dispatch-request.schema.json
+++ b/skills/roadmap-runtime/install_assets/openspec/schemas/dispatch-request.schema.json
@@ -195,7 +195,11 @@
         },
         "decision": {"enum": ["approved", "rejected"]},
         "approval_ref": {"$ref": "#/$defs/ApprovalRef"},
-        "provenance": {"$ref": "#/$defs/Provenance"}
+        "provenance": {"$ref": "#/$defs/Provenance"},
+        "resume_at": {
+          "enum": ["VALIDATE"],
+          "description": "Operator-approved escalate_resume target: re-run VALIDATE instead of resuming the parked phase."
+        }
       }
     },
     "Provenance": {
diff --git a/skills/supervise/scripts/cycle_state.py b/skills/supervise/scripts/cycle_state.py
index 2e67e70..91782f4 100644
--- a/skills/supervise/scripts/cycle_state.py
+++ b/skills/supervise/scripts/cycle_state.py
@@ -1287,6 +1287,8 @@ def _cmd_gate_answer(args: argparse.Namespace) -> int:
         context["dispatch_id"] = args.dispatch_id
     if args.lease_generation is not None:
         context["lease_generation"] = args.lease_generation
+    if getattr(args, "resume_at", None):
+        context["resume_at"] = args.resume_at
 
     try:
         routed = gate_router.answer(
@@ -1364,6 +1366,10 @@ def main(argv: list[str] | None = None) -> int:
     p_gate_answer.add_argument("--note")
     p_gate_answer.add_argument("--dispatch-id", dest="dispatch_id")
     p_gate_answer.add_argument("--lease-generation", dest="lease_generation", type=int)
+    p_gate_answer.add_argument(
+        "--resume-at", dest="resume_at", choices=["VALIDATE"],
+        help="escalate_resume only: resume the child at VALIDATE instead of its parked phase.",
+    )
 
     p_gate_log = sub.add_parser("gate-log", help="Print the sidecar + child gate_decisions for a roadmap (D6).")
     p_gate_log.add_argument("--roadmap", required=True)
diff --git a/skills/supervise/scripts/execution.py b/skills/supervise/scripts/execution.py
index 221fbea..406a1ff 100644
--- a/skills/supervise/scripts/execution.py
+++ b/skills/supervise/scripts/execution.py
@@ -328,6 +328,8 @@ def _gate_answer(checkpoint: Any, attempt: Mapping[str, Any]) -> dict[str, Any]
     provenance = record.get("provenance")
     if isinstance(provenance, Mapping) and provenance.get("source") in {"posture", "human"}:
         answer["provenance"] = dict(provenance)
+    if record.get("resume_at") == "VALIDATE" and answer["decision"] == "approved":
+        answer["resume_at"] = "VALIDATE"
     return answer
 
 
diff --git a/skills/supervise/scripts/gate_router.py b/skills/supervise/scripts/gate_router.py
index a3e43f8..8b5800f 100644
--- a/skills/supervise/scripts/gate_router.py
+++ b/skills/supervise/scripts/gate_router.py
@@ -963,6 +963,7 @@ def answer(
     IS the human answer."""
     gate_enum = gate if isinstance(gate, Gate) else Gate(gate)
     ctx = dict(context or {})
+    resume_at = ctx.get("resume_at")
     workspace = Path(workspace)
     repo_root = Path(repo_root)
     moment = now or datetime.now(timezone.utc)
@@ -1029,6 +1030,10 @@ def answer(
     extra = _correlation_extra(gate_enum, ctx, roadmap=roadmap, fingerprint=fingerprint, verb=verb)
     if note is not None:
         extra["note"] = note
+    if resume_at is not None:
+        if gate_enum is not Gate.ESCALATE_RESUME or not approved or resume_at != "VALIDATE":
+            raise GateRefusalError("resume_at=VALIDATE applies only to an approved escalate_resume")
+        extra["resume_at"] = resume_at
     record = build_gate_decision_record(decision, phase=_PHASE, extra=extra)
     # Project before persisting -- a `GateRefusalError` (e.g. a blocked answer
     # naming no `change_id`) must never follow a partial write.
diff --git a/skills/tests/autopilot/test_console_interviewer.py b/skills/tests/autopilot/test_console_interviewer.py
index 11cdfe4..81b6298 100644
--- a/skills/tests/autopilot/test_console_interviewer.py
+++ b/skills/tests/autopilot/test_console_interviewer.py
@@ -326,3 +326,67 @@ def test_apply_outcome_still_works_when_no_gate_is_pending(workspace: Path) -> N
 
     assert rc == 0
     assert read_state(state_path)["last_handoff_id"] == "h-1"
+
+
+# ---------------------------------------------------------------------------
+# escalate_resume --resume-at VALIDATE (operator-approved re-validation)
+# ---------------------------------------------------------------------------
+
+
+def _escalated_after_goal_gate(workspace: Path) -> Path:
+    return seed(
+        workspace,
+        pending=pending_request(
+            Gate.ESCALATE_RESUME,
+            phase="ESCALATE",
+            edge={"outcome": "resolved", "target": "SUBMIT_PR"},
+            context={"escalation_reason": "goal gate refused", "previous_phase": "SUBMIT_PR"},
+        ),
+        current_phase="ESCALATE",
+        previous_phase="SUBMIT_PR",
+    )
+
+
+def test_resume_at_validate_reruns_validation_instead_of_the_parked_phase(
+    workspace: Path,
+) -> None:
+    state_path = _escalated_after_goal_gate(workspace)
+
+    rc = runner.main([
+        "gate-answer", "demo", "--gate", "escalate_resume", "--decision", "approved",
+        "--resume-at", "VALIDATE",
+    ])
+
+    assert rc == 0
+    state = read_state(state_path)
+    assert state["current_phase"] == "VALIDATE"
+    assert state["pending_gate"] is None
+    assert state["gate_decisions"][-1]["resolution"] == "console_approved"
+
+
+def test_without_resume_at_the_parked_phase_resumes(workspace: Path) -> None:
+    state_path = _escalated_after_goal_gate(workspace)
+
+    rc = runner.main([
+        "gate-answer", "demo", "--gate", "escalate_resume", "--decision", "approved",
+    ])
+
+    assert rc == 0
+    assert read_state(state_path)["current_phase"] == "SUBMIT_PR"
+
+
+@pytest.mark.parametrize(
+    "argv",
+    [
+        ["--gate", "escalate_resume", "--decision", "rejected", "--resume-at", "VALIDATE"],
+        ["--gate", "proposal_approval", "--decision", "approved", "--resume-at", "VALIDATE"],
+    ],
+)
+def test_resume_at_is_refused_outside_an_approved_escalate_resume(
+    workspace: Path, argv: list[str]
+) -> None:
+    state_path = _escalated_after_goal_gate(workspace)
+    before = state_path.read_bytes()
+
+    assert runner.main(["gate-answer", "demo", *argv]) == 2
+    assert state_path.read_bytes() == before
diff --git a/skills/tests/autopilot/test_goal_gate.py b/skills/tests/autopilot/test_goal_gate.py
index 6166402..a1d332a 100644
--- a/skills/tests/autopilot/test_goal_gate.py
+++ b/skills/tests/autopilot/test_goal_gate.py
@@ -328,3 +328,110 @@ def test_verdict_is_frozen(tmp_path: Path) -> None:
 
     with pytest.raises(FrozenInstanceError):
         verdict.verdict = "refused"  # type: ignore[misc]
+
+
+# ---------------------------------------------------------------------------
+# Binding record and report time (VAL_REVIEW appends to the report; a checkout
+# resets mtime)
+# ---------------------------------------------------------------------------
+
+def review_entry(offset_seconds: int, outcome: str = "converged") -> dict[str, Any]:
+    at = REPORT_MTIME + timedelta(seconds=offset_seconds)
+    return {"phase": "VAL_REVIEW", "outcome": outcome, "at": at.isoformat()}
+
+
+def _review_sections() -> dict[str, str]:
+    return {"Spec Compliance": "pass", "Validation Review": "pass"}
+
+
+def test_converged_val_review_binds_a_report_it_appended_to(tmp_path: Path) -> None:
+    """VALIDATE passed, then VAL_REVIEW appended its section (report touched
+    after VALIDATE) and converged: the review record binds the report."""
+    change_dir = write_change_dir(tmp_path, sections=_review_sections())
+    state = FakeState(
+        phase_history=[validate_entry(-120), review_entry(60)], val_review_enabled=True
+    )
+    verdict = check(state, change_dir)
+
+    assert verdict.verdict == "passed"
+    assert verdict.evidence["bound_by"] == "VAL_REVIEW"
+
+
+def test_unconverged_val_review_does_not_bind(tmp_path: Path) -> None:
+    change_dir = write_change_dir(tmp_path, sections=_review_sections())
+    state = FakeState(
+        phase_history=[validate_entry(-120), review_entry(60, outcome="max_iter")],
+        val_review_enabled=True,
+    )
+    verdict = check(state, change_dir)
+
+    assert verdict.verdict == "refused"
+    assert verdict.reason == goal_gate.REASON_STALE_REPORT
+
+
+def test_val_review_before_the_latest_validate_does_not_bind(tmp_path: Path) -> None:
+    """A review that converged before a later VALIDATE run reviewed an older report."""
+    change_dir = write_change_dir(tmp_path, sections=_review_sections())
+    state = FakeState(
+        phase_history=[review_entry(60), validate_entry(-120)], val_review_enabled=True
+    )
+    verdict = check(state, change_dir)
+
+    assert verdict.reason == goal_gate.REASON_STALE_REPORT
+
+
+def test_val_review_does_not_bind_when_disabled(tmp_path: Path) -> None:
+    change_dir = write_change_dir(tmp_path)
+    state = FakeState(phase_history=[validate_entry(-120), review_entry(60)])
+    verdict = check(state, change_dir)
+
+    assert verdict.reason == goal_gate.REASON_STALE_REPORT
+
+
+def _git(cwd: Path, *args: str, when: datetime | None = None) -> None:
+    import subprocess
+
+    env = dict(os.environ)
+    if when is not None:
+        env["GIT_COMMITTER_DATE"] = env["GIT_AUTHOR_DATE"] = when.isoformat()
+    subprocess.run(
+        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
+        cwd=cwd, env=env, check=True, capture_output=True,
+    )
+
+
+def _committed_change_dir(tmp_path: Path, committed_at: datetime) -> Path:
+    change_dir = write_change_dir(tmp_path)
+    _git(tmp_path, "init", "-q")
+    _git(tmp_path, "add", "-A")
+    _git(tmp_path, "commit", "-q", "-m", "report", when=committed_at)
+    # A checkout or clone stamps the file with "now", long after validation.
+    stamp = FROZEN_NOW.timestamp()
+    os.utime(change_dir / "validation-report.md", (stamp, stamp))
+    return change_dir
+
+
+def test_a_committed_unmodified_report_is_timed_by_its_commit(tmp_path: Path) -> None:
+    change_dir = _committed_change_dir(tmp_path, REPORT_MTIME)
+    verdict = check(FakeState(phase_history=[validate_entry(60)]), change_dir)
+
+    assert verdict.verdict == "passed"
+    assert verdict.evidence["report_time_source"] == "commit"
+
+
+def test_a_report_committed_after_validation_is_stale(tmp_path: Path) -> None:
+    change_dir = _committed_change_dir(tmp_path, REPORT_MTIME + timedelta(seconds=120))
+    verdict = check(FakeState(phase_history=[validate_entry(60)]), change_dir)
+
+    assert verdict.reason == goal_gate.REASON_STALE_REPORT
+    assert verdict.evidence["report_time_source"] == "commit"
+
+
+def test_an_uncommitted_edit_falls_back_to_mtime(tmp_path: Path) -> None:
+    change_dir = _committed_change_dir(tmp_path, REPORT_MTIME)
+    report = change_dir / "validation-report.md"
+    report.write_text(report.read_text() + "\nedited after validation\n")
+    verdict = check(FakeState(phase_history=[validate_entry(60)]), change_dir)
+
+    assert verdict.reason == goal_gate.REASON_STALE_REPORT
+    assert verdict.evidence["report_time_source"] == "mtime"
diff --git a/skills/tests/supervise/test_execution_contract.py b/skills/tests/supervise/test_execution_contract.py
index 179a7f5..70fe5aa 100644
--- a/skills/tests/supervise/test_execution_contract.py
+++ b/skills/tests/supervise/test_execution_contract.py
@@ -349,3 +349,43 @@ def test_checkpoint_attempts_and_results_are_single_definitions() -> None:
     assert attempt["properties"]["application_journal"]["properties"]["result"] == {
         "$ref": result_v2["$id"]
     }
+
+
+def test_gate_answer_may_name_validate_as_the_resume_target(
+    validators: dict[str, Draft202012Validator],
+) -> None:
+    request = _v2_request()
+    request["lease_generation"] = 2
+    request["continuation"] = {
+        "kind": "policy_pause",
+        "approval_ref": "gate-decision:33333333-4444-4555-8666-777777777777",
+    }
+    request["gate_answer"] = {
+        "gate": "escalate_resume",
+        "decision": "approved",
+        "approval_ref": "gate-decision:33333333-4444-4555-8666-777777777777",
+        "resume_at": "VALIDATE",
+    }
+    assert _errors(validators["request_v2"], request) == []
+    request["gate_answer"]["resume_at"] = "IMPLEMENT"
+    assert _errors(validators["request_v2"], request)
+
+
+def test_the_continuation_answer_carries_the_recorded_resume_target() -> None:
+    from types import SimpleNamespace
+
+    import execution
+
+    ref = "gate-decision:33333333-4444-4555-8666-777777777777"
+    record = {
+        "decision_id": ref.removeprefix("gate-decision:"),
+        "gate": "escalate_resume",
+        "outcome": "proceed",
+        "resume_at": "VALIDATE",
+    }
+    checkpoint = SimpleNamespace(gate_decisions=[record])
+    attempt = {"continuation": {"kind": "policy_pause", "approval_ref": ref}}
+
+    assert execution._gate_answer(checkpoint, attempt)["resume_at"] == "VALIDATE"
+    record.pop("resume_at")
+    assert "resume_at" not in execution._gate_answer(checkpoint, attempt)
diff --git a/skills/tests/supervise/test_gate_router.py b/skills/tests/supervise/test_gate_router.py
index 2f13400..f1409b4 100644
--- a/skills/tests/supervise/test_gate_router.py
+++ b/skills/tests/supervise/test_gate_router.py
@@ -1535,3 +1535,30 @@ def test_cycle_state_gate_answer_covers_a_pending_escalate_resume_park(
     assert payload["outcome"] == "proceed"
     assert payload["lease_generation"] == 3
     assert _resolve_current(repo, workspace, adapter).outcome == "proceed"
+
+
+def test_escalate_resume_answer_records_resume_at_validate(repo: Path, workspace: Path) -> None:
+    _save_escalation_checkpoint(repo, workspace)
+
+    routed = gate_router.answer(
+        Gate.ESCALATE_RESUME, workspace=workspace, repo_root=repo, approved=True,
+        context={"dispatch_id": "d-1", "resume_at": "VALIDATE"},
+    )
+
+    assert routed.record["resume_at"] == "VALIDATE"
+    assert routed.decision.proceed
+
+
+@pytest.mark.parametrize("approved, resume_at", [(False, "VALIDATE"), (True, "IMPLEMENT")])
+def test_resume_at_is_refused_unless_an_approved_validate_resume(
+    repo: Path, workspace: Path, approved: bool, resume_at: str
+) -> None:
+    _save_escalation_checkpoint(repo, workspace)
+    before = (workspace / "checkpoint.json").read_bytes()
+
+    with pytest.raises(gate_router.GateRefusalError, match="resume_at"):
+        gate_router.answer(
+            Gate.ESCALATE_RESUME, workspace=workspace, repo_root=repo, approved=approved,
+            context={"dispatch_id": "d-1", "resume_at": resume_at},
+        )
+    assert (workspace / "checkpoint.json").read_bytes() == before

```

### Rule groups

#### Group 1 (default: `(default)`)
Applies to:
- openspec/changes/dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g3.json
- openspec/changes/dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g4.json
- openspec/changes/dispatch-contract/dispatch-results/batch-1199bf07b6cb5035d4c22472-ri-21-attempt-1-g5.json
- openspec/changes/dispatch-contract/loop-state.json
- openspec/changes/dispatch-contract/session-log.md
- openspec/changes/dispatch-contract/validation-report.md
- skills/roadmap-runtime/install_assets/openspec/schemas/dispatch-request.schema.json

Review for correctness, security, and adherence to this repository's conventions.

#### Group 2 (default: `openspec/schemas/*.schema.json`)
Applies to:
- openspec/schemas/dispatch-request.schema.json

Verify the schema is valid Draft 2020-12, that required fields were not silently dropped, and that any mirrored copy (install_assets, sentinel-injected) is checked for the same change.

#### Group 3 (default: `skills/*/scripts/*.py`)
Applies to:
- skills/autopilot/scripts/autopilot.py
- skills/autopilot/scripts/goal_gate.py
- skills/autopilot/scripts/runner.py
- skills/supervise/scripts/cycle_state.py
- skills/supervise/scripts/execution.py
- skills/supervise/scripts/gate_router.py

Check for unhandled exceptions on the failure paths this module is meant to guard (network, subprocess, file I/O). Verify a function documented as "never raises" actually catches every exception class it claims to. Flag silent behavior changes to existing callers.

#### Group 4 (default: `skills/tests/**`)
Applies to:
- skills/tests/autopilot/test_console_interviewer.py
- skills/tests/autopilot/test_goal_gate.py
- skills/tests/supervise/test_execution_contract.py
- skills/tests/supervise/test_gate_router.py

Same standard as scripts/tests/: verify the test would fail if the behavior it targets were broken. Check that fixture paths use openspec_paths.change_dir rather than a literal openspec/changes/<id>/ path where the guide requires it.

### Spec excerpts
#### specs/parallel-infrastructure/spec.md
## ADDED Requirements

### Requirement: Dispatchable Vendor Verification

`review_dispatcher.py --check-vendors` SHALL count a vendor lane as available for a mode only after a dry invocation for that mode succeeds: the adapter's declared no-op command (for a CLI lane, `<cli> --version`; for an SDK or API lane, the adapter's own authenticated no-op such as a model-list call) run with a 10-second timeout. Credentials MAY be read only inside the adapter's existing credential path, and the probe SHALL NOT print, log, or return any environment value or credential. With `--json` it SHALL print `{"modes": {<mode>: {"verified": [...], "unverified": [{"vendor", "reason"}]}}, "probe_command": "<argv>"}` and keep its existing exit codes (0 at quorum, 2 below quorum or on probe failure); when the roster cannot be resolved it SHALL print `{"error": "<reason>", "modes": {}}` and exit 2.

#### Scenario: A listed vendor without its CLI is unverified
- **WHEN** `agents.yaml` lists `codex` for mode `review` and no `codex` executable is on `PATH`
- **THEN** `--check-vendors --json` SHALL list `codex` under `unverified` with reason `cli_not_found`, and SHALL NOT count it toward `--min-vendors`

#### Scenario: A hanging dry invocation is unverified
- **WHEN** a lane's dry invocation does not exit within 10 seconds
- **THEN** the lane SHALL be `unverified` with reason `probe_timeout`

#### Scenario: The probe never discloses credentials
- **WHEN** the test sets `ANTHROPIC_API_KEY=sk-test-SENTINEL-1234567890` and `OPENAI_API_KEY=sk-test-SENTINEL-0987654321` and runs `--check-vendors --json`
- **THEN** neither sentinel value SHALL appear in stdout, stderr, or the JSON, and no `env` or `printenv` subprocess SHALL have been spawned


#### specs/roadmap-orchestration/spec.md
## ADDED Requirements

### Requirement: Published Dispatch Contract Schemas

The repository SHALL publish `openspec/schemas/dispatch-request.schema.json` and `openspec/schemas/dispatch-result.schema.json` at `schema_version` 2 as the only definition of the supervisor-worker dispatch boundary, mirrored byte-identically under `skills/roadmap-runtime/install_assets/openspec/schemas/`. `skills/shared/dispatch_contract.py` SHALL load and validate both with JSON Schema Draft 2020-12, and the roadmap orchestrator, the supervise execution adapter, and `checkpoint.schema.json` (through `$ref`) SHALL validate against that definition and SHALL NOT keep their own field sets for the request or result. Readers SHALL accept a `schema_version` 1 result by upgrading it in memory; writers SHALL emit only version 2. The existing `openspec/contracts/roadmap-orchestration/schemas/supervised-dispatch-request.schema.json` and `supervised-dispatch-result.schema.json` SHALL be kept unchanged as the version-1 reader schemas that a version-1 document is validated against before upgrade, `delegated-dispatch-attempt.schema.json` SHALL be the only definition of a checkpoint attempt (`checkpoint.schema.json` SHALL `$ref` it), and `bounded-dispatch-context.schema.json` SHALL be `$ref`'d by the version-2 request. Schema validation of a version-1 document SHALL be host-independent; only the upgrade step, which takes `repo_root`, `managed_root`, and `host_id` explicitly, depends on the host.

#### Scenario: Existing fixtures validate against the published schemas
- **WHEN** the test suite validates the byte-unchanged fixtures under `skills/tests/supervise/fixtures/execution/contracts/` with this mapping: `valid-request.json` and `invalid-continuation-without-kind.json` through `dispatch_contract.validate_request`; each entry (`success`, `parked`) of `valid-results.json` through `dispatch_contract.validate_result`; `valid-prepared-attempt.json` through the checkpoint attempt validator after the legacy reader converts its `launch_token`
- **THEN** every `valid-*` document SHALL validate and every `invalid-*` document SHALL be rejected with a `DispatchContractError` naming the failing JSON pointer, on any host and without a managed worktree root existing at the fixtures' `/workspace/...` paths

#### Scenario: No hand-written result field set remains
- **WHEN** a guard test scans `skills/supervise/scripts/execution.py` and `skills/autopilot-roadmap/scripts/orchestrator.py`
- **THEN** neither file SHALL define `_RESULT_REQUIRED`, `_RESULT_ALLOWED`, `_validate_result`, or `_validate_dispatch_result`
- **AND** `checkpoint.schema.json`'s attempt `result` property SHALL be a `$ref` to `dispatch-result.schema.json`

#### Scenario: Schema mirrors stay identical
- **WHEN** the parity test compares `openspec/schemas/dispatch-*.schema.json` and `checkpoint.schema.json` with their `install_assets` copies
- **THEN** the bytes SHALL be identical, and a difference SHALL fail the test naming the file

#### Scenario: A version-1 result is upgraded, not rejected
- **WHEN** `ExecutionAdapter.apply` receives a schema-valid version-1 `success` result whose absolute `worktree_path` lies inside the current host's managed worktree root
- **THEN** the result SHALL be upgraded to version 2 with `degradations: []`, a relative `worktree_ref`, an `evidence.loop_state_path` relative to that worktree, and the current `host_id`, and applied

#### Scenario: A version-1 result that cannot be made portable is rejected
- **WHEN** a version-1 result's `worktree_path` lies outside both the managed worktree root and the repo root
- **THEN** validation SHALL fail with `DispatchContractError("v1 result worktree_path is not repo-relative")` and the attempt SHALL be left unchanged

### Requirement: Launch Token Digest

The roadmap checkpoint SHALL store, for each delegated attempt, `launch_digest` with the form `sha256:<64 lowercase hex>` and SHALL NOT store a raw launch token in any field. The raw token SHALL appear only in the request returned to the host. `ExecutionAdapter.child_start` SHALL verify a presented token by constant-time comparison of its SHA-256 digest with `launch_digest`. A token SHALL be minted per launch generation: `ExecutionAdapter.resume` and `ExecutionAdapter.reissue` SHALL mint a fresh token and replace `launch_digest` under the same compare-and-swap that changes the generation. `reissue` SHALL be refused for any attempt that is not `prepared` and not a pre-go expired claim. Loading a checkpoint whose attempt carries a legacy `launch_token` SHALL convert it to `launch_digest` in memory, and the next save SHALL drop the raw value.

#### Scenario: No raw token is persisted
- **WHEN** `prepare_delegated_batch` persists a batch and the checkpoint is read back from disk
- **THEN** no attempt SHALL contain a `launch_token` field, every attempt SHALL contain a `launch_digest` matching `^sha256:[0-9a-f]{64}$`, and the token in each returned request SHALL hash to its attempt's digest

#### Scenario: child_start rejects a wrong token
- **WHEN** `child_start` is called with a token whose digest differs from `launch_digest`
- **THEN** it SHALL raise `ExecutionStateError("launch token mismatch")` and the checkpoint SHALL be byte-identical before and after the call

#### Scenario: Resume rotates the token
- **WHEN** an authorized parked attempt is resumed
- **THEN** the returned continuation request SHALL carry a token different from the previous generation's, `launch_digest` SHALL equal its digest, and `child_start` with the previous token SHALL raise `launch token mismatch`

#### Scenario: Reissue is refused after go
- **WHEN** `reissue` is called for an attempt whose launch gate has released go
- **THEN** it SHALL raise `ExecutionStateError` and SHALL NOT change `launch_digest` or the generation

#### Scenario: Legacy checkpoint loads and migrates
- **WHEN** the archived `openspec/roadmaps/archive/2026-09-26-roadmap-supervisor-orchestration/checkpoint.json` (raw tokens, absolute paths) is copied to a temp workspace, loaded, and saved
- **THEN** load SHALL succeed, and the saved file SHALL contain `launch_digest` values equal to the SHA-256 of the former tokens and no `launch_token` field

#### Scenario: A committed checkpoint with live attempts passes the default secret scan
- **WHEN** the fixture `skills/tests/roadmap-runtime/fixtures/landable-checkpoint.json`, produced by `prepare` plus `child_start` and `acknowledge`, is scanned by the CI gitleaks job using `.gitleaks.toml`
- **THEN** gitleaks SHALL report no finding, and `.gitleaks.toml` SHALL contain no path, regex, or commit entry referring to that fixture or to `launch_digest`
- **AND** a unit test SHALL assert that no field name in the serialized checkpoint matches the default `generic-api-key` keyword set (`access`, `auth`, `api`, `credential`, `creds`, `key`, `passw`, `secret`, `token`)

### Requirement: Host-Portable Attempt Isolation

Each delegated attempt SHALL record isolation as `{mode, worktree_ref, branch, host_id}`, where `worktree_ref` is the worktree path relative to the managed worktree root (`managed_worktree`) or to the repo root (`harness_provided` inside the repo), or `null` otherwise, and `host_id` is the non-secret identifier from `skills/shared/environment_profile.py`. Absolute worktree paths SHALL exist only in memory and SHALL NOT be persisted in the checkpoint, the request, or the result. When reconciling an attempt whose `host_id` differs from the current host, the adapter SHALL rebind it when a worktree for its branch exists under the current managed root whose `HEAD` contains the last recorded evidence commit and whose `loop-state.json` digest matches; otherwise it SHALL reinitialize it (create a managed worktree for the branch, increment the generation, mint a new token) when the attempt is `prepared`, `parked`, or a pre-go claim whose lease has expired (an unexpired claim is not taken over); otherwise it SHALL leave the attempt subject to the existing quarantine rules. Legacy absolute `worktree_path` values SHALL be converted to `worktree_ref` on load when they lie inside the managed root or repo root, and SHALL otherwise mark the attempt `needs_rebind`.

#### Scenario: Persisted isolation has no absolute path
- **WHEN** a batch is prepared and the checkpoint is read back
- **THEN** every attempt's `isolation` SHALL have exactly the keys `mode`, `worktree_ref`, `branch`, `host_id`, and no persisted string in the attempt SHALL start with `/` or a drive letter

#### Scenario: Reconcile on another host rebinds a matching worktree
- **GIVEN** a checkpoint with a `parked` attempt committed on host A with evidence commit C
- **WHEN** host B, which has a managed worktree for the attempt's branch whose `HEAD` contains C and whose loop-state digest matches, reconciles the checkpoint
- **THEN** the attempt SHALL keep its generation, gain a `rebound` history entry, and record host B's `host_id`

#### Scenario: Reconcile on another host reinitializes when no worktree exists
- **GIVEN** the same committed checkpoint and a `prepared` attempt
- **WHEN** host B has no worktree for the branch and reconciles
- **THEN** a managed worktree SHALL be created for the branch, the generation SHALL increase by one, a new `launch_digest` SHALL be stored, and `prepare` on host B SHALL NOT skip the item

#### Scenario: A post-go attempt of unknown liveness is not rebound
- **WHEN** host B reconciles a post-go `launched` attempt from host A and the durable task handle cannot establish live or dead status
- **THEN** the attempt SHALL become `quarantined` and no worktree SHALL be created

#### Scenario: Rebind refuses a diverged worktree
- **WHEN** host B's worktree for the branch does not contain the evidence commit, or its loop-state digest differs
- **THEN** the attempt SHALL NOT be rebound and reconciliation SHALL report `rebind_refused:evidence_mismatch` for it

## MODIFIED Requirements

### Requirement: Outcome-Only Resume Contract

The roadmap orchestrator SHALL persist only structured dispatch outcomes and handoff identifiers needed to resume; it MUST NOT persist a child transcript in roadmap state or dispatch context.

#### Scenario: Apply a successful child outcome
- **WHEN** a child returns a schema-valid success result correlated to the current dispatch identifier and change identifier
- **THEN** the item is completed and its learning entry is written once only after the result's `worktree_ref`, `branch`, `host_id`, and loop-state evidence exactly match the prepared attempt and the worktree resolved from `worktree_ref` on the current host remains contained by its verified root
- **AND** contradictory status/outcome pairs are schema-invalid and the checkpoint records bounded outcome metadata, including the result's `degradations`, without transcript content

#### Scenario: Reject stale or mismatched child outcome
- **WHEN** a result carries a different dispatch identifier, change identifier, or already-applied attempt
- **THEN** the result is rejected without advancing the item
- **AND** a resumed run can safely redispatch or reconcile the current attempt

#### Scenario: Preserve a parked child
- **WHEN** a child Autopilot run returns a schema-valid parked result of kind `pending_gate`, `policy_pause`, `permission_blocked`, or `capability_unavailable`
- **THEN** the attempt is recorded as parked and the roadmap item is not marked failed or completed
- **AND** dependents are not failure-blocked while the parked snapshot's bounded metadata (`kind`, `reason`, and the nullable `gate`, `deadline`, `resume_hint`, plus the kind's typed payload the result contract permits — never an `approval_id`, which lives only in the supervise gate router's own ledger) remains available to that router, which is the only consumer permitted to resume it

#### Scenario: Refuse an unroutable parked result at apply time
- **WHEN** `apply` receives a parked result whose `(kind, gate)` pair has no

[spec excerpt truncated]


#### specs/skill-workflow/spec.md
## ADDED Requirements

### Requirement: Code-Emitted Dispatch Result

`skills/autopilot/scripts/runner.py` SHALL provide `emit-result <change-id> --dispatch-id ID --generation N --attempt A` that derives a `dispatch-result.schema.json` version-2 result from the committed `loop-state.json` through `dispatch_contract.result_from_loop_state`, writes it to `openspec/changes/<change-id>/dispatch-results/<dispatch-slug>-g<N>.json` (where `dispatch-slug` replaces each character outside `[A-Za-z0-9._-]` with `-`), and prints it to stdout. The mapping SHALL be, first match wins: `park` set -> `parked/<park.kind>`; `pending_gate` set -> `parked/pending_gate` with the pending gate; `ESCALATE` -> `parked/policy_pause` with `previous_phase` in `resume_hint`; `DONE` with `goal_gate.verdict` `abandoned` -> `failed:abandoned`; `DONE` with verdict `passed` and a `last_handoff_id` -> `success`; any other `DONE` -> `failed:goal_gate_unverified`. Evidence SHALL be the loop-state path, the `HEAD` commit, and the SHA-256 of `loop-state.json` at `HEAD`. Worker prompts and SKILL.md files SHALL instruct workers to return only the path and commit of this file, never a hand-composed result.

#### Scenario: Every terminal and parked shape maps to a schema-valid result
- **WHEN** the end-to-end test builds a committed loop state for each of: `DONE`/passed, `DONE`/abandoned, `DONE`/refused, `ESCALATE`, `pending_gate` for each gate the result schema permits, `park` of kind `permission_blocked`, and `park` of kind `capability_unavailable`, and runs `emit-result` for each
- **THEN** each written file SHALL validate against `dispatch-result.schema.json`, its outcome and kind SHALL equal the mapping above, and `ExecutionAdapter.apply` SHALL accept it for a matching prepared attempt

#### Scenario: A non-terminal phase produces no result
- **WHEN** `emit-result` runs while `current_phase` is `IMPLEMENT` with no `pending_gate` or `park`
- **THEN** it SHALL exit 5, write no file, and print `runner: loop state is not terminal or parked`

#### Scenario: Uncommitted loop state is refused
- **WHEN** `loop-state.json` differs from its `HEAD` version
- **THEN** `emit-result` SHALL exit 2 and write no file

#### Scenario: Abandoned work is not reported as success
- **WHEN** the loop reached `DONE` through `ESCALATE --abandoned-->`
- **THEN** the result outcome SHALL be `failed:abandoned`

### Requirement: Loop State Parks and Degradations

`LoopState` SHALL advance to `schema_version` 6, adding `park: dict | None` and `degradations: list[dict]`, and `load_state()` SHALL migrate a version-5 file by defaulting both. `runner.py park <change-id> --kind permission_blocked --tool T --rule R --command C --reason X` and `runner.py park <change-id> --kind capability_unavailable --phase P --missing-lane L ...` SHALL be the only writers of `park`; `runner.py record-degradation <change-id> --code CODE --phase P --detail D` SHALL be the only writer of `degradations`, accepting only the enumerated codes of `dispatch-result.schema.json`. `_apply_transition` SHALL refuse to move a phase while `park` is set, and `runner.py gate-answer --gate escalate_resume --approval-ref R` SHALL clear it.

#### Scenario: Version-5 state migrates
- **WHEN** `load_state()` reads a `schema_version` 5 file
- **THEN** the result SHALL have `schema_version` 6, `park` None, `degradations` [], and every v5 field unchanged

#### Scenario: A park blocks transitions
- **WHEN** `park` is set and `runner.py apply-outcome` is called
- **THEN** it SHALL exit non-zero naming the park kind, and `current_phase` SHALL be unchanged

#### Scenario: An unknown degradation code is rejected
- **WHEN** `record-degradation` is called with `--code made_up`
- **THEN** it SHALL exit 2 and `degradations` SHALL be unchanged

#### Scenario: The park command is redacted before it is stored
- **WHEN** `park --kind permission_blocked --command 'curl -H "Authorization: Bearer abc123def456ghi789"'` runs
- **THEN** the stored `park.command` SHALL not contain `abc123def456ghi789`

### Requirement: Gate Authority and Re-Evaluation on Resume

Gate authority SHALL depend on whether the child is dispatched (a launch marker is returned by `dispatch_contract.read_launch_marker`). In a dispatched child the supervisor SHALL be authoritative: the child SHALL apply a gate decision only from the marker's `gate_answer` through `runner.py gate-answer --approval-ref`, SHALL NOT re-evaluate an existing `pending_gate` itself, and, when its worktree posture digest differs from the marker's `posture_digest`, SHALL NOT take an `auto` disposition for any gate but SHALL park `pending_gate` with `posture`-provenance instead. In a standalone run, `runner.py gate-check` SHALL, when a `pending_gate` has a `posture.posture_digest` different from the worktree's current posture digest, re-evaluate that gate before printing it: a `proceed` SHALL clear `pending_gate`, record a `posture`-provenance decision, apply the pending edge, and exit 3; a block SHALL replace `pending_gate` with one carrying the new digest; a gate whose last decision has `human` provenance SHALL NOT be re-evaluated. A human rejection of a gate SHALL stay in force until a later `human`-provenance `proceed` on `escalate_resume` (the operator resuming the run); while it is in force, `gate-check --gate` for that gate SHALL record nothing, SHALL enter `ESCALATE` if the loop is not already there, and SHALL exit 4, and a `posture`-provenance resume SHALL NOT end it. `gate-answer` SHALL record `--approval-ref gate-decision:<id>` in the decision's `provenance` and SHALL refuse (exit 2, nothing recorded) a dispatched child's reference that differs from the marker's `gate_answer.approval_ref`.

#### Scenario: A dispatched child applies the supervisor's answer
- **GIVEN** a dispatched child parked at `pending_gate/proposal_approval` and a resumed marker whose `gate_answer` is `{gate: proposal_approval, decision: approved, approval_ref: gate-decision:Y}`
- **WHEN** the child runs `gate-answer --gate proposal_approval --decision approved --approval-ref gate-decision:Y`
- **THEN** `pending_gate` SHALL be None, the last decision SHALL carry `provenance: {source: human, approval_ref: gate-decision:Y}` or, when the supervisor's decision was posture-derived, `{source: posture, posture_digest}` copied from the answer, and the pending edge SHALL have been applied

#### Scenario: A dispatched child does not self-re-evaluate
- **WHEN** a dispatched child with a `pending_gate` and no `gate_answer` in its marker runs `gate-check` after its worktree posture changed
- **THEN** `pending_gate` SHALL be printed unchanged and exit 0, and no decision SHALL be recorded

#### Scenario: Posture drift between child and supervisor blocks auto
- **WHEN** a dispatched child's worktree posture has `proposal_approval: auto` but its digest differs from the marker's `posture_digest`
- **THEN** the gate SHALL park as `pending_gate` with reason containing `posture digest differs from dispatch`, and the child SHALL NOT proceed

#### Scenario: A standalone stale posture block clears without an answer
- **GIVEN** a standalone run with `pending_gate` for `pr_creation` recorded under posture digest D1 (gate `block`)
- **WHEN** the worktree posture changes `pr_creation` to `auto` and `gate-check` runs
- **THEN** `pending_gate` SHALL be None, the last decision SHALL have `outcome: proceed` and `provenance.source: posture`, and the exit code SHALL be 3

#### Scenario: A human rejection is not re-evaluated
- **WHEN** the last decision for the gate has `provenance.source: human` and outcome `blocked`, and the posture changes to `auto`
- **THEN** `gate-check` SHALL NOT record a new decision and the loop SHALL remain in `ESCALATE`

#### Scenario: An operator resume ends a human rejection
- **GIVEN** a human rejection of `merge` followed by a `human`-provenance `escalate_resume` `proceed`
- **WHEN** the resumed phase runs `gate-check --gate merge`
- **THEN** the gate SHALL be evaluated again under the current posture

#### Scenario: A mismatched approval reference is refused
- **WHEN** a dispatched child runs `gate-answer --approval-ref gate-decision:X` and the marker's `gate_answer.approval_ref` is `gate-decision:Y`
- **THEN** it SHALL exit 2 and loop state SHALL be byte-identical

### Requirement: Honest Review Quorum

When the launch marker of a dispatched child carries `review_requirements`, a review phase whose verified lanes from `execution_profile` are fewer than `review_requirements.min_quorum[phase]` SHALL record `park(kind=capability_unavailable, phase, missing_lanes)` and stop, and SHALL NOT run the review with a lower quorum. A standalone run (no launch marker) SHALL keep disabling CLI review below quorum and SHALL record a `review_skipped` degradation, or a `single_vendor_review` degradation when exactly one lane reviewed.

#### Scenario: Dispatched child below quorum parks
- **WHEN** `review_requirements.min_quorum.PLAN_REVIEW` is 2 and only `claude_code` is verified
- **THEN** the loop SHALL have `park.kind == capability_unavailable` with `missing_lanes` naming the counting lanes not verified, no review dispatch SHALL have run, and `emit-result` SHALL return `parked/capability_unavailable`

#### Scenario: A single-lane review under a quorum-1 policy is recorded
- **WHEN** a dispatched child's `review_requirements.min_quorum.PLAN_REVIEW` is 1 by policy data and exactly one review lane dispatches, the others having failed to dispatch
- **THEN** the review SHALL run and `degradations` SHALL contain a `single_vendor_review` entry for `PLAN_REVIEW` whose detail names the vendor
- **AND** the child SHALL NOT have read environment variables or credentials to decide that only one lane exists

#### Scenario: GATEKEEPER review scheduling on the host-driven path
- **WHEN** `runner.py transition --outcome proceed_with_review` is applied in `GATEKEEPER`
- **THEN** `val_review_enabled` SHALL be True and `gate_verdict` SHALL be `proceed_with_review`

#### Scenario: Standalone run below quorum records a degradation
- **WHEN** no launch marker exists and `--check-vendors` reports one vendor
- **THEN** `cli_review_enabled` SHALL be False and `degradations` SHALL contain one `review_skipped` entry for `PLAN_REVIEW`


#### specs/supervise/spec.md
## ADDED Requirements

### Requirement: Dispatch Result Closure

For every `(outcome class, parked.kind, parked.gate)` combination that `dispatch-result.schema.json` permits, the supervisor SHALL have exactly one answer or resume path, declared in a single table `gate_router.ANSWER_PATHS`. A contract test SHALL derive the permitted combinations from the schema itself (not from a hand-written list) and SHALL fail when any combination lacks an entry or an entry names a combination the schema forbids. A parked branch whose `kind` or `gate` is not a `const` or `enum` SHALL fail the enumeration rather than be read as `null`. The table SHALL include the `pending_gate` / `escalate_resume` path merged from `openspec/supervise-pending-escalate-answer`. Before applying a version-2 `success` or `parked` result, `ExecutionAdapter.apply` SHALL re-derive the result from its evidenced loop state through `dispatch_contract.result_from_loop_state` and SHALL refuse the batch when the outcome, the success `handoff_id`, the parked `kind`, a `pending_gate`'s `gate`, or a capability park's dedupe fingerprint differs.

#### Scenario: A result the loop state does not map to is refused
- **WHEN** a version-2 result claims `success` but its evidenced loop state is `DONE` with `goal_gate.verdict: abandoned`
- **THEN** `apply` SHALL raise naming the expected outcome, and the attempt SHALL be unchanged

#### Scenario: Every permitted combination has a path
- **WHEN** the closure test enumerates the schema's `parked` `oneOf` branches and their `kind` / `gate` enums, plus the `success`, `failed:*`, and `vendor_limit:*` outcome classes
- **THEN** each combination SHALL map to an entry in `ANSWER_PATHS`, and the test SHALL report the full list of missing combinations when any is absent

#### Scenario: Adding a kind without a path fails the test
- **WHEN** a test fixture copy of the result schema adds a parked kind `example_kind` with no `ANSWER_PATHS` entry and the closure check runs against that copy
- **THEN** the check SHALL fail naming `("parked", "example_kind", null)`

#### Scenario: pending_gate with escalate_resume is answerable
- **WHEN** a child returns `parked/pending_gate` with `gate: escalate_resume`
- **THEN** `resolve_parked` SHALL evaluate `escalate_resume` for that dispatch generation and, on `proceed`, resume it

### Requirement: Typed Gate Answers With Provenance

Every gate-decision record the router writes SHALL carry `provenance`, either `{source: "posture", posture_digest}` or `{source: "human", approval_ref}`. When resolving a parked attempt, the router SHALL re-evaluate a prior `posture`-provenance block whose `posture_digest` differs from the current posture digest, and SHALL treat a `human`-provenance decision as final for its subject. A resume request SHALL carry the decision to the child only as `gate_answer: {gate, decision, approval_ref}`; the supervisor SHALL NOT write any file in a child worktree other than the launch marker.

#### Scenario: A posture-derived block clears after a posture change
- **GIVEN** an attempt parked `pending_gate/proposal_approval` whose supervisor record has `resolution: posture_block` and `provenance.posture_digest` D1
- **WHEN** the operator changes `TRUST_POSTURE.md` so `proposal_approval` is `auto` (digest D2) and `resolve_parked` runs for the attempt, whose persisted `roadmap_approval_ref` was verified at prepare
- **THEN** a new `proceed` record with `provenance: {source: posture, posture_digest: D2}` SHALL be written and the attempt SHALL be resumed with `gate_answer.decision: approved`
- **AND** the child applying that answer SHALL leave `PLAN` without parking again

#### Scenario: A human rejection survives a posture change
- **GIVEN** a prior record for the same subject with `resolution: console_rejected` and `provenance.source: human`
- **WHEN** the posture changes the gate to `auto` and `resolve_parked` runs
- **THEN** no new record SHALL be written, the attempt SHALL stay parked, and the router SHALL return the existing blocked entry

#### Scenario: An unchanged posture does not re-evaluate
- **WHEN** `resolve_parked` runs for a `posture_block` record whose `posture_digest` equals the current digest
- **THEN** the prior record SHALL be reused and no approval SHALL be filed

#### Scenario: A prose-only posture edit is not a posture change
- **WHEN** only the Markdown body of `TRUST_POSTURE.md` changes and its front matter is unchanged
- **THEN** the posture digest SHALL be unchanged

### Requirement: Execution Profile and Review Requirements

Before launching a batch, the supervisor SHALL resolve an `execution_profile` (verified lanes per mode `review`, `alternative`, `quick`; `location`; isolation mode; and `probe_command`, the only probe a worker may run) by invoking `review_dispatcher.py --check-vendors --json`, and `review_requirements` (`min_quorum` per review phase, default 2 and overridable by router context `review_min_quorum`, and `counting_lanes` ordered by the `cost_policy.tiers` ladder of `agent-coordinator/routing.yaml`), and SHALL place both in every request. The worker protocol in `skills/autopilot/SKILL.md` SHALL forbid reading environment variables or credentials to discover capabilities. `ExecutionAdapter.apply` SHALL persist the result's `degradations` on the checkpoint attempt and SHALL return them in its summary.

#### Scenario: Request carries a resolved profile
- **WHEN** `prepare` returns a batch
- **THEN** every request SHALL validate against `dispatch-request.schema.json` with non-empty `execution_profile.lanes.review`, `execution_profile.probe_command`, and `review_requirements.min_quorum` keyed by review phase

#### Scenario: Profile resolution failure blocks launch
- **WHEN** `--check-vendors --json` prints output that does not parse as JSON, or JSON carrying an `error` field
- **THEN** `prepare` SHALL raise without writing any attempt, and the error SHALL name the probe failure

#### Scenario: Below-quorum availability still launches with an honest profile
- **WHEN** `--check-vendors --json` exits 2 (below quorum) with valid JSON and no `error` field
- **THEN** `prepare` SHALL succeed, and each request's `execution_profile.lanes.review` SHALL list only the verified lanes, so the child parks `capability_unavailable` at its first review phase

#### Scenario: The per-environment quorum is resolved from data
- **WHEN** the quorum policy data declares an active `cloud_container` entry with `min_quorum` 1 that applies below 2 verified review lanes, and `prepare` runs in a cloud container where one review lane verifies
- **THEN** every request's `review_requirements.min_quorum` SHALL be 1 for each review phase and `review_requirements.quorum_policy` SHALL name the environment, the policy entry, and its sunset condition
- **AND** on a host, or in a container where two or more review lanes verify, `min_quorum` SHALL stay 2

#### Scenario: Degradations reach the checkpoint
- **WHEN** a success result carries `degradations: [{code: single_vendor_review, phase: PLAN_REVIEW, detail: "codex not dispatchable"}]`
- **THEN** after `apply` the checkpoint attempt's outcome metadata and the `apply` return value SHALL both contain that entry unchanged

#### Scenario: Worker protocol forbids env probing
- **WHEN** a guard test scans `skills/autopilot/SKILL.md` and `skills/supervise/SKILL.md`
- **THEN** neither SHALL contain an instruction to run `env`, `printenv`, or to read API key variables for vendor discovery

### Requirement: Single Escalation Per Capability Park

The router SHALL map `permission_blocked` and `capability_unavailable` parks to an `escalate_resume` subject keyed by a dedupe fingerprint — `sha256(tool, rule, classifier_reason)` for `permission_blocked`, `sha256(phase, sorted(missing_lanes))` for `capability_unavailable` — and SHALL project exactly one `pending_gates` entry per fingerprint listing every parked dispatch that shares it. One `proceed` answer SHALL resume each listed attempt through its own generation-checked compare-and-swap. The stored redacted command SHALL be the output of `sanitize_session_log.sanitize()` (secret-pattern and high-entropy redaction) truncated to 256 characters.

#### Scenario: Three workers blocked on one rule produce one escalation
- **WHEN** three attempts park `permission_blocked` with tool `Bash`, rule `Bash(env *)`, and the same classifier reason
- **THEN** the supervisor record SHALL contain one `pending_gates` entry whose dispatch list has all three IDs

#### Scenario: One answer resumes every attempt in the entry
- **WHEN** the operator answers that entry `approved`
- **THEN** each of the three attempts SHALL be resumed once with a distinct new generation, and an attempt whose generation changed since projection SHALL be skipped and reported, not resumed

#### Scenario: Different missing lanes are separate escalations
- **WHEN** one attempt parks `capability_unavailable` missing `{codex}` and another missing `{codex, gemini}` for the same phase
- **THEN** two `pending_gates` entries SHALL exist

#### Scenario: A secret in the blocked command is redacted
- **WHEN** a `permission_blocked` park reports command `curl -H "Authorization: Bearer abc123..."`
- **THEN** the persisted command SHALL not contain `abc123` and SHALL contain a `[REDACTED:` marker


#### specs/trust-posture/spec.md
## ADDED Requirements

### Requirement: Roadmap-Approval-Scoped Auto Dispositions

The trust posture SHALL let the `proposal_approval` and `replan_required` gate configs declare an optional `unscoped` sub-config (`disposition` of `notify_with_timeout` or `block`, with the same `timeout_seconds` / `default_action` rules as a gate config), defaulting to `{disposition: block}` when absent. When either gate's disposition is `auto`, the approval gate SHALL apply `auto` only if the current launch marker, obtained by the gate through its `marker_reader` seam, carries a `roadmap_approval_ref`, and SHALL ignore any `roadmap_approval_ref` supplied in the evaluation context; otherwise it SHALL apply the `unscoped` config and record `scope: unscoped` and a reason naming the fallback in the decision. `unscoped` with disposition `auto`, or on any other gate, SHALL be a validation error. The loader SHALL also expose `posture_digest(posture)`: the SHA-256 of the canonical JSON of the parsed `gates` map, with a fixed value for the absent-posture default.

#### Scenario: Dispatched run with a valid approval reference proceeds
- **WHEN** `proposal_approval` is `auto` and `marker_reader` returns a marker carrying `roadmap_approval_ref`
- **THEN** the decision SHALL be `proceed` with `resolution: auto` and `scope: roadmap_approval`

#### Scenario: Standalone run falls back to the unscoped disposition
- **WHEN** `proposal_approval` is `auto`, no `unscoped` is declared, and `marker_reader` returns None
- **THEN** the decision SHALL be `blocked` with `resolution: posture_block`, `scope: unscoped`, and a reason containing `unscoped fallback`

#### Scenario: Declared notify fallback is used
- **WHEN** `replan_required` is `auto` with `unscoped: {disposition: notify_with_timeout, timeout_seconds: 600, default_action: block}` and no reference is present
- **THEN** the approval gate SHALL file an approval and apply `block` on timeout

#### Scenario: A reference not from the launch marker is ignored
- **WHEN** the evaluation context carries `roadmap_approval_ref: gate-decision:Z` but `marker_reader` returns None
- **THEN** the unscoped fallback SHALL apply and the record's `scope` SHALL be `unscoped`

#### Scenario: Invalid unscoped config is rejected
- **WHEN** `TRUST_POSTURE.md` declares `unscoped: {disposition: auto}` or declares `unscoped` on `merge`
- **THEN** `validate_posture_file` SHALL return an error naming the gate and field

#### Scenario: Digest ignores prose and key order
- **WHEN** two posture files differ only in Markdown body text and front-matter key order
- **THEN** `posture_digest` SHALL return the same value for both


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
- [25] Outcome 6 evidence is overstated. The report says 'The CI gitleaks job remains the real-binary check', but .github/workflows/security.yml runs gitleaks only on push to main and on pull_request/merge_group targeting main. This change's PR targets openspec/roadmap-multiplayer-collaboration, so no real gitleaks run covers it until the roadmap PR (#662) to main runs Security. Locally only one default rule (generic-api-key) is ported to Python; the full default ruleset was never applied. The Result line ('All eight acceptance outcomes are covered by passing tests') does not qualify outcome 6.
- [26] Outcome 4 on the capability-fingerprint path is only half-proved. The human side is covered (rejection survives membership change, approval ends the subject), but no test parks a capability fingerprint under escalate_resume=block, flips the posture to auto with no human answer, and shows resolve_parked proceeds with posture provenance and resumes the child. _resolve_capability_park reaches that path only via _apply_prior_record + the dispatch_ids==listed check, which nothing exercises. test_an_operator_approval_ends_a_human_rejected_escalation reaches posture-auto only after a human approval.
- [27] Outcome 7 evidence cannot detect the defect the outcome targets. Host A and host B share the same repo root and workspace directory, so an absolute host-A path leaking into checkpoint.json (or into any record reconcile reads) would still resolve on 'host B'. Nothing asserts that a reconciled checkpoint holds no absolute path, and nothing reconciles a checkpoint copied to a different repository root (the 'committed on one host, checked out on another' case).
- [28] Outcome 5 says execution_profile, review_requirements and degradations[] are 'carried end to end', which the proposal defines as request -> launch marker -> child loop-state.json -> emit-result file -> apply -> checkpoint attempt and apply return value. The report's only end-to-end citation is the capability-park routing test; degradations are proven only piecewise (test_emit_result::test_degradations_travel_into_the_result, and test_execution::test_apply_persists_degradations_on_the_attempt with a hand-composed result), and the marker's profile only in a unit test.
- [29] Citations omit or misplace evidence. Outcome 4 omits the IMPL_ITERATE/IMPL_REVIEW regression tests for the fingerprint path (test_a_human_rejected_escalation_is_not_cleared_when_its_membership_changes, test_an_operator_approval_ends_a_human_rejected_escalation, test_an_approval_resumes_a_member_that_joined_after_the_rejection, supervise test_execution posture tests) and the dispatched-child path (test_a_dispatched_child_does_not_self_re_evaluate, test_posture_drift_between_child_and_supervisor_blocks_auto, test_a_posture_derived_resume_does_not_end_a_human_rejection, test_a_matching_reference_does_not_authorize_another_gate_or_decision). Outcome 3 omits the apply-time refusal test test_supervised_dispatch::test_unroutable_parked_result_is_refused_before_any_callback and the non-enumerable-gate test. Outcome 6 cites test_delegated_checkpoint for child_start digest verification, but the wrong-token refusal is supervise/test_execution.py::test_child_start_rejects_a_wrong_token_without_touching_the_checkpoint.

Do not emit findings for issues already in the ledger except to re-verify the open items listed above.

### Instructions
Return findings as JSON with a top-level `findings` array.

This is round 1. Focus on remaining issues.