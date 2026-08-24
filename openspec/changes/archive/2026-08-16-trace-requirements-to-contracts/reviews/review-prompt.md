# Plan Review — `trace-requirements-to-contracts` — ROUND 2 (verification round)

You are an independent plan reviewer. You are running inside the repository's
managed worktree on branch `openspec/trace-requirements-to-contracts`; **all
paths below are relative to your current working directory**.

**Run commands.** You have shell access. Prefer findings you can *demonstrate*
by executing something (`ls`, `grep`, `git show`, `git diff`, `python3 -c ...`,
`openspec validate`) over findings you infer from prose. A finding backed by a
command and its output is worth ten backed by a reading.

## Why this round exists — read this first

Round 1 of this review returned **not_converged** with 10 blocking findings. The
plan author then fixed all 10 **inline, in a single commit `3891089b`**, and now
claims they are closed. Round 1's reviewers read the tree *before* that commit
and cannot corroborate the claim.

**Your primary job is to test that claim, not to re-derive it.** "All findings
fixed" is currently the author's own assertion about their own work.

Start here:

```bash
git log --oneline -3
git show --stat 3891089b
git show 3891089b -- openspec/changes/trace-requirements-to-contracts/specs/
git show 3891089b -- openspec/changes/trace-requirements-to-contracts/tasks.md
git show 3891089b -- openspec/changes/trace-requirements-to-contracts/work-packages.yaml
git show 3891089b -- openspec/changes/trace-requirements-to-contracts/design.md
```

## Part A — Verify each of the 10 claimed fixes against the CURRENT tree

The standard: **a fix stated in prose but with no scenario, no task, and no
verification step is not a fix.** For each item below, decide one of: genuinely
closed / partially closed (name what is missing) / not closed. Where a fix is
only rhetorical — a paragraph of rationale added to `design.md` with nothing
executable behind it — say so.

| # | Round-1 finding | Author's claimed fix |
|---|---|---|
| B1 | An unreadable/empty/schema-invalid `traceability-exclusions.yaml` read as "not opted in", silently disabling reverse enforcement | Now fails closed; negative asserted explicitly |
| B2 | Cross-capability exclusions permitted by the schema, unspecified by the spec | Now refused: citations permitted, exclusions refused |
| B3 | wp-wiring's dispatch precondition was prose the DAG could not read | Converted to an "executable preflight verification step" |
| B4 | The opt-in transition was invisible to change scope | Touched set now includes every operation in a newly-traced document and every requirement of a newly-excluded capability |
| B5 | Blocking full sweep was `push`-triggered on `main`, i.e. after the merge | Blocking sweep moved to `pull_request`; push-on-main kept as non-blocking |
| B6 | `phase-record`, `project-context-refresh`, `prototyping` have contract dirs and no capability spec → sweep reds `main` on merge | Resolved by the new "contract document" definition (they are schemas-only) |
| B7 | "contract document" used 20+ times, never defined | Defined as an instance under `openapi/` or `cli/`; `schemas/` files are not documents |
| B8 | Task 2.0's schema promotion drifts `docs/architecture-analysis/contracts-inventory.md`; no package could write it | Added to wp-model `write_allow` + a context-drift-gate verification step |
| B9 | `skills/tests/validate-feature` absent from `skills/pyproject.toml` testpaths → new skill tests never run in CI | New task 5.7b + write_allow + verification step |
| B10 | Task 4.3 proves RED on mutations; nothing requires GREEN on the merge candidate | New task 5.7c, marked `[human]` |

Checks worth actually running for Part A:

- B6/B7: `ls openspec/contracts/`, then for each capability dir compare against
  `ls openspec/specs/`. Does the new "contract document" definition actually
  spare all three specless capabilities? Is `code-search/v2.yaml` (an OpenAPI
  3.1 instance at the capability *root*) now a hard failure — and if so, does
  the plan contain a task that fixes it before the blocking sweep turns on? A
  definition that converts three silent skips into one loud failure with no
  remediation task has moved the breakage, not removed it.
- B8/B9: grep the current `work-packages.yaml` for the claimed `write_allow`
  entries and verification steps. Do they exist? Do they name the right paths?
  Does `skills/pyproject.toml` actually lack a `validate-feature` testpath
  today (`grep -n testpaths -A 20 skills/pyproject.toml`)?
- B10: find task 5.7c. Does it state a pass condition an implementer could
  fail, or is it a placeholder?
- B4: find the two new scenarios. Do the tasks that implement them exist, with
  fixtures?

## Part B — The FIXES introduced four new mechanisms. These have had NO review.

Treat them as new surface, not as settled. This is where the real defects most
likely are, because they were written under time pressure to close findings and
nobody has looked at them once.

1. **A contract-document definition keyed on directory location** (D6, and the
   "gate fails closed" requirement). A contract document is now a file under
   `openspec/contracts/<capability>/openapi/` or `.../cli/`; `schemas/` files
   are not documents; an instance at the capability root SHALL fail discovery.
   - How does the gate decide a root-level file is "instance-format" in order
     to fail on it? Is that rule specified anywhere, or does it require the
     very parse the definition says it will not perform? What about a README,
     a `.gitignore`, `traceability-exclusions.yaml` itself, or any other
     non-instance file sitting at a capability root — does the rule fail on
     those too?
   - `traceability-exclusions.yaml` lives at the capability root by design
     (D13). The misplaced-instance rule also fires at the capability root.
     Do these two collide? Is the exception written down?
   - Does the definition survive a capability that has a spec, an exclusions
     file, and zero documents?
2. **Opt-in widens the touched set** (D12 + the change-scope requirement).
   "Adding a traceability block to a previously untraced document touches
   every operation in that document; adding a capability's exclusions file
   touches every requirement of that capability."
   - Is "previously untraced" computable from the diff the gate is given? What
     is the baseline — merge base, or the working tree? What happens when a
     document is *created* already-traced in the same change? When a
     traceability block is *removed*, opting a document back out?
   - The design asserts this "does not violate the restriction property"
     (change scope only ever restricts what the full sweep enforces). Verify
     that claim rather than accepting it. Is there a case where change scope
     now fails something the full sweep would pass?
3. **Cross-capability exclusion refusal** (D13 + a new scenario). An exclusions
   entry whose requirement prefix is not the owning capability fails.
   - The requirement id is `<capability>.<slug>` where capability is a
     *directory name*. Is the prefix parse unambiguous when a capability name
     itself contains a dot, or when a slug contains one? Check real capability
     names: `ls openspec/specs/`.
   - Is the schema (`contracts/traceability-exclusions.schema.json`) now
     consistent with the spec, or does its field description still advertise
     the behaviour the spec refuses? `git show 3891089b -- openspec/changes/trace-requirements-to-contracts/contracts/`
   - What excuses a requirement legitimately served from another capability
     (D9's own example: the coordinator serves `/gen-eval/scenarios`)? If A's
     operation cites B's requirement, B's reverse completeness passes. But if
     nobody serves it and B's owner knows A will never build it — where does
     that exclusion live now?
4. **An executable preflight step standing in for a DAG precondition the schema
   cannot express** (wp-wiring). The claim is that
   `work-packages.schema.json` has `additionalProperties: false` and
   `depends_on` accepts only package ids, so the precondition cannot live in
   the DAG — therefore it becomes a verification step inside the package.
   - **Verify the premise by reading the schema**, don't take it on trust.
   - A verification step runs *inside* the package, i.e. **after** the
     scheduler has already dispatched it. Does that actually prevent premature
     dispatch, or does it merely make premature dispatch fail loudly after the
     agent has spun up? Is failing-after-dispatch adequate here, and does the
     plan say what the scheduler does with that failure?
   - Is the preflight actually executable — a command with a pass/fail
     condition — or is it prose wearing a checkbox?

## Part C — Standing checks

- Does anything in the change still assume the pre-fix semantics? Grep for
  residue of the old rules (push-triggered blocking sweep, "capability
  directory containing contracts", the old single opt-in).
- Do the new scenarios have corresponding tasks, and do the new tasks have
  corresponding scenarios? Cross-check both directions.
- Run the mechanical gates yourself:
  `openspec validate trace-requirements-to-contracts --strict`, and the work
  package validator if you can locate it.
- Are the new `[human]` carve-outs (5.7c and others) consistent with
  `work-packages.yaml`'s exclusions list?

## Artifacts

All under `openspec/changes/trace-requirements-to-contracts/`:
`proposal.md`, `design.md` (D1–D13), `specs/gen-eval-framework/spec.md`,
`specs/skill-workflow/spec.md`, `tasks.md`, `work-packages.yaml`,
`contracts/traceability.schema.json`,
`contracts/traceability-exclusions.schema.json`, `contracts/README.md`.
Round 1 evidence: `reviews/` and `handoffs/plan-review-20260728T151918Z.json`.

## Do NOT re-raise this (settled, empirically, by four independent reviewers)

The GATEKEEPER proposed widening `wp-model`'s `write_allow` to cover
`packages/gen-eval/evaluation/descriptor.yaml` and the generated
`interface-descriptor.schema.json`. That proposal is **wrong** and was refuted
unanimously against the source: the traceability field lands on archetype-only
models unreachable from `InterfaceDescriptor` (check the generated `$defs`),
and `exclude_defaults=True` on the flag/positional/command dumps keeps
`descriptor.yaml` byte-identical. Do not re-raise it. (The *separate*
`contracts-inventory.md` drift, B8, is real and different — that one you should
verify.)

## Output

Emit **only** a single JSON object, no prose before or after, conforming to
`openspec/schemas/review-findings.schema.json`:

```json
{
  "review_type": "plan",
  "target": "trace-requirements-to-contracts",
  "reviewer_vendor": "<your model name>",
  "findings": [
    {
      "id": 1,
      "axis": "correctness",
      "severity": "critical",
      "type": "spec_gap",
      "criticality": "high",
      "description": "Critical: <what, where, and the command output that proves it>",
      "resolution": "<the specific edit that closes it>",
      "disposition": "fix"
    }
  ]
}
```

Rules: every finding needs both `axis` (one of correctness, readability,
architecture, security, performance) and `severity` (critical, nit, optional,
fyi, none), and the `description` MUST begin with the matching prefix
(`Critical:` / `Nit:` / `Optional:` / `FYI:` / nothing for `none`). Use
`severity: none` for positive observations — in particular, say explicitly
which of the 10 fixes you verified as genuinely closed, and how. A round that
finds nothing wrong must still record what it checked.

Wrap the object in `{"findings": [...]}` exactly as shown — a bare array is
discarded by the dispatcher.
