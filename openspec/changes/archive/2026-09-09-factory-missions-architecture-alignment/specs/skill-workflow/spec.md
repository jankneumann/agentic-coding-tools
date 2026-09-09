# skill-workflow Spec Delta — Factory Missions Architecture Alignment

## ADDED Requirements

### Requirement: Validator Surface Documentation

The repository SHALL document the two validator surfaces (scrutiny via `parallel-review-*`, behavioral via `gen-eval`) under a single Three-Role section in `README.md` and a corresponding section in `docs/skills-workflow.md`. Both sections MUST map each existing skill onto exactly one of the three roles: Orchestrator, Worker, or Validator.

The `docs/skills-workflow.md` validator section MUST reference both validator surfaces and explain that gen-eval findings are merged into the same consensus surface as scrutiny findings (per the Behavioral Findings in Consensus Surface requirement in evaluation-framework).

#### Scenario: README opener leads with attention bottleneck

- **GIVEN** the rewritten `README.md`
- **WHEN** examined as a text file
- **THEN** the substring `human attention` (case-insensitive) MUST appear within the first 500 characters of the file body (after the H1 title)
- **AND** the substring `Three Roles` (or `Three-Role`) MUST appear in a heading line (matching `^##? .*Three[- ]Roles?`) that precedes the first occurrence of `## Projects`
- **AND** all of `/plan-feature`, `/implement-feature`, `/parallel-review-plan`, `/parallel-review-implementation`, and `/gen-eval` MUST appear as substrings within the body of the Three-Roles section (between its heading and the next `^##? ` heading)

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
- **WHEN** examined as a text file
- **THEN** a heading line matching `^##? .*(Five-Tier|Multi-Agent Taxonomy)` MUST exist
- **AND** the section under that heading (until the next `^##? ` heading) MUST contain all 5 pattern names as substrings: `Delegation`, `Creator-Verifier`, `Direct Communication`, `Negotiation`, `Broadcast`
- **AND** for each pattern, the section MUST contain at least one repo-relative file path (matching the regex `\b(skills|agent-coordinator|docs)/[A-Za-z0-9_./-]+`) within the lines describing that pattern

---

### Requirement: Scope-Isolated Parallelism Documentation

The `docs/parallel-agentic-development.md` document SHALL include a named "Scope-Isolated Parallelism" pattern section that:

- Acknowledges the Factory Missions talk's diagnosis ("agents step on each other when parallelizing").
- States the repo's alternative prescription (write-scope isolation via `write_allow` globs, lock-key prefix serialization in the merge queue) rather than the talk's "run features serially" prescription.
- References the enforcement code at `skills/parallel-infrastructure/scripts/scope_checker.py` and the merge-queue serialization in `agent-coordinator/`.

#### Scenario: Section names the talk and the divergence

- **GIVEN** the updated `docs/parallel-agentic-development.md`
- **WHEN** examined as a text file
- **THEN** a heading line containing `Scope-Isolated Parallelism` MUST exist
- **AND** the section under that heading (until the next `^##? ` heading) MUST contain the substring `Factory Missions` (citing the talk by name)
- **AND** the section MUST contain at least one of the substrings `serial`, `serially`, or `serialize` (acknowledging the talk's prescription)
- **AND** the section MUST contain the path `skills/parallel-infrastructure/scripts/scope_checker.py` OR a reference to the merge queue in `agent-coordinator/`

---

### Requirement: Mission Glossary Entry

The `docs/lessons-learned.md` or `docs/skills-workflow.md` document SHALL include a glossary entry mapping the term "Mission" (as used in the Factory Missions architecture) to "one OpenSpec change-id flowing through `/plan-feature` → `/implement-feature` → `/validate-feature` → `/cleanup-feature`."

#### Scenario: Glossary entry exists and is searchable

- **GIVEN** the updated `docs/skills-workflow.md` (or `docs/lessons-learned.md`)
- **WHEN** examined as a text file
- **THEN** a section heading or definition list entry containing `Mission` MUST exist
- **AND** the entry's body MUST contain the substring `OpenSpec change-id`
- **AND** the entry's body MUST contain all four exact substrings: `/plan-feature`, `/implement-feature`, `/validate-feature`, `/cleanup-feature`

---

### Requirement: Self-Healing at Milestone Boundaries Reframing

The `docs/lessons-learned.md` document SHALL include a section heading titled "Self-Healing at Milestone Boundaries" that frames the existing `escalation_handler.py` behavior in those terms.

The section MUST be additive (a new heading + paragraph) and MUST NOT modify the existing escalation-handler section content.

#### Scenario: New heading anchors existing content

- **GIVEN** the updated `docs/lessons-learned.md`
- **WHEN** a reader searches for "Self-Healing at Milestone Boundaries"
- **THEN** they MUST find a heading
- **AND** the section under it MUST cross-reference the existing escalation_handler.py documentation (without duplicating it)
