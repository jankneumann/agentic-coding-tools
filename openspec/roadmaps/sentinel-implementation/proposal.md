# Sentinel Implementation Roadmap

## Motivation

The `seed-sentinel-security-eval` OpenSpec change established Sentinel — an agentic security-evaluation capability adapted from Cisco's foundry-security-spec — as a hardened, validated spec plus a vendored constitution. The seed deliberately implements **no** role logic; it maps the 8 foundry roles onto this repo's existing coordinator/worker/validator infrastructure and defers all implementation to this roadmap.

This roadmap decomposes that implementation into prioritized, dependency-ordered OpenSpec change candidates. Each candidate binds to the existing capability it extends (per `seed-sentinel-security-eval/design.md` D1) so Sentinel is built by *extending* the platform, not duplicating it. Success looks like: an operator can point Sentinel at an authorized first-party, source-available target and receive a triaged, evidence-gated set of security findings published to GitHub, with coverage- and yield-based auto-stop — every finding carrying CVSS-v4 severity, a CWE class, and verdict provenance.

The 5 optional foundry extension roles are recorded here as **deferred** candidates gated on their adopt-when preconditions; none is scheduled for the initial build.

## Capabilities

### Service: Coordination Substrate Binding

Wire Sentinel's role agents onto `agent-coordinator`'s existing Work Queue and Heartbeat-and-Dead-Agent-Detection requirements: tag claims and heartbeats with eval-role semantics, emit heartbeats on a separate execution lane, and tie claim release to heartbeat staleness (never wall-clock). This is an extension of existing coordinator behavior, not a rebuild.

**Acceptance Outcomes:**
- Two role agents claiming concurrently receive different tasks (atomic claiming) via the existing Work Queue.
- A killed role agent's claim auto-releases within the heartbeat-stale window.
- Heartbeat emission is never blocked by a role's primary work.

### Service: Finding Store with Fingerprint and Provenance

Implement the internal finding store and its state machine (`candidate → verdict-assigned → confirmed → [validated] → published`), the structure-based fingerprint `(normalized_path, symbol, vulnerability_class)`, and the verdict-provenance record (vendor, model, corpus version). All writes are atomic write-then-replace.

**Acceptance Outcomes:**
- A finding's fingerprint is unchanged by edits that move line numbers but not the symbol or class.
- A re-run against an unchanged target produces zero new findings and zero duplicates.
- Every persisted verdict carries vendor, model, and corpus-version provenance; a verdict missing provenance is rejected.
- A crash mid-write leaves readers observing the complete prior state.

### Service: Sandbox and Scope Enforcement

Provide sandbox-by-infrastructure for the role fleet: egress constrained to an allowlist (LLM providers, issue tracker, testbed) enforced by ephemeral containers and E2B, target mounts read-only, and operator hard-rules injected into every agent system prompt as defense-in-depth.

**Acceptance Outcomes:**
- An agent with elevated privileges cannot reach a host outside the allowlist.
- Writes to target source, config, or sandbox definition fail (read-only mounts).
- Every spawned role agent's system prompt contains the operator hard-rules plus default non-testbed prohibitions.

### Service: Indexer

Build the structural index of target source (symbols, call graph, cross-references) using a deterministic parser, exposing the query interface (`get-function-body`, `get-callers`, `get-callees`, `find-symbol`, full-text) that every downstream role consumes. Incremental on re-run.

**Acceptance Outcomes:**
- The index becomes queryable and signals readiness so the Orchestrator can release downstream roles.
- A re-run updates only changed portions of the index.
- Unparseable files are recorded without aborting the pass.

### Service: Cartographer

Produce persisted security-context documents (architecture overview, attack-surface enumeration, trust boundaries, data flows, threat model) readable by all roles, extending `codebase-analysis`. Roles degrade gracefully when the map is absent.

**Acceptance Outcomes:**
- All five security-context documents are persisted and readable by every role.
- A downstream role runs using the Indexer alone when the map is not yet present.

### Service: Detector

Produce candidate findings breadth-first via rule application (per-function, dependency, secret scanning) and exploratory hunting, drawing on an independent versioned rule corpus and recording rule gaps. Candidates go to the finding store, never the tracker.

**Acceptance Outcomes:**
- Candidates are written to the store with state `candidate`, never to the issue tracker.
- Rule gaps are recorded against the corpus version while the candidate is still queued.
- The Detector assigns no verdict, severity, or exploited status.

### Service: Triager

Investigate each candidate, assign exactly one of the five verdicts, and enforce the three-leg evidence gate (reachability, trust boundary, impact) with the presence-vuln carve-out and mechanical citation resolution. Surface `true-positive` toward publication and `needs-review` to humans.

**Acceptance Outcomes:**
- Each candidate receives exactly one verdict with recorded reasoning.
- An unprovable-likelihood candidate is assigned `needs-review`, not `true-positive`.
- A citation that fails mechanical resolution demotes the verdict to `needs-review`.
- Non-true-positive verdicts remain in internal storage.

### Service: Validator

For `true-positive` findings claiming exploitability, attempt independent clean-room reproduction against a testbed with a fresh agent; set `exploited` only on observed impact, record explanations on failure without clearing verdicts, and produce a runnable PoC. Degrade to PoC-only when no testbed exists.

**Acceptance Outcomes:**
- `exploited` is set only when impact is independently reproduced, with a PoC attached.
- A failed reproduction records an explanation and leaves the verdict intact.
- With no testbed, the Validator never sets `exploited`.

### Capability: Severity, Classification, and Label Taxonomy

Implement Reporter-owned CVSS-v4 severity derivation, CWE weakness classification, and the fixed namespaced label taxonomy (`triaged/true-positive`, `triaged/needs-review`, `verdict/false-positive`, `severity/<band>`, `cwe/<id>`, `exploited`). Raw model severity is never authoritative.

**Acceptance Outcomes:**
- Every published finding carries a CVSS-v4 severity computed via the owned rubric and a CWE class.
- A model-emitted severity string is ignored as authoritative.
- `needs-review` findings are surfaced via the `triaged/needs-review` label and never carry `triaged/true-positive`.

### Service: Reporter

Produce self-contained per-finding reports (title, location, description, impact, reproduction, evidence) and an evaluation-level rollup grouping findings by component, publishing to GitHub issues with consistent labels and updating (not duplicating) by fingerprint.

**Acceptance Outcomes:**
- A published finding contains all required report fields and taxonomy labels.
- A finding whose fingerprint matches an existing tracker entry updates it rather than creating a duplicate.

### Service: Coverage-Guide

Derive a finite checklist from operator goals and the security map, queue directed tasks toward uncovered items, check items off on credible attempt (not outcome), and declare coverage-complete when all items are checked. Refuse empty goals.

**Acceptance Outcomes:**
- A non-empty goal set yields a finite checklist with directed tasks for gaps.
- A credibly attempted item with no finding is still checked off.
- Empty goals are refused with a reported missing-goals condition.

### Capability: Governance Gates

Implement the coverage + yield auto-stop (stop only when coverage-complete AND yield-below-threshold, after a full trailing window and minimum runtime) and task auto-blocking (claimed/released N times → `blocked`, re-openable). Severity weights, multiplier, window, runtime, and threshold are operator-configurable.

**Acceptance Outcomes:**
- Low yield before coverage-complete does not stop the run.
- Coverage-complete with nonzero yield resets the yield timer.
- A task claimed and released N times transitions to `blocked` and stops being offered.

### Service: Orchestrator

Implement the Orchestrator's two non-blocking lanes — lifecycle (validate config, spawn/maintain fleet, enforce budgets) and conversational (Q&A, accept tasks, resolve help requests) — extending `agent-coordinator`'s Agent Orchestration. Gate fleet spawn on a queryable index.

**Acceptance Outcomes:**
- Invalid configuration blocks the run with a specific validation failure, no partial fleet.
- Downstream roles are withheld until the Indexer signals queryable.
- A long conversational request never stalls lifecycle-lane fleet maintenance.

### Service: Observability Dashboard and Session Logs

Implement the operability surfaces (foundry FR-120–FR-124): a dashboard of per-agent state, finding counts by verdict/severity/exploited, coverage checklist, budget/yield, queue depth, and unacked operator messages; a merged filterable activity feed; structured replayable session logs; and per-role cost/token rollups. Status query and dashboard must agree.

**Acceptance Outcomes:**
- The dashboard and a point-in-time status query report identical fleet/findings/budget.
- Full provenance (detection → triage → validation → report) is reconstructable from session logs.

### Capability: Deep-Tester Extension (deferred)

Optional extension that builds PoC binaries for findings. **Adopt when** a stable testbed exists and findings need PoC binaries; **do not adopt** without a testbed. Not scheduled for the initial build.

**Acceptance Outcomes:**
- Recorded as a deferred candidate; activation requires a stable testbed precondition to be met.

### Capability: Variant-Hunter Extension (deferred, blocked)

Optional extension that finds variants of confirmed findings via semantic similarity. **Adopt when** a vector store, semantic embeddings, and a true-positive corpus all exist. **Blocked:** the seed has no vector store. Not scheduled.

**Acceptance Outcomes:**
- Recorded as a blocked candidate; activation requires introducing a vector store and embeddings first.

### Capability: Attack-Mapper Extension (deferred)

Optional extension that maps finding-chaining and attack paths. **Adopt when** reviewers ask about chaining and evaluations are older than two quarters; **do not adopt** on first build. Not scheduled.

**Acceptance Outcomes:**
- Recorded as a deferred candidate gated on the chaining-demand precondition.

### Capability: Remediator Extension (deferred)

Optional extension that proposes code fixes for findings. **Adopt when** a code-review process for AI changes and merge gating are mature; **do not adopt** until Reporter output is trusted. Not scheduled.

**Acceptance Outcomes:**
- Recorded as a deferred candidate gated on mature merge-gating and trusted Reporter output.

### Capability: Self-Improver Extension (deferred)

Optional extension that improves the detection rule corpus from measured gaps. **Adopt when** the rule corpus has measured gaps with examples; **do not adopt** on day one. Not scheduled.

**Acceptance Outcomes:**
- Recorded as a deferred candidate gated on a measured rule-gap corpus.

## Constraints

- Every capability must bind to its mapped existing capability per `seed-sentinel-security-eval/design.md` D1 rather than duplicate infrastructure.
- The coordination substrate must reuse `agent-coordinator`'s Work Queue and Heartbeat requirements (depends-on, not rebuild).
- Every verdict must carry vendor/model/corpus-version provenance (Deviation D-1 mitigation).
- Sandbox boundaries must be enforced by infrastructure, never by prompt alone.
- The `exploited` flag must be settable only by the Validator and only on independently reproduced impact.
- Findings must satisfy the three-leg evidence gate before reaching `true-positive`.
- The initial build must not adopt any of the 5 extension roles.

## Phases

### Phase 1: Foundation

- Service: Coordination Substrate Binding
- Service: Finding Store with Fingerprint and Provenance
- Service: Sandbox and Scope Enforcement

### Phase 2: Knowledge

- Service: Indexer
- Service: Cartographer

### Phase 3: Detection and Triage

- Service: Detector
- Service: Triager
- Capability: Severity, Classification, and Label Taxonomy

### Phase 4: Validation, Reporting, and Coverage

- Service: Validator
- Service: Reporter
- Service: Coverage-Guide
- Capability: Governance Gates

### Phase 5: Operability

- Service: Orchestrator
- Service: Observability Dashboard and Session Logs

### Phase 6: Deferred Extensions (not scheduled)

- Capability: Deep-Tester Extension (deferred)
- Capability: Variant-Hunter Extension (deferred, blocked)
- Capability: Attack-Mapper Extension (deferred)
- Capability: Remediator Extension (deferred)
- Capability: Self-Improver Extension (deferred)

## Out of Scope

- Re-planning the seed itself (`seed-sentinel-security-eval` is complete and validated).
- Adopting any of the 5 extension roles in the initial build.
- Introducing a vector store / semantic search (blocks Variant-Hunter until a future decision).
- Compliance-framework mapping and multi-tenancy (explicitly out for the seed; revisit later).
- Restoring single-provider LLM operation (the multi-vendor Deviation D-1 is accepted).
