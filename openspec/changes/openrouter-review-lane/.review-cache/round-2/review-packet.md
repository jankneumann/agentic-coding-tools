## Review Round 2

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
diff --git a/openspec/changes/openrouter-review-lane/.review-ledger/ledger.json b/openspec/changes/openrouter-review-lane/.review-ledger/ledger.json
index b88ff9b6..a1173d15 100644
--- a/openspec/changes/openrouter-review-lane/.review-ledger/ledger.json
+++ b/openspec/changes/openrouter-review-lane/.review-ledger/ledger.json
@@ -207,6 +207,75 @@
       ],
       "description": "The round-2 spec fix names the consensus file per phase (consensus-plan.json, consensus-impl-review.json, consensus-val-review.json). Task 5.6 and design D9 still say reviews/consensus-<review_type>.json, which gives consensus-implementation.json for both implementation phases, so they collide. The PLAN_REVIEW case, which the retirement evidence depends on, agrees in all three artifacts. Design D9 also cites 'task 5.5' for this write, but the work is in task 5.6.",
       "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 13,
+      "status": "open",
+      "axis": "architecture",
+      "type": "contract_mismatch",
+      "criticality": "medium",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/openrouter-review-lane/design.md",
+      "fingerprint": "9560d906c79108e4",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "D6 and tasks 3.8a/5.6 have converge() build a second, tool-less packet and 'pass both paths to dispatch_and_wait', and have dispatch_and_wait hand the tool-less body and its tools_overflow flag to OpenAI-compatible adapters. That needs a new optional dispatch_and_wait parameter (for both ReviewOrchestrator and the CompositeOrchestrator that converge() calls through _accepts_kwarg) and a new tools_overflow keyword on OpenAICompatAdapter.dispatch. Neither is named anywhere, and the cross-cutting interface contract table lists only include_lanes for dispatch_and_wait. Groups 3 and 5 implement the two sides of this interface in separate packages.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 14,
+      "status": "open",
+      "axis": "correctness",
+      "type": "spec_gap",
+      "criticality": "medium",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/openrouter-review-lane/tasks.md",
+      "spec_file": "/home/user/agentic-coding-tools/openspec/changes/openrouter-review-lane/specs/parallel-infrastructure/spec.md",
+      "fingerprint": "760c0f61babee0d4",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The Metered Review Lane Spend Accounting requirement says every review an openrouter lane dispatches is recorded with spend_recorder.record(), and acceptance outcome 3 says every OpenRouter review is recorded against the ceiling. The only task that calls record() is 5.5, inside agent_lane's CompositeOrchestrator. D5 also selects the metered lane on a host with fewer than fill_target non-metered lanes (for example one CLI vendor and OPENROUTER_API_KEY in non-OpenBao mode). That review runs through ReviewOrchestrator.dispatch_and_wait from converge() or /parallel-review-*, never through agent_lane, so its spend is neither recorded nor spooled and no metered_spend_unrecorded degradation is raised.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 15,
+      "status": "open",
+      "axis": "observability",
+      "type": "contract_mismatch",
+      "criticality": "low",
+      "evidence_class": "deterministic",
+      "file_path": "openspec/changes/openrouter-review-lane/specs/parallel-infrastructure/spec.md",
+      "fingerprint": "23f6b8e0d50773bb",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "The spec fixes work_unit_ref as '<change_id>:<review_type>:round-<n>'. IMPL_REVIEW and VAL_REVIEW both run with review_type 'implementation', so their rows get the same work_unit_ref and spend cannot be split by phase. This is the collision the round-2 fix already removed for the consensus files. Design D4 allows '<phase|review_type>'.",
+      "consensus_status": "unconfirmed"
+    },
+    {
+      "id": 16,
+      "status": "open",
+      "axis": "architecture",
+      "type": "architecture",
+      "criticality": "medium",
+      "evidence_class": "judgment",
+      "file_path": "openspec/changes/openrouter-review-lane/design.md",
+      "fingerprint": "50d0804bc4341887",
+      "first_seen_round": 1,
+      "last_seen_round": 1,
+      "vendor_hits": [
+        "claude_code"
+      ],
+      "description": "D4 and task 5.7 put the per-round budget re-check in converge(). converge() is vendor-agnostic: it receives only verified_lanes and an orchestrator, does not know which lanes are metered, has no coordinator-usage client, and has no way to keep one lane out of a dispatch except through orchestrator-specific kwargs. CompositeOrchestrator already knows the metered lanes and builds include_lanes, so the check fits there, or in ReviewOrchestrator.dispatch_and_wait next to the probe code. Keeping it in converge() widens the converge() signature with routing concerns.",
+      "consensus_status": "unconfirmed"
     }
   ],
   "compacted_at": "2026-10-11T14:18:09Z"
diff --git a/openspec/changes/openrouter-review-lane/design.md b/openspec/changes/openrouter-review-lane/design.md
index 126d3661..d749c6cd 100644
--- a/openspec/changes/openrouter-review-lane/design.md
+++ b/openspec/changes/openrouter-review-lane/design.md
@@ -180,13 +180,16 @@ to single-vendor review on its own.
 `usage.cost`. The adapter adds `prompt_tokens`, `completion_tokens`, `cost_usd` and
 `cost_source` (`reported`, or `estimated` when the response has no cost) to `ReviewResult`.
 
-A new `skills/parallel-infrastructure/scripts/spend_recorder.py` writes one row per review:
+A new `skills/parallel-infrastructure/scripts/spend_recorder.py` writes one row per review. The
+caller is `ReviewOrchestrator.dispatch_and_wait`, after each metered result, so every dispatch
+path records (a host `converge()` that selected the lane by D5, `/parallel-review-*`, and
+`agent_lane`'s `CompositeOrchestrator`). It sets `ReviewResult.spend_recorded`:
 
 - It posts to a new authenticated `POST /routing/spend` that calls the existing
   `LedgerService.record`.
 - The row holds `vendor` = lane id, `model` = `model_used`, `endpoint_kind = openrouter`,
   `generation_id`, the token counts, `actual_usd`, `tokens_estimated` (true when `cost_source`
-  is `estimated`), and `work_unit_ref = <change_id>:<phase|review_type>:round-<n>`.
+  is `estimated`), and `work_unit_ref = <change_id>:<phase>:round-<n>`.
 
 The same fields always go into the round checkpoint's vendor index, which is durable on the
 branch.
@@ -234,8 +237,9 @@ no HTTP call. The existing Empty Or Blinded Review Is Not Success floor still ap
 lanes.
 
 The packet metadata is the sidecar `build_review_packet` writes next to `packet_path`.
-`dispatch_and_wait` already receives `packet_path`, and passes the `tools_overflow` flag to
-the adapter.
+`dispatch_and_wait` already receives `packet_path`. It reads the flag from the sidecar of the
+packet an OpenAI-compatible lane will receive and passes it to
+`OpenAICompatAdapter.dispatch(..., tools_overflow: bool = False)`.
 
 **Refusal must stay rare.** Refusal alone would make the lane useless in practice. Plan-review
 packets on long-lived branches routinely overflow: the round-1 PLAN_REVIEW packet for this change
@@ -253,6 +257,11 @@ whenever the primary packet overflows:
 - The tool-less packet gets its own sidecar (`review-packet.toolless.meta.json`). An HTTP lane
   refuses with `packet_requires_tools` only when this packet *also* has `tools_overflow: true`.
   The CLI and handshake lanes keep the primary packet.
+- `converge()` passes the tool-less packet as a new optional keyword,
+  `dispatch_and_wait(..., toolless_packet_path: Path | None = None)`, only when the orchestrator
+  accepts it (the existing `_accepts_kwarg` check). Both `ReviewOrchestrator` and
+  `CompositeOrchestrator` accept it, and `CompositeOrchestrator` forwards it to
+  `ReviewOrchestrator`. When it is `None`, OpenAI-compatible lanes get the primary packet as today.
 
 A scenario covers a plan review whose full branch diff overflows: the HTTP lane receives a
 tool-less packet that fits, and it is dispatched. The D9 evidence run must use a change whose
@@ -334,10 +343,12 @@ re-evaluation is expected and is recorded in the session log.
 
 | Contract | Change | Compatibility |
 |---|---|---|
-| `ReviewResult` | adds `prompt_tokens`, `completion_tokens`, `cost_usd`, `cost_source` (all optional, default `None`) | additive, existing callers unaffected |
+| `ReviewResult` | adds `prompt_tokens`, `completion_tokens`, `cost_usd`, `cost_source`, `spend_recorded` (all optional, default `None`) | additive, existing callers unaffected |
 | `--check-vendors --json` | adds `modes.<mode>.lane_kinds`; API lanes may now be `verified` or carry the new reasons | additive; consumers ignore unknown keys |
 | `review_quorum_policy.json` | adds `vendor_families` and `metered_lanes.{fill_target, review_reservation_usd}` | additive; `resolve_quorum_policy` ignores them |
-| `dispatch_and_wait` | adds optional `include_lanes` | default keeps behaviour |
+| `dispatch_and_wait` (`ReviewOrchestrator`, `CompositeOrchestrator`) | adds optional `include_lanes` and `toolless_packet_path: Path \| None = None` (D6) | defaults keep behaviour; `converge()` passes `toolless_packet_path` only when `_accepts_kwarg` reports it |
+| `OpenAICompatAdapter.dispatch` | adds keyword `tools_overflow: bool = False` (D6) | default keeps behaviour |
+| `dispatch_and_wait` / `converge()` spend context | `dispatch_and_wait` adds optional `work_unit_ref: str \| None = None`; `converge()` adds optional `phase: str \| None = None` and passes `work_unit_ref = <change_id>:<phase>:round-<n>` when `phase` is set (D4) | defaults keep behaviour; without a `work_unit_ref` the spend row omits it (the route field is optional) |
 | `dispatch-result.schema.json` `Degradation.code` | adds enum value `metered_spend_unrecorded` | additive enum; writers older than this change never emit it |
 | Coordinator HTTP | adds `POST /routing/spend` (X-API-Key auth, Pydantic `extra="forbid"`, `actual_usd >= 0`, `generation_id` idempotency) | new route |
 
diff --git a/openspec/changes/openrouter-review-lane/specs/parallel-infrastructure/spec.md b/openspec/changes/openrouter-review-lane/specs/parallel-infrastructure/spec.md
index f3d8d034..ca844e7d 100644
--- a/openspec/changes/openrouter-review-lane/specs/parallel-infrastructure/spec.md
+++ b/openspec/changes/openrouter-review-lane/specs/parallel-infrastructure/spec.md
@@ -158,10 +158,16 @@ Every review that an `openrouter` lane dispatches SHALL request inline usage acc
 
 `converge()` SHALL write these fields into the round checkpoint's vendor index.
 
-After each review, `spend_recorder.record()` SHALL send one row to `POST /routing/spend` with:
+After each review that sent a request, `ReviewOrchestrator.dispatch_and_wait` SHALL call
+`spend_recorder.record()`, which SHALL send one row to `POST /routing/spend` with:
 `vendor` (the lane id), `model`, `endpoint_kind: openrouter`, `generation_id`, token counts,
 `actual_usd`, `tokens_estimated` (true when `cost_source` is `estimated`), and
-`work_unit_ref` (`<change_id>:<review_type>:round-<n>`).
+`work_unit_ref` (`<change_id>:<phase>:round-<n>`, for example
+`openrouter-review-lane:VAL_REVIEW:round-2`; the phase, not the review type, so IMPL_REVIEW and
+VAL_REVIEW rows stay distinct; `converge()` supplies it to `dispatch_and_wait` when its caller
+gives the phase, and a call without one omits the field). The call SHALL happen on every dispatch path, including a host
+`converge()` or `/parallel-review-*` run that selected the metered lane, not only inside
+`agent_lane.py`. The result SHALL carry `spend_recorded` (the recorder's `recorded` value).
 
 If the write fails, the record SHALL be appended to
 `openspec/changes/<change-id>/reviews/spend-spool.jsonl`, and the caller SHALL record the
@@ -187,6 +193,12 @@ and reason `spend_ceiling_exceeded`.
   and `tokens_estimated: false`, and the round checkpoint index entry for the lane SHALL carry
   the same generation id, model and cost
 
+#### Scenario: A host-path metered review is recorded
+- **WHEN** a host with one non-metered lane runs `converge()` with `ReviewOrchestrator`, the fill
+  rule selects the `openrouter` lane, and its review returns `id: gen-host`
+- **THEN** `spend_recorder.record()` SHALL have been called once for `gen-host`, and the result's
+  `spend_recorded` SHALL be true when the coordinator accepts the write
+
 #### Scenario: Missing cost is labelled estimated
 - **WHEN** the response has token usage but no `usage.cost`
 - **THEN** `cost_source` SHALL be `estimated` and the ledger row SHALL have
diff --git a/openspec/changes/openrouter-review-lane/tasks.md b/openspec/changes/openrouter-review-lane/tasks.md
index ed7ccf44..ae4ec51e 100644
--- a/openspec/changes/openrouter-review-lane/tasks.md
+++ b/openspec/changes/openrouter-review-lane/tasks.md
@@ -8,14 +8,14 @@
 ## Dependency graph
 
 ```
-1 (adapter) ──┐
-              ├─> 3 (dispatcher discovery/probe) ──┬─> 5 (convergence) ──┐
-2 (roster) ───┘                                    ├─> 6 (supervisor)  ──┼─> 7 (cloud E2E + retirement)
-4 (spend route + recorder) ────────────────────────┴───────────────────────┘
+1 (adapter) ────────────────┐
+2 (roster) ─────────────────┼─> 3 (dispatcher discovery/probe/spend call) ──┬─> 5 (convergence) ──┬─> 7 (cloud E2E + retirement)
+4 (spend route + recorder) ─┘                                               └─> 6 (supervisor)  ──┘
 ```
 
-Groups 1, 2 and 4 are independent, so up to 3 can run in parallel. Groups 5 and 6 run in
-parallel after group 3. Group 7 runs last. Sequential chain length is 4.
+Groups 1, 2 and 4 are independent, so up to 3 can run in parallel. Group 3 needs all three
+(4 for the `spend_recorder.record()` call in task 3.10). Groups 5 and 6 run in parallel after
+group 3. Group 7 runs last. Sequential chain length is 4.
 
 ## 1. OpenAI-compatible adapter: probe, cost capture, packet refusal
 
@@ -45,8 +45,8 @@ dataclass fields and the shared ingest helper extracted in 1.7),
     to the new `ReviewResult` fields.
   - Without a cost, `cost_source == "estimated"`.
 - [ ] 1.4 Add the optional `ReviewResult` fields `prompt_tokens`, `completion_tokens`,
-  `cost_usd` and `cost_source`, all defaulting to `None`, and implement the capture in
-  `dispatch()`.
+  `cost_usd`, `cost_source` and `spend_recorded` (set by task 3.10), all defaulting to `None`,
+  and implement the capture in `dispatch()`.
 - [ ] 1.5 Write a failing test: `dispatch(..., tools_overflow=True)` returns
   `packet_requires_tools` / `vendor_unavailable` with zero transport calls. Then implement the
   `tools_overflow` keyword (default False).
@@ -100,7 +100,7 @@ dataclass fields and the shared ingest helper extracted in 1.7),
 `skills/parallel-infrastructure/scripts/tests/test_review_dispatcher.py`,
 `skills/parallel-infrastructure/scripts/tests/test_review_packet.py`,
 `skills/parallel-infrastructure/tests/test_check_vendors_api_lane.py` (new)
-**Depends:** 1, 2 (the roster is needed only for the integration test in 3.9; tests 3.1–3.8 use inline config dicts)
+**Depends:** 1, 2 (the roster is needed only for the integration test in 3.9; tests 3.1–3.8 use inline config dicts), 4 (the `spend_recorder.record()` interface, task 3.10)
 **Specs:** parallel-infrastructure "OpenAI-Compatible Dispatcher Discovery" (MODIFIED),
 "Dispatchable Vendor Verification" (MODIFIED), "Tool-less Lane Packet Refusal"
 
@@ -150,6 +150,16 @@ dataclass fields and the shared ingest helper extracted in 1.7),
 - [ ] 3.9 Integration test: with the repository's `agents.yaml`, an injected transport and no
   `pi`/`codex` binaries on `PATH`, `--check-vendors --json` lists `openrouter` as verified and
   maps it to `openrouter` in `lane_kinds`.
+- [ ] 3.10 Write failing tests, then implement: `ReviewOrchestrator.dispatch_and_wait` calls
+  `spend_recorder.record()` once after every OpenAI-compatible result with `endpoint_kind:
+  openrouter` that made an HTTP request, and sets `ReviewResult.spend_recorded` to its
+  `recorded` value. The row's `work_unit_ref` comes from a new optional `dispatch_and_wait`
+  keyword `work_unit_ref` (omitted from the row when `None`). This covers every dispatch path: `converge()` with `ReviewOrchestrator` on a
+  host where the fill rule (D5) selected the metered lane, the `/parallel-review-*` one-shot
+  dispatch, and `CompositeOrchestrator` (which calls `dispatch_and_wait`). Tests: a host-path
+  dispatch with an injected transport and an injected recorder records one row; a refused
+  (`packet_requires_tools`) or budget-skipped lane records nothing; a recorder returning
+  `recorded=False` yields `spend_recorded=False`.
 
 ## 4. Spend recording route and client
 
@@ -205,13 +215,16 @@ parallel-infrastructure "Metered Review Lane Spend Accounting" (checkpoint part)
   - `--verified-lanes claude_code` alone → `capability_unavailable` with no handshake files.
 - [ ] 5.5 Implement `--verified-lanes`, `CompositeOrchestrator` (the handshake lane plus
   `ReviewOrchestrator.dispatch_and_wait(include_lanes=...)` run concurrently, with the result
-  callback forwarded), and quorum-policy resolution from the verified count. After each
-  metered result, call `spend_recorder.record()`. On `recorded=False`, record the
-  `metered_spend_unrecorded` degradation through the result payload. Update
-  `_review_body` to list the lanes.
+  callback forwarded), and quorum-policy resolution from the verified count. For each
+  metered result whose `spend_recorded` is `False` (recorded by the dispatcher, task 3.10),
+  record the `metered_spend_unrecorded` degradation through the result payload. `agent_lane`
+  does not call `spend_recorder.record()` itself. Update `_review_body` to list the lanes.
 - [ ] 5.6 Write failing tests, then implement:
+  - `converge()` accepts an optional `phase` and, when it is set, passes
+    `work_unit_ref=<change_id>:<phase>:round-<n>` to `dispatch_and_wait` (via `_accepts_kwarg`);
+    `agent_lane.py` passes its `--phase`.
   - `converge()` builds the tool-less packet (task 3.8a) when the primary packet overflows, and
-    passes both paths to `dispatch_and_wait`.
+    passes the tool-less packet as `dispatch_and_wait(..., toolless_packet_path=...)` (design D6).
   - `agent_lane.py` `result.json` carries `missing_lanes` (from `ConvergenceResult.missing_lanes`),
     `lanes` (the lane ids that returned a successful result), `quorum_received`, a per-lane
     `{model_used, generation_id, cost_usd, cost_source}` map, and `degradations` (including
@@ -285,7 +298,7 @@ parallel-infrastructure "Metered Review Lane Spend Accounting" (checkpoint part)
 |---|---|
 | parallel-infrastructure: OpenAI-Compatible Dispatcher Discovery | 2.1–2.3, 3.1–3.4, 3.9 |
 | parallel-infrastructure: Dispatchable Vendor Verification | 1.1–1.2, 3.5–3.7, 3.9 |
-| parallel-infrastructure: Metered Review Lane Spend Accounting | 1.3–1.4, 4.3–4.4, 5.2, 5.5, 5.7 |
+| parallel-infrastructure: Metered Review Lane Spend Accounting | 1.3–1.4, 3.10, 4.3–4.4, 5.2, 5.5, 5.7 |
 | parallel-infrastructure: Tool-less Lane Packet Refusal | 1.5–1.7, 3.8, 3.8a, 5.6 |
 | skill-workflow: Honest Review Quorum | 5.1–5.3 |
 | skill-workflow: Composite Agent-Lane Review | 5.4–5.6, 6.4 |

```

### Rule groups

#### Group 1 (default: `(default)`)
Applies to:
- openspec/changes/openrouter-review-lane/.review-ledger/ledger.json
- openspec/changes/openrouter-review-lane/design.md
- openspec/changes/openrouter-review-lane/tasks.md

Review for correctness, security, and adherence to this repository's conventions.

#### Group 2 (default: `openspec/changes/*/specs/**/spec.md`)
Applies to:
- openspec/changes/openrouter-review-lane/specs/parallel-infrastructure/spec.md

Verify every SHALL/MUST has at least one Scenario with WHEN/THEN. Check that a MODIFIED requirement's unchanged scenarios were preserved, not silently dropped.

### Spec excerpts
#### specs/model-routing/spec.md
## ADDED Requirements

### Requirement: Review Spend Recording Route

The coordinator SHALL expose `POST /routing/spend`, which requires the `X-API-Key` header.

The request body SHALL be validated with unknown fields forbidden. It accepts:
- required: `vendor`, `model`, `endpoint_kind`, `generation_id`;
- optional: `prompt_tokens`, `completion_tokens` (non-negative integers), `actual_usd` (a
  non-negative number), `tokens_estimated`, `work_unit_ref`, `occurred_at`.

A valid request SHALL write one `routing_spend_ledger` row through `LedgerService.record`.
`generation_id` SHALL be the idempotency key: a second request with a `generation_id` already
in the ledger SHALL return the existing row with HTTP 200 and SHALL NOT insert another row.
`GET /routing/usage` SHALL include recorded review rows in `metered_usd_used`.

#### Scenario: A review spend row is recorded
- **WHEN** an authenticated client posts `{vendor: "openrouter", model: "<publisher>/<model>", endpoint_kind: "openrouter", generation_id: "gen-abc", actual_usd: 0.0042, tokens_estimated: false}`
- **THEN** the response SHALL be HTTP 201, and the next `GET /routing/usage?window=month` SHALL
  report `metered_usd_used` increased by 0.0042

#### Scenario: Duplicate generation id is not double-counted
- **WHEN** the same body is posted twice
- **THEN** the second response SHALL be HTTP 200 and the ledger SHALL contain one `gen-abc` row

#### Scenario: Unauthenticated write is rejected
- **WHEN** the request has no `X-API-Key` header, or an invalid one
- **THEN** the response SHALL be HTTP 401 and no row SHALL be written

#### Scenario: Invalid spend is rejected
- **WHEN** the body has `actual_usd: -1`, or an unknown field `api_key`
- **THEN** the response SHALL be HTTP 422 and no row SHALL be written


#### specs/parallel-infrastructure/spec.md
## MODIFIED Requirements

### Requirement: OpenAI-Compatible Dispatcher Discovery

The review dispatcher SHALL construct an OpenAI-compatible adapter for configured `local` or
`openrouter` endpoints with a `base_url` after CLI and SDK discovery. A usable CLI SHALL retain
precedence over the endpoint adapter for the same agent.

The lane id of an endpoint lane SHALL be its agent `type`. Its model family SHALL be the
publisher prefix of its primary model slug (`<publisher>/<model>`). The family of a CLI or SDK
vendor SHALL be read from `vendor_families` in `review_quorum_policy.json`.

The dispatcher SHALL skip, and SHALL NOT count toward quorum, an `openrouter` lane in either
of these cases:
- its primary model or any fallback model has publisher `anthropic`;
- its family equals the family of a lane already selected at tier 1 or tier 2. The skip
  reason SHALL be `duplicate_model_family`.

An agent with `endpoint_kind: openrouter` selected at tier 2.5 is a metered lane. Metered lanes
SHALL be selected only while the non-metered selected lanes number fewer than
`metered_lanes.fill_target`. That value defaults to the policy file's `default_min_quorum`.
Metered lanes are added in roster order until the target is reached. `--check-vendors` and
`dispatch_and_wait` SHALL apply the same selection.

`dispatch_and_wait` SHALL accept an optional `include_lanes` set. When it is given, only those
lanes SHALL be dispatched. When it is `None`, behaviour SHALL be unchanged.

#### Scenario: Endpoint-only agent is discoverable

- **WHEN** dispatch configuration contains a local/OpenRouter endpoint with no CLI or SDK block
- **THEN** review discovery SHALL return an OpenAI-compatible reviewer for that endpoint

#### Scenario: CLI retains precedence

- **WHEN** an agent has both a usable CLI and an OpenAI-compatible endpoint
- **THEN** review discovery SHALL select the CLI tier first

#### Scenario: Anthropic-family OpenRouter lane is rejected

- **WHEN** an `openrouter` agent resolves the primary model `anthropic/<any>` or lists an
  `anthropic/` fallback
- **THEN** discovery SHALL NOT return that lane, and `--check-vendors --json` SHALL list it
  under `unverified` with reason `anthropic_family`

#### Scenario: Duplicate family is skipped

- **WHEN** `codex` is selected at tier 1, `vendor_families.codex` is `openai`, and an
  `openrouter` lane's primary model is `openai/<model>`
- **THEN** that lane SHALL be listed `unverified` with reason `duplicate_model_family` and SHALL
  NOT be dispatched

#### Scenario: Metered lane fills quorum only

- **WHEN** `fill_target` is 2, and two non-metered lanes and one verified `openrouter` lane are
  available
- **THEN** discovery SHALL return the two non-metered lanes only, and no HTTP request SHALL be
  sent to the OpenRouter endpoint during dispatch

#### Scenario: Metered lane fills a cloud roster

- **WHEN** `fill_target` is 2, `claude_code` is the only non-metered lane, and one `openrouter`
  lane verifies
- **THEN** discovery SHALL return `claude_code` and the `openrouter` lane

#### Scenario: include_lanes restricts dispatch

- **WHEN** `dispatch_and_wait` is called with `include_lanes={"openrouter"}` and `claude_code` and
  `openrouter` are both available
- **THEN** exactly one review SHALL be dispatched, to `openrouter`

### Requirement: Dispatchable Vendor Verification

`review_dispatcher.py --check-vendors` SHALL count a vendor lane as available for a mode only
after a dry invocation for that mode succeeds. The dry invocation is the adapter's declared
no-op, run with a 10-second timeout:
- for a CLI lane, `<cli> --version`;
- for an `openrouter` API lane, one authenticated `GET {base_url}/key`;
- for a `local` API lane, one authenticated `GET {base_url}/models`.

An SDK lane with no authenticated no-op SHALL remain `unverified` with reason
`probe_unsupported`.

Credentials MAY be read only inside the adapter's existing credential path. The probe SHALL
NOT print, log, or return any environment value, credential, or response body. From an API
probe response it SHALL keep only the numeric budget fields (`limit`, `usage`,
`limit_remaining`).

An `openrouter` lane SHALL verify only if:
- the authenticated probe succeeds;
- at least one spend ceiling source is available: the coordinator monthly ceiling when it is
  greater than 0 and the coordinator is reachable, or the key's non-null `limit`; and
- every available source has remaining budget of at least
  `metered_lanes.review_reservation_usd`.

A `local` API lane SHALL verify when its probe succeeds; no budget rule applies to it.
An `openrouter` lane that fails any of these conditions SHALL be `unverified` with one of these reasons: `auth_failed`,
`probe_timeout`, `endpoint_unreachable`, `spend_ceiling_exceeded`, or
`spend_ceiling_unverifiable`.

With `--json` it SHALL print
`{"modes": {<mode>: {"verified": [...], "unverified": [{"vendor", "reason"}], "lane_kinds": {<lane>: <endpoint_kind>}}}, "probe_command": "<argv>"}`.
It SHALL keep its existing exit codes: 0 at quorum, 2 below quorum or on probe failure. When
the roster cannot be resolved it SHALL print `{"error": "<reason>", "modes": {}}` and exit 2.

#### Scenario: A listed vendor without its CLI is unverified
- **WHEN** `agents.yaml` lists `codex` for mode `review` and no `codex` executable is on `PATH`
- **THEN** `--check-vendors --json` SHALL list `codex` under `unverified` with reason
  `cli_not_found`, and SHALL NOT count it toward `--min-vendors`

#### Scenario: A hanging dry invocation is unverified
- **WHEN** a lane's dry invocation does not exit within 10 seconds
- **THEN** the lane SHALL be `unverified` with reason `probe_timeout`

#### Scenario: The probe never discloses credentials
- **WHEN** the test sets `ANTHROPIC_API_KEY=sk-test-SENTINEL-1234567890`,
  `OPENAI_API_KEY=sk-test-SENTINEL-0987654321` and
  `OPENROUTER_API_KEY=sk-or-test-SENTINEL-5555555555`, configures an `openrouter` lane with an
  injected transport that echoes the request headers in its response body, and runs
  `--check-vendors --json`
- **THEN** no sentinel value SHALL appear in stdout, stderr, log records, or the JSON, and no
  `env` or `printenv` subprocess SHALL have been spawned

#### Scenario: An OpenRouter lane verifies by its authenticated no-op
- **WHEN** the injected transport answers `GET /key` with HTTP 200 and `limit: 20.0`,
  `limit_remaining: 15.0`, the coordinator is unreachable, and `review_reservation_usd` is 1.0
- **THEN** the lane SHALL be listed under `verified` for mode `review`, `lane_kinds` SHALL map
  it to `openrouter`, and no chat-completions request SHALL have been sent

#### Scenario: A rejected key is unverified
- **WHEN** the injected transport answers `GET /key` with HTTP 401
- **THEN** the lane SHALL be `unverified` with reason `auth_failed`

#### Scenario: An exhausted ceiling is unverified
- **WHEN** the coordinator reports `metered_ceiling_usd: 50.0` and `metered_usd_used: 49.5`, and
  `review_reservation_usd` is 1.0
- **THEN** the lane SHALL be `unverified` with reason `spend_ceiling_exceeded`, even if the key's
  `limit_remaining` is larger

#### Scenario: No ceiling source fails closed
- **WHEN** the coordinator is unreachable or reports `metered_ceiling_usd: 0`, and the key
  reports `limit: null`
- **THEN** the lane SHALL be `unverified` with reason `spend_ceiling_unverifiable`

#### Scenario: An unexpected probe response shape fails closed
- **WHEN** `GET /key` returns HTTP 200 with a body that has no `data` object
- **THEN** the lane SHALL be `unverified` with reason `spend_ceiling_unverifiable` unless the
  coordinator ceiling source alone verifies it

## ADDED Requirements

### Requirement: Metered Review Lane Spend Accounting

Every review that an `openrouter` lane dispatches SHALL request inline usage accounting
(`"usage": {"include": true}`). On the resulting `ReviewResult` it SHALL set:
- `generation_id`, `model_used`, `prompt_tokens`, `completion_tokens`;
- `cost_usd`, taken from the response's `usage.cost`;
- `cost_source`: `reported` when `usage.cost` is present, `estimated` when it is absent.

`converge()` SHALL write these fields into the round checkpoint's vendor index.

After each review that sent a request, `ReviewOrchestrator.dispatch_and_wait` SHALL call
`spend_recorder.record()`, which SHALL send one row to `POST /routing/spend` with:
`vendor` (the lane id), `model`, `endpoint_kind: openrouter`, `generation_id`, token counts,
`actual_usd`, `tokens_estimated` (true when `cost_source` is `estimated`), and
`work_unit_ref` (`<change_id>:<phase>:round-<n>`, for example
`openrouter-review-lane:VAL_REVIEW:round-2`; the phase, not the review type, so IMPL_REVIEW and
VAL_REVIEW rows stay distinct; `converge()` supplies it to `dispatch_and_wait` when its caller
gives the phase, and a call without one omits the field). The call SHALL happen on every dispatch path, including a host
`converge()` or `/parallel-review-*` run that selected the metered lane, not only inside
`agent_lane.py`. The result SHALL carry `spend_recorded` (the recorder's `recorded` value).

If the write fails, the record SHALL be appended to
`openspec/changes/<change-id>/reviews/spend-spool.jsonl`, and the caller SHALL record the
degradation `metered_spend_unrecorded` with phase and lane.

`spend_recorder.py replay --change-id <id>` SHALL post the spooled rows. Replay SHALL skip a
`generation_id` the ledger already holds, and SHALL remove each row it delivers.

Before each review round dispatches a metered lane, the remaining budget SHALL be re-checked
with the same rule the probe uses. A lane below `review_reservation_usd` SHALL NOT be dispatched
for that round and SHALL be reported as a failed result with `error_class` `vendor_unavailable`
and reason `spend_ceiling_exceeded`.

#### Scenario: A later round finds the ceiling exhausted
- **WHEN** the coordinator ceiling had budget at probe time, and before round 2 its remaining
  budget is below `review_reservation_usd`
- **THEN** round 2 SHALL NOT dispatch the `openrouter` lane, and SHALL record it as
  `vendor_unavailable` with reason `spend_ceiling_exceeded`

#### Scenario: A review is recorded against the ledger
- **WHEN** an `openrouter` review returns `id: gen-abc`, `usage: {prompt_tokens: 1200, completion_tokens: 300, cost: 0.0042}`, and the coordinator accepts the write
- **THEN** the ledger SHALL contain one row with `generation_id: gen-abc`, `actual_usd: 0.0042`,
  and `tokens_estimated: false`, and the round checkpoint index entry for the lane SHALL carry
  the same generation id, model and cost

#### Scenario: A host-path metered review is recorded
- **WHEN** a host with one non-metered lane runs `converge()` with `ReviewOrchestrator`, the fill
  rule selects the `openrouter` lane, and its review returns `id: gen-host`
- **THEN** `spend_recorder.record()` SHALL have been called once for `gen-host`, and the result's
  `spend_recorded` SHALL be true when the coordinator accepts the write

#### Scenario: Missing cost is labelled estimated
- **WHEN** the response has token usage but no `usage.cost`
- **THEN** `cost_source` SHALL be `estimated` and the ledger row SHALL have
  `tokens_estimated: true`

#### Scenario: Coordinator unavailable spools the record
- **WHEN** `POST /routing/spend` fails with a connection error or HTTP 403
- **THEN** the review result SHALL be unchanged, one line SHALL be appended to
  `reviews/spend-spool.jsonl`, and a `metered_spend_unrecorded` degradation SHALL be recorded

#### Scenario: Replay is idempotent
- **WHEN** `replay` runs twice over a spool holding `gen-abc`, and the first run succeeds
- **THEN** the ledger SHALL hold exactly one `gen-abc` row and the spool SHALL be empty

### Requirement: Tool-less Lane Packet Refusal

When a round's primary review packet has `tools_overflow: true`, `converge()` SHALL also build a
tool-less packet for OpenAI-compatible lanes, within the same `BUDGET_CHARS`, with its own sidecar
`review-packet.toolless.meta.js

[spec excerpt truncated]


#### specs/skill-workflow/spec.md
## MODIFIED Requirements

### Requirement: Honest Review Quorum

When the launch marker of a dispatched child carries `review_requirements`, a review phase
whose verified lanes from `execution_profile` are fewer than
`review_requirements.min_quorum[phase]` SHALL record
`park(kind=capability_unavailable, phase, missing_lanes)` and stop. It SHALL NOT run the review
with a lower quorum.

A standalone run (no launch marker) SHALL keep disabling CLI review below quorum. It SHALL
record a `review_skipped` degradation, or a `single_vendor_review` degradation when exactly one
lane reviewed.

During `converge()`, a round can end with fewer successful results than `min_quorum`.
`missing_lanes` SHALL be the round's verified lanes minus the lanes that returned a successful
result. When `missing_lanes` is non-empty and every lane in it has a recorded failure whose
`error_class` is `vendor_unavailable` or `auth_required`, `converge()` SHALL return
`reason="capability_unavailable"` with `missing_lanes` naming those lanes. A verified lane with
no result at all SHALL NOT satisfy this condition. This
covers an exhausted budget, HTTP 402, a revoked key, or `packet_requires_tools`. Any other
quorum loss SHALL remain `reason="quorum_lost"`.


#### Scenario: A lane that returns nothing is not a capability loss
- **WHEN** a PLAN_REVIEW round has verified lanes `claude_code` and `openrouter`, `claude_code`
  succeeds, and `openrouter` returns neither a result nor a recorded failure
- **THEN** `converge()` SHALL return `reason="quorum_lost"`, not `capability_unavailable`

#### Scenario: Dispatched child below quorum parks
- **WHEN** `review_requirements.min_quorum.PLAN_REVIEW` is 2 and only `claude_code` is verified
- **THEN** the loop SHALL have `park.kind == capability_unavailable` with `missing_lanes` naming
  the counting lanes not verified, no review dispatch SHALL have run, and `emit-result` SHALL
  return `parked/capability_unavailable`

#### Scenario: A single-lane review under a quorum-1 policy is recorded
- **WHEN** a dispatched child's `review_requirements.min_quorum.PLAN_REVIEW` is 1 by policy
  data, and exactly one review lane dispatches because the others failed to dispatch
- **THEN** the review SHALL run, and `degradations` SHALL contain a `single_vendor_review` entry
  for `PLAN_REVIEW` whose detail names the vendor
- **AND** the child SHALL NOT have read environment variables or credentials to decide that only
  one lane exists

#### Scenario: GATEKEEPER review scheduling on the host-driven path
- **WHEN** `runner.py transition --outcome proceed_with_review` is applied in `GATEKEEPER`
- **THEN** `val_review_enabled` SHALL be True and `gate_verdict` SHALL be `proceed_with_review`

#### Scenario: Standalone run below quorum records a degradation
- **WHEN** no launch marker exists and `--check-vendors` reports one vendor
- **THEN** `cli_review_enabled` SHALL be False and `degradations` SHALL contain one
  `review_skipped` entry for `PLAN_REVIEW`

#### Scenario: Budget exhausted mid-run parks instead of losing quorum
- **WHEN** `min_quorum` is 2, round 1 succeeds with `claude_code` and `openrouter`, and in round 2
  `openrouter` fails with HTTP 402 (`error_class=vendor_unavailable`)
- **THEN** `converge()` SHALL return `reason="capability_unavailable"` with
  `missing_lanes == ["openrouter"]`, and SHALL NOT return `quorum_lost`

#### Scenario: A malformed review still loses quorum
- **WHEN** `min_quorum` is 2 and a round's `openrouter` result fails with
  `error_class=unknown` ("Review output was not valid review-findings JSON")
- **THEN** `converge()` SHALL return `reason="quorum_lost"`

## ADDED Requirements

### Requirement: Composite Agent-Lane Review

`agent_lane.py converge` SHALL accept `--verified-lanes` (repeatable). A dispatched child SHALL
take the values from its launch marker's `execution_profile.lanes.review`. A standalone run
SHALL take them from the `--check-vendors --json` output and SHALL NOT read environment
variables or credentials.

It SHALL resolve the quorum policy with `verified_review_lanes` equal to the number of
verified lanes, and SHALL pass those lanes to `converge()` as `verified_lanes`.

Each round SHALL:
- dispatch the `claude_code` handshake lane;
- in parallel, dispatch `ReviewOrchestrator.dispatch_and_wait(include_lanes=<verified lanes except claude_code>)`;
- return both results to `converge()`.

Every lane's findings SHALL be written to the round checkpoint under its own lane id, and
ConsensusSynthesizer SHALL attribute consensus findings to those lane ids.

After each run, `agent_lane.py` SHALL write `ConvergenceResult.consensus` (including
`quorum_received`) under `openspec/changes/<change-id>/reviews/`, with one file per phase:
- `consensus-plan.json` for `PLAN_REVIEW`;
- `consensus-impl-review.json` for `IMPL_REVIEW`;
- `consensus-val-review.json` for `VAL_REVIEW`.

The two implementation phases share `review_type: implementation`, so the file is named by phase
and neither run overwrites the other. `converge()` itself SHALL NOT be required to write these
files.

The review body written for `VAL_REVIEW` SHALL list every lane that reviewed. It SHALL name a
`single_vendor_review` degradation only when exactly one lane reviewed.

#### Scenario: Cloud plan review reaches quorum two
- **WHEN** `agent_lane.py converge --phase PLAN_REVIEW --verified-lanes claude_code --verified-lanes openrouter`
  runs against a fixture change, with an injected OpenRouter transport that returns
  schema-valid findings and an agent handshake that writes schema-valid findings
- **THEN** `converge()` SHALL be called with `min_quorum=2`, the round checkpoint SHALL contain
  findings files for both `claude_code` and `openrouter`, `consensus` SHALL report
  `quorum_received: 2`, and `reviews/consensus-plan.json` SHALL contain the same consensus

#### Scenario: Findings carry vendor attribution
- **WHEN** both lanes report a finding at the same file and line range
- **THEN** the consensus finding SHALL list both `claude_code` and `openrouter` in its vendor
  attribution, and the review ledger entry SHALL preserve both lane ids

#### Scenario: Only the agent lane verified
- **WHEN** `--verified-lanes claude_code` is the only lane and no active policy lowers the quorum
- **THEN** `converge()` SHALL return `capability_unavailable` with `missing_lanes` naming the
  counting lanes not verified, and no handshake file SHALL be written

### Requirement: Cloud Single-Vendor Policy Retirement

The temporary cloud single-vendor policy SHALL be retired only after an evidence file
`openspec/changes/openrouter-review-lane/evidence/cloud-quorum-run.md` records a cloud-container
autopilot run on a fixture change. The run must show:
- `PLAN_REVIEW` with `min_quorum=2`;
- a `consensus-plan.json` attributing findings or confirmations to `claude_code` and to an
  `openrouter` lane;
- a ledger or spool row carrying that review's `generation_id`.

Retirement SHALL:
- delete the `cloud-container-single-vendor-2026-10-09` entry from
  `review_quorum_policy.json`, keeping the `policies` array and its `sunset` field as the
  mechanism for future exceptions;
- delete the "Review quorum in cloud containers (temporary)" section of `TRUST_POSTURE.md`;
- update `skills/autopilot/SKILL.md` so that no instruction tells a cloud worker to accept
  single-vendor review.

#### Scenario: Retirement restores quorum two in cloud
- **WHEN** the policy entry has been deleted and `resolve_quorum_policy(environment="cloud_container", verified_review_lanes=1)` is called
- **THEN** `min_quorum` SHALL be 2 for each review phase and `policy_id` SHALL be null

#### Scenario: Retirement is blocked without evidence
- **WHEN** a guard test finds `review_quorum_policy.json` without the cloud entry but no
  `evidence/cloud-quorum-run.md` in this change, or an evidence file missing a `generation_id`
- **THEN** the test SHALL fail

#### Scenario: No prose exception remains
- **WHEN** a guard test scans `TRUST_POSTURE.md` after retirement
- **THEN** it SHALL find no section titled "Review quorum in cloud containers"


#### specs/supervise/spec.md
## MODIFIED Requirements

### Requirement: Execution Profile and Review Requirements

Before launching a batch, the supervisor SHALL resolve two values by invoking
`review_dispatcher.py --check-vendors --json`, and SHALL place both in every request:

- **`execution_profile`**: verified lanes per mode (`review`, `alternative`, `quick`);
  `location`; isolation mode; and `probe_command`, the only probe a worker may run.
- **`review_requirements`**: `min_quorum` per review phase, and `counting_lanes`.
  - `min_quorum` defaults to 2 and can be overridden by the router context
    `review_min_quorum`.
  - `counting_lanes` are ordered by the `cost_policy.tiers` ladder of
    `agent-coordinator/routing.yaml`. Each lane's endpoint kind is read from the report's
    `lane_kinds`. The kind is inferred from the `probe_unsupported` reason only when
    `lane_kinds` is absent.

The worker protocol in `skills/autopilot/SKILL.md` SHALL forbid reading environment variables
or credentials to discover capabilities. `ExecutionAdapter.apply` SHALL persist the result's
`degradations` on the checkpoint attempt and SHALL return them in its summary. When the result
carries a `metered_spend_unrecorded` degradation, `apply` SHALL run
`spend_recorder.py replay --change-id <id>` once, and SHALL report the replay outcome in its
summary without failing the apply.

#### Scenario: Request carries a resolved profile
- **WHEN** `prepare` returns a batch
- **THEN** every request SHALL validate against `dispatch-request.schema.json` with non-empty
  `execution_profile.lanes.review`, `execution_profile.probe_command`, and
  `review_requirements.min_quorum` keyed by review phase

#### Scenario: Profile resolution failure blocks launch
- **WHEN** `--check-vendors --json` prints output that does not parse as JSON, or JSON carrying
  an `error` field
- **THEN** `prepare` SHALL raise without writing any attempt, and the error SHALL name the probe
  failure

#### Scenario: Below-quorum availability still launches with an honest profile
- **WHEN** `--check-vendors --json` exits 2 (below quorum) with valid JSON and no `error` field
- **THEN** `prepare` SHALL succeed, and each request's `execution_profile.lanes.review` SHALL
  list only the verified lanes, so the child parks `capability_unavailable` at its first review
  phase

#### Scenario: The per-environment quorum is resolved from data
- **WHEN** the quorum policy data declares an active `cloud_container` entry with `min_quorum` 1
  that applies below 2 verified review lanes, and `prepare` runs in a cloud container where one
  review lane verifies
- **THEN** every request's `review_requirements.min_quorum` SHALL be 1 for each review phase,
  and `review_requirements.quorum_policy` SHALL name the environment, the policy entry, and its
  sunset condition
- **AND** on a host, or in a container where two or more review lanes verify, `min_quorum` SHALL
  stay 2

#### Scenario: A verified OpenRouter lane is ranked as metered
- **WHEN** the report's `review.verified` is `["claude_code", "openrouter"]` with
  `lane_kinds: {"claude_code": "vendor-cli", "openrouter": "openrouter"}`, and the routing ladder is
  `[vendor-cli, vendor-sdk, openrouter]`
- **THEN** `counting_lanes` SHALL be `["claude_code", "openrouter"]`, and `min_quorum` SHALL be 2
  for each review phase

#### Scenario: A report without lane_kinds still ranks
- **WHEN** the report has no `lane_kinds` key
- **THEN** ranking SHALL use the previous `probe_unsupported` inference and `prepare` SHALL succeed

#### Scenario: Degradations reach the checkpoint
- **WHEN** a success result carries
  `degradations: [{code: single_vendor_review, phase: PLAN_REVIEW, detail: "codex not dispatchable"}]`
- **THEN** after `apply` the checkpoint attempt's outcome metadata and the `apply` return value
  SHALL both contain that entry unchanged

#### Scenario: Unrecorded spend is replayed on apply
- **WHEN** a result carries a `metered_spend_unrecorded` degradation and the coordinator accepts
  the replay
- **THEN** `apply` SHALL return a summary with the replayed row count, and the degradation SHALL
  remain on the checkpoint attempt

#### Scenario: Worker protocol forbids env probing
- **WHEN** a guard test scans `skills/autopilot/SKILL.md` and `skills/supervise/SKILL.md`
- **THEN** neither SHALL contain an instruction to run `env`, `printenv`, or to read API key
  variables for vendor discovery


### Open ledger items
- [1] D6 makes HTTP lanes refuse any packet with tools_overflow:true, but PLAN_REVIEW packets for real changes in this repo routinely overflow: the round-1 packet for this very change is 320000/320000 chars with tools_overflow:true (branch diff vs origin/main spans ~420 files). In cloud, the OpenRouter lane would therefore return packet_requires_tools on round 1 of most reviews and the run parks capability_unavailable, so Acceptance Outcome 1 (quorum 2 in cloud) holds only for the small fixture used as evidence.
- [2] OpenAICompatAdapter.dispatch only calls CliVendorAdapter._parse_findings. The CLI ingest path also runs coerce_findings_payload, schema validation, stamp_judgment_ingest, line resolution, placeholder rejection and the empty_findings_too_fast floor. No task brings the HTTP lane onto that pipeline, yet the spec scenario 'Fast empty HTTP review does not count' and Acceptance Outcome 4 (findings conform to the schema and are synthesized like CLI lanes) depend on it. The traceability table maps Tool-less Lane Packet Refusal only to 1.5 and 3.8. Without judgment stamping, OpenRouter findings default to evidence_class=deterministic and count as blocking while CLI-lane findings do not, which skews consensus.
- [3] The mid-run mapping fires when 'every failed lane's error_class is UNAVAILABLE or AUTH'. A verified lane can also produce no ReviewResult at all: it is filtered at dispatch by the family or fill rule, not discovered in the worker environment, or dispatch_and_wait returns [] when job_count == 0. In that case the failed set is empty, the condition is vacuously true, and converge() returns capability_unavailable with missing_lanes == [].
- [4] The D9 evidence gate and the 'Cloud Single-Vendor Policy Retirement' requirement both require two lanes attributed in consensus-plan.json. The converge()/agent_lane path that autopilot PLAN_REVIEW must use never writes consensus-plan.json; only /parallel-review-plan does. converge() writes .review-cache/round-N/findings-<vendor>-plan.json plus the index, and agent_lane writes result.json without the consensus. As written, the evidence cannot be produced from the mandated path.
- [5] D1 gives openrouter-review location: cloud. In routing.yaml the only tier carrying endpoint_kind openrouter is metered-api with location: local, so RoutingPolicy.cost_tier('cloud', 'openrouter') returns None, and select_model excludes the candidate (model_routing/api.py around lines 577-600). The new agent becomes an inconsistent roster entry for the coordinator router.
- [6] discover_reviewers makes a single pass over sorted(all_vendors), so the 'roster order' that D5 relies on is not available. The D2 family rule and the D5 fill rule both depend on tier-1/2 selections, which can include vendors that sort after 'openrouter' (e.g. 'pi'). Implemented inside the existing loop, both rules would read an incomplete selection.
- [7] D4 checks the budget only in the probe, which the supervisor runs once per batch against a $1.00 reservation. A dispatched child can then run up to 3 rounds in each of 3 review phases with packets of roughly 80k tokens, and every concurrently dispatched child sees the same remaining budget. When the coordinator ceiling is the only source (key limit null), nothing stops an overrun, so 'bounded before dispatch' does not hold.
- [8] D1 says the agent has 'no cli and no sdk block, the same shape as ocr-local', but ocr-local declares a cli block (agents.yaml around lines 452-468).
- [9] agent_lane.run_converge does not copy ConvergenceResult.missing_lanes into result.json. Task 6.4 expects the worker to park capability_unavailable with missing_lanes, but no task adds that field (or per-lane cost) to result.json.
- [10] The round-1 fix adds normative behaviour to design D6 and tasks 3.8a/5.6: when the primary packet overflows, HTTP lanes get a separate tool-less packet (for plan reviews, scoped to openspec/changes/<id>/**) with its own sidecar, and they refuse only if that packet also overflows. The 'Tool-less Lane Packet Refusal' requirement still describes refusal of the round's packet only. No requirement or scenario defines the tool-less packet, so the spec no longer matches the design and tasks.
- [11] Task 5.6 now has agent_lane persist ConvergenceResult.consensus to reviews/consensus-<review_type>.json, which the retirement evidence depends on. The 'Composite Agent-Lane Review' requirement does not state this. Also, IMPL_REVIEW and VAL_REVIEW share review_type 'implementation', so a VAL_REVIEW run would overwrite the IMPL_REVIEW consensus file.
- [12] The round-2 spec fix names the consensus file per phase (consensus-plan.json, consensus-impl-review.json, consensus-val-review.json). Task 5.6 and design D9 still say reviews/consensus-<review_type>.json, which gives consensus-implementation.json for both implementation phases, so they collide. The PLAN_REVIEW case, which the retirement evidence depends on, agrees in all three artifacts. Design D9 also cites 'task 5.5' for this write, but the work is in task 5.6.
- [16] D4 and task 5.7 put the per-round budget re-check in converge(). converge() is vendor-agnostic: it receives only verified_lanes and an orchestrator, does not know which lanes are metered, has no coordinator-usage client, and has no way to keep one lane out of a dispatch except through orchestrator-specific kwargs. CompositeOrchestrator already knows the metered lanes and builds include_lanes, so the check fits there, or in ReviewOrchestrator.dispatch_and_wait next to the probe code. Keeping it in converge() widens the converge() signature with routing concerns.

Do not emit findings for issues already in the ledger except to re-verify the open items listed above.

Hunt only in the attached last-fix diff. Re-verify open ledger items. Do not re-open retired or parked items.

### Instructions
Return findings as JSON with a top-level `findings` array.

This is round 2. Focus on remaining issues.