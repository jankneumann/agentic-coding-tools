# Plan Findings: route-supervise-gates-through-the-approval-gate-service

Findings from `/iterate-on-plan` (threshold: medium, max 3 iterations). Each iteration
lists what was found against the code on the branch and what changed in the plan.

## Iteration 1 (2026-09-03)

Baseline: `openspec validate --strict` green; every MODIFIED requirement carries all
scenarios of the live spec (checked by script against `openspec/specs/`).

| # | Type | Criticality | Description | Fix |
|---|------|-------------|-------------|-----|
| 1 | consistency / feasibility | high | `ApprovalGate.evaluate` is synchronous: under `notify_with_timeout` it files, notifies, polls until `timeout_seconds`, then applies the default action — it never returns "pending". The child's `pending_gate` snapshot (`build_gate_request`) is built only for `posture_block` and never carries an `approval_id`. Design D4 step 2 and the "never re-files while pending" scenario assumed a pending state that does not exist. | Rewrote D4 as a prior-record rule over the router's own ledger (reuse `proceed`; re-surface an open `posture_block`; check a filed `approval_id` through a new `ApprovalGate.check_filed` before re-filing; `rejected` is terminal); rewrote the notify scenario as "waits for the posture timeout and honours a late answer without re-filing"; recorded the two gate-service facts in design Context. |
| 2 | completeness | high | `openspec/schemas/gate-request.schema.json` embeds the gate enum and `test_gate_schemas.py::test_gate_enum_matches_trust_posture` pins it (and `gate-decision`) to `Gate`; adding the ninth member without it goes red in CI. The mirror schema also embeds the enum (the plan left this as an open question). | Five gate-bearing schemas named everywhere (proposal, D1, tasks 1.1/1.3, skill-workflow requirement + scenario 1, contracts README, wp-contracts locks/scope); added `gate-request` and mirror copies under `contracts/schemas/`. |
| 3 | consistency | high | `build_gate_decision_record` lives in `skills/autopilot/scripts/autopilot.py` (the orchestrator has its own `_gate_decision_record`); D2 cited it as if shared, and supervise must not import the 1,700-line autopilot loop. | Moved into `shared.approval_gate` in wp-contracts (autopilot delegates; orchestrator left as-is, out of scope); `autopilot.py` added to Impact, task 1.5, wp-contracts locks/scope; AST test also forbids `import autopilot` under `skills/supervise/scripts/`. |
| 4 | clarity | high | `console_decision(gate, posture, approved, note)` was undefined against `runner._console_decision(gate, pending, …)`, which reads `pending["posture"]`; and task 3.3 ran `gate-answer` with no prior `gate-check`, which `runner.py gate-answer` semantics would refuse. | Defined `posture` as the `{disposition, posture_present}` snapshot; D5 now states that `roadmap_approval` is the one gate whose console answer may originate a record (live-posture snapshot) and every other gate needs a parked record; new scenario 5. |
| 5 | assumptions | high | Whether an approved roadmap is re-asked on every cycle (or expires) was an open question; re-asking is the interruption ri-04 exists to remove. | Decided in D5: a `proceed` record is reused while the roadmap's DAG fingerprint (sha256 of sorted `(item_id, change_id, depends_on)`) is unchanged; item completion does not re-ask, `refine-roadmap`/replan does; no time expiry. New scenario 4 and tests in 2.1/2.2. |
| 6 | consistency | medium | Proposal/design said `add-supervisor-candidate-work-digest` edits `cycle_state.py`; its proposal states `cycle_state.py` keeps its current surface — only `SKILL.md` `cycle` §2–§5 overlaps. | Corrected in proposal Approach 2, design Constraints and Risks, task 3.4. |
| 7 | testability / parallelizability | medium | `skills/tests/supervise/test_workflow_contract.py` slices `SKILL.md` on `### Approval gate` / `### Reconcile and resume` and pins ``durable `approval_ref` ``; task 3.2 could break it and wp-skill-docs could not edit it. | Task 3.2 keeps the headings and phrase (or updates the test); file added to task 3.2, wp-skill-docs scope and verification. |
| 8 | scope | medium | Task 1.4 named a non-existent `skills/autopilot/tests/test_runner_gates.py`; the runner console tests are `skills/tests/autopilot/test_console_interviewer.py`, outside wp-contracts scope. | Task and wp-contracts scope/verification corrected. |
| 9 | parallelizability | medium | wp-router edits `supervised-dispatch-request.schema.json` (task 2.6) without locking it; wp-contracts locks omitted the template, `gate-request`, mirror and `autopilot.py`. | Locks added. |
| 10 | clarity | medium | `gate-log` "active changes" and `gate-check` exit-4 semantics were undefined. | D6: the change_ids named by the roadmap's items, tagged with `origin`; D5: exit 4 = terminal block (`rejected` / `timeout_default_block` / `coordinator_unreachable`), operator may still `gate-answer`. |
| 11 | security | low | `require_approval_ref` trusts the tracked ledger, so repository write access can forge a `proceed` record. | Documented in D3 and Risks as the same trust boundary `TRUST_POSTURE.md` sits on; no signing (out of scope). |
| 12 | clarity | low | `approval_ref` pattern differed between D3 (`[0-9a-f-]{36}`) and the contract patch (8-4-4-4-12). | D3 aligned to the patch. |

Deferred / out of scope:
- The roadmap orchestrator's private `_gate_decision_record` duplicates the shared builder; consolidating it is a follow-up, not part of ri-04.
- `BridgeCoordinatorClient.push_notification` always returning `False` (ri-05) still fails a `default_action: proceed` closed; documented, unchanged.

## Iteration 2 (2026-09-03)

Re-review of the iteration-1 documents against `cycle_state.py` and the `cycle` SKILL flow.

| # | Type | Criticality | Description | Fix |
|---|------|-------------|-------------|-----|
| 13 | completeness | high | `pending_gates` and `standing_decisions` are non-derivable sections that `build_supervisor_record` only carries forward; nothing deterministic adds or clears an entry, so the router's blocked decisions would never reach a rehydrated session and answered gates would never leave the digest. | New D7: the router projects blocked decisions into the tracked mirror's `pending_gates` (keyed by `decision_id`) and proceeds out of it, upserting the `roadmap_approval` standing decision, through the existing `cycle_state.write_mirror`; requirement sentence and scenario 11 added; tasks 2.1/2.2 cover it. |
| 14 | consistency | high | The `cycle` SKILL's final step rebuilds the record from the pre-gate `$SUPERVISE_RECORD` snapshot and writes the mirror, which would overwrite the router's projection made at the gate. | D7 and task 3.2: re-select the prior with `rehydrate --handoff` at write time; e2e test rehydrates after the gate and after the final write. |
| 15 | clarity | medium | `execute` had no deterministic source for `roadmap_approval_ref` in a rehydrated session. | D5: `execute` always opens with `gate-check`; its exit-3 record supplies the ref; exit 0/4 is the refuse path. |
| 16 | clarity | medium | `cycle --dry-run` writes no supervisor state, but `gate-check` appends to `checkpoint.json` and the mirror. | D5: `gate-check` never runs under `--dry-run`; task 2.7 asserts the subcommand has no dry-run mode to hide behind; task 3.2 documents it. |
| 17 | feasibility | low | Checked that `openspec/roadmaps/` and `openspec/supervise/` are inside `_ALLOWED_WRITE_PREFIXES`, so the router's checkpoint and mirror writes pass `audit-since`; the fingerprint excludes the mirror, so a projection never forces a re-sense. | Recorded in D7; no change needed. |

Remaining below threshold: none identified. Parallelizability unchanged
(wp-contracts → wp-router ∥ wp-skill-docs → wp-integration; max width 2 packages, 3 task
chains inside wp-router after 2.2).

## Plan review round 1 (2026-09-03) — multi-vendor

`/parallel-review-plan`, 4 vendors dispatched, quorum 2 required. Participating:
`claude_code` (20 findings), `grok` / grok-4.5 (12), `antigravity` /
gemini-3.6-flash-medium (2). Dropped from round 2: `pi` (`auth_required` — the OpenRouter
key is expired) and `codex` (dispatch returned the CLI banner instead of JSON,
`error_class: unknown`). Both drops are recorded in `reviews/round-1/review-manifest.json`.
Artifacts under `reviews/round-1/`.

Three findings were reached independently by two vendors (#18, #23, #30/#31); #22 was
raised by grok as a security case and by claude_code as a clarity gap, and is recorded at
grok's severity.

| # | Type | Criticality | Description | Fix |
|---|------|-------------|-------------|-----|
| 18 | correctness | high | **(claude_code + grok)** `cycle_state._clean_pending_gate` is an allowlist that rebuilds every `pending_gates` entry from a fixed key set, so `write_mirror` silently strips the `decision_id` D7 keys its projection on; and its `_GATES` literal still rejects `gate: roadmap_approval` until the enum import lands. Task 1.3 grew only the schemas and task 2.8 only swapped the enums — after task 2.7. Projection could not go green at 2.2. | New task 2.0 (ahead of 2.1/2.2) makes both `cycle_state.py` edits and pins the `write_mirror` round trip; the old task 2.8 is removed; D7 states the allowlist behaviour. |
| 19 | consistency | high | The roadmap-orchestration delta asserted parked metadata carries "any filed `approval_id`", but `supervised-dispatch-result.schema.json` caps `parked` at `{kind, reason, gate, deadline, resume_hint}` with `additionalProperties: false` and `execution.py:416` re-checks the same set — contradicting design Context, which says the snapshot never carries one. | Scenario reworded to the contract's actual bounded metadata; the filed-approval state is named as living in the router's own ledger. |
| 20 | feasibility | high | `gate_router.evaluate` records through `CheckpointManager.record_gate_decision`, whose `load()` raises `FileNotFoundError` on a workspace without `checkpoint.json`. Nine of the ten workspaces under `openspec/roadmaps/` have none. D5 runs `gate-check` at the end of the digest, before `execute` creates one, so a first `cycle` on any un-executed roadmap crashed instead of parking. | D2 / task 2.2 bootstrap with `manager.load() if manager.exists() else manager.create(roadmap)` (as `orchestrator.py:178` does); task 2.7 covers the missing-checkpoint case for `gate-check` and `gate-log`; the ADDED requirement states it. |
| 21 | completeness | high | D6 claimed `gate-log` makes every gate answerable "from tracked state" via `openspec/changes/<id>/loop-state.json`. That file is untracked per-worktree state (`git ls-files` finds it only under `archive/`) and lives in the child's isolated worktree, so the supervisor's copy is empty for every in-flight child — leaving acceptance outcome 2 unmet for the seven autopilot gates. Task 2.10's co-located tmp workspace could not fail on it. | D6 resolves each child through `isolation.worktree_path` / `evidence.loop_state_path`, reports unreadable children as a degraded origin, and task 2.10 places a child's loop state outside the supervisor repo root. |
| 22 | security | high | **(grok)** `check_filed` was specified to map `expired` through `_interpret_status` → `_apply_default`, which fails a `default_action: proceed` gate closed only when `notified` is false. A later `check_filed` has no delivery bit, and `BridgeCoordinatorClient.push_notification` always returns `False` today, so assuming delivery could unpark work nobody was notified about. The posture source for the disposition was also unstated. | `check_filed(gate, approval_id, *, notified)`: disposition from the live posture, `notified` from the prior record, and `expired` + `notified=False` returns `None` so the fail-closed block stands. New scenario arm, D4 step 0.3, task 1.4, and a new NFR row. |
| 23 | scope | high | **(claude_code + antigravity)** Task 2.6's `approval_ref` pattern breaks `skills/tests/autopilot-roadmap/test_supervised_dispatch.py:483` (`approval_ref: "approval-1"`) and the `prepare` argument breaks `test_supervised_dispatch_e2e.py`, which calls `adapter.prepare` directly. Neither file was in any package's `write_allow`, yet wp-router's own verification runs that directory — the package could not make its own gate green. | Both files added to wp-router's `write_allow`, lock set, and task 2.5; the fixture `invalid-continuation-without-kind.json` gets a conforming ref so it still isolates one failure. |
| 24 | consistency | high | The Risks table mitigated `test_workflow_contract.py` by keeping two headings and one phrase, but `test_execute_requires_one_durable_roadmap_altitude_approval_before_mutation` pins six phrases inside `### Approval gate`, and `before any roadmap checkpoint or execution-state mutation` becomes false by design once `execute` opens with `gate-check`. | Task 3.2 and the Risks row now say that assertion must be replaced in the same commit, naming the gate ledger write as the one pre-approval checkpoint mutation. |
| 25 | clarity | high | D2's `answer(...)` snapshots the posture from "the snapshot a parked record carries". Autopilot's `pending_gate` in `loop-state.json` carries one; the supervisor's parked attempt does not, and by contract cannot. | D5 / D2: the snapshot comes from the router's own prior blocked record, or from the live posture for an originating `roadmap_approval` answer. |
| 26 | security | medium | `roadmap_fingerprint` covered only `(item_id, change_id, depends_on)`, so a superseded or skipped item (`refine-roadmap`'s output) or a changed `external_depends_on` edge left it unchanged and the ask-once rule reused an approval given for a different scope. | Fingerprint now includes `external_depends_on` and a normalized `status` that keeps `superseded` / `skipped` distinct from progress; scenario, D5, and a new NFR row. |
| 27 | feasibility | medium | **(grok)** `gate_router` projects through `cycle_state.write_mirror` while `cycle_state`'s subcommands call `gate_router`; both at top level would be an import cycle, and `cycle_state` does heavy import-time work in `_load_runtime_models`. | D2 and tasks 2.2 / 2.9 require lazy imports inside the call sites in both directions. |
| 28 | testability | medium | **(grok)** Scenario "Router is the only seam" forbade `.evaluate(` in every supervise script, which the natural `gate_router.evaluate(...)` call from `cycle_state` would trip. | Scenario narrowed to approval-gate receivers and explicitly permits the router's own module-level functions. |
| 29 | completeness | medium | D7's whole-record view of `write_mirror` was left implicit: it derives all three durable sections from its `record` argument alone, so a projection passing only `pending_gates` would erase `back_edge` and unrelated standing decisions. | D7 and the requirement state the read-merge-write; task 2.1 adds a preservation case. |
| 30 | completeness | medium | **(claude_code + grok)** `$defs.pendingGate` requires `change_id`, and `_clean_pending_gate` drops entries failing the change-id pattern, so a `roadmap_approval` park on a roadmap with no ready item was unrepresentable. | D7 defines the fallback (first item carrying a `change_id`) and requires the gate to be refused with a reason when the roadmap names no change; scenario and task 2.1 updated. |
| 31 | scope | medium | **(claude_code + grok)** wp-contracts edits `skills/tests/supervise/test_supervisor_record_schema.py`, whose `test_gate_enum_matches_trust_posture` reddens the moment task 1.2 lands, but its verification ran only `skills/shared/tests` and three autopilot files. | Third verification step added to wp-contracts. |
| 32 | clarity | medium | Task 3.1 said the supervise prose-free test "mirrors" the autopilot one. That file keys a `_GATE_SECTIONS` map (which does not transfer — supervise raises three of nine gates) and carries `test_mirror_is_byte_identical` cases wp-skill-docs cannot satisfy, since `install.sh` runs in wp-integration. A bare name scan also false-positives on `merge` at `skills/supervise/SKILL.md:216`. | Task 3.1 and scenario 4 specify a backticked / `Gate.`-qualified rule keyed to the three gates supervise raises, and exclude mirror-parity cases. |
| 33 | consistency | medium | **(grok)** D5 claimed the exit codes "mirror `runner.py gate-check`", but runner's exit 4 clears `pending_gate` and enters ESCALATE, so `runner.py gate-answer` refuses it — while supervise's exit 4 deliberately stays answerable. | D5 documents the divergence and task 3.2 puts it in the protocol block. |
| 34 | consistency | low | **(grok)** D2 and the tasks required a `verb` field the change's `gate-decision.schema.json` never declared; `additionalProperties: true` hid the disagreement. | `verb` declared as an optional enum (`cycle` / `execute` / `resume`) in the change contract; task 1.3 names it. |
| 35 | clarity | low | The router's `repo_root` was unpinned, though `runner._evaluate_gate` deliberately uses the child's `Path.cwd()` so a child decides under its own branch's posture. | D2 pins the supervisor's root and names the re-evaluation of a parked child under the supervisor's posture as the intended hot-reload seam. |
| 36 | clarity | low | The ADDED requirement's absolute "SHALL append … before acting" contradicted its own reuse and re-surface scenarios; and D3 did not say the `resume` provenance check must run before `resume` pops `parked`. | Requirement reworded to "whenever the router produces a new decision"; D3 and task 2.6 pin the ordering. |
| 37 | testability | low | `resolve_parked`'s unknown-gate rule did not cover a `pending_gate` park with a null `gate`, which the result contract permits; and task 4.3 verified "reaches dispatch" against an outcome that says "merged PR". | Scenario 10 covers the null gate; task 4.3 sets every gate to `auto` and records what the walk does not cover. |

Not adopted: nothing. Every round-1 finding above `fyi` was applied. Parallelizability
unchanged (wp-contracts → wp-router ∥ wp-skill-docs → wp-integration); the new task 2.0
lengthens wp-router's critical chain by one XS/S step but adds no cross-package edge.

## Round 2 (`/parallel-review-plan`, 2026-09-03)

grok (grok-4.5, 444s) and antigravity (gemini-3.6-flash-medium, 89s) participated; claude_code's
dispatch produced findings that failed `review-findings.schema.json` validation (invalid `type`
enum values) and was dropped from synthesis. Every one of antigravity's seven findings described
an issue round-1's fixes above (findings 22-31) already resolved — verified each against the
current file content before discarding rather than trusting the vendor's read; its dispatch
appears to have captured a pre-round-1-fix snapshot despite running after those commits.

| # | axis | severity | finding | resolution |
|---|---|---|---|---|
| 38 | security | high | **(grok)** Finding #22 gave `check_filed` a `notified` parameter, but nothing declared where the bit is stored, and `_apply_default` overwrites `default_action` to `block` on the undelivered-proceed path — so a genuine `default_action: block` timeout and an undelivered `proceed` looked identical on the persisted record. | `notified` (bool) and `roadmap_fingerprint` declared on `gate-decision.schema.json` and task 1.3; D2 stamps `notified` from `push_notification`'s own return value whenever an approval files, and D4 step 3 reads it from the record's own field, never a default. |
| 39 | security | high | **(grok)** D4's subject-key dedup stops a *fresh* `gate-check` from reusing a stale decision, but `require_approval_ref` never checked `roadmap_fingerprint`, so a caller holding an old `gate-decision:<id>` from before a `refine-roadmap` could still authorize `prepare`. | D3: `require_approval_ref` recomputes and compares `roadmap_fingerprint` for `roadmap_approval` references; task 2.5 adds `test_prepare_rejects_stale_fingerprint`. |
| 40 | consistency | high | **(grok)** The skill-workflow delta only ADDED `Roadmap Approval Gate`; it never MODIFIED the live `Autopilot Gate Call Sites` requirement, which still SHALLs an eight-gate world and a `GIVEN a TRUST_POSTURE.md whose eight gates are all auto` scenario that would contradict the ADDED text after archive. | New MODIFIED delta extends the non-autopilot carve-out to `roadmap_approval` and de-numbers the all-auto scenario. |
| 41 | testability | nit | **(grok)** The "Late coordinator answer" scenario's `WHEN check_filed(Gate.ROADMAP_APPROVAL, approval_id)` omitted the keyword-only `notified` the API requires — not a valid call of the method under test. | WHEN clause now passes `notified=True`/`notified=False` explicitly per arm; added bullet stating the caller always sources it from the record's own field. |
| 42 | clarity | nit | **(grok)** wp-router's blurb still read "Tasks 2.1-2.10" after round-1 inserted task 2.0 ahead of it. | Description corrected to "Tasks 2.0-2.10" and task 2.0's prerequisite role named. |

Not adopted: antigravity's seven round-2 findings (stale re-reports of 22, 23, 22, 27, 30/D6,
26, 27 respectively — cross-checked against current `tasks.md` line 40, `work-packages.yaml`
`wp-router.scope.write_allow`, and design D2/D4/D5/D6 before rejecting). Parallelizability
unchanged.

## Round 3 (`/parallel-review-plan`, 2026-09-03, final round)

grok (grok-4.5, 454s) and antigravity (gemini-3.6-flash-medium, 105s) participated; codex
failed dispatch (non-JSON output, ~3s) and pi failed on an expired OpenRouter key — both
recorded in the round-3 manifest, quorum held at 2. This is the third and final round
`max_phase_iterations` allows; no round 4 was dispatched.

grok's six findings all traced concretely to round-2's own fixes (28-38 vs 40) being
correct in intent but incompletely wired across files — a real, narrower class of gap than
rounds 1-2 found. antigravity's two findings were genuine documentation-only misses in
files round-1/round-2 touched; its third finding confirmed all 42 prior findings resolved.

| # | axis | severity | finding | resolution |
|---|---|---|---|---|
| 43 | security | high | **(grok)** Finding #38 declared `notified` on the schema but never on `ApprovalDecision` / `to_audit_record()` — `_notify` keeps the bit local, so `build_gate_decision_record` had nothing to copy, and a `default_action: block` timeout and an undelivered `proceed` still persisted identically. | `ApprovalDecision`/`_Draft` gain `notified: Optional[bool] = None`, threaded from `_notify`'s local value through `_interpret_status`/`_apply_default` and exposed by `to_audit_record()`; task 1.4 covers the round-trip. |
| 44 | security | high | **(grok)** The ADDED `Supervise Gate Routing` requirement's own SHALL text still said `check_filed` reads delivery from "the prior record's resolution" — the exact approach #38 proved doesn't work — while the skill-workflow twin had already been fixed. | Requirement body rewritten to source `notified` from the record's own field; matches the skill-workflow scenario. |
| 45 | security | high | **(grok)** `roadmap_fingerprint` (finding #39) was only specified as stamped on a fresh `evaluate`, not on the `check_filed`-reuse or console-`answer` paths that produce the *common* case (console approval under an absent posture). A missing stamp compares unequal to any current hash, so `prepare` would refuse every console-approved roadmap. Separately, `require_approval_ref`'s signature had no way to obtain the roadmap to hash. | D2: fingerprint stamped at the one point both `evaluate` and `answer` build a record, covering all three paths. D3: `require_approval_ref` gains a `roadmap` keyword, required for `roadmap_approval`; `prepare` loads `roadmap.yaml` before calling it. |
| 46 | testability | nit | **(grok)** "Refuse unapproved roadmap execution" never named the still-`proceed`-but-stale-fingerprint case as a refusal, leaving the D3/task-2.5 rule unpinned in the live spec. | WHEN clause extended with the stale-fingerprint arm. |
| 47 | testability | nit | **(grok)** The supervise spec's own late-answer scenario called `check_filed` without the keyword-only `notified` the API requires (mirroring #41's skill-workflow fix, this file was missed). | `notified=False` added with the reasoning (a `default_action: block` timeout has no delivery), matching the skill-workflow twin. |
| 48 | clarity | nit | **(grok)** `gate-decision.schema.json`'s `default_action` description claimed the field preserves the posture's *declared* value; live `_apply_default` overwrites it to `block` on a fail-closed proceed, and this change doesn't retask that. | Description corrected to describe the *applied* value and point readers at `notified` for distinguishability; `notified`'s own description states the pairing. |
| 49 | clarity | nit | **(antigravity)** `contracts/schemas/trust-posture.schema.json`'s `gates` description still said "eight enumerated gates" after task 1.3 added a ninth. | Corrected to "nine". |
| 50 | clarity | nit | **(antigravity)** `gate-decision.schema.json` and `gate-request.schema.json` `$id` URIs still pointed at the parent change `encode-autopilot-gates-and-goal-gate-in-code`. | `$id`s updated to this change's path. |

Not adopted: nothing. Parallelizability unchanged; no task moved packages or introduced a
new cross-package dependency. `openspec validate --strict` green; work-packages VALID;
every MODIFIED requirement carries all live-spec scenarios; the D2 bullet-list restatement
of `require_approval_ref`'s signature was also synced with D3's (a drift the reviewers
didn't catch, found on self-review before commit).
