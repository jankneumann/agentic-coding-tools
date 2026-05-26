## ADDED Requirements

### Requirement: Orchestrator Role

Sentinel SHALL provide an Orchestrator as the single operator interface, running as the long-running coordinator service this repository already operates. It SHALL serve two non-blocking execution lanes: a **lifecycle lane** (validate config, spawn/maintain the role fleet, enforce budgets) and a **conversational lane** (answer questions, accept tasks, resolve help requests). The Orchestrator SHALL validate operator configuration and confirm the Indexer's index is queryable before spawning downstream roles (foundry FR-001, FR-003, FR-019; Constitution X).

#### Scenario: Fleet spawn gated on a queryable index

**WHEN** the operator starts an evaluation with valid configuration
**THEN** the Orchestrator SHALL validate the configuration before spawning any role
**AND** SHALL withhold spawning Cartographer, Detector, Triager, Validator, Reporter, and Coverage-Guide until the Indexer reports its index queryable
**AND** SHALL maintain the operator-configured count of each role for the run's duration

#### Scenario: Conversational lane never blocks the lifecycle lane

**WHEN** a long-running conversational request (e.g., a free-form question) is being served
**THEN** the lifecycle lane SHALL continue to maintain role counts and enforce budgets
**AND** the Orchestrator SHALL NOT defer heartbeat-driven fleet maintenance behind conversational work

#### Scenario: Invalid configuration blocks the run

**WHEN** the operator supplies a configuration that fails validation
**THEN** the Orchestrator SHALL refuse to spawn the fleet
**AND** SHALL report the specific validation failure to the operator without partially starting roles

### Requirement: Indexer Role

Sentinel SHALL provide an Indexer that builds and maintains structural knowledge of the target source — symbols, call graph, and cross-references — using a deterministic parser, and exposes a query interface (`get-function-body`, `get-callers`, `get-callees`, `find-symbol`, full-text search) that every downstream role queries for investigation context (foundry FR-020, FR-021, FR-022, FR-024, FR-026). Semantic/vector search (FR-023) is **out of scope for the seed**.

#### Scenario: Index becomes queryable before downstream roles run

**WHEN** the Indexer completes a first pass over the target source
**THEN** it SHALL expose the query interface for functions, callers, callees, and symbols
**AND** SHALL signal queryable status so the Orchestrator can release downstream roles

#### Scenario: Incremental re-index on re-run

**WHEN** the Indexer runs against a target it has previously indexed
**THEN** it SHALL update only the portions of the index affected by source changes
**AND** SHALL NOT require a full rebuild for an unchanged file

#### Scenario: Unparseable source does not abort indexing

**WHEN** the deterministic parser fails on a subset of files
**THEN** the Indexer SHALL record the unparseable files
**AND** SHALL continue indexing the remaining files rather than failing the whole pass

### Requirement: Cartographer Role

Sentinel SHALL provide a Cartographer that produces persisted security-context documents — architecture overview, attack-surface enumeration, trust boundaries, data flows, and threat model — readable by all roles (foundry FR-030–FR-035). Roles SHALL remain functional, at reduced quality, when the map is absent (FR-036).

#### Scenario: Security map persisted for all roles

**WHEN** the Cartographer completes its passes
**THEN** it SHALL persist the architecture overview, attack-surface enumeration, trust boundaries, data flows, and threat model
**AND** the persisted documents SHALL be readable by every other role

#### Scenario: Roles degrade gracefully without a map

**WHEN** a downstream role runs before the Cartographer has produced a map
**THEN** the role SHALL continue operating using the Indexer alone
**AND** SHALL NOT block solely on the absence of the security map

### Requirement: Detector Role

Sentinel SHALL provide a Detector that produces candidate findings breadth-first via systematic rule application (per-function analysis, dependency scanning, secret scanning) and free-form exploratory hunting, drawing on an independent, versioned rule corpus and recording rule gaps (foundry FR-037–FR-042). Candidate findings SHALL be written to the internal finding store, **never directly to the issue tracker** (FR-044; Constitution II). The Detector SHALL maintain a coverage log as an audit trail (FR-046).

#### Scenario: Candidates go to the store, not the tracker

**WHEN** the Detector identifies a plausible candidate
**THEN** it SHALL write the candidate to the internal finding store with state `candidate`
**AND** SHALL NOT publish the candidate to the issue tracker

#### Scenario: Rule gaps are recorded

**WHEN** exploratory hunting finds an issue class not covered by the rule corpus
**THEN** the Detector SHALL record the rule gap against the corpus version
**AND** SHALL still queue the candidate for triage

#### Scenario: Detector does not assign verdicts

**WHEN** the Detector produces a candidate
**THEN** it SHALL NOT assign a verdict, severity, or `exploited` status
**AND** SHALL leave verdict assignment to the Triager

### Requirement: Triager Role

Sentinel SHALL provide a Triager that investigates each candidate and assigns **exactly one** verdict from {`true-positive`, `false-positive`, `needs-review`, `not-applicable`, `code-quality`}, gating `true-positive` on the Evidence Gate and recording the verdict with its reasoning (foundry FR-050–FR-054). Only `true-positive` findings SHALL be surfaced toward publication; all other verdicts remain internal except `needs-review`, which SHALL be surfaced to humans per the Label Taxonomy (FR-057; Constitution II).

#### Scenario: Exactly one verdict with reasoning

**WHEN** the Triager completes investigation of a candidate
**THEN** it SHALL assign exactly one of the five verdicts
**AND** SHALL record the investigation reasoning alongside the verdict

#### Scenario: Unprovable likelihood becomes needs-review

**WHEN** a candidate is likely real but the Evidence Gate cannot be satisfied
**THEN** the Triager SHALL assign `needs-review` rather than `true-positive`
**AND** SHALL surface the `needs-review` item to humans

#### Scenario: Non-true-positive verdicts stay internal

**WHEN** the Triager assigns `false-positive`, `not-applicable`, or `code-quality`
**THEN** the finding SHALL remain in internal storage
**AND** SHALL NOT be published to the issue tracker

### Requirement: Validator Role

Sentinel SHALL provide a Validator that, for `true-positive` findings claiming exploitability, attempts **independent clean-room reproduction** of the headline impact against a testbed, using a fresh agent that is not the Triager (foundry FR-060–FR-063, FR-066; Constitution VII). The Validator SHALL set the `exploited` flag **only** when impact is directly observed, SHALL record an explanation on failure (never clearing the verdict), and SHALL produce a runnable PoC artifact. With no testbed available, it SHALL degrade to PoC-only and SHALL NOT set `exploited`.

#### Scenario: Exploited set only on observed impact

**WHEN** the Validator independently reproduces the headline impact on the testbed
**THEN** it SHALL set the `exploited` flag
**AND** SHALL attach the runnable PoC artifact demonstrating the impact

#### Scenario: Failed reproduction does not clear the verdict

**WHEN** the Validator cannot reproduce the claimed impact
**THEN** it SHALL record an explanation of the failed attempt
**AND** SHALL leave the `true-positive` verdict intact
**AND** SHALL NOT set the `exploited` flag

#### Scenario: No testbed degrades to PoC-only

**WHEN** no testbed is available for a finding claiming exploitability
**THEN** the Validator SHALL produce a PoC artifact without execution
**AND** SHALL NOT set the `exploited` flag under any circumstance

### Requirement: Coverage-Guide Role

Sentinel SHALL provide a Coverage-Guide that derives a finite checklist from operator goals and the security map, steers the fleet toward uncovered items, checks items off on credible attempt (not on outcome), and declares coverage-complete when all items are checked (foundry FR-067–FR-071). It SHALL refuse to run against empty goals.

#### Scenario: Checklist derived from goals

**WHEN** the operator provides non-empty evaluation goals
**THEN** the Coverage-Guide SHALL derive a finite checklist from the goals and the security map
**AND** SHALL queue directed tasks toward uncovered checklist items

#### Scenario: Items checked on attempt, not outcome

**WHEN** a checklist item is credibly attempted and yields no finding
**THEN** the Coverage-Guide SHALL mark the item checked ("we looked and found nothing")
**AND** SHALL set coverage-complete only once every item is checked

#### Scenario: Empty goals are refused

**WHEN** the operator provides empty or absent evaluation goals
**THEN** the Coverage-Guide SHALL refuse to derive a checklist
**AND** SHALL report the missing-goals condition to the operator

### Requirement: Reporter Role

Sentinel SHALL provide a Reporter that produces self-contained per-finding reports (title, location, description, impact, reproduction, evidence) and an evaluation-level rollup grouping findings by component with counts, severity, exploited status, and coverage status (foundry FR-075–FR-081). The Reporter SHALL publish to the issue tracker with consistent labels and SHALL update existing findings rather than duplicate them, keyed on the Finding Fingerprint.

#### Scenario: Self-contained per-finding report published

**WHEN** the Reporter publishes a `true-positive` finding
**THEN** the report SHALL contain title, location, description, impact, reproduction steps, and cited evidence
**AND** SHALL be published to the issue tracker with labels from the Label Taxonomy

#### Scenario: Update rather than duplicate on re-run

**WHEN** the Reporter publishes a finding whose fingerprint matches an already-published finding
**THEN** it SHALL update the existing tracker entry
**AND** SHALL NOT create a duplicate entry

### Requirement: Finding Lifecycle and Verdicts

A Sentinel finding SHALL progress through the states `candidate → verdict-assigned → confirmed → [validated] → published`. The five verdicts and their surfacing rules SHALL be: `true-positive` (surfaced), `false-positive` (internal), `needs-review` (surfaced to humans), `not-applicable` (internal), `code-quality` (internal) (foundry §7.2, FR-085–FR-093; Constitution II).

#### Scenario: Confirmed requires true-positive

**WHEN** a finding is assigned the `true-positive` verdict
**THEN** it SHALL transition to `confirmed`
**AND** SHALL become eligible for optional validation and for publication

#### Scenario: Only surfaced verdicts reach operators

**WHEN** a finding carries a verdict other than `true-positive` or `needs-review`
**THEN** it SHALL remain in internal storage
**AND** SHALL NOT appear in the operator-facing tracker

### Requirement: Evidence Gate

A `true-positive` verdict SHALL require an investigation report citing three elements: (1) **reachability** — an attacker-controlled entry point from which the sink is reachable; (2) **trust boundary** — the point where untrusted data crosses without sufficient validation; (3) **impact** — a concrete security consequence at the sink (foundry §7.3, FR-087; Constitution I). For presence-vulnerabilities (hardcoded credentials, deprecated cryptography, secrets in source), the trust-boundary citation MAY be "the repository itself" and the reachability citation "the file's inclusion in the build", but the impact leg SHALL still be required (FR-087a). Every cited code location SHALL be mechanically verified to resolve; a failed citation SHALL demote the verdict to `needs-review` (FR-088).

#### Scenario: Three-leg citation satisfies the gate

**WHEN** the Triager cites a reachable entry point, a crossed trust boundary, and a concrete impact, all resolving to real code locations
**THEN** the Evidence Gate SHALL pass
**AND** the verdict MAY be `true-positive`

#### Scenario: Presence-vuln carve-out

**WHEN** the finding is a hardcoded credential or deprecated-crypto presence-vulnerability
**THEN** the trust-boundary leg MAY cite "the repository itself" and reachability "inclusion in the build"
**AND** the impact leg SHALL still be cited for the gate to pass

#### Scenario: Unresolvable citation demotes the verdict

**WHEN** any cited code location fails mechanical resolution
**THEN** the Evidence Gate SHALL fail
**AND** the verdict SHALL be demoted to `needs-review`

### Requirement: Finding Fingerprint

Sentinel SHALL identify a finding by a deterministic fingerprint computed from `(normalized_file_path, function_or_symbol_name, vulnerability_class)`. The fingerprint SHALL NOT incorporate line numbers, code snippets, or timestamps, so that finding identity is stable across edits to the surrounding file (foundry §7.5, FR-090–FR-091; Constitution VIII). The fingerprint SHALL be the deduplication key for the store and the tracker.

#### Scenario: Stable identity under unrelated edits

**WHEN** the target file is edited in a way that changes line numbers but not the vulnerable symbol or class
**THEN** the finding's fingerprint SHALL be unchanged
**AND** a re-run SHALL recognize it as the same finding

#### Scenario: Re-run produces no duplicates

**WHEN** Sentinel re-runs against an unchanged target
**THEN** it SHALL produce zero new findings and zero duplicates for already-published issues
**AND** SHALL match each rediscovered finding to its existing fingerprint

### Requirement: Exploited Flag

The `exploited` flag SHALL be set **only** by the Validator, and only when headline impact has been independently reproduced against a testbed (foundry §7.4, FR-089; Constitution VII). It SHALL never be set by the Detector, Triager, or Reporter, and SHALL never be inferred. A set `exploited` flag SHALL imply a runnable PoC artifact exists.

#### Scenario: Only the Validator sets exploited

**WHEN** any role other than the Validator attempts to set `exploited`
**THEN** the system SHALL reject the change
**AND** the flag SHALL remain unset

#### Scenario: Exploited implies a PoC

**WHEN** a finding carries the `exploited` flag
**THEN** a runnable PoC artifact SHALL be attached to the finding
**AND** the absence of such an artifact SHALL be treated as an invariant violation

### Requirement: Verdict Provenance

Because Sentinel reuses this repository's multi-vendor LLM routing (Deviation D-1 in `constitution.md`, exception to Constitution V), every verdict SHALL record its provenance: the vendor, the model, and the rule/corpus version that produced it. A verdict without recorded provenance SHALL be invalid. Re-run comparison SHALL be provenance-aware: a verdict difference between runs SHALL be flagged as a regression only when provenance is held constant.

#### Scenario: Verdict carries provenance

**WHEN** the Triager assigns any verdict
**THEN** the recorded verdict SHALL include the vendor, model, and rule/corpus version
**AND** a verdict missing any provenance field SHALL be rejected as invalid

#### Scenario: Provenance-aware regression detection

**WHEN** a re-run produces a different verdict for the same fingerprint under a different vendor or model
**THEN** the difference SHALL NOT be reported as a target regression
**AND** the system SHALL attribute the difference to provenance variance

### Requirement: Severity and Weakness Classification

The Reporter SHALL own severity assignment using **CVSS v4**, and SHALL classify each finding's weakness using **CWE** (foundry FR-076, FR-077, §11.9; Constitution I). Severity SHALL NOT be taken as raw model output; it SHALL be derived through the owned CVSS-v4 rubric.

#### Scenario: CVSS v4 severity and CWE class assigned

**WHEN** the Reporter publishes a finding
**THEN** it SHALL assign a CVSS v4 severity via the Reporter-owned rubric
**AND** SHALL assign a CWE weakness class

#### Scenario: Raw model severity rejected

**WHEN** a candidate arrives carrying a severity string emitted directly by a model
**THEN** the Reporter SHALL ignore that string as authoritative
**AND** SHALL compute severity through the CVSS-v4 rubric instead

### Requirement: Label Taxonomy

Sentinel SHALL publish findings to the issue tracker using a fixed, namespaced label taxonomy (e.g., `triaged/true-positive`, `triaged/needs-review`, `verdict/false-positive`, `severity/<cvss-band>`, `cwe/<id>`, `exploited`). Labels SHALL be consistent across runs and SHALL be the mechanism by which `needs-review` items are surfaced to human reviewers (foundry FR-078, FR-092–FR-093, §7.6).

#### Scenario: Consistent labels on publish

**WHEN** the Reporter publishes a finding
**THEN** it SHALL apply labels drawn only from the defined namespaced taxonomy
**AND** SHALL apply the same label strings for equivalent verdicts across runs

#### Scenario: needs-review surfaced by label

**WHEN** a finding carries the `needs-review` verdict
**THEN** it SHALL be published with the `triaged/needs-review` label for human attention
**AND** SHALL NOT carry a `triaged/true-positive` label

### Requirement: Coverage and Yield Auto-Stop

Sentinel SHALL auto-stop an evaluation only when **both** coverage-complete **and** yield-below-threshold hold (foundry §9.4, FR-115–FR-117; Constitution VI). Yield SHALL be computed as severity-weighted findings per spend over a trailing window. The auto-stop SHALL additionally require that at least one full trailing window of spend has accumulated and a configurable minimum runtime has elapsed. Severity weights, the `exploited` multiplier, window size, minimum runtime, and threshold SHALL be operator-configurable.

#### Scenario: Both conditions required to stop

**WHEN** trailing yield is below threshold but coverage is not yet complete
**THEN** Sentinel SHALL continue the run
**AND** SHALL NOT auto-stop

#### Scenario: Coverage-complete with nonzero yield resets the timer

**WHEN** coverage becomes complete while yield is still above threshold
**THEN** Sentinel SHALL continue running
**AND** SHALL reset the yield window timer rather than stopping

#### Scenario: Auto-stop on both conditions after minimum runtime

**WHEN** coverage is complete, a full trailing window has accumulated, minimum runtime has elapsed, and yield is below threshold
**THEN** Sentinel SHALL auto-stop the evaluation

### Requirement: Task Auto-Blocking

A work-queue task that is claimed and released N times without completion (N operator-configurable, seed default N=3) SHALL auto-transition to `blocked` (foundry FR-097). A blocked task SHALL be re-openable by the operator or the Coverage-Guide with an improved description.

#### Scenario: Repeated release blocks the task

**WHEN** a task has been claimed and released without completion N times
**THEN** the task SHALL transition to `blocked`
**AND** SHALL stop being offered to claiming agents

#### Scenario: Operator re-opens a blocked task

**WHEN** the operator or Coverage-Guide re-opens a blocked task with a better description
**THEN** the task SHALL return to `open`
**AND** SHALL again be eligible for claiming

### Requirement: Sandbox by Infrastructure

Sentinel's agent fleet SHALL run inside an isolation boundary whose network egress is constrained to an allowlist (LLM provider(s), issue tracker, and testbed by default), enforced by **infrastructure** — ephemeral containers and E2B for code execution — and never by prompt alone (foundry §9.1, FR-107–FR-109; Constitution IX). Target source, config, prompts, and the sandbox definition SHALL be mounted read-only.

#### Scenario: Egress confined to the allowlist

**WHEN** an agent with elevated privileges attempts to reach a host outside the allowlist
**THEN** the infrastructure boundary SHALL block the connection
**AND** the block SHALL not depend on any prompt-level instruction

#### Scenario: Read-only target mounts

**WHEN** an agent attempts to modify the target source, config, or sandbox definition
**THEN** the write SHALL fail because the mount is read-only

### Requirement: Hard-Rule Scope Enforcement

Operator-authored hard-rules (out-of-scope hosts, prohibited actions, data that must not be modified) SHALL be present in every agent's system prompt as defense-in-depth behind the sandbox (foundry §9.2, FR-110–FR-111; Constitution IX, X). On non-testbed systems, default rules SHALL prohibit denial-of-service, data deletion or modification, credential changes, and actions affecting non-test users.

#### Scenario: Hard-rules present in every agent

**WHEN** any role agent is spawned
**THEN** its system prompt SHALL include the operator's hard-rules
**AND** SHALL include the default non-testbed prohibitions when the target is not a testbed

#### Scenario: Hard-rules do not replace the sandbox

**WHEN** an agent's reasoning is manipulated by adversarial target content to attempt a prohibited action
**THEN** the infrastructure sandbox SHALL still block the action
**AND** the hard-rule SHALL serve only as an additional layer, not the sole control

### Requirement: Coordination Substrate Binding

Sentinel SHALL use the existing `agent-coordinator` capability for its coordination substrate rather than introducing a parallel one. Atomic task claiming and the `open`/`blocked`/`closed` work-queue states SHALL be provided by `agent-coordinator`'s **Work Queue** requirement; liveness and dead-agent claim release SHALL be provided by its **Heartbeat and Dead Agent Detection** requirement (foundry FR-094–FR-101; Constitution III, IV). Sentinel roles SHALL emit heartbeats on a separate execution lane from their primary work, and claim release SHALL be tied to heartbeat staleness, never to wall-clock runtime.

#### Scenario: Atomic claiming across concurrent roles

**WHEN** two role agents attempt to claim work simultaneously
**THEN** the `agent-coordinator` Work Queue SHALL grant each a different task
**AND** no task SHALL be double-claimed

#### Scenario: Dead-agent claim release by heartbeat

**WHEN** a role agent dies while holding a claim
**THEN** the claim SHALL auto-release within the heartbeat-stale window via `agent-coordinator`'s Heartbeat and Dead Agent Detection
**AND** release SHALL NOT wait on any wall-clock timeout or operator action

### Requirement: Atomic Persistence

Every Sentinel artifact read by multiple components (index, finding store, coverage checklist, shared notes) SHALL be updated by writing the new state completely and then atomically replacing the old, never by delete-then-write (foundry §8.6, FR-106a; Constitution XI). Readers SHALL never observe partial state.

#### Scenario: Atomic replace on update

**WHEN** a shared artifact is updated
**THEN** the new state SHALL be written in full and then atomically swapped in
**AND** a concurrent reader SHALL see either the complete old state or the complete new state

#### Scenario: Crash mid-write leaves a complete prior state

**WHEN** the writing process crashes during an artifact update
**THEN** readers SHALL still observe the complete previous state
**AND** SHALL NOT observe an empty or truncated artifact
