# Factory Missions Architecture Alignment

## Why

The repo implements roughly 80% of the Factory Missions architecture (https://www.youtube.com/watch?v=ow1we5PzK-o) under domain-specific names. Three concrete consequences for users:

1. **Discoverability gap.** A new contributor reading `README.md` cold has no entry vocabulary for the three-role model (Orchestrator / Workers / Validators). Existing terms (work packages, escalation handlers, scope-isolated parallelism) are correct but not pedagogical. The talk's framing — "the bottleneck is human attention, not model intelligence" — is a stronger opener than the current "tools and workflows for AI-assisted software development."

2. **Validator surface fragmentation.** Two validator implementations exist today and operate in isolation:
   - **Scrutiny validators** — `parallel-review-plan` and `parallel-review-implementation` produce structured findings via `consensus_synthesizer.py` against `review-findings.schema.json`.
   - **Behavioral validators** — `gen-eval` runs against live deployments, producing markdown/JSON reports in its own format. Already wired into `validate-feature` as `--phase gen-eval` (template-only mode), but findings do not flow into the consensus surface and are not seeded by OpenSpec scenarios.
   The result: humans reconcile two parallel reports instead of one ranked finding list.

3. **Worker bias risk.** `review_dispatcher.py` already enforces vendor diversity for reviewers. Workers fall back to archetype-based escalation within one provider family, so a worker and its validator can share training-data biases on the same package — exactly the failure mode the talk warns against.

4. **Frontend validation absent.** `gen-eval` covers HTTP, MCP, and CLI surfaces. Any future frontend feature has no behavioral-validation path. Adding a Playwright-CLI-driven validator now (with a sample frontend to prove the design) closes this gap before it blocks a real feature.

This proposal aligns vocabulary, unifies the two validator surfaces into one consensus output, closes the worker-vendor bias gap, and adds frontend coverage — without renaming any existing skill or breaking any existing caller.

## What Changes

Seven scope-isolated work packages, organized by directory:

- **WP1** (`docs/`) — Rewrite `README.md` opener with attention-bottleneck framing and a Three-Role section mapping each existing skill onto Orchestrator / Workers / Validators.
- **WP2** (`docs/`) — Add to `docs/parallel-agentic-development.md`: a Five-Tier Multi-Agent Taxonomy table (Delegation, Creator-Verifier, Direct Communication, Negotiation, Broadcast), a named "Scope-Isolated Parallelism" pattern that engages the talk directly, and a "Mission" glossary entry. Reframe escalation handler in `docs/lessons-learned.md` as "Self-Healing at Milestone Boundaries." **Additive only** — no edits to existing sections that `harness-engineering-features` touches.
- **WP3** (`agent-coordinator/evaluation/gen_eval/`) — Extend gen-eval generator with `--openspec-change <change-id>` flag. When set, walks `openspec/changes/<change-id>/specs/**/*.md`, parses Requirement+Scenario blocks, and passes them as constraints into the cli-augmented prompt. Update `skills/gen-eval/SKILL.md` and `openspec/specs/gen-eval-framework/spec.md`.
- **WP4** (`skills/validate-feature/`) — **Extend the existing template-only gen-eval phase** to use `--mode cli-augmented --openspec-change <change-id>` when both `evaluation/gen_eval/descriptors/*.yaml` AND an OpenSpec change directory exist; fall back to template-only otherwise. Smaller delta than originally planned because the phase already exists at `SKILL.md:30,260-307`.
- **WP5** (`skills/parallel-infrastructure/`) — Emit `findings-gen-eval.json` from gen-eval runs conforming to `review-findings.schema.json`, with new finding type `behavioral_failure` keyed by originating OpenSpec scenario file:line. Extend `consensus_synthesizer.py` to merge gen-eval findings as a vendor source. Add `behavioral_failure` to the schema's `type` enum. **Additive only** — new vendor source, new finding type, no modifications to existing finding-merge code paths that overlap with `harness-engineering-features`.
- **WP6** (`agent-coordinator/agents.yaml` + `skills/parallel-infrastructure/scripts/`) — Add a worker-vendor-rotation policy: when a worker and a validator are dispatched to the same change, they MUST come from different vendors. Implement in `review_dispatcher.py` (and equivalent worker-side selection in implement-feature) using the existing `exclude_vendor` pattern. Fall back gracefully with a logged warning when only one vendor is available. Update `openspec/specs/agent-archetypes/spec.md`.
- **WP7** (new `skills/playwright-validator/` + `evaluation/gen_eval/playwright/`) — Playwright-CLI-based behavioral validator for frontend features. Generates Playwright test scripts from OpenSpec scenarios + frontend descriptor (base URL, auth flow, selector aliases, browser matrix), executes via `npx playwright test --reporter=json`, emits findings in `review-findings.schema.json` shape. Includes a sample frontend (minimal demo HTML page in `evaluation/gen_eval/fixtures/sample-frontend/`) and a sample frontend descriptor exercised end-to-end as design validation.

This proposal **merges before** the active `harness-engineering-features` change, which will then rebase onto these doc and consensus-synthesizer changes. Coordination communicated via this proposal's archive entry.

## Selected Approach

**Approach 2: Single Umbrella Change with Scope-Isolated Work Packages** (chosen by the operator at Gate 1 — see "Approaches Considered" below).

Rationale: The 7 items share one coherent theme (alignment with Factory Missions vocabulary, validator-surface unification) and merge to one feature branch. One human-attention gate at plan approval and one at PR review keeps coordination cost bounded. The DAG scheduler can still parallelize WP1, WP2, WP6 (independent of each other and of the gen-eval chain) while serializing WP3 → WP4 → WP5 → WP7 along the gen-eval-extension chain.

Concrete dependency DAG:

```
wp-contracts (root)
   ├── wp1-readme-attention            (depends on wp-contracts only — DOCS, parallel-safe)
   ├── wp2-docs-vocabulary             (depends on wp-contracts only — DOCS, parallel-safe)
   ├── wp6-worker-vendor-rotation      (depends on wp-contracts only — CONFIG, parallel-safe)
   ├── wp3-gen-eval-openspec-seeds     (depends on wp-contracts)
   │     └── wp4-validate-gen-eval-extend (depends on wp3)
   │           └── wp5-consensus-gen-eval     (depends on wp4)
   │                 └── wp7-playwright-validator (depends on wp5)
   └── wp-integration                  (depends on all of the above)
```

WP1, WP2, WP6 run in parallel with the gen-eval chain. WP3→WP4→WP5→WP7 serialize because each depends on the schema/output shape of the prior.

## Approaches Considered

### Approach 1: Roadmap of Four Smaller Proposals (REJECTED)

**Description.** Decompose into four separate OpenSpec changes — `docs-vocabulary-alignment`, `gen-eval-validation-integration`, `worker-vendor-rotation`, `playwright-frontend-validator`. Each gets its own proposal, plan-approval gate, PR cycle.

**Pros.**
- Each change is small and reviewable in one sitting.
- Failures isolated — a regression in Playwright work doesn't block doc edits from merging.
- Natural fit for `/plan-roadmap` with prioritized DAG.

**Cons.**
- Four plan-approval gates × four PR cycles = roughly 4× human-attention cost. The repo's CLAUDE.md explicitly frames human attention as the bottleneck.
- Cross-WP dependencies (WP5 needs WP3's output schema) become inter-proposal contracts, which are harder to evolve than intra-proposal interfaces.
- Documentation changes split across changes lose narrative coherence.

**Effort.** L (overhead dominates).

### Approach 2: Single Umbrella Change with Scope-Isolated Work Packages (RECOMMENDED — selected)

**Description.** One OpenSpec change, seven work packages, one feature branch. Work packages decompose by directory (docs/, evaluation/gen_eval/, skills/validate-feature/, skills/parallel-infrastructure/, agents.yaml, new skills/playwright-validator/) so write-scope isolation is natural. The DAG scheduler parallelizes independent work packages (WP1, WP2, WP6) while serializing the gen-eval-extension chain (WP3→WP4→WP5→WP7).

**Pros.**
- One plan-approval gate + one PR review = bounded human attention.
- Cross-WP dependencies are intra-change contracts (schema files in `contracts/`), easier to evolve.
- Coherent narrative in proposal.md and PR description: "align with Factory Missions vocabulary and unify validator surfaces."
- Coordinator-tier parallelism still applies: independent work packages run concurrently in worktrees.

**Cons.**
- Larger PR to review at the end. Mitigated by the per-WP commit log (rebase-merge strategy keeps individual commits visible on `main`).
- One regression in any WP can delay all of them. Mitigated by independent work-package branches that merge into the feature branch only after their own validation passes.

**Effort.** L (but lower than Approach 1 once review overhead is counted).

### Approach 3: Defer WP7 (Playwright) to a Follow-Up Change (REJECTED)

**Description.** Ship WP1-WP6 now. Add Requirements + Scenarios for the Playwright validator to `gen-eval-framework` spec but do not implement until a real frontend feature lands.

**Pros.**
- Smallest current scope.
- No risk of building infrastructure that doesn't fit the first real frontend user's needs.

**Cons.**
- Operator's stated preference (Gate 1) is full implementation with sample frontend, so the design is proven before the first real user.
- Spec-only Requirements without an executable reference implementation drift over time as adjacent code changes. Better to have a sample-frontend exercise that catches drift in CI.
- Removes the cross-validation that WP5's consensus-synthesizer integration actually accepts findings from a non-gen-eval source — Playwright is the second vendor that proves the abstraction is real.

**Effort.** M (smaller, but creates a future-debt item).

## Conflict Resolution with `harness-engineering-features`

This proposal merges first. After merge, `harness-engineering-features` will need to rebase its changes to:
- `docs/lessons-learned.md` — onto the new "Self-Healing at Milestone Boundaries" header introduced by WP2.
- `docs/parallel-agentic-development.md` — onto the new Five-Tier Taxonomy and Scope-Isolated Parallelism sections from WP2.
- `skills/parallel-infrastructure/scripts/consensus_synthesizer.py` — onto the new gen-eval vendor source path added by WP5 (additive; existing finding-merge logic untouched).
- `skills/validate-feature/SKILL.md` — onto the cli-augmented mode extension at lines 260-307 from WP4 (additive; template-only fallback preserved).

To minimize rebase risk, this proposal **strictly avoids modifying** existing sections in those files. WP2 only appends new sections. WP5 only adds a new vendor source. WP4 only adds an `if --mode cli-augmented` branch alongside the existing template-only path.

## Out of Scope

- Renaming existing skill files, schema files, or coordinator service names. Vocabulary additions only.
- Replacing OpenSpec's WHEN/THEN scenario format with a different format.
- Building a new computer-use integration (Playwright CLI is the chosen browser surface).
- Removing the standalone `/gen-eval` skill — it remains user-invocable.
- Modifying existing sections in `docs/lessons-learned.md`, `docs/parallel-agentic-development.md`, `consensus_synthesizer.py` finding-merge logic, or `validate-feature/SKILL.md` template-only handler — to avoid conflict with `harness-engineering-features`.

## Success Criteria

1. A new contributor reading the rewritten `README.md` can identify which skills correspond to each role (Orchestrator/Workers/Validators) without reading other docs.
2. `validate-feature --phase gen-eval` on a change that has both a descriptor and OpenSpec scenarios runs in cli-augmented mode and produces `findings-gen-eval.json` conforming to `review-findings.schema.json`.
3. `consensus_synthesizer.py` emits a single `consensus.json` that ranks scrutiny findings (from parallel-review) and behavioral findings (from gen-eval) together, with severity comparable across types.
4. `review_dispatcher.py` selects different vendors for worker and validator on the same change; logs a warning and continues when only one vendor is available.
5. The sample frontend in `evaluation/gen_eval/fixtures/sample-frontend/` passes Playwright validation when its descriptor + WHEN/THEN scenarios are run via `validate-feature --phase gen-eval`.
6. `harness-engineering-features` rebases cleanly onto the new sections without merge conflicts in any of the four shared files.
