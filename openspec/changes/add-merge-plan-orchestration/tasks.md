# Tasks — add-merge-plan-orchestration

Phase 1 only (file-tier artifact + `--execute --pr <n>` + downstream re-validation).
Phase 2 (coordinator system-of-record, event-driven re-validation, cross-host dispatch,
auth scoping) is specified in `design.md` and deferred to a follow-on change — see the
final section.

## 1. Plan schema + emission

- [x] 1.1 Write tests for the merge-plan schema and its producer
  **Spec scenarios**: merge-pull-requests "Analysis round emits a durable plan", "Dependency edges are derived from file overlap and base branch"; merge-infrastructure "Plan state is separated into definition and live fields"
  **Contracts**: contracts/schemas/merge-plan.schema.json
  **Design decisions**: D1 (definition vs live state), D2 (DAG edges)
  **Also cover**: producer-enforced DAG semantic invariants JSON Schema cannot express (contracts/README.md) — tests MUST reject duplicate `node.pr`, dangling `depends_on` targets, self-dependencies, and cycles; and assert every node's `state` carries `staleness`/`ci_state`/`unresolved_comments`
  **Dependencies**: None
- [x] 1.2 Add `build_plan.py` (or extend the analysis round) to emit `merge-plan.json` from `discover_prs` + `check_staleness` + `analyze_comments` output, validating against the schema
  **Dependencies**: 1.1
- [x] 1.3 Derive dependency edges from file overlap + base-branch relationships between PR nodes
  **Design decisions**: D2
  **Dependencies**: 1.1

- [x] 1.4 Checkpoint: run tests, review diff, verify scope

## 2. Rendered projection

- [x] 2.1 Write tests for the `merge-plan.md` renderer (fidelity + non-mutation)
  **Spec scenarios**: merge-infrastructure "Rendered projection matches the authoritative JSON"
  **Design decisions**: D3 (file is a projection)
  **Dependencies**: 1.1
- [x] 2.2 Implement the `merge-plan.md` renderer as a pure projection of `merge-plan.json`
  **Dependencies**: 2.1

## 3. Storage tier selection (file authoritative)

- [x] 3.1 Write tests for tier selection degrading to the file when no coordinator is available
  **Spec scenarios**: merge-infrastructure "File tier is authoritative when no coordinator is available"
  **Design decisions**: D3 (reuse merge_backend detection ladder)
  **Dependencies**: 1.1
- [x] 3.2 Wire plan storage to `merge_backend.py` detection so file tier is authoritative absent a coordinator; stub the coordinator tier as an explicit `NotImplemented` Phase-2 seam
  **Dependencies**: 3.1

- [x] 3.3 Checkpoint: run tests, review diff, verify scope

## 4. Plan-driven single-PR execution

- [ ] 4.1 Write tests for `--execute <plan> --pr <n>`: live re-check, gate halt, security-backstop deferral, outcome write-back
  **Spec scenarios**: merge-pull-requests "Executing one node updates the plan and flags downstream nodes", "Gated node halts for human decision", "Execution respects the security-check backstop"
  **Design decisions**: D5 (merge serialisation), D6 (human gates), D9 (canonical paths)
  **Dependencies**: 1.1
- [ ] 4.2 Implement `--execute --pr <n>` in the skill entrypoint: load plan, re-check live PR/CI, refresh if stale, run `vendor_review.py` when eligible, merge via `merge_pr.py` respecting gates, write `outcome` back
  **Dependencies**: 4.1, 1.2, 3.2
- [ ] 4.3 On successful merge, flag downstream nodes (`needs_revalidation=true`) and recompute mergeability before executing a flagged node
  **Spec scenarios**: merge-pull-requests "Executing one node updates the plan and flags downstream nodes"
  **Design decisions**: D2
  **Dependencies**: 4.2
- [ ] 4.4 Enforce canonical `skills/...` helper paths in the executor (no `.claude/skills` mirror dependence)
  **Design decisions**: D9
  **Dependencies**: 4.2

- [ ] 4.5 Checkpoint: run tests, review diff, verify scope

## 5. Living-plan amendment + comment-addressing seam

- [ ] 5.1 Write tests for inserting a discovered prerequisite node and for the comment-addressing delegation hand-off
  **Spec scenarios**: merge-pull-requests "A discovered blocker is inserted as a prerequisite", "Unresolved comments produce a delegation hand-off"
  **Design decisions**: D7 (living plan), D8 (delegation seam)
  **Dependencies**: 4.1
- [ ] 5.2 Implement plan amendment: insert prerequisite node + edges with a reason; block affected nodes until it merges
  **Design decisions**: D7
  **Dependencies**: 5.1, 4.2
- [ ] 5.3 Implement the comment-addressing seam: record unresolved comments on the node and offer delegation to `iterate-on-implementation`/`quick-task` (no automated code-writing)
  **Design decisions**: D8
  **Dependencies**: 5.1

- [ ] 5.4 Checkpoint: run tests, review diff, verify scope

## 6. Skill docs + wiring

- [ ] 6.1 Update `merge-pull-requests/SKILL.md`: document the plan artifact, `--execute --pr <n>`, gates, and the fresh-context-per-merge workflow
  **Dependencies**: 4.2
- [ ] 6.2 Sync runtime mirrors (`bash skills/install.sh --mode rsync --force --deps none --python-tools none`) and run the skill test suite
  **Dependencies**: 6.1

## Deferred — Phase 2 (follow-on change, specified in design.md)

- [ ] P2.1 Coordinator system-of-record: model plan nodes as `work_queue` (`task_type=pr_merge`, `blockedBy`) + `merge_queue` serialisation (design.md D3, D5)
- [ ] P2.2 Event-driven re-validation over `event_bus` LISTEN/NOTIFY (design.md D4)
- [ ] P2.3 Cross-host dispatch of per-PR executors with worktree isolation (design.md D5)
- [ ] P2.4 Auth scoping for cloud-SDK plan endpoints (design.md D10)
- [ ] P2.5 Automated comment-addressing via worktree-isolated sub-agents (out of scope here; design.md D8)
