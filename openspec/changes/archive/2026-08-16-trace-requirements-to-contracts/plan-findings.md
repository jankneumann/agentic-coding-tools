# Plan Findings — trace-requirements-to-contracts

## Iteration 1 — 2026-07-28

Five parallel analysis passes (completeness, clarity/consistency, feasibility/
parallelizability, testability, security/performance). Baseline
`openspec validate --strict` passed, so no automatic critical findings.
Findings below are deduplicated across analysts; "confirmed by N" counts
independent analysts reporting the same defect.

### Critical

| # | Type | Confirmed by | Description | Resolution |
|---|------|--------------|-------------|------------|
| F1 | consistency | 3 | Opt-in unit contradicts itself: spec says per contract (`spec.md` "opt-in per contract") AND per capability ("Opt-in status SHALL likewise be recorded per capability"); design D6 says per contract, D10 says per capability then per file ten lines later. The mixed capability (contract A traced, contract B untraced) gets opposite answers, and task 5.2's staging plan is infeasible under the per-capability reading. | New D13: the two directions opt in separately. Forward opt-in per contract document (block presence). Reverse opt-in per capability (presence of `traceability-exclusions.yaml`). Spec, design, proposal, tasks all updated to one rule. |
| F2 | completeness | 3 | Requirement-side exclusions are load-bearing (reverse completeness, stale-exclusion check) but have no schema shape and no home — the schema's `excluded` hangs off an operation, and a requirement with no operation has no operation to hang it on. No task authors the artifact; no package could write it. | `openspec/contracts/<capability>/traceability-exclusions.yaml`, shape lifted from `coverage-exclusions.yaml`, schema added (`traceability-exclusions.schema.json`), doubles as the reverse opt-in switch (D13). Task 4.2b authors gen-eval's. |
| F3 | testability | 3 | Change scope is only defined for touched *operations*. "Touched requirement" is undefined; change-scoped reverse completeness has no scenario (a change adding a requirement nobody cites passes validation silently); "the merge base" names no base ref and has no defined behavior when unresolvable (empty scope = vacuous pass on a blocking gate); "the active change" is never identified (34 candidates on disk). | D12 expanded: touched-set definition for both directions, explicit `--change` argument, pinned merge base with fail-closed unresolvable behavior, `fetch-depth: 0` note on CI wiring. New scenarios. |

### High

| # | Type | Confirmed by | Description | Resolution |
|---|------|--------------|-------------|------------|
| F4 | feasibility | 3 | `cli-contract.schema.json` sets `additionalProperties: false` at flag/positional/command levels — `traceability:` is invalid today, `ToolCommandSpec(**c)` silently drops it, and no task or package can change the schema. The in-flight promotion of `traceability.schema.json` promised by contracts/README.md is likewise assigned to nobody. | New task 2.0 (wp-model): extend `cli-contract.schema.json`, promote both schemas with `$id` rewrite; paths added to wp-model `write_allow`. |
| F5 | testability | 1 | No scenario exercises a *valid* exclusion suppressing a completeness failure — an implementation that ignores exclusions entirely passes every scenario in the delta. | Two suppression scenarios added (forward + reverse). |
| F6 | testability | 1 | Cross-capability citations: success path only. Whether the citation credits the *cited* capability's reverse completeness is unstated (the worked example depends on yes); no failure scenario for an unresolvable cross-capability id. | Scenarios added; D9 amended. |
| F7 | scope | 2 | Opting gen-eval's CLI contract in (4.2) triggers reverse completeness over ~31-48 requirements; only the 17-flag forward direction was planned or sized. Same for 5.2: 122 coordinator requirements. The flagship retrofit turns its own capability red at the sweep as specced. | D13 decouples the directions; task 4.2b authors the reverse exclusions for gen-eval (flagship demonstrates the full chain); coordinator's reverse opt-in explicitly deferred out of 5.2. |
| F8 | consistency | 1 | Sweep blocking semantics differ: proposal says the sweep "reports" unconditionally; D12 and task 5.7 say opted-in capabilities block. The spec never states the sweep's blocking rule at all, and proposal line ~216 still carries the "flips from reported to blocking" wording D12 explicitly struck. | Spec requirement extended + sweep scenario added; proposal wording fixed both places; "scheduled runs" naming unified to push-triggered runs on main. |
| F9 | completeness | 1 | `RENAMED` delta sections are unhandled: old id keeps resolving from the archive (fails open, contradicting D2) while the new id resolves to nothing. | D11 + spec + task 1.5 extended with RENAMED semantics and scenario. |
| F10 | consistency | 1 | Spec's first normative sentence permits "zero or more" citations; the schema (`minItems: 1` + `oneOf`), the README, and forward completeness all forbid zero. | Reworded to "one or more … or carry an exclusion". |
| F11 | testability | 3 | "Disproportionate share" has no deterministic trigger — task 3.7's test would assert the implementation against itself (the mirror problem). Denominator says "a contract's operations", contradicting D10's capability unit and defeated by file splits. | Deterministic output rule: per-requirement count/share over the capability's traced operations, descending; named display-only constant that can never change an exit code. Scenarios added. |
| F12 | completeness | 1 | No `skill-workflow` delta although the change modifies behavior that capability specs: Contract Ref hand-population (`3-Phase Incremental Generation`) becomes generated (D8), and a new blocking gate is wired into `/validate-feature` (ri-08 precedent specs such gates in skill-workflow). | `specs/skill-workflow/spec.md` delta added: MODIFIED 3-Phase requirement, ADDED validation-gate requirement. Ordinal-vs-slug join defined in D8 (join by parse position; Req ID format unchanged). |
| F13 | feasibility | 1 | Gatekeeper's proposed wp-model fix (widen write_allow to regenerated artifacts) is wrong: `interface-descriptor.schema.json` is only reachable from `InterfaceDescriptor`; the traceability field belongs on archetype-only models (`FlagSpec`/`PositionalSpec`/`ToolCommandSpec`/`OperationSpec`) and must default to absent so `exclude_defaults=True` keeps `descriptor.yaml` byte-identical. The real gap was that this constraint was written nowhere. | Constraint written into task 2.2 and wp-model description; write_allow left narrow. |
| F14 | feasibility | 2 | No package can write fixture files (four exact paths, `openspec/contracts/**` denied) and the gate has no injectable roots — tests literally cannot point at anything. | Tasks 1.2/3.5/3.14 require `--specs-root/--contracts-root/--repo-root/--base-ref` parameters (precedent: `check_coverage_completeness.py`); `tests/fixtures/traceability/**` added to write_allow as relief valve. |
| F15 | consistency | 2 | "Phases 4 and 5 are human-led" lives only in work-packages.yaml (tasks.md readers can't see it), and the blanket claim is over-broad: 8 of 12 phase-4/5 tasks are ordinary engineering (generator, wiring, docs) left with no package, no scope, no verification. | tasks.md phase preamble + `[human]` tags on judgement tasks (4.1, 4.2, 4.2b, 5.1, 5.2, 5.3); wp-matrix (5.4-5.5) and wp-wiring (5.6-5.9) packages added with explicit human-precondition notes; yaml comment narrowed. |
| F17 | completeness | 2 | Slug algorithm unspecified; real headings (backtick-leading, em-dashes) produce ids the schema pattern rejects under a naive rule; two headings slugging identically silently merge, defeating reverse completeness with no signal. | D2 gains the explicit algorithm (NFKD fold, lowercase, non-alnum runs to `-`, collapse, strip) + collision-fails-closed scenario; task 1.1 broadened to every `openspec/specs/*/spec.md` with schema-pattern conformance. |

### Medium

| # | Type | Description | Resolution |
|---|------|-------------|------------|
| F18 | completeness | Malformed contract YAML silently downgrades to `untraced` → pass (parse error disables the gate); capability with contracts but no spec.md indistinguishable from author error; schema-invalid blocks (both keys, empty list) reach the gate with no defined behavior. | New "gate fails closed on malformed input" requirement, 4 scenarios. |
| F19 | testability | Scope banner and no-satisfaction wording unpinned — tests would freeze invented literals; "state or imply" undecidable. | Canonical output lines pinned in the spec; "imply" narrowed to a decidable rule. |
| F21 | feasibility | Task 1.3 names a non-enumerating command (`validate --strict` returns a verdict, not a list); `npx` unresolvable (no root package.json); wp-resolver verification lacks `-m` filter so the integration test runs during package verification. | Note rewritten (`openspec show <cap> --json --type spec`, `shutil.which`, skipif); verification command filtered. |
| F22 | feasibility | Task 1.4's REMOVED case has no real instance in the repository; "no fixtures" instruction contradicts it. | Note amended: REMOVED case constructed under `tmp_path` via injectable roots. |
| F23 | feasibility | `deny: openspec/specs/**` starves wp-resolver's read context (deny wins over read_allow in `IndexScopes.allows()`) while buying nothing on writes (write_allow is already an exact-path allowlist). | Dropped from deny on all three packages; `agent-coordinator/**` kept. |
| F24 | feasibility | wp-gate: 9 test tasks, 3 declared test files; 3.11/3.13 have no stated home — the natural `test_change_scope.py` would be a scope violation at the last task of the chain. | File mapping stated; `test_change_scope.py` added to write_allow and verification. |
| F25 | feasibility | wp-resolver and wp-gate run no regression suite or lint; wp-gate is the last link, so a green package with a broken import elsewhere ships to CI. | Regression + ruff verification steps added. |
| F26 | feasibility | Declared task sizes exceed the 120-minute timeouts severalfold. | wp-gate 240min, wp-resolver/wp-model 180min. |
| F28 | testability | MODIFIED delta shadowing has no scenario; the heading-rename case is the D11×D2 intersection where implementations plausibly diverge. | Scenario + task 1.4 case added. |
| F29 | testability | "Completeness is evaluated per capability" has only success scenarios — a gate that never fails reverse completeness passes both. | Failing counterpart scenario added (named once, not once per contract). |
| F31 | testability | "Must be shown to FAIL" has no protocol or evidence capture; final checkpoint says gates must "fail on an unmodified tree" (a correct gate passes there); task 4.3's `__pycache__` note is a non-sequitur carried over from a Python-source mutation (this mutation is YAML). | RED-demonstration protocol stated once at top of tasks.md; checkpoint reworded (fail on documented mutation, pass after restore, evidence recorded); 4.3 note replaced with the real staleness hazard (regenerated descriptor). |
| F33 | consistency | `contracts.openapi.primary` points at README.md, which itself says "No OpenAPI document". | Primary set to the schema file. |

### Low (not fixed this iteration, listed for the record)

| # | Type | Description |
|---|------|-------------|
| F27 | parallelizability | Three isolated worktrees on a zero-parallelism chain are pure merge overhead — addressed: worktree mode set to `shared` (one-word edits, keeps write_allow discipline as the isolation mechanism). |
| F30 | testability | "several" quantified; proportion-negative restated concretely — addressed inline while editing the spec. |
| F32 | performance | Candidate-headings output unbounded (122-208 headings per unresolved citation) — addressed: bounded to nearest-5 with "ranking-for-display is not rebinding" note in D2. |
| F34 | feasibility | Shipped `gen_eval.traceability` module must not hardcode `parent.parent` repo-root hops — folded into the injectable-roots note on task 1.2. |

### Parallelizability assessment (iteration 1)

- Packages: wp-resolver -> wp-model -> wp-gate chain (genuine data dependency,
  shared file `traceability.py`, shared lock key), then wp-matrix and wp-wiring
  after wp-gate; wp-wiring additionally gated on human tasks 4.1-4.2b.
- Independent tasks within packages: phase-3 test tasks 3.1-3.4 are mutually
  independent (fan out under one implementer); phases are otherwise sequential
  by construction.
- Max parallel width: 1 at package level until wp-gate lands, then 2
  (wp-matrix ∥ human phase-4 authoring).
- File overlap: `traceability.py` shared by wp-resolver/wp-model — serialized
  by depends_on + lock key; no unordered overlap remains.

### Vendor review

Deliberately not dispatched from this skill run: the autopilot orchestrator
runs its own PLAN_REVIEW phase (multi-vendor `parallel-review-plan`) immediately
after PLAN_ITERATE, and dispatching the same review twice doubles cost for no
information. Stated here so the skip is visible, per the no-silent-fallback
rule.
