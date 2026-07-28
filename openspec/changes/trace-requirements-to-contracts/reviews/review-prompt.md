# Plan Review — `trace-requirements-to-contracts`

You are an independent plan reviewer. Review the OpenSpec change plan named
`trace-requirements-to-contracts`. You are running inside the repository's
managed worktree; **all paths below are relative to your current working
directory**. Use your tools to read files and to run read-only shell commands.
Verify claims against the real repository rather than trusting the plan's prose.

## Artifacts to read (all under `openspec/changes/trace-requirements-to-contracts/`)

- `proposal.md` — why, what changes, scope, acceptance outcomes, risks
- `design.md` — 13 numbered design decisions (D1–D13)
- `specs/gen-eval-framework/spec.md` — 14 ADDED requirements, 35 scenarios
- `specs/skill-workflow/spec.md` — 1 MODIFIED + 1 ADDED requirement
- `tasks.md` — 5 phases, ~44 tasks, RED-demonstration protocol
- `work-packages.yaml` — 5 work packages (wp-resolver, wp-model, wp-gate,
  wp-matrix, wp-wiring) plus 6 tasks deliberately excluded as `[human]`
- `contracts/traceability.schema.json`, `contracts/traceability-exclusions.schema.json`,
  `contracts/README.md`

## What the change does, in one paragraph

It adds the "requirement → contract" edge above an already-shipped
contract → descriptor → implementation chain. Contracted operations gain a
`traceability` block citing requirement identifiers (`<capability>.<slug>`
derived from spec headings). A new `packages/gen-eval/scripts/check_traceability.py`
gate checks four things: citations resolve, forward completeness (every
operation cites or is excluded), reverse completeness (every requirement is
cited or excluded), and exclusions carry reasons. Enforcement is opt-in with
**one switch per direction**: forward opts in per contract *document* (keyed on
a traceability block existing anywhere in it — D6); reverse opts in per
*capability*, keyed on the existence of
`openspec/contracts/<capability>/traceability-exclusions.yaml` — D13. The gate
runs change-scoped and blocking at `/validate-feature`, and as a full sweep on
`main` where opted-in surfaces block and the rest report.

## Priority focus — review these hardest

1. **Design decision D13 (directional opt-in).** This is the one genuinely new
   mechanism, introduced in the most recent plan iteration, and it has had **no
   prior review**. Attack it:
   - Is "the exclusions file's existence IS the reverse opt-in switch" sound, or
     does overloading one artifact with two meanings create a state nobody can
     express? Consider: what does a capability do if it wants to record a
     requirement exclusion *without* turning on blocking reverse enforcement?
     Is that a real need? What happens if the file is deleted, empty,
     malformed, or present-but-unreadable?
   - D12 struck a "reported-to-blocking" flag as redundant. D13 adds a second
     switch and argues it is not the same redundancy because it switches a
     *different claim*. Is that distinction real or a rationalization? Can you
     construct a state that is "opted in but not blocking" under D13 — the
     outcome D6/D12 exist to make impossible?
   - Interaction of the two switches: a capability whose only traced document
     is in *another* capability; a capability with an exclusions file but zero
     contract documents; an exclusions file naming cross-capability
     requirements (the schema permits it — see the `requirement` pattern
     description); a requirement cited only by an *untraced* document's block
     (can that even exist?).
   - Does any requirement, task, or acceptance outcome still assume the old,
     single, per-capability opt-in? Grep the whole change directory for
     leftovers.

2. **The wp-model write scope dispute.** An earlier gate review recommended
   widening `wp-model`'s `write_allow` to include
   `packages/gen-eval/src/gen_eval/contracts/**` and
   `packages/gen-eval/evaluation/descriptor.yaml`, because two CI steps assert
   byte identity of artifacts derived from `descriptor.py` /
   `service_descriptor.py` (`generate_contract_schemas.py --check` and
   `generate_tool_descriptor.py --check`, around `.github/workflows/ci.yml`
   lines 411 and 431). The plan iteration **refused** that fix, arguing instead
   that the new `traceability` field goes only on archetype-only models
   (`FlagSpec`, `PositionalSpec`, `ToolCommandSpec`, `OperationSpec`), which are
   *not reachable from* `InterfaceDescriptor`, and that an absent default keeps
   `evaluation/descriptor.yaml` byte-identical under `exclude_defaults=True`.
   **Judge this refutation on its merits — do not assume either party is
   right.** Verify empirically:
   - Read `packages/gen-eval/src/gen_eval/descriptor.py` and
     `service_descriptor.py`. Is `OperationSpec` genuinely unreachable from
     `InterfaceDescriptor`? What about `FlagSpec` / `PositionalSpec` /
     `ToolCommandSpec`?
   - Read `packages/gen-eval/scripts/generate_contract_schemas.py`. Which models
     does it actually walk, and would adding an optional field to those four
     models change any generated schema byte?
   - Read `packages/gen-eval/scripts/generate_tool_descriptor.py`. Does
     `exclude_defaults=True` actually apply on the path that emits
     `evaluation/descriptor.yaml`, and is `None` the model default?
   - If the refutation is wrong, that is a **critical** finding: the
     implementer will red CI with no in-scope way to fix it. If it is right,
     say so explicitly with the evidence.

## Standard review dimensions

Also evaluate:

- **Spec quality.** Every requirement's FIRST line must contain SHALL/MUST
  (`openspec validate --strict` only checks the first line). Scenarios testable,
  no vague judgement words that a test would have to invent a threshold for.
- **Internal consistency.** proposal ↔ design ↔ spec ↔ tasks ↔ work-packages
  must not contradict each other. Check task numbering references, scenario
  names referenced by tasks actually existing in the spec, design decision ids
  referenced by tasks actually existing in design.md.
- **The gate's own falsifiability.** This change's stated thesis is that a gate
  observed only to pass is decoration. Does every check have a documented
  mutation that makes it fail? Are there checks in the spec with no
  corresponding RED demonstration? Is the final checkpoint satisfiable as
  worded?
- **Fail-open holes.** Enumerate ways the gate could exit zero while the
  property it claims does not hold: parse errors read as "no blocks", empty
  touched set, missing capability spec, unreadable exclusions file, a capability
  directory that does not exist, symlinks, non-UTF8, duplicate operation ids,
  citations naming a capability whose spec exists but is empty.
- **Work package validity.** DAG acyclic; write scopes non-overlapping between
  packages that could run concurrently; `write_allow` covers every file each
  package's tasks must touch (including files the edit *invalidates*, not just
  files it edits); verification commands runnable and meaningful; the
  `[human]` task carve-out coherent with `depends_on`.
- **Feasibility.** Are the LOC estimates and task sizes plausible? Is any task
  secretly an L/XL? Is the `wp-wiring` DISPATCH PRECONDITION (do not dispatch
  before human tasks 4.1/4.2/4.2b land) expressible in the scheduler, or only
  in prose?
- **Adoption risk.** Does the change red the tree for unrelated work? Does the
  full sweep on `main` start failing on day one? Is the flagship retrofit
  (tasks 4.1/4.2/4.2b) actually bounded, or does it drag in an unbounded
  requirement triage?

## Useful commands (read-only)

```bash
ls openspec/contracts/
ls openspec/specs/ | head -40
grep -rn "traceability" openspec/changes/trace-requirements-to-contracts/ | head -50
sed -n '400,440p' .github/workflows/ci.yml
grep -n "class .*Spec\|class InterfaceDescriptor" packages/gen-eval/src/gen_eval/descriptor.py packages/gen-eval/src/gen_eval/service_descriptor.py
grep -rn "exclude_defaults" packages/gen-eval/scripts/
```

## Output format — MANDATORY

Output **only** a single JSON object, no prose before or after, no markdown
fences. It must conform to `openspec/schemas/review-findings.schema.json`:

```json
{
  "review_type": "plan",
  "target": "trace-requirements-to-contracts",
  "reviewer_vendor": "<your model or CLI name>",
  "findings": [
    {
      "id": 1,
      "axis": "architecture",
      "severity": "critical",
      "type": "architecture",
      "criticality": "high",
      "description": "Critical: <what is wrong, naming the exact file and section>",
      "resolution": "<the specific change that fixes it — describe, do not write code>",
      "disposition": "fix"
    }
  ]
}
```

Rules:
- `axis` ∈ `correctness | readability | architecture | security | performance` — exactly one per finding.
- `severity` ∈ `critical | nit | optional | fyi | none`, and the `description`
  MUST begin with the matching prefix (`Critical:` / `Nit:` / `Optional:` /
  `FYI:` / no prefix for `none`).
- `criticality` ∈ `high | medium | low`. `disposition` ∈ `fix | regenerate | accept | escalate`.
- Every finding must name a concrete file and section/line. Findings that
  reference paths or sections that do not exist will be discarded.
- Do NOT emit zero findings. If the plan is strong, emit `severity: none`
  positive observations naming precisely what it got right — and at minimum
  state your verdict on D13 and on the wp-model dispute as findings
  (`fyi`/`none` if you agree with the plan, `critical`/`nit` if you do not).
- Do not modify any file in the repository. This is a read-only review.
