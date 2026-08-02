---
name: simplify
description: >
  Review changed code for reuse, quality, and efficiency, then apply low-risk
  simplifications that preserve behavior exactly. Requires a coverage gate and
  characterization tests when the surface is unpinned; dual-run verification
  proves the suite stays green without changing test expectations.
category: Engineering Methodology
tags: [refactor, simplification, code-quality, review, characterization, isomorphic]
triggers:
  - "simplify"
  - "simplify the code"
  - "review for simplification"
  - "clean this up"
  - "refactor for clarity"
  - "code-simplify"
  - "isomorphic refactor"
  - "reduce duplication without changing behavior"
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

This skill is **read → pin → edit**: it reviews first, applies a **coverage gate**, writes characterization tests when needed, gates each candidate against Chesterton's Fence, applies changes one pattern at a time, and dual-runs the suite. Large surface areas are deferred (Rule of 500).

**Primary invoke:** `/simplify`  
**Invocation mode:** **manual only** — operators (or explicit human request) run this skill. Autopilot and implement-feature do **not** auto-run simplify by default.

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
| Cleanup mixed into an in-progress feature | `NOTICED BUT NOT TOUCHING:` + later `/simplify` |
| Code is already clear | Stop — do not simplify for its own sake |

## Scope

- Run on the current diff, a specified file/module, or a tech-debt finding ID.
- Production edits only after the coverage gate passes.
- Characterization commits may add tests; simplify commits must not change assertion **bodies**.
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
2. **What problem does it still solve?** Rate limits, retries, ordering, error masking, security boundaries — load-bearing fences stay.
3. **What non-obvious invariants does it preserve?** Idempotency, transactional boundaries, timezone normalization, injection defense.

If (2) is "nothing — reason is gone," the fence may come down. Otherwise leave it (or document why in a `# CHESTERTON: kept because …` comment).

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

## Workflow

### 0. Scope

Identify target: `git diff`, path, module, or tech-debt finding ID. Record the **baseline SHA** (tip before any simplify production edit; after characterization commits if those land first).

### 1. Understand (Chesterton's Fence)

Blame, callers, existing tests, edge cases. Read project conventions (AGENTS.md / CLAUDE.md / neighboring modules).

### 2. Coverage gate

Pin or characterize (see above). Run characterization tests and confirm green on baseline.

### 3. Candidate list

List opportunities by pattern. Drop any that fail Chesterton's Fence; note fences kept.

### 4. Rule of 500

Group remaining work. Automate, split, or escalate if over budget.

### 5. Apply incrementally

For each remaining candidate:

1. Make **one** simplification.
2. Run the targeted suite (then broader suite if targeted is green).
3. If red → revert that simplification; re-evaluate.
4. Commit: `refactor(<scope>): <pattern> — <brief>` (e.g. `refactor(parser): extract guard clauses from validate_input`).

Never mix `feat` / `fix` with simplify polish in the same commit.

### 6. Dual-run verify

```bash
# Recommended mechanical dual-run (writes simplify-report.json by default).
# Prefer an absolute interpreter so detached worktrees resolve tools;
# the script also symlinks .venv / node_modules from the main repo when present.
python3 "<skill-base-dir>/scripts/verify_behavior_preservation.py" \
  --baseline <baseline-sha> \
  --test-cmd "skills/.venv/bin/python -m pytest -q"   # or npm test / project-specific

# Assertion contract on the simplify range (should be clean for expectation bodies).
# --base MUST be the tip AFTER characterization commits.
python3 "<skill-base-dir>/scripts/check_test_contract.py" --base <baseline-sha>
python3 "<skill-base-dir>/scripts/check_scope.py" --base <baseline-sha>
```

Manual equivalent: run the same suite on `<baseline-sha>` and on `HEAD`; both must pass.

### 7. Report

Summarize: patterns applied, fences kept, characterization tests added, dual-run evidence (commands + exit codes or report path), Rule of 500 status.

## Script helpers

Scripts live in `<skill-base-dir>/scripts/` (installed copy under `.claude/skills/simplify/scripts/` or `.agents/skills/simplify/scripts/`). They use only the standard library plus `git`.

| Script | Purpose | Exit |
|---|---|---|
| `check_scope.py` | Diff line/file counts vs Rule of 500 | `0` ok, `2` over limit without `--allow-codemod`, `1` error |
| `check_test_contract.py` | Detect assertion/expect body changes in test paths | `0` ok, `2` contract break, `1` error |
| `verify_behavior_preservation.py` | Run tests at baseline and HEAD in detached worktrees; write JSON report | `0` both green, `2` failure, `1` error |

`check_test_contract.py` expects `--base` at the tip **after** characterization commits. Within that range, any `+/-` assertion line (including deleted test files) is a contract break.

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
| Local complexity / nesting / naming / local dup | Stay on `/simplify` |
| Tech-debt hub / high coupling / large redesign | `/plan-feature` |
| Dead public API / multi-consumer removal | `/deprecation-and-migration` |
| Measured perf bottleneck | `/performance-optimization` |
| Bug or missing behavior | `/test-driven-development` + fix (not simplify) |

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

## Red Flags

- Production simplify commits without a coverage-gate decision (existing pins **or** new characterization tests).
- A simplify PR that changes test assertion bodies to go green.
- Diff over 500 lines or 5 files with no codemod / split plan (Rule of 500 violation).
- Removed code with no blame / caller investigation recorded.
- `feat`/`fix` mixed into the same commit as a clarity refactor.
- Autopilot or implement silently running simplify without operator request.
- Inlined helper that deleted a comment documenting a non-obvious invariant (fence lost).
- Isomorphic extract landed without tests covering all rewritten call sites.

## Verification

1. Cite each pattern catalog entry applied in the PR/report.
2. For removed/renamed/inlined constructs, cite blame or introducing commit (Chesterton's Fence).
3. Confirm coverage gate: either list existing pinning tests **or** show the characterization commit (`test(...): pin behavior…`) that is green on baseline.
4. Confirm dual-run: suite green on baseline SHA and on HEAD (attach `simplify-report.json` from `verify_behavior_preservation.py` when used).
5. Confirm assertion contract: `check_test_contract.py --base <baseline>` exits 0 for the simplify range (characterization commits may add tests; simplify commits must not mutate expectation bodies).
6. Confirm scope: `check_scope.py --base <baseline>` exits 0, or `--allow-codemod` with the codemod named in the report.
7. Confirm `git diff <baseline>..HEAD --stat` (or report) shows intentional surface only — no unrelated drive-by files.
