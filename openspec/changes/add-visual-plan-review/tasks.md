# Tasks — add-visual-plan-review

## Phase 1 — Annotation schema & persistence

- [ ] 1.1 Write tests for `annotations.py`: record construction, 240-char text truncation, artifact-header population, round-trip read/write of `plan-annotations.json`
  **Spec scenarios**: skill-workflow "Annotation record persisted", "Annotation artifact carries header"
  **Design decisions**: D2 (schema), D3 (anchors)
  **Dependencies**: None
  **Size**: S

- [ ] 1.2 Implement `skills/shared/plan_review/annotations.py` — `Annotation` dataclass, `append(change_id, record)`, `load(change_id)`, header stamping (reuse the shared artifact-header helper if present, else inline ~10 LOC)
  **Spec scenarios**: skill-workflow "Annotation record persisted", "Annotation artifact carries header"
  **Design decisions**: D2, D3
  **Dependencies**: 1.1
  **Size**: M

## Phase 2 — Rendering

- [ ] 2.1 Write tests for `render.py`: proposal.md → HTML with a `data-plan-anchor` on every requirement and task; deterministic slug anchors; self-contained (no external asset refs)
  **Spec scenarios**: skill-workflow "Proposal rendered with stable anchors"
  **Design decisions**: D3 (stable anchors), D7 (self-contained)
  **Dependencies**: None
  **Size**: M

- [ ] 2.2 Implement `skills/shared/plan_review/render.py` — parse the change's `proposal.md` + `tasks.md` task DAG, emit `.plan-review/<change-id>.html` with inlined CSS/JS and anchored sections (goal → current state → approach → task DAG)
  **Spec scenarios**: skill-workflow "Proposal rendered with stable anchors"
  **Design decisions**: D3, D7
  **Dependencies**: 2.1
  **Size**: L

## Phase 3 — Review server (gate + long-poll)

- [ ] 3.1 Write tests for `server.py`: loopback binding, long-poll returns queued annotations, layout-gate finding shape `{selector, kind, overflowPx, viewportWidth, severity}`, `--timeout-ms` test escape hatch
  **Spec scenarios**: skill-workflow "Long-poll returns annotations", "Layout gate masks on error severity"
  **Design decisions**: D4 (gate), D5 (long-poll), D7 (security)
  **Dependencies**: 1.2
  **Size**: M

- [ ] 3.2 Implement `skills/shared/plan_review/server.py` — serve the artifact on `127.0.0.1`, capture element/text-range annotations → `annotations.append`, run the open-time layout gate, expose the no-timeout poll endpoint keyed by change-id
  **Spec scenarios**: skill-workflow "Long-poll returns annotations", "Layout gate masks on error severity"
  **Design decisions**: D4, D5, D7
  **Dependencies**: 3.1, 2.2
  **Size**: L

## Phase 4 — Skill integration

- [ ] 4.1 Wire `--visual-review` into `plan-feature` **after `tasks.md` is generated (Step 6)** so the task DAG is populated: render + serve + long-poll, then fold the **unresolved** annotations into the `iterate-on-plan` pass as element-anchored findings and mark each `resolved: true` once applied; short-circuit in headless/cloud via `environment_profile.detect()`
  **Spec scenarios**: skill-workflow "Visual review gate in plan-feature", "Visual review skipped when headless"
  **Design decisions**: D6 (environment awareness)
  **Dependencies**: 3.2
  **Size**: M

- [ ] 4.2 Teach `parallel-review-plan` to attach `plan-annotations.json` (when present) to reviewer context
  **Spec scenarios**: skill-workflow "Reviewers see human annotations"
  **Design decisions**: D1 (shared module)
  **Dependencies**: 1.2
  **Size**: S

- [ ] 4.3 Update `skills/plan-feature/SKILL.md` and `skills/parallel-review-plan/SKILL.md` docs; run `skills/install.sh` to regenerate `.agents/` + `.claude/` mirrors
  **Spec scenarios**: (docs)
  **Design decisions**: —
  **Dependencies**: 4.1, 4.2
  **Size**: S

## Phase 5 — Verification

- [ ] 5.1 Integration test: full loop on a fixture change — render, queue two annotations (one anchored, one text-range), poll returns them, artifact re-render preserves anchors, headless run skips cleanly
  **Spec scenarios**: all
  **Design decisions**: D3, D5, D6
  **Dependencies**: 4.1
  **Size**: M

- [ ] 5.2 Run `openspec validate add-visual-plan-review --strict`; run skill test suite; update this change's `session-log.md`
  **Spec scenarios**: —
  **Design decisions**: —
  **Dependencies**: 5.1
  **Size**: S

## Gate 1 — operator decision required

- [ ] G1 Confirm layout-gate default (Decision D / D4): **soft gate** (record finding, continue) vs. **hard gate** (block agent until layout fixed). Proposed default: soft.
