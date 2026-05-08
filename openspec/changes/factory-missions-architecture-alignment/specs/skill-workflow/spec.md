# skill-workflow Spec Delta — Factory Missions Architecture Alignment

## ADDED Requirements

### Requirement: Validator Surface Documentation

The repository SHALL document the two validator surfaces (scrutiny via `parallel-review-*`, behavioral via `gen-eval`) under a single Three-Role section in `README.md` and a corresponding section in `docs/skills-workflow.md`. Both sections MUST map each existing skill onto exactly one of the three roles: Orchestrator, Worker, or Validator.

The `docs/skills-workflow.md` validator section MUST reference both validator surfaces and explain that gen-eval findings are merged into the same consensus surface as scrutiny findings (per the Behavioral Findings in Consensus Surface requirement in evaluation-framework).

#### Scenario: README opener leads with attention bottleneck

- **GIVEN** a new contributor reading `README.md` for the first time
- **WHEN** they read the first paragraph
- **THEN** the paragraph MUST name "human attention" (not "model intelligence" or "tool capability") as the primary bottleneck this repo addresses
- **AND** a section titled "Three Roles" or equivalent MUST appear before the project list

#### Scenario: Each skill mapped to exactly one role

- **GIVEN** the rewritten `README.md` Three-Roles section
- **WHEN** a reader examines the role-to-skill mapping
- **THEN** every user-invocable skill listed in `skills/` MUST appear under exactly one role heading
- **AND** the mapping MUST list at minimum: `/plan-feature` and `/implement-feature` under Orchestrator/Workers, and `/parallel-review-plan`, `/parallel-review-implementation`, and `/gen-eval` under Validators

---

### Requirement: Five-Tier Multi-Agent Taxonomy Documentation

The `docs/parallel-agentic-development.md` document SHALL include a "Five-Tier Multi-Agent Taxonomy" section that names and maps the five communication patterns identified in the Factory Missions architecture onto the repo's existing primitives:

- **Delegation** → `submit_work` / `get_work` queue operations
- **Creator-Verifier** → orchestrator + `parallel-review-*` + gen-eval validator pair
- **Direct Communication** → MCP tools (with documented warning about state fragmentation)
- **Negotiation** → merge queue with lock-key prefix serialization
- **Broadcast** → coordinator discovery and heartbeat

The section MUST be additive — no existing content in `docs/parallel-agentic-development.md` may be removed or restructured by this change.

#### Scenario: Taxonomy table present and complete

- **GIVEN** the updated `docs/parallel-agentic-development.md`
- **WHEN** a reader searches for "Five-Tier" or "Multi-Agent Taxonomy"
- **THEN** a section MUST exist
- **AND** the section MUST contain a table or list with all 5 patterns named above
- **AND** each pattern MUST link to the specific primitive (file path or function name) that implements it

---

### Requirement: Scope-Isolated Parallelism Documentation

The `docs/parallel-agentic-development.md` document SHALL include a named "Scope-Isolated Parallelism" pattern section that:

- Acknowledges the Factory Missions talk's diagnosis ("agents step on each other when parallelizing").
- States the repo's alternative prescription (write-scope isolation via `write_allow` globs, lock-key prefix serialization in the merge queue) rather than the talk's "run features serially" prescription.
- References the enforcement code at `skills/parallel-infrastructure/scripts/scope_checker.py` and the merge-queue serialization in `agent-coordinator/`.

#### Scenario: Section names the talk and the divergence

- **GIVEN** the updated `docs/parallel-agentic-development.md`
- **WHEN** a reader searches for "Scope-Isolated Parallelism"
- **THEN** the section MUST reference the Factory Missions talk
- **AND** the section MUST state explicitly that the repo parallelizes intra-feature work packages where the talk runs them serially
- **AND** the section MUST cite at least one enforcement file path

---

### Requirement: Mission Glossary Entry

The `docs/lessons-learned.md` or `docs/skills-workflow.md` document SHALL include a glossary entry mapping the term "Mission" (as used in the Factory Missions architecture) to "one OpenSpec change-id flowing through `/plan-feature` → `/implement-feature` → `/validate-feature` → `/cleanup-feature`."

#### Scenario: Glossary entry exists and is searchable

- **GIVEN** the updated docs
- **WHEN** a reader searches for "Mission" in the docs
- **THEN** they MUST find a definition that maps Mission to an OpenSpec change-id
- **AND** the definition MUST name all four lifecycle skills

---

### Requirement: Self-Healing at Milestone Boundaries Reframing

The `docs/lessons-learned.md` document SHALL include a section heading titled "Self-Healing at Milestone Boundaries" that frames the existing `escalation_handler.py` behavior in those terms.

The section MUST be additive (a new heading + paragraph) and MUST NOT modify the existing escalation-handler section content.

#### Scenario: New heading anchors existing content

- **GIVEN** the updated `docs/lessons-learned.md`
- **WHEN** a reader searches for "Self-Healing at Milestone Boundaries"
- **THEN** they MUST find a heading
- **AND** the section under it MUST cross-reference the existing escalation_handler.py documentation (without duplicating it)
