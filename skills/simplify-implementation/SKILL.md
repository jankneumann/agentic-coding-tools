---
name: simplify-implementation
description: >
  Review changed code for reuse, quality, and efficiency, then apply low-risk
  simplifications that preserve behavior exactly. Requires a coverage gate and
  characterization tests when the surface is unpinned; optionally prunes tests
  that assert implementation instead of behavior, then removes the production
  seams those tests held open. Dual-run verification proves the suite stays
  green without changing test expectations.
category: Engineering Methodology
tags: [refactor, simplification, code-quality, review, characterization, isomorphic, test-pruning]
triggers:
  - "simplify-implementation"
  - "simplify the implementation"
  - "simplify the code"
  - "review for simplification"
  - "clean this up"
  - "refactor for clarity"
  - "code-simplify"
  - "isomorphic refactor"
  - "reduce duplication without changing behavior"
  - "prune low-value tests"
  - "delete tests that assert implementation"
  - "remove duplicative tests"
  - "tests that only re-assert the source"
  - "remove test-induced seams"
user_invocable: true
related:
  - test-driven-development
  - tech-debt-analysis
  - deprecation-and-migration
  - iterate-on-implementation
  - performance-optimization
---

# Simplify

Inspect a focused diff, file, or module for **behavior-preserving** simplifications: dead code, deep nesting, long functions, premature abstractions, generic names, and isomorphic DRY extracts. The goal is fewer moving parts and faster comprehension — not stylistic preference and **not** fewer lines for their own sake.

This skill is **read → pin → (prune) → edit**: it reviews first, applies a **coverage gate**, writes characterization tests when needed, optionally prunes tests that assert implementation rather than behavior, gates each candidate against Chesterton's Fence, applies changes one pattern at a time, and dual-runs the suite. Large surface areas are deferred (Rule of 500).

The test suite is part of the surface under review. A test that must be edited every time the source changes is asserting implementation, not behavior — it is a cost on every commit that catches nothing, and it frequently holds open a production seam that exists for no other reason. Removing both is a simplification; see [Test Pruning](#test-pruning-optional-phase--never-first).

**Primary invoke:** `/simplify-implementation`  
**Naming:** deliberately not `/simplify` — Claude Code ships a bundled `simplify` skill (quality-only cleanup via parallel agents, no coverage gate). Ours is the stricter, gated variant and coexists with it under this name.  
**Invocation mode:** **manual only** by default — invocation is **not** default-on anywhere. Operators (or an explicit human request) run this skill directly; in the orchestrated path `/autopilot --simplify` **is** the operator request, and dispatches the [Review role](#roles) and then the Apply role to separate agents. Without that flag, autopilot and implement-feature do **not** run simplify.

## When to Use

- After a feature is green and the implementation feels heavier than needed
- During review when readability / complexity is flagged without a behavior bug
- When tech-debt reports local Long Method, Deep Nesting, or local Duplication
- When consolidating duplicated logic that should share one helper
- Optional polish after `/implement-feature` or `/iterate-on-implementation` (separate `refactor` commits)

## When NOT to Use

| Situation | Do this instead |
|---|---|
| You do not yet understand the code | Read, blame, and map callers first — then return |
| Behavior or public contracts must change | Feature / fix workflow (`implement-feature`, TDD) |
| Performance rewrite with different algorithms | `/performance-optimization` |
| Removing a public or multi-consumer surface | `/deprecation-and-migration` |
| Hub / coupling / multi-module redesign | `/plan-feature` (Rule of 500 / structural debt) |
| Cleanup mixed into an in-progress feature | `NOTICED BUT NOT TOUCHING:` + later `/simplify-implementation` |
| Code is already clear | Stop — do not simplify for its own sake |

## Scope

- Run on the current diff, a specified file/module, or a tech-debt finding ID.
- Production edits only after the coverage gate passes.
- Characterization commits may add tests; prune commits may remove them; simplify commits must not change assertion **bodies**.
- Test pruning is in scope for the named surface only, is test-only per commit, and is ledgered.
- Single-PR / small-batch changes. Cross-cutting refactors follow Rule of 500 or escalate.

## Principles

### 1. Preserve behavior exactly

Same inputs → same outputs, errors, side effects, and ordering. If unsure, do not change it.

### 2. Tests are the isomorphism proof

Observable equivalence is proven by behavioral tests, not by agent confidence. Prefer **state-based** tests (inputs/outputs) over interaction mocks so structure can move without rewriting tests — see `test-driven-development` (Beyoncé Rule, DAMP tests).

### 3. Follow project conventions

Match neighboring code: imports, naming, error handling, typing depth. External “clever” idioms that fight the codebase are churn, not simplification.

### 4. Clarity over cleverness and line count

A short nested ternary is not simpler than an explicit branch. Over-inlining that erases a useful name is a failure mode.

### 5. Scope to what you intended

No drive-by refactors outside the named surface unless the operator broadens scope.

## Chesterton's Fence — Pre-Simplification Check

Before removing or refactoring any non-trivial piece of code, answer all three. If any answer is "I don't know," **stop and investigate**.

1. **Why does this exist?** `git blame`, introducing commit message, callers (`grep`), tests that pin it.
2. **What problem does it still solve — or is it specified to solve?** Rate limits, retries, ordering, error masking, security boundaries — load-bearing fences stay. So does a seam whose consumer is named in an **active, approved** OpenSpec change (`openspec/changes/<id>/`, not archived, not a draft): a specified consumer is a consumer with a delivery commitment. A roadmap item or a "we'll need this later" comment is not.
3. **What non-obvious invariants does it preserve?** Idempotency, transactional boundaries, timezone normalization, injection defense.

If (2) is "nothing — reason is gone," the fence may come down. Otherwise leave it and document why: `# CHESTERTON: kept because …`, or for a specified-but-unbuilt consumer `# CHESTERTON: kept for openspec/changes/<change-id>` so the justification can be verified — and lapsed — later.

## Coverage Gate (required)

```
Surface under edit
       │
       ▼
 Existing state-based tests pin inputs/outputs/errors/side effects?
       │
  yes  │  no
       │   └──► CHARACTERIZE first:
       │         • Write tests that pass on CURRENT code (green-on-baseline)
       │         • Prefer real impl / fakes over interaction mocks
       │         • Commit: test(<scope>): pin behavior for <surface>
       │         • Only then proceed to production edits
       ▼
 Continue to candidate list / Chesterton / edits
```

**If you cannot pin the surface, you cannot simplify it.** Hope is not a dual-run.

Characterization tests are **not** a license to change behavior later in the same PR — they freeze today's behavior so refactors cannot silently drift.

## Test Pruning (optional phase — never first)

**Tests must justify their presence.** A test earns its place by failing when
behavior breaks. A test that must be edited whenever the source changes fails
that bar: it is rewritten to match whatever the code now does, so it never
catches anything — it only taxes every commit and anchors the production
structure it happens to reach into.

Pruning such tests is a real simplification, and it is usually the *enabling*
one: the seams that exist only so a test could reach inside can go with them
(see [Test-induced seams](#test-induced-seams-only-after-pruning)).

Pruning **removes** coverage, so it is ordered, bounded, and ledgered. It is not
permission to delete a test that is merely inconvenient, slow, or failing.

The repo-wide statement of this policy — and the half about which tests get
*written* — lives in `docs/guides/testing-policy.md` (consumer-project-relative)
and the `test-driven-development` skill.

### Phase order — characterize before you prune

```
B0  tip before any simplify work
 │
 ├── Phase A — CHARACTERIZE   test(<scope>): pin behavior for <surface>
 │      add state-based pins for behavior the surface really has
 │
B1' (optional intermediate — the pins now exist)
 │
 ├── Phase B — PRUNE          test(<scope>): remove <smell> tests for <surface>
 │      test-only commits; every removal ledgered
 │
B1  post-prune tip  ◄── baseline for check_test_contract.py AND the dual-run
 │
 ├── Phase C — SIMPLIFY       refactor(<scope>): <pattern> — <brief>
 │      production edits, one pattern at a time
 │
HEAD
```

**Characterize first, always.** Behavioral pins must exist *before*
implementation-coupled tests come out. Prune first and the surface drops to zero
coverage, and every "simplification" after it is unverified — you deleted the
only thing that could have contradicted you.

Do not prune a surface you are not also simplifying. Pruning alone is a coverage
reduction with no offsetting gain; it belongs to whoever owns that surface.

### Delete catalog

| Smell | Signal | Verdict |
|---|---|---|
| **Orphan** (general case) | No path up to a spec clause, invariant, or goal; the rows below are how orphans usually present | Delete, with the most specific reason below |
| **Source-mirroring** | Assertion restates a literal from the source (`assert TIMEOUT == 30` beside `TIMEOUT = 30`) | Delete — it asserts the source, not the behavior the value causes |
| **Change-detector** | Any source edit forces an edit here; asserts call order, private names, or internal structure | Delete, or rewrite state-based first and keep the rewrite |
| **Self-mocking** | Mocks the unit under test, then asserts the mock was called | Delete — it tests the mocking library |
| **Duplicative** | Same behavior, same equivalence class, different name | Merge or parametrize; keep one |
| **Accessor-only** | Asserts a dataclass returns what it was handed, with no validation or invariant | Delete unless it pins a constraint |
| **Library-under-test** | Asserts stdlib / framework / ORM behavior you do not own | Delete |
| **Vacuous** | No assertion, or one that cannot fail (`assert obj is not None` right after constructing `obj`) | Delete |
| **Unreviewed snapshot** | Snapshot re-blessed on every change without anyone reading the diff | Delete, or narrow to the fields that carry meaning |

### Keep catalog — Chesterton's Fence for tests

A test that looks trivial is not automatically low value. **Keep** it when any of
these hold, whatever it costs to maintain:

- **Regression tests** tied to a bug, incident, or issue ID — the triviality is the point; someone paid for it in production.
- The **only** test covering an error path, boundary, or empty/overflow case.
- **Contract tests** on a public or multi-consumer API (Hyrum's Law — someone depends on it).
- **Security, authz, injection, or PII** assertions.
- **Property, fuzz, or concurrency** tests — non-obvious inputs are their whole value.
- The only **executable documentation** of a subtle or surprising behavior.
- **Contract tests on a seam whose consumer is specified** in an active OpenSpec change — the architecture-level RED phase. Cite it: `# CHESTERTON: kept for openspec/changes/<id>`. This protects the seam's contract, not the implementation-coupled tests below it.
- A test you cannot explain the origin of. Unknown origin means investigate, not delete — the same rule as production code.

If you cannot say what a test would catch *and* what it would cost to keep,
you have not finished reading it. Keep it.

### The coverage-preserving rule

For every removal, exactly one of these must be true and written down:

- **(a) No behavior was asserted** — reasons `source-mirroring`, `vacuous`, `library-under-test`, `accessor-only`, `self-mocking`. Nothing to preserve.
- **(b) The behavior survives elsewhere** — reasons `change-detector`, `duplicative`, `unreviewed-snapshot`. Name the surviving test in `covered-by:`. If no test covers it, write that test **first** (Phase A), then prune.

There is no **(c) "I'll re-add coverage later."** A removal you cannot justify
today is a test you keep today.

### The review artifact

The [Review role](#roles)'s single output is `simplify-review.json`: a review-findings
document with `review_type: simplify`, governed by `schemas/simplify-review.schema.json`
(composed over the canonical `review-findings.schema.json`). In an autopilot run it lives at
`openspec/changes/<change-id>/simplify-review.json`; a manual run may put it anywhere that
ships with the PR.

**Envelope:** `target` (change id, or a surface label for a manual run), `baseline_b0` (the
`<B0>` SHA), `scope` (`files`, `lines`, `rule_of_500: within | exceeded`), and
`skipped_reason` — set when there is nothing to apply, so a refusal is *recorded* rather
than inferred from an empty findings list.

**Each finding** carries the usual review-findings fields (`id`, `description`,
`disposition`, `axis`, `severity`, `criticality: low`) plus:

| Field | Meaning |
|---|---|
| `type` | `simplification` (a production construct) or `test_quality` (a test to prune) |
| `pattern` | Catalog entry: a Local clarity, Isomorphic structure, Test-induced seam, or Delete-catalog name |
| `fence` | `verdict` (`remove` / `keep` / `investigate`), `rationale`, and `evidence` (blame SHAs, caller searches, active OpenSpec change ids) |
| `coverage` | `pinned`, plus `characterize`: the behaviors the Apply role must pin **before** touching this finding |
| `prune` | `reason` (a ledger reason code) and `covered_by` — required on `test_quality` findings with `disposition: fix` |
| `consumer` | `present` / `specified` caller lists, on Test-induced seam findings |
| `test_id` | Optional nodeid of the test to remove (`tests/test_client.py::test_x`). It is what the rendered ledger addresses; when absent, `file_path` becomes a file-level entry covering every test in that file |

Four rules the artifact must satisfy, all enforced by `simplify_review.py validate`:

1. `disposition: fix` requires `fence.verdict: remove` — you cannot apply a fence you kept.
2. `type: test_quality` with `disposition: fix` requires `prune` and `file_path`.
3. A `prune.reason` of `change-detector`, `duplicative`, or `unreviewed-snapshot` requires a
   non-null `prune.covered_by` — the [coverage-preserving rule](#the-coverage-preserving-rule),
   mechanized.
4. A non-empty `consumer.present` or `consumer.specified` forces `fence.verdict: keep` and a
   disposition other than `fix` — a seam with a consumer is a design decision.

### Prune ledger

One entry per removal, in a file that ships with the PR (e.g.
`docs/simplify-implementation/test-prune-ledger.md`). A file-level `removed:` entry covers
every test in that file.

Whenever a review artifact exists — always, in the orchestrated path — this file is
**rendered from it**, never written by hand:

```bash
python3 "<skill-base-dir>/scripts/simplify_review.py" render-ledger <artifact> \
  --out docs/simplify-implementation/test-prune-ledger.md
```

One entry per `test_quality` finding with `disposition: fix`; every other finding is
skipped. Rendering is what makes the ledger the *reviewer's* decision: the prune gate below
then checks that the implementer removed what the reviewer said, and nothing else.

```markdown
- removed: tests/test_config.py::test_timeout_is_thirty
  reason: source-mirroring
  covered-by: none

- removed: tests/test_parser.py::test_calls_tokenize_then_normalize
  reason: change-detector
  covered-by: tests/test_parser.py::test_parses_iso_timestamps_to_utc

- removed: tests/test_client_internals.py
  reason: duplicative
  covered-by: tests/test_client.py::test_retries_on_503_then_succeeds
```

### Gate

```bash
# Prune range must be test-only, and every removal must be ledgered.
python3 "<skill-base-dir>/scripts/check_test_prune.py" \
  --base <B0> --head <B1> --ledger docs/simplify-implementation/test-prune-ledger.md
```

Then re-baseline: `check_test_contract.py` and the dual-run both take `--base` /
`--baseline` of **`<B1>`**, the post-prune tip. Pointing them at `<B0>` reports
the pruned assertions as contract breaks — which is exactly what they are
*outside* this phase, and why the prune gets its own range and its own gate.

## Rule of 500

Simplifications that touch **more than 500 lines** OR **more than 5 files** SHALL NOT be done by hand.

When exceeded:

- **(a) Automate** — codemod / AST tool (libcst, ts-morph, jscodeshift) with reviewable automation.
- **(b) Split** — one module / one pattern / one PR; repeat.
- **(c) Escalate** — `/plan-feature` for design + review gates.

Mechanical check (recommended):

```bash
python3 "<skill-base-dir>/scripts/check_scope.py" --base <baseline-sha>
# oversized? re-run with --allow-codemod only when a real codemod produced the diff
```

## Pattern catalog

### Local clarity (existing)

| Pattern | Signal | Move |
|---|---|---|
| Deep nesting → guard clauses | 3+ levels of `if`/`for`/`try` | Early return; happy path top-to-bottom |
| Long functions → extract helpers | ~50+ lines or multiple responsibilities | Named steps; outline stays in the parent |
| Nested ternaries → branches / maps | Ternary inside ternary | `if/elif` or lookup table |
| Boolean flag params → split | `do(true, false)` switches behavior | Two named functions or options object |
| Generic names → domain names | `data`, `info`, `obj`, `temp`, `result` | `user_record`, `pending_invoice`, … |
| Premature abstraction → inline | One-impl interface / factory-of-one | Inline; re-abstract when a second impl is real |

### Isomorphic structure (added)

| Pattern | Signal | Move |
|---|---|---|
| **Isomorphic extract** | Same ≥~5-line structural block in 2+ sites | Shared helper; both sites call it. **Requires** characterization (or existing tests) on **all** sites |
| **Dead code removal** | Unreachable branches, unused private symbols, commented-out blocks | Remove only after Fence + reference search + tests |
| **Redundant intermediate** | Wrapper that only forwards, no policy | Inline; **do not** if public API, documented extension point, or Hyrum-visible |

**Rebalance note:** Inlining premature abstractions is still valid for *single-use* abstractions that are not extension points. Extracting real duplication is the dual — do not “inline” away a helper that names a real domain concept used in multiple places.

### Test-induced seams (only after pruning)

The payoff of [Test Pruning](#test-pruning-optional-phase--never-first). Once an
implementation-coupled test is gone, the production seam it reached through
often has no remaining consumer — it was never a design, only an affordance for
a test that itself asserted nothing.

| Pattern | Signal | Move |
|---|---|---|
| Mock-only interface | Protocol / interface / ABC with exactly one production implementation, introduced so a test could inject a double | Inline the concrete type; delete the interface |
| Test-only constructor param | `def __init__(self, ..., clock=None, _fetcher=None)` left default at every production call site | Drop the parameter; construct the dependency directly |
| Visibility widened for tests | Symbol made public / module-level whose only non-test reference was the deleted test | Restore the narrower scope |
| Factory-of-one | `build_x()` returning the single concrete `X`, existing so tests could patch the factory | Inline; construct `X` at the call site |
| `_for_testing` / `reset_state()` hooks | Symbol named for tests, referenced only by tests you just removed | Remove |

**Gate — stricter than the rest of the catalog.** A seam may come out only when
**both** hold:

1. The seam has **no consumer**, checked two ways: a reference search over the
   whole repo (not just the diff) finds no non-test caller, **and** no active
   OpenSpec change under `openspec/changes/<id>/` specifies one. A green suite
   proves nothing here — a seam with one production caller and zero tests still
   looks unused to the suite — and a reference search cannot see a consumer that
   has not been written yet.
2. The behavior the seam served is still pinned by a surviving state-based test.

A seam with a present or specified consumer is a design decision. Chesterton's
Fence applies to it exactly as it does to any other construct. A specified
consumer keeps the seam's *contract*; simplifying its internals stays in scope.
When the specifying change is later archived without landing, the seam becomes
an orphan and comes back onto this list.

## Roles

This skill is **two roles sharing one artifact**: a **Review** role that decides, and an
**Apply** role that executes those decisions. The artifact between them is
[`simplify-review.json`](#the-review-artifact).

### Review role (workflow steps 0–2, 4–5)

Read-only with respect to production **and** test code. It records the scope and `<B0>`,
runs Chesterton's Fence, makes the coverage-gate decision (which behaviors must be pinned,
and by whom), sweeps the suite against the Delete and Keep catalogs, lists candidates by
pattern, and applies the Rule of 500 at review scope. Its only write is the artifact, and it
ends by validating it:

```bash
python3 "<skill-base-dir>/scripts/simplify_review.py" validate <artifact>
```

An artifact that does not validate is not a review. If there is nothing to apply — nothing
fails the catalogs, or the surface exceeds the Rule of 500 at review scope — the role still
writes an artifact, with `skipped_reason` set.

### Apply role (workflow steps 3, 6–8)

Starts by validating the same artifact, then works only from it: it characterizes exactly
the behaviors each finding's `coverage.characterize` names, executes the Review role's
`prune` findings in step 3 from a ledger it **renders** (`render-ledger`) rather than writes,
applies only findings with `disposition: fix`, one pattern at a time, and dual-runs.

The Apply role **MUST NOT** change any finding's `fence.verdict` or `disposition`. A finding
it cannot land is reported as **skipped**, with the reason, in step 8 — not silently dropped
and not re-dispositioned. A verdict it disagrees with goes back to a **human**; disagreement
is not a licence to edit the artifact. Kept fences stay kept, and appear in the report under
findings kept.

A manual run **may** perform both roles in one session, but it **must write the artifact
between them** — the artifact, not the agent's memory, is what the Apply role executes.
`/autopilot --simplify` dispatches the two roles to different archetypes (`reviewer`, then
`implementer`), which is the same contract with a process boundary in the middle.

## Workflow

Each step is tagged with the [role](#roles) that runs it. The order below does not change:
the Review role records its decisions in the artifact, and the Apply role executes them —
including the prune in step 3, whose removals come from the artifact's `prune` findings, not
from the implementer's own judgment.

### 0. Scope [Review]

Identify target: `git diff`, path, module, or tech-debt finding ID. Record `<B0>`, the tip before any simplify work. The **baseline SHA** for the downstream gates is `<B1>` — the tip after characterization **and** prune commits, i.e. immediately before the first production edit. When neither phase produces a commit, `<B1>` is `<B0>`.

### 1. Understand (Chesterton's Fence) [Review]

Blame, callers, existing tests, edge cases. Read project conventions (AGENTS.md / CLAUDE.md / neighboring modules).

### 2. Coverage gate [Review]

Pin or characterize (see above). Run characterization tests and confirm green on baseline.

### 3. Test prune (optional) [Apply]

The [Review role](#roles) already swept the surface against the
[Delete catalog](#delete-catalog) and the
[Keep catalog](#keep-catalog--chestertons-fence-for-tests); this step executes its
`test_quality` findings with `disposition: fix`, and nothing else. Render the ledger from
the artifact (`simplify_review.py render-ledger`), remove exactly the tests it names, one
test-only commit per group: `test(<scope>): remove <smell> tests for <surface>`. Run the
suite; it must stay green with production code untouched. Record `<B1>` — the post-prune
tip — as the baseline for everything downstream.

Skip this step entirely when the artifact has no `test_quality` finding to apply. Most runs
of `/simplify-implementation` skip it. A run with no artifact cannot prune: the ledger is
rendered from the artifact, not from memory.

### 4. Candidate list [Review]

List opportunities by pattern, including any [test-induced seams](#test-induced-seams-only-after-pruning)
the prune just orphaned. Drop any that fail Chesterton's Fence; note fences kept.

### 5. Rule of 500 [Review]

Group remaining work. Automate, split, or escalate if over budget.

### 6. Apply incrementally [Apply]

For each remaining candidate:

1. Make **one** simplification.
2. Run the targeted suite (then broader suite if targeted is green).
3. If red → revert that simplification; re-evaluate.
4. Commit: `refactor(<scope>): <pattern> — <brief>` (e.g. `refactor(parser): extract guard clauses from validate_input`).

Never mix `feat` / `fix` with simplify polish in the same commit.

### 7. Dual-run verify [Apply]

```bash
# Prune range (skip when no tests were removed): test-only diff, every removal ledgered.
python3 "<skill-base-dir>/scripts/check_test_prune.py" \
  --base <B0> --head <B1> --ledger docs/simplify-implementation/test-prune-ledger.md

# Recommended mechanical dual-run (writes simplify-report.json by default).
# Prefer a project-local interpreter so detached worktrees resolve tools;
# the script also symlinks .venv / node_modules from the main repo when present.
python3 "<skill-base-dir>/scripts/verify_behavior_preservation.py" \
  --baseline <B1> \
  --test-cmd "python3 -m pytest -q"   # or: .venv/bin/python -m pytest / npm test

# Assertion contract on the simplify range (should be clean for expectation bodies).
# --base MUST be <B1> — the tip AFTER characterization AND prune commits.
python3 "<skill-base-dir>/scripts/check_test_contract.py" --base <B1>
python3 "<skill-base-dir>/scripts/check_scope.py" --base <B1>
```

`<B1>` is the baseline for the dual-run precisely because it is the last commit
where production code is untouched but the suite is already final: running that
suite at `<B1>` and at `HEAD` isolates the production edits as the only variable.
Baselining at `<B0>` instead compares two different suites and proves nothing.

Source-contribution-only example (this monorepo, not portable to consumers):
`skills/.venv/bin/python -m pytest -q skills/tests/simplify-implementation/`

Manual equivalent: run the same suite on `<B1>` and on `HEAD`; both must pass.

### 8. Report [Apply]

Summarize: patterns applied, fences kept, characterization tests added, tests pruned (with the rendered ledger, or "none"), seams removed and the reference search that cleared them, dual-run evidence (commands + exit codes or report path), Rule of 500 status.

Report **against the artifact**: findings reviewed, applied, kept, and skipped — each skip with its reason. A finding the Apply role could not land is reported, never re-dispositioned; a verdict it disagrees with is raised to a human here, with the evidence, not edited into the artifact.

## Script helpers

Scripts live in `<skill-base-dir>/scripts/` (installed copy under `.claude/skills/simplify-implementation/scripts/` or `.agents/skills/simplify-implementation/scripts/`). They use only the standard library plus `git` — except `simplify_review.py validate`, which also needs `jsonschema` and `referencing`, and exits `1` rather than reporting a pass when they are missing.

| Script | Purpose | Exit |
|---|---|---|
| `check_scope.py` | Diff line/file counts vs Rule of 500 | `0` ok, `2` over limit without `--allow-codemod`, `1` error |
| `check_test_prune.py` | Prune range is test-only; every removed test is ledgered with a valid reason (and `covered-by:` when it covered behavior) | `0` ok, `2` unjustified removal or production edit in range, `1` error |
| `check_test_contract.py` | Detect assertion/expect body changes in test paths | `0` ok, `2` contract break, `1` error |
| `verify_behavior_preservation.py` | Run tests at baseline and HEAD in detached worktrees; write JSON report | `0` both green, `2` failure, `1` error |
| `simplify_review.py` | `validate <artifact>`: the [review artifact](#the-review-artifact) against its contract and the canonical review-findings schema, naming the failing finding and path (`--json` for the machine-readable error list); `render-ledger <artifact> --out <path>`: emit `test-prune-ledger.md` from the artifact's `test_quality` / `fix` findings | `0` valid or rendered, `2` invalid artifact, `1` error |

`simplify_review.py` resolves the canonical `review-findings.schema.json` through the
installed `parallel-infrastructure` skill (`<skill-base-dir>/../parallel-infrastructure/scripts`),
falling back to an `install_assets` copy, and the contract from `schemas/` next to this skill
(override with `--contract`).

`check_test_contract.py` expects `--base` at `<B1>` — the tip **after** characterization and prune commits. Within that range, any `+/-` assertion line (including deleted test files) is a contract break. Test removals belong in the prune range, where `check_test_prune.py` gates them; a removal inside the simplify range means you deleted a test to make a refactor go green.

`verify_behavior_preservation.py` takes a **trusted** `--test-cmd` shell string (e.g. `pytest -q`). Both SHAs are checked out via temporary detached worktrees so a dirty working tree cannot skew results.

## Language sketches (clarity, not prescription)

**Python — guard clauses**

```python
# Before: nested happy path
def process(data):
    if data is not None:
        if data.is_valid():
            return do_work(data)
        raise ValueError("invalid")
    raise TypeError("missing")

# After
def process(data):
    if data is None:
        raise TypeError("missing")
    if not data.is_valid():
        raise ValueError("invalid")
    return do_work(data)
```

**TypeScript — redundant boolean**

```typescript
// Before
function isValid(input: string): boolean {
  if (input.length > 0 && input.length < 100) return true;
  return false;
}
// After
function isValid(input: string): boolean {
  return input.length > 0 && input.length < 100;
}
```

Prefer project idioms when they conflict with these sketches.

## Handoffs

| Signal | Route |
|---|---|
| Local complexity / nesting / naming / local dup | Stay on `/simplify-implementation` |
| Tech-debt hub / high coupling / large redesign | `/plan-feature` |
| Dead public API / multi-consumer removal | `/deprecation-and-migration` |
| Measured perf bottleneck | `/performance-optimization` |
| Bug or missing behavior | `/test-driven-development` + fix (not simplify) |
| Suite has no behavioral pins at all to prune against | `/test-driven-development` first — write pins, then return |
| Whole-suite testing-strategy overhaul (pyramid, fixtures, harness) | `/test-driven-development` + `/plan-feature`, not a prune sweep |

## Common Rationalizations

| Rationalization | Why it's wrong |
|---|---|
| "I don't need blame — this is obviously dead" | "Obviously dead" is the #1 subtle regression source. Blame and callers are free; use them. |
| "It's only 600 lines — I'll be careful" | Rule of 500 is about reviewability and tail risk, not ego. Automate or split. |
| "Tests pass so behavior is preserved" | Tests that never exercised the surface cannot pin it. Coverage gate first. |
| "I'll tweak the assertion — the new code is equivalent" | Expectation edits mean you changed observable behavior or the test was wrong. Revert the simplify; fix with an explicit behavior change outside this skill. |
| "I'll simplify while finishing the feature" | Mixed feat+refactor PRs hide regressions and break revertability. Separate commits/PRs; use `NOTICED BUT NOT TOUCHING` during implement. |
| "This abstraction will pay off later" | Speculative abstractions are cost without value. Inline until a second real implementation appears. |
| "Fewer lines is always simpler" | Nested one-liners can be harder to read. Optimize for comprehension speed. |
| "More tests are always better" | A test that never fails on a real break is not coverage, it is a maintenance tax that also freezes the code shape. Tests must justify their presence. |
| "I'll delete these tests first, then write pins" | Backwards. Prune with zero pins in place and every later simplification is unverified. Characterize, then prune. |
| "The test kept failing on every refactor, so I removed it" | That is a signal to check *why* it is coupled — a change-detector gets deleted with a `covered-by:` target, a real regression test gets kept and the refactor gets fixed. |
| "It is just a test — deleting it is low risk" | Deleting a test is the one edit in this skill that reduces the evidence for every edit after it. It is the highest-risk change here, not the lowest. |
| "The seam is unused now that the test is gone" | A green suite cannot tell an unused seam from an untested production caller. Do the reference search, and check active OpenSpec changes for a specified one. |
| "A future feature will need this seam" | Only if that feature is an active, approved OpenSpec change you can cite. A roadmap wish is the speculative abstraction two rows up, wearing a spec costume. |

## Red Flags

- Production simplify commits without a coverage-gate decision (existing pins **or** new characterization tests).
- A simplify PR that changes test assertion bodies to go green.
- Diff over 500 lines or 5 files with no codemod / split plan (Rule of 500 violation).
- Removed code with no blame / caller investigation recorded.
- `feat`/`fix` mixed into the same commit as a clarity refactor.
- Autopilot or implement silently running simplify without operator request.
- Inlined helper that deleted a comment documenting a non-obvious invariant (fence lost).
- Isomorphic extract landed without tests covering all rewritten call sites.
- Prune commits landing **before** characterization commits, or with no characterization at all.
- A prune commit that also touches production code (`check_test_prune.py` exits 2).
- A removed test with no ledger entry, or `reason: change-detector` / `duplicative` with `covered-by: none`.
- A deleted regression test that cites a bug or incident ID.
- Net coverage of an error path, boundary, or authz check dropping to zero after the prune.
- A seam removed on the strength of a green suite alone, with no repo-wide reference search.
- `check_test_contract.py --base <B0>` used instead of `<B1>` to make the prune look clean.
- The Apply role changed a finding's `fence.verdict` or `disposition` instead of reporting the finding skipped and raising the disagreement to a human.
- A hand-written `test-prune-ledger.md` in the orchestrated path — or one whose entries do not match `simplify_review.py render-ledger` output.

## Verification

1. Cite each pattern catalog entry applied in the PR/report.
2. For removed/renamed/inlined constructs, cite blame or introducing commit (Chesterton's Fence).
3. Confirm coverage gate: either list existing pinning tests **or** show the characterization commit (`test(...): pin behavior…`) that is green on baseline.
4. Confirm dual-run: suite green on `<B1>` and on HEAD (attach `simplify-report.json` from `verify_behavior_preservation.py` when used).
5. If tests were pruned, confirm `check_test_prune.py --base <B0> --head <B1> --ledger <path>` exits 0, and attach the ledger. If none were pruned, say so explicitly.
6. For each removed test, confirm the coverage-preserving rule: reason code recorded, and a named surviving test in `covered-by:` for every reason that is not a no-behavior code.
7. For each removed seam, cite the repo-wide reference search showing no non-test caller **and** state that no active OpenSpec change specifies a consumer (name the changes you checked, or `openspec list`).
8. Confirm assertion contract: `check_test_contract.py --base <B1>` exits 0 for the simplify range (characterization commits may add tests, prune commits may remove them; simplify commits must not mutate expectation bodies).
9. Confirm scope: `check_scope.py --base <B1>` exits 0, or `--allow-codemod` with the codemod named in the report.
10. Confirm `git diff <B1>..HEAD --stat` (or report) shows intentional surface only — no unrelated drive-by files.
11. Confirm the review artifact: `simplify_review.py validate <artifact>` exits 0 (the Review role ran it, and the Apply role re-ran it before touching anything), and the ledger attached in (5) is `simplify_review.py render-ledger` output, not a hand-written file.
12. Confirm no finding's `fence.verdict` or `disposition` differs from the artifact the Review role validated, and list every finding the Apply role reported skipped, with its reason.
