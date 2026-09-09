# Design — Factory Missions Architecture Alignment

## Problem Restatement

Two structural gaps and three documentation gaps, all blocking adoption of Factory Missions vocabulary in this repo:

1. **Validator surface fragmentation.** Two validator implementations (`parallel-review-*` and `gen-eval`) produce findings in different formats. Operators reconcile two reports manually.
2. **Worker-validator vendor coupling.** Reviewers already enforce vendor diversity; workers do not. A worker and its validator can run on the same model family.
3. **Discoverability** — README, parallel-agentic-development.md, lessons-learned.md don't use the talk's pedagogical vocabulary. (DOCS gaps)

Frontend behavioral validation is also absent; Playwright closes that gap.

## Dependency DAG

```
                          ┌──────────────────┐
                          │  wp-contracts    │  ← schema deltas, frontend descriptor, agents.yaml policy schema
                          └────────┬─────────┘
                                   │
        ┌──────────────────────────┼─────────────────────────┐
        │                          │                         │
        ▼                          ▼                         ▼
┌──────────────┐         ┌──────────────────┐      ┌──────────────────┐
│ wp1-readme   │         │ wp2-docs-vocab   │      │ wp6-vendor-rotn  │
│  (DOCS)      │         │  (DOCS)          │      │  (CONFIG+CODE)   │
└──────┬───────┘         └─────────┬────────┘      └────────┬─────────┘
       │                           │                        │
       │                           │                        │
       │          ┌────────────────┴───────┐                │
       │          ▼                                          │
       │   ┌──────────────┐                                  │
       │   │ wp3-gen-eval │                                  │
       │   │ -openspec    │                                  │
       │   └──────┬───────┘                                  │
       │          ▼                                          │
       │   ┌──────────────┐                                  │
       │   │ wp4-validate │                                  │
       │   │ -gen-eval    │                                  │
       │   └──────┬───────┘                                  │
       │          ▼                                          │
       │   ┌──────────────┐                                  │
       │   │ wp5-consensus│                                  │
       │   │ -gen-eval    │                                  │
       │   └──────┬───────┘                                  │
       │          ▼                                          │
       │   ┌──────────────┐                                  │
       │   │ wp7-playwrt  │                                  │
       │   │ -validator   │                                  │
       │   └──────┬───────┘                                  │
       │          │                                          │
       └──────────┴──────────────────────────────────────────┘
                  │
                  ▼
          ┌──────────────────┐
          │ wp-integration   │  ← merge worktrees, run validate-feature end-to-end on sample frontend
          └──────────────────┘
```

**Parallelizable**: WP1, WP2, WP6 run concurrently with the WP3→WP4→WP5→WP7 chain after wp-contracts completes. Three distinct write-scope partitions (`docs/` for WP1+WP2 — see decision D1 below — vs `agents.yaml` for WP6 vs `evaluation/gen_eval/` and `skills/` for the chain) prevent collisions.

**Serializable**: WP3 → WP4 → WP5 → WP7 is a hard chain. WP4 needs WP3's `--openspec-change` flag to call. WP5 needs WP4 to produce a `findings-gen-eval.json`. WP7 needs WP5's schema (`behavioral_failure` type) and consensus integration.

## Key Decisions

### D1 — WP1 and WP2 share the `docs/` write scope but operate on disjoint files

**Decision.** WP1 writes only `README.md`. WP2 writes only `docs/parallel-agentic-development.md`, `docs/lessons-learned.md`, and `docs/skills-workflow.md`. They share the `docs/` directory tree but never the same file.

**Why.** `scope_checker.py` enforces `write_allow` globs at the file level. As long as the globs don't overlap on a specific file, two work packages can both list `docs/**` in `write_allow`. Per-file disjoint scopes are sufficient for parallel execution.

**Alternative considered.** Combine WP1+WP2 into a single docs work package. Rejected because the docs changes are pedagogically distinct (README opener is for first-impression readers; parallel-agentic-development.md additions are for intermediate readers) and reviewers can sign off on them independently.

### D2 — Playwright validator packaged as a peer skill, not a new gen-eval mode

**Decision.** Create `skills/playwright-validator/` rather than adding `--mode playwright` to `evaluation/gen_eval/__main__.py`.

**Why.**
- The Playwright pipeline has different system dependencies (npx, browser binaries) from the existing Python-only gen-eval modes. Packaging as a peer skill keeps gen-eval's dependency surface minimal.
- Skill packaging matches the repo's convention (`skills/<name>/SKILL.md`) and integrates with existing skill discovery (`/playwright-validator`).
- The peer skill can still be invoked from `validate-feature --phase gen-eval` when a `frontend-descriptor.yaml` is detected, without coupling gen-eval's Python module to Node tooling.

**Alternative considered.** New mode in gen-eval (`--mode playwright`). Rejected because it expands gen-eval's responsibility beyond its current Python-only surface and complicates rate-limit / cost handling that gen-eval's `AdaptiveBackend` is built for.

**Implication for spec.** The gen-eval-framework spec delta describes the Playwright pipeline's behavior abstractly without binding it to either packaging choice. The `evaluation-framework` spec delta references "the Playwright validator skill" by behavior, not by entry point.

### D3 — `behavioral_failure` is a new type-enum value, not a subtype of `correctness`

**Decision.** Add `behavioral_failure` as a peer to `correctness`, `security`, `performance`, etc., in `review-findings.schema.json`'s `type` enum.

**Why.**
- `correctness` is used by scrutiny reviewers for static analysis findings (logic bugs found by reading code). `behavioral_failure` is structurally different — it's evidence of the deployed system behaving wrong, not a hypothesis from code review.
- A separate enum value lets consumers filter or route by type (e.g., only behavioral findings block PR merge in `cleanup-feature`).
- Severity comparability is preserved: both types use the same `severity` rubric, so consensus ranking remains uniform.

**Alternative considered.** Reuse `correctness` with a `metadata.source: behavioral` discriminator. Rejected because consumers using JSON Schema validation can't easily route on metadata; type-enum values are first-class.

### D4 — Vendor-diversity policy is per-change, not per-package

**Decision.** The `worker_vs_validator` constraint applies across roles within one OpenSpec change. It does NOT apply per work package within a change.

**Why.**
- Within a change, a worker on WP4 (Python) and a validator on WP4 share the change. They get different vendors.
- A worker on WP4 and a worker on WP5 are both workers; the constraint doesn't apply between them. They MAY share a vendor.
- This keeps the policy implementable from existing change-id metadata in the dispatcher's session state, without per-package tracking.

**Alternative considered.** Per-package diversity (every package gets a different vendor). Rejected because it would force exhaustion of the vendor pool on changes with more packages than vendors, leading to many fallback-warnings.

### D5 — Existing template-only gen-eval phase is preserved as the fallback path, not replaced

**Decision.** WP4 wraps the existing template-only invocation in a conditional. The cli-augmented branch is NEW; the template-only branch is UNCHANGED.

**Why.**
- Backward compatibility for projects that have descriptors but no OpenSpec changes (or where the operator wants the cheaper template-only run).
- Reduces risk of regression — the existing template-only handler is well-tested via the in-repo gen-eval descriptors.
- Aligns with the proposal's "additive only" stance toward `validate-feature/SKILL.md` to minimize conflict with `harness-engineering-features`.

### D7 — Sample-frontend HTTP server binds to localhost only

**Decision.** The sample frontend's `lifecycle.startup_command` (in the sample descriptor) and the runtime check in the Playwright validator both bind/expect `127.0.0.1`, never `0.0.0.0`. The frontend descriptor schema enforces this default via the `bind_address` field with default `127.0.0.1`. The validator asserts the listening socket binds to the configured address before launching browsers.

**Why.** Running validator infrastructure on a developer machine (or in CI) should not expose a server to the network. Default-secure binding prevents accidental exposure when the validator is invoked from contexts where firewall rules differ.

**Alternative considered.** Default to `0.0.0.0` for "convenience in containerized CI." Rejected — operators who genuinely need non-localhost binding can opt in via the descriptor's `bind_address` field; the default should fail closed.

### D8 — Findings filename is bound to the validator's packaging, not its surface

**Decision.** Per D2 (Playwright as peer skill), the Playwright validator emits `findings-playwright.json`. Gen-eval emits `findings-gen-eval.json`. A change with both an HTTP descriptor and a frontend descriptor produces both files; consensus_synthesizer treats them as separate vendor sources.

**Why.** The original spec said `findings-gen-eval.json (or findings-playwright.json)` with OR-ambiguity, leaving consumers unable to predict which file to expect. Binding the filename to the packaging removes the ambiguity: skill-name → filename. The two filenames coexist when both validators run; neither overwrites the other.

**Alternative considered.** Single `findings-behavioral.json` with a `metadata.source` discriminator. Rejected because consensus_synthesizer's vendor-source logic keys on filenames, and merging into one file removes the per-vendor traceability that D3 relies on.

### D9 — Vendor-diversity session state is change-scoped, file-backed, and cleanup-managed

**Decision.** The dispatcher's worker/validator vendor-tracking state is persisted at `openspec/changes/<change-id>/.dispatch-state.json`. Permissions: `0644`. Cleanup: removed by `/cleanup-feature` on archive.

**Why.**
- Change-scoped paths align with the existing per-change artifact convention (`session-log.md`, `handoffs/`).
- File-backed (rather than in-memory) supports cross-skill-invocation continuity — `/implement-feature` and a later `/parallel-review-implementation` see the same state.
- World-readable is acceptable (the state isn't sensitive — it's just vendor names) but world-writable is rejected to prevent forging records that bypass the diversity policy.

**Alternative considered.** Coordinator-side state (HTTP API to register/query vendor selections). Rejected for now — adds a coordinator dependency for a feature that should work in standalone mode. Can be promoted to coordinator-side state in a follow-up if cross-machine sessions emerge.

### D6 — Sample frontend uses static HTML, not a framework

**Decision.** The sample frontend at `evaluation/gen_eval/fixtures/sample-frontend/` is a single static `index.html` with inline JavaScript, served by `python -m http.server`. No npm dependencies, no React/Vue/Svelte.

**Why.**
- Smallest possible surface — proves the validator works without introducing a JS toolchain.
- No npm install in CI (Playwright still needs `npx playwright install` for browser binaries, but no app-side dependencies).
- A real frontend feature in this repo would bring its own framework; the validator should be agnostic to that choice. A static page validates the agnosticism.

## Interface Contracts Between Work Packages

### WP3 → WP4

**Contract:** gen-eval CLI accepts `--openspec-change <id>` flag. When set in `cli-augmented` mode, gen-eval emits scenarios with a `source.openspec_scenario: "<file>:<line-start>-<line-end>"` metadata field.

**File:** `contracts/gen-eval-cli.md` (CLI flag specification)

### WP3 + WP5 → WP4

**Contract:** When invoked with `--report-format json` or `both`, gen-eval emits `findings-gen-eval.json` at `<output-dir>/findings-gen-eval.json` conforming to `review-findings.schema.json` with `type: behavioral_failure`.

**File:** `openspec/schemas/review-findings.schema.json` (modified by WP5 to add `behavioral_failure` to enum)

### WP5 → WP7

**Contract:** `consensus_synthesizer.py` accepts `findings-gen-eval.json` (produced by gen-eval OR Playwright) as a vendor-source input. Both gen-eval and Playwright validators must emit findings in the same shape so the synthesizer can treat them uniformly.

**File:** `contracts/findings-vendor-source.md` (the convention for naming and locating per-vendor findings files)

### WP6 → all

**Contract:** `agents.yaml` gains a top-level `policies.vendor_diversity` block. The dispatcher's `select_agent()` function reads this block and applies the constraint.

**File:** `contracts/agents-policy-schema.json` (JSON Schema fragment for the new block)

### WP7 frontend descriptor

**Contract:** `evaluation/gen_eval/descriptors/<name>-frontend.yaml` files conform to `contracts/frontend-descriptor.schema.json` with required fields `base_url`, `auth_flow`, `selectors`, `browsers`.

## Risk Register

| Risk | Mitigation |
|---|---|
| `harness-engineering-features` merges first despite our intent | Coordinate via this proposal's session log; WP2 and WP5 are strictly additive so rebase conflicts are minimal even if order swaps |
| `behavioral_failure` enum addition rejected by `openspec validate` schema-compatibility check | Run schema validation as the first step of WP5; if rejected, fall back to a `metadata.source: behavioral` discriminator (D3 alternative) — recoverable design pivot |
| Playwright system dependencies (browser binaries) flake in CI | WP7 includes a `playwright-deps-check` task that runs `npx playwright install --dry-run` and skips the phase with a clear error if unavailable (per the spec's "Missing Playwright CLI degrades cleanly" scenario) |
| Vendor diversity policy blocks dispatch in single-vendor environments | Spec requires `warn_and_continue` fallback; tested in agent-archetypes spec scenario "Single-vendor environment falls back gracefully" |
| Static-HTML sample frontend insufficient for first real frontend user | Acceptable risk — sample's purpose is to prove the abstraction works end-to-end, not to be a comprehensive starter kit. First real user can extend the sample or replace it. |

## Spec Compliance Summary

| Spec | Requirements added | Scenarios |
|---|---|---|
| `gen-eval-framework` | 3 (OpenSpec-Seeded Scenario Generation, Behavioral Findings Schema Conformance, Browser-Driving Behavioral Validation) | 9 |
| `evaluation-framework` | 2 (gen-eval Phase Cli-Augmented Mode Selection, Behavioral Findings in Consensus Surface) | 7 |
| `agent-archetypes` | 1 (Worker-Validator Vendor Diversity) | 4 |
| `skill-workflow` | 5 (Validator Surface Documentation, Five-Tier Multi-Agent Taxonomy Documentation, Scope-Isolated Parallelism Documentation, Mission Glossary Entry, Self-Healing at Milestone Boundaries Reframing) | 6 |

Total: **11 new Requirements, 26 new Scenarios.** All Scenarios use OpenSpec-canonical WHEN/THEN/AND structure with SHALL/MUST language for normative statements.
