# Seed Sentinel — Agentic Security-Evaluation Capability (Foundry adaptation)

## Why

Cisco's [foundry-security-spec](https://github.com/CiscoDevNet/foundry-security-spec) is an infrastructure-neutral blueprint for **agentic AI security evaluation**: a fleet of specialised agents that index a target's source, map its attack surface, detect candidate vulnerabilities, triage them behind an evidence gate, independently validate exploitability, and report only findings that survive. It ships ~130 functional requirements and 11 inviolable principles distilled from production failures, deliberately under-specified at ~35 `[NEEDS CLARIFICATION]` points so each adopter resolves them for their own stack.

This repository is already an agentic multi-agent platform — it has an orchestrator/worker/validator model, a coordinator work-queue with atomic claiming and heartbeat liveness, worktree/container sandboxing, verification tiers, and observability surfaces. That overlap is exactly why foundry is a strong fit here: the security-evaluation roles can **map onto the coordinator we already run** rather than standing up a parallel stack.

The foundry adoption workflow is *seed → clarify → specify → iterate → implement*. Normally driven via spec-kit; we use **OpenSpec** instead. The clarify step (all ~35 markers) is **already complete** — see the resolved decision record below. This change performs the **seed + specify** steps as a single OpenSpec change: it vendors an adapted constitution and hardens the clarified seed into WHEN/THEN, SHALL/MUST spec deltas. It deliberately stops before role *implementation*, which a follow-on `/plan-roadmap` decomposes into separate changes.

The system is named **Sentinel**.

### Resolved clarification record (foundry clarify step — do not re-litigate here)

**Identity & scope (Group A):**
- System name: **Sentinel**.
- Eval scope: **authorized, first-party, source-available** (foundry §1.5 holds → all invariants intact).
- Core roles: all **8** (Orchestrator, Indexer, Cartographer, Detector, Triager, Validator, Reporter, Coverage-Guide) **mapped onto the existing coordinator/worker/validator model**, not built net-new. Orchestrator = the long-running coordinator service.

**Integration (Group B):**
- VCS + issue tracker: **GitHub**. Datastore: **Postgres/ParadeDB**. Config format: **YAML**. Defect export: **GitHub issues**. Agent harness: **coordinator + Claude Code/Codex**.
- Vector store: **none for the seed** (so Variant-Hunter stays deferred).
- Sandbox enforcement (§9.1/§11.6): **ephemeral containers + E2B** ("sandbox-by-infrastructure").
- Compliance mapping (§11.10): **none for the seed** (explicit, not silence). Multi-tenancy (§13/NFR-003): **single-tenant for the seed**.
- **DEVIATION — recorded, not silent:** foundry §11.2 / Principle V assume a single LLM provider for reproducible verdicts; Sentinel instead **reuses this repo's multi-vendor routing — as a consensus mechanism, not a tolerated liability**. Each vendor applies the rubric internally (within-vendor consistency); vendor scales are calibrated to a common reference; calibrated results are synthesized into a `confirmed`/`unconfirmed`/`disagreement` consensus verdict reusing `parallel-infrastructure`'s `ConsensusSynthesizer` (the same substrate as vendor-diverse code review). The deviation is captured as a named exception (D-1) in `constitution.md`; **verdict-provenance** records vendor/model/corpus plus per-vendor dispositions and consensus status; the synthesized consensus verdict — not a lone vendor's — is what the Reporter publishes. The governing rule: never mix raw cross-vendor outputs on one scale.

**Policy (Group C):**
- Severity: **CVSS v4**, owned by the Reporter (never raw model output). Weakness taxonomy: **CWE**. Triager **surfaces `needs-review`** to humans for findings that fail the evidence gate. Label naming: namespaced strings (`triaged/true-positive`, `triaged/needs-review`, `verdict/false-positive`, …).

**Extensions (Group D):** all five (Deep-Tester, Variant-Hunter, Attack-Mapper, Remediator, Self-Improver) **deferred** to the roadmap, each with its adopt-when precondition recorded.

## What Changes

This is a **seed-only spec change**. No role logic is implemented. It produces governing + specification artifacts only.

### Vendored constitution (1)

**`constitution.md`** (in this change dir) — the 11 foundry principles adapted to this repo's vocabulary, plus an explicit **Deviations** section documenting the multi-vendor exception to Principle V ("The Provider Is The Rate Arbiter" / single-provider reproducibility) and its mitigation (verdict-provenance). A task wires a reference to it from `openspec/project.md`.

### New capability spec (1)

**`specs/sentinel-security-eval/spec.md`** — the hardened seed. Adds requirements covering:
- The **8 core roles**, each as a `### Requirement:` with success + failure scenarios, written as bindings onto existing coordinator/worker/validator infrastructure.
- The **finding lifecycle**: states (`candidate → verdict → confirmed → [validated] → published`), the five verdicts, the three-leg **evidence gate** (reachability, trust boundary, impact) with the presence-vuln carve-out, structure-based **fingerprinting**, and the Validator-only **exploited** flag.
- **Governance**: coverage gate, three-condition yield auto-stop, auto-blocking, hard-rule scope.
- **Policy bindings**: CVSS v4 severity owned by Reporter, CWE taxonomy, `needs-review` surfacing, namespaced labels.
- **Verdict-provenance** (the deviation mitigation): every verdict records the vendor/model and rule/corpus version that produced it.

### Binding onto the existing coordinator (no `MODIFIED` deltas in the seed)

Sentinel's coordination substrate (atomic claiming, heartbeat liveness, auto-block) maps onto requirements `agent-coordinator` **already owns** — "Work Queue" and "Heartbeat and Dead Agent Detection". The seed *uses* these; it does not change their contract, so it adds **no `MODIFIED` deltas**. Instead, the relevant Sentinel requirements are authored as `## ADDED Requirements` that explicitly **depend on** those coordinator requirements, and `design.md` carries the full role→primitive binding table. Concrete coordinator extensions (e.g., tagging claims/heartbeats with eval-role semantics) are deferred to roadmap implementation, where the exact requirement text to modify is known.

### Design doc (1)

**`design.md`** — the **role-mapping table** (each foundry role → existing capability/primitive it binds to), the seed↔roadmap boundary, and the deviation analysis (what reproducibility we lose by reusing multi-vendor routing and how verdict-provenance compensates).

### Roadmap handoff

A `tasks.md` item to run `/plan-roadmap` against this seed, decomposing the 8 roles + lifecycle + governance into prioritized follow-on implementation changes, and recording the 5 extension roles as roadmap candidates with their adopt-when preconditions.

### Out of scope

- **Any role implementation** (no Indexer parser, no Detector rules, no Triager loop, etc.) — deferred to the roadmap.
- The **5 extension roles** — recorded as roadmap candidates only.
- **Vector store / semantic search** (FR-023) — dropped for the seed; revisited if Variant-Hunter is later adopted.
- **Compliance-framework mapping** and **multi-tenancy** — explicitly out for the seed.
- Restoring the single-provider invariant — we accept the multi-vendor deviation; revisiting it is a future decision, not this change.

## Approaches Considered

### Approach A — Single cohesive `sentinel-security-eval` capability (hybrid) — **Recommended**

One new capability spec holds the full seed (roles + lifecycle + governance + policy + verdict-provenance) as `## ADDED Requirements`. The "map onto existing coordinator" decision lives in `design.md` as a binding table, reinforced by a *minimal* set of `## MODIFIED Requirements` on `agent-coordinator` only where Sentinel genuinely extends an existing invariant (e.g., tagging claims/heartbeat with eval-role semantics).

- **Pros:** Cohesive and reviewable as one unit; archives cleanly into a single `openspec/specs/sentinel-security-eval/`; the roadmap can decompose from one authoritative source; respects OpenSpec's one-capability-per-concern without fragmenting; keeps security-eval specifics out of general-purpose capability specs.
- **Cons:** One large spec file; the role→infra binding is documented in design.md rather than enforced by spec structure.
- **Effort:** M

### Approach B — Distributed deltas across existing capabilities

Spread the seed as `MODIFIED`/`ADDED` deltas onto existing capabilities: `agent-coordinator` (substrate), `evaluation-framework`/`gen-eval-framework` (Detector/Triager), `live-service-testing` (Validator/testbed), `observability` (Reporter/dashboards), with only finding-lifecycle as a new capability.

- **Pros:** Maximizes literal reuse; each role's spec lives next to the machinery it extends.
- **Cons:** Pollutes general-purpose capabilities with security-eval-specific requirements; the seed is scattered across 5+ files, hard to review/archive/roadmap as a unit; high risk of conflicting with unrelated in-flight changes to those capabilities; the foundry "constitution + seed" gestalt is lost.
- **Effort:** L

### Approach C — One capability per role-group

Several new capabilities (`sentinel-detection`, `sentinel-triage-validation`, `sentinel-reporting`, `sentinel-coordination`).

- **Pros:** Modular; mirrors eventual implementation packages; smaller individual files.
- **Cons:** Premature fragmentation for a seed; heavy cross-referencing between capabilities for the shared finding lifecycle; the roadmap step is the right place to decide this decomposition, not the seed.
- **Effort:** L

**Recommendation: Approach A.** It honors the "map onto existing coordinator" decision (via the design.md binding table + minimal targeted deltas) while keeping the seed cohesive, reviewable, and cleanly archivable — and it leaves role decomposition to `/plan-roadmap`, which is where the clarification record says implementation planning belongs.

### Selected Approach

**Approach A — Single cohesive `sentinel-security-eval` capability (hybrid).** Selected at Gate 1. The seed is authored as one new capability spec; the role→infrastructure bindings are documented in `design.md`. The seed binds to `agent-coordinator`'s existing "Work Queue" and "Heartbeat and Dead Agent Detection" requirements by **dependency** (ADDED Sentinel requirements that reference them), not by `MODIFIED` delta — the seed introduces no change to coordinator behavior, so coordinator extensions are deferred to roadmap implementation. Approaches B and C are recorded above as considered-and-rejected.

## Success Criteria

- `openspec validate seed-sentinel-security-eval --strict` passes.
- The capability spec encodes all 8 roles, the 5-verdict lifecycle, the 3-leg evidence gate (with presence-vuln carve-out), structure-based fingerprinting, the Validator-only exploited flag, the coverage + yield-auto-stop + auto-block governance, and the CVSS-v4/CWE/`needs-review`/namespaced-label policy — each requirement carrying ≥1 success and ≥1 failure/edge scenario.
- `constitution.md` contains all 11 principles AND a Deviations section naming the multi-vendor exception and its verdict-provenance mitigation.
- `design.md` contains a role→existing-capability binding table covering all 8 roles.
- No role implementation code is added; the diff is confined to `openspec/changes/seed-sentinel-security-eval/` plus the `project.md` constitution reference.
- A `tasks.md` item hands off to `/plan-roadmap` and records the 5 deferred extensions with adopt-when preconditions.
