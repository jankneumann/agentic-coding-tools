# Human tasks — `trace-requirements-to-contracts`

Four of five work packages are implemented. The remaining work is blocked on
seven `[human]` tasks plus one untagged dependent (4.3). Every one of them is
blocked for the same reason: **D1 forbids an agent from guessing which
requirement a contracted operation serves.** Deciding that is the judgement
this change exists to force, so delegating it would defeat the change.

Nothing here is coding. It is triage, and its output is YAML.

---

## Shared setup

All gate commands run from `packages/gen-eval`:

```bash
cd packages/gen-eval
GATE="uv run python scripts/check_traceability.py --repo-root ../.."
```

**The gate generates its own worklist.** This is the single most useful fact
below — you do not have to inventory anything by hand:

```bash
$GATE --scope capability --change trace-requirements-to-contracts \
  | grep '^  - gen-eval-framework: gen-eval-framework\.'
```

Today that prints **34 lines** — 20 requirements from the archived
`openspec/specs/gen-eval-framework/spec.md` plus 14 from this change's spec
delta. Each is one triage decision in Track A. Re-run it after every edit; the
list shrinks as you work.

### The three authoring formats

**Citation on a CLI flag** — `openspec/contracts/gen-eval-framework/cli/gen-eval.yaml`:

```yaml
- name: --mode
  # …existing keys unchanged…
  traceability:
    requirements:
      - gen-eval-framework.evaluation
```

**Exclusion on a CLI flag** — same place, mutually exclusive with the above.
Setting both is a parse error by design ("it has a purpose and it has none"):

```yaml
  traceability:
    excluded:
      reason: "Diagnostic output only; serves no contracted behaviour."
```

**Citation on an OpenAPI operation** — the key is `x-traceability`, same body.

**Capability exclusions file** — `openspec/contracts/<capability>/traceability-exclusions.yaml`:

```yaml
exclusions:
  - requirement: gen-eval-framework.dogfood
    reason: "Served by the framework API; the CLI exposes no surface for it."
```

Requirement ids are `<capability>.<kebab-slug-of-heading>`. A blank reason,
an unknown id, or an id owned by another capability is a hard error — the file
is validated, not decorative.

---

## Track A — the flagship retrofit (gen-eval-framework)

This track unblocks task **5.6** (the change-scoped gate wired into
`/validate-feature`), which is the larger half of the remaining engineering.

### A1 · Task 4.1 — give the 17 contracted flags requirements `[M]`

**Where**: `openspec/changes/trace-requirements-to-contracts/specs/gen-eval-framework/spec.md`

**The gap, measured**: `openspec/contracts/gen-eval-framework/cli/gen-eval.yaml`
declares **17 flags**. The archived spec names exactly three flag-like tokens —
`--print`, `--check`, `--name-only` — and **none of the 17 is among them**
(`--print-contract-version` is a different flag from `--print`). So the honest
starting position is *zero of 17 contracted flags currently have a requirement.*

The 17: `--print-contract-version`, `--descriptor`, `--mode`, `--cli-command`,
`--time-budget`, `--sdk-budget`, `--max-iterations`, `--parallel`,
`--changed-features-ref`, `--categories`, `--report-format`, `--output-dir`,
`--verbose`, `--no-services`, `--fail-threshold`, `--min-coverage`,
`--openspec-change`.

**How**: for each flag, one of three outcomes —

1. An existing requirement already covers it → nothing to write here; you will
   cite it in 4.2.
2. No requirement covers it, but the behaviour is real and intended → add a
   requirement to the spec delta. Lead the first line with SHALL (`--strict`
   only checks the first line).
3. Neither → that is a **finding about the flag**, not about this task. Record
   it; do **not** delete the flag here.

**Done when**: every one of the 17 has a decided destination, and
`openspec validate --strict --changes trace-requirements-to-contracts` passes.

---

### A2 · Task 4.2 — write the citations `[S]` — depends on A1

**Where**: `openspec/contracts/gen-eval-framework/cli/gen-eval.yaml`

**How**: attach a `traceability:` block to each of the 17 flags using the
formats above. Adding the *first* one opts the whole document into forward
enforcement (D6) — there is no partial state, so plan to finish the file in one
sitting.

**Then regenerate the derived descriptor**, bare, exactly as CI invokes it
(`ci.yml:431` runs the `--check` form; passing extra flags to one and not the
other reports drift on a correct file):

```bash
uv run python scripts/generate_tool_descriptor.py           # write
uv run python scripts/generate_tool_descriptor.py --check   # must exit 0
```

**Done when**: `--check` exits 0 and
`$GATE --scope capability --change trace-requirements-to-contracts` no longer
reports any *uncited operation* for the CLI document.

---

### A3 · Task 4.2b — author the exclusions file `[M]` — depends on A2

**Where**: `openspec/contracts/gen-eval-framework/traceability-exclusions.yaml`

This is the **reverse** direction and the larger half of the retrofit. Creating
this file flips gen-eval-framework into blocking reverse enforcement (D13), so
it lands last in the track.

**How**: run the worklist command. For each of the 34 requirements, either it
is cited by some operation after A2, or it needs a line here with a written
reason. *"Served by the framework API, no CLI surface"* is a real and expected
reason — recording it is the entire point, not a workaround.

```bash
$GATE --scope capability --change trace-requirements-to-contracts \
  | grep 'gen-eval-framework\.' | sed 's/.*gen-eval-framework\.\([a-z0-9-]*\).*/\1/'
```

**Budget check**: if this triage runs materially larger than expected, the
correct response is to **defer the reverse opt-in to a follow-up change** —
delete the file and re-scope. Do *not* weaken the gate, and do *not* write
exclusions whose reason is a placeholder. A placeholder reason parses fine and
is exactly the unfalsifiable-green artifact this change exists to eliminate.

**Done when**: the capability-scope run reports no uncited
gen-eval-framework requirement.

---

### A4 · Task 4.3 — RED demonstration `[S]` — **agent-doable** once A3 lands

Not `[human]`. Scripted verification of your artifacts: remove one citation →
gate exits non-zero naming that flag → restore; remove one exclusion → gate
exits non-zero naming that requirement → restore. Confirm the failing run reads
the mutated YAML and not the stale regenerated descriptor.

---

## Track B — the coordinator contract

Independent of Track A. This track unblocks task **5.7** (the CI sweep).

### B1 · Task 5.1 — author `openspec/contracts/agent-coordinator/openapi/v1.yaml` `[M]`

**Authored from `openspec/specs/agent-coordinator/spec.md`, NOT generated from
the running app.** `app.openapi()` produces the app describing itself;
verifying the app against that compares it to a copy of itself and reports zero
violations forever. That failure mode is the reason this change exists.

**Scale, measured 2026-07-26**: the app serves 82 operations; the spec's 122
requirements name 35 of them. You are writing the contract for the 35, from the
spec text.

Land it `untraced` (no `x-traceability` yet) — D6 means the document is not
enforced until something opts in, which is B2.

### B2 · Task 5.2 — split the contract, opt **one** document in `[M]`

Split `openspec/contracts/agent-coordinator/openapi/` into per-subsystem
documents (`locks.yaml`, `work-queue.yaml`, …). D6's unit is the *document*, so
each subsystem opts in when it is ready, and D10's capability-level union means
the split costs nothing in rigour.

**Start with `locks` or `work-queue`** — small, and the operations the spec
names most concretely. This proves the model on real requirements before anyone
commits to all 82.

**FORWARD ONLY.** Do **not** create the coordinator's
`traceability-exclusions.yaml` — reverse opt-in there means triaging all 122
coordinator requirements, which is the backlog this change *creates* (B3), not
work it performs.

### B3 · Task 5.3 — file the unattributed operations as findings `[S]`

The ~47 operations no requirement names are out of scope by construction. File
them as issues; do not spec them here. What each is for is mostly not
gen-eval's call.

---

## Track C — after both tracks

Once A1–A3 and B1–B2 are done, **`wp-wiring` unblocks and an agent can run
5.6, 5.7, 5.7b, 5.8, 5.9** (re-invoke `/autopilot` or `/implement-feature`).
One human task remains after that:

### C1 · Task 5.7c — the acceptance criterion `[M]` — depends on A3, B2, 5.7

```bash
$GATE --scope capability --change trace-requirements-to-contracts; echo "EXIT=$?"
```

**It MUST exit 0.** This change flips gen-eval-framework into blocking reverse
enforcement *and* installs the blocking CI sweep in the same PR — a non-zero
result here means merging reds `main` immediately. Passing may require triage
decisions, which is why it is `[human]`.

Pass `--change` explicitly: the requirements A1 adds exist only in this
change's spec delta, so an archive-only run reports every one as unresolved.

**Also run the post-merge form once and record it without gating on it:**

```bash
$GATE --scope capability; echo "EXIT=$?"    # no --change — union mode
```

It unions every in-flight change on the branch and *will* report other changes'
uncited requirements. That is precisely why that run is non-blocking. Recording
it proves the two modes were distinguished on real artifacts rather than
assumed to differ.

**Expect `code-search/v2.yaml` in the REPORT, not the failures.** It is a
pre-existing root-misplaced instance; the rule reports existing violations and
fails only newly added ones. If it appears as a *failure*, discovery was built
as a cliff rather than a ratchet and task 3.6's assertion (a) does not hold —
that is a bug to fix, not a triage decision.

**Before trusting the exit code**, check that no edit has reintroduced a
blocking invocation this task does not run. An earlier plan draft had
`merge_group` block in union mode, which made 5.7c exercise an invocation no
blocking event actually ran.

---

## Critical path

```
A1 → A2 → A3 ─┐
              ├─→ [agent: 4.3, 5.6, 5.7, 5.7b, 5.8, 5.9] → C1 → merge
B1 → B2 ──────┘
B3 (independent, file anytime)
```

Track A and Track B are fully independent and can be done in either order or
in parallel. **A2 alone unblocks 5.6; B2 alone unblocks 5.7.**

## What NOT to do

- Do not let an agent write 4.1, 4.2, 4.2b, 5.1, 5.2, or 5.3. D1 forbids it,
  and the resulting citations would be name-similarity guesses wearing the
  costume of a decision.
- Do not generate the coordinator OpenAPI from the running app (B1).
- Do not write a placeholder exclusion reason to make the gate green (A3).
- Do not weaken the gate to pass C1. Defer the reverse opt-in instead.
