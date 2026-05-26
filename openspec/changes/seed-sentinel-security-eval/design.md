# Design — Sentinel Security-Evaluation Seed

## Context

This change seeds Cisco's foundry-security-spec into the repo as the `sentinel-security-eval` capability. The defining design decision (Gate-1 Approach A + clarification record) is that Sentinel's roles **map onto the coordinator/worker/validator infrastructure that already exists**, rather than standing up a parallel security-eval stack. This document records that mapping, the boundary between the seed and the roadmap, and the analysis behind the one accepted deviation.

## D1 — Role → existing-infrastructure binding

Each foundry role binds to an existing capability or primitive. The seed spec adds Sentinel-specific *behavior*; the *substrate* is reused.

| Foundry role | Binds onto | Nature of binding |
|---|---|---|
| **Orchestrator** | `agent-coordinator` (the long-running coordinator service) + `Agent Orchestration` requirement | Sentinel's two lanes (lifecycle/conversational) are a specialization of existing orchestration; no new orchestrator process. |
| **Indexer** | `codebase-analysis` capability + `docs/architecture-analysis/` artifacts | Structural index reuses existing codebase-analysis machinery; query interface is the new surface. |
| **Cartographer** | `codebase-analysis` (architecture summary) extended with security-context documents | Net-new security documents; reuses the analysis substrate. |
| **Detector** | `evaluation-framework` / `gen-eval-framework` (generation/evaluation passes) | Detection rules + exploratory hunting are new; the eval-pass execution model is reused. |
| **Triager** | `evaluation-framework` + `agent-coordinator` Verification Gateway/Policies | Verdict assignment + evidence gate are new; verification-tier plumbing is reused. |
| **Validator** | `live-service-testing` capability | Clean-room reproduction against a testbed maps directly onto live-service testing. |
| **Coverage-Guide** | `roadmap-orchestration` (goal→checklist decomposition) + `observability` | Checklist derivation reuses decomposition patterns; coverage status feeds observability. |
| **Reporter** | `observability` + `merge-pull-requests`/GitHub issue tooling | Per-finding reports + rollup reuse observability and GitHub publishing surfaces. |
| **Coordination substrate** | `agent-coordinator` **Work Queue** + **Heartbeat and Dead Agent Detection** | Atomic claiming, `open/blocked/closed` states, heartbeat liveness, auto-block — all already specified; Sentinel depends on them (no `MODIFIED` delta in the seed). |

**Why dependency, not `MODIFIED`:** the seed introduces no change to coordinator behavior — it consumes the queue and heartbeat as-is. Authoring `MODIFIED` deltas now would mean inventing extensions (e.g., eval-role claim tags) before they're concrete. Those belong to roadmap implementation changes, which will copy the exact existing requirement text and modify it.

## D2 — Seed ↔ roadmap boundary

| In the seed (this change) | Deferred to `/plan-roadmap` |
|---|---|
| Vendored `constitution.md` + Deviations | Wiring each role into runnable agents |
| `sentinel-security-eval` capability spec (roles, lifecycle, governance, policy) | Indexer parser, Detector rule corpus, Triager investigation loop |
| Role→infra binding table (this doc) | Testbed provisioning + Validator reproduction harness |
| Verdict-provenance requirement | Dashboard/feed implementation (FR-120–FR-124) |
| Recording the 5 extensions as candidates | Adopting any extension role |

The seed is **spec + governance only**. `openspec validate --strict` is the acceptance test; no role logic ships here.

## D3 — Deviation analysis (multi-vendor vs. single-provider)

Foundry §11.2 + Constitution V assume a single LLM provider so verdicts are reproducible. This repo is multi-vendor by design. We accept the deviation (D-1 in `constitution.md`) and mitigate:

- **What we lose:** bit-for-bit verdict reproducibility across runs — a re-triage may land on a different model and reach a different verdict.
- **What we keep:** the rate-arbiter behavior of Principle V, preserved *per provider* (shared per-provider backoff).
- **Mitigation:** the **Verdict Provenance** requirement records vendor/model/corpus-version on every verdict, and re-run comparison is provenance-aware so model variance is not mistaken for a target regression (relevant to foundry SC-005 dedup).
- **Residual risk (accepted):** cross-run stability is statistical; high-stakes verdicts should be corroborated across providers before publication. Revisiting single-provider mode is a future decision, not part of this seed.

## D4 — Deferred extensions (adopt-when preconditions)

Recorded so the roadmap can pick them up with the right gating:

| Extension | Adopt when | Do not adopt when |
|---|---|---|
| Deep-Tester | A stable testbed exists and findings need PoC binaries | No testbed |
| Variant-Hunter | A vector store, semantic embeddings, and a true-positive corpus all exist | Any of those is missing (true for the seed — no vector store) |
| Attack-Mapper | Reviewers ask about chaining and evaluations are >2 quarters old | First build |
| Remediator | A code-review process for AI changes and merge gating are mature | Reporter output is not yet trusted |
| Self-Improver | The rule corpus has measured gaps with examples | Day one |

## D5 — Risks

- **Spec size:** one large capability spec (~21 requirements). Mitigated by the roadmap decomposing it into per-role implementation changes.
- **Binding drift:** the design table is documentation, not enforced by spec structure. Mitigated by roadmap changes authoring concrete `MODIFIED` deltas when they extend coordinator behavior.
- **Deviation creep:** the multi-vendor exception could erode reproducibility further. Mitigated by the binding verdict-provenance requirement and the residual-risk note.
