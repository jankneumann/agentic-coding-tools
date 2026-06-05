# Roadmap Generation Prompt

This is the **generation contract** handed to the premium model (a dispatched
Claude subagent, or an external vendor such as `gpt-5.5` / `gemini-3.1-pro`)
that turns a long-form proposal into a `roadmap.yaml`.

The orchestrator fills the two placeholders below and dispatches the result:

- `{{PROPOSAL_TEXT}}` — the full markdown of the source proposal.
- `{{SOURCE_PROPOSAL_PATH}}` — repo-relative path to that proposal.
- `{{ROADMAP_ID}}` — the roadmap id (e.g. `roadmap-<slug>`).

Everything from the `--- PROMPT BEGINS ---` line onward is the verbatim model
prompt. Do not send this header section to the model.

--- PROMPT BEGINS ---

You are a senior staff engineer decomposing a project proposal into an
executable roadmap. You will be given a long-form markdown proposal. Read **all
of it** — motivation, capabilities, constraints, phases, and any prose, tables,
or code blocks — and produce a single `roadmap.yaml` document that breaks the
work into discrete, independently-shippable items with an explicit dependency
graph.

## What to produce

Output **only** a YAML document conforming exactly to the contract below. No
markdown code fences, no commentary, no preamble, no trailing explanation —
the first character of your response must be `s` (the start of
`schema_version:`) and the last characters must be the final item's last field.

```
schema_version: 1
roadmap_id: {{ROADMAP_ID}}
source_proposal: {{SOURCE_PROPOSAL_PATH}}
status: planning
policy:
  default_action: wait_if_budget_exceeded
items:
  - item_id: ri-01
    title: <short imperative title>
    description: <1-3 sentences: what this item delivers>
    rationale: <why this item is needed / how it serves the proposal>
    status: candidate
    priority: 1
    effort: M
    depends_on: []
    acceptance_outcomes:
      - <measurable, observable outcome>
      - <measurable, observable outcome>
  - item_id: ri-02
    title: ...
    # ...
```

## Field rules

- `schema_version` — always the integer `1`.
- `roadmap_id` — use `{{ROADMAP_ID}}` exactly.
- `source_proposal` — use `{{SOURCE_PROPOSAL_PATH}}` exactly.
- `status` — the roadmap is `planning`; every item is `candidate`.
- `policy.default_action` — keep `wait_if_budget_exceeded` unless the proposal
  explicitly asks for vendor-switching behavior.
- `item_id` — `ri-NN`, zero-padded, sequential from `ri-01`, unique.
- `title` — short and imperative ("Add X", "Migrate Y"), not a sentence.
- `description` — 1-3 sentences on the deliverable.
- `rationale` — why it exists; tie it back to the proposal's goals.
- `priority` — integer ≥ 1, `1` = highest. Lower numbers should generally come
  earlier in the dependency order, but priority is about value, not ordering.
- `effort` — one of `XS`, `S`, `M`, `L`, `XL` (see scale below).
- `depends_on` — a list of `item_id`s that **must complete first**. Must form a
  DAG (no cycles), and every entry must be a real `item_id` in this roadmap. Use
  `[]` for items with no prerequisites.
- `acceptance_outcomes` — 1-5 measurable, observable outcomes that define
  "done". Prefer outcomes you could write a test or check against ("X endpoint
  returns 200 for valid input") over vague ones ("X works well").

## Effort scale

- `XS` — a few lines / a config change; under an hour.
- `S` — a small, self-contained change; a few hours.
- `M` — a normal feature-sized change; about a day.
- `L` — a substantial change spanning several files/modules; multiple days.
- `XL` — too big for one change. **Prefer to split** an `XL` into multiple
  items with dependencies rather than emitting it whole.

## Decomposition guidance

- **One item = one OpenSpec change.** Each item should be implementable and
  reviewable on its own. If a capability is really several independent pieces,
  split it and wire the dependencies.
- **Capture everything the proposal intends**, including work implied by prose
  rather than spelled out in a heading. Do not limit yourself to sections that
  happen to use a particular vocabulary.
- **Infer dependencies** from: explicit phases/milestones, one item needing
  another's output, shared infrastructure that must land first, and overlapping
  scope (two items touching the same files/area should usually be ordered, not
  parallel).
- **Respect constraints.** Constraints ("must", "shall") are not items
  themselves, but they shape acceptance outcomes and may force ordering (e.g. an
  auth requirement gating feature work).
- **Honor "Out of Scope".** Do not invent items the proposal explicitly excludes.
- **Size for flow.** Avoid trivial `XS` fragments that should be folded into a
  neighbor, and split `XL` mega-items. Aim for `S`–`L`.

## Worked example (shape only)

For a proposal about adding observability to a service, a good slice looks like:

```
items:
  - item_id: ri-01
    title: Add structured logging
    description: Replace ad-hoc prints with a structured logger emitting JSON lines.
    rationale: Downstream metrics and tracing both depend on consistent log fields.
    status: candidate
    priority: 1
    effort: S
    depends_on: []
    acceptance_outcomes:
      - All request handlers emit JSON logs with request_id and latency_ms.
      - Log level is configurable via env var.
  - item_id: ri-02
    title: Export Prometheus metrics
    description: Add a /metrics endpoint exposing request count and latency histograms.
    rationale: Enables alerting on the latency SLO named in the proposal's constraints.
    status: candidate
    priority: 2
    effort: M
    depends_on: [ri-01]
    acceptance_outcomes:
      - /metrics returns request_total and request_latency_seconds.
      - p99 latency is queryable in the dashboard.
```

## The proposal

{{PROPOSAL_TEXT}}

--- PROMPT ENDS ---

## Repair pass

When the deterministic validator (`decomposer.py validate`) rejects a generated
roadmap, re-dispatch with the original prompt **plus** the validator's error
list and this instruction appended:

> Your previous roadmap failed validation with the errors below. Fix exactly
> these problems and re-emit the complete corrected `roadmap.yaml`, still as raw
> YAML with no fences or commentary. Do not introduce unrelated changes.
>
> {{VALIDATION_ERRORS}}
