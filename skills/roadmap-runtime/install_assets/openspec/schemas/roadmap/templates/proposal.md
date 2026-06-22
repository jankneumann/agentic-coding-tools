# <Epic Title>

<!--
This template is consumed by /plan-roadmap to produce roadmap.yaml.
The section structure below is the contract: the decomposer expects each
of these H2 sections, and the agent uses them to extract capabilities,
constraints, phases, and acceptance outcomes.

Replace placeholder text in <angle brackets>. Delete this comment when done.
Inline guidance comments (HTML comments inside each section) explain what
goes where; remove them as you fill the section in.
-->

## Motivation

<!--
Why does this epic exist? What problem are we solving, and for whom?
2-4 paragraphs. State the user-facing pain or strategic gap, then the
one-line "what success looks like."
-->

<motivation prose>

## Capabilities

<!--
The substantive list of what the system will do. Each H3 below becomes a
candidate roadmap item. Use clear capability names — the decomposer's
keyword vocabulary covers terms like "capability", "feature", "service",
"port", "adapter", "endpoint", "pipeline", "queue", "handler", "worker",
"workspace", "module", "component", "subsystem", "retry queue".

If your epic introduces something the vocabulary doesn't recognize, prefer
naming the H3 with a recognized term (e.g. "Service: Foo" rather than
"Foo Thingy") so the structural pass picks it up.

Each capability should have:
  - 1-3 paragraphs of description
  - An "Acceptance Outcomes" bulleted list (measurable, observable)
-->

### Capability: <name>

<description prose>

**Acceptance Outcomes:**
- <measurable outcome 1>
- <measurable outcome 2>

### Capability: <name>

<description prose>

**Acceptance Outcomes:**
- <measurable outcome 1>

## Constraints

<!--
Non-functional requirements, invariants, limits. Use "must" / "shall"
language — the decomposer recognizes these as constraint markers.
Constraints are global by default; if a constraint applies only to a
specific capability, name the capability inline.
-->

- The system must <constraint>.
- The system shall <constraint>.

## Phases

<!--
Optional. Temporal grouping that suggests dependency ordering. If your
capabilities are independent, leave a single phase or remove this section.
The decomposer uses phase boundaries to infer "items in phase N depend on
items in phase N-1" by default; override this in the roadmap if needed.
-->

### Phase 1: <name>

- <Capability or item that lands first>

### Phase 2: <name>

- <Capability that depends on Phase 1>

## Out of Scope

<!--
Explicit exclusions to prevent decomposer drift and reviewer confusion.
"We are NOT doing X in this epic; that belongs to <other epic / future>."
-->

- <thing not in scope>
