---
name: simplify
description: Review changed code for reuse, quality, and efficiency, then apply low-risk simplifications that preserve behavior exactly.
category: Engineering Methodology
tags: [refactor, simplification, code-quality, review]
triggers:
  - "simplify"
  - "simplify the code"
  - "review for simplification"
  - "clean this up"
  - "refactor for clarity"
user_invocable: true
---

# Simplify

Inspect a focused diff or module for **behavior-preserving** simplifications: dead code, deep nesting, long functions, premature abstractions, generic names. The goal is fewer moving parts, not stylistic preference.

This skill is **read-then-edit**: it reviews first, names the candidate simplifications, gates each one against Chesterton's Fence, and only then makes changes. Simplifications that span large surface areas are deferred to automation (Rule of 500).

## Scope

- Run on the current diff, a specified file, or a specified module.
- Touches code only — does not modify tests' assertions, public APIs, or behavior.
- Single-PR changes only. Cross-cutting refactors are not in scope (see Rule of 500).

## Chesterton's Fence — Pre-Simplification Check

Before removing or refactoring any non-trivial piece of code, answer all three questions. If any answer is "I don't know," **stop and investigate** — do not simplify.

1. **Why does this exist?**
   - Run `git blame` on the relevant lines and read the introducing commit message.
   - `grep` for callers / references — what else depends on this?
   - Search the test suite — what scenarios pin this behavior?
2. **What did it solve that we still need to solve another way?**
   - If the original problem still exists (rate limiting, retry, error masking, ordering guarantee), the fence is load-bearing. Removing it without an equivalent replacement is a regression in disguise.
3. **What invariants does it preserve that aren't obvious?**
   - Examples: idempotency of a callback, ordering of effects, transactional boundary, SQL injection defense, time-zone normalization, CSRF token rotation.
   - Invariants that the type system doesn't enforce are exactly the ones simplifications break.

If all three questions have clear answers and the answer to (2) is "nothing — the original reason is no longer relevant" then the fence is safe to remove. Otherwise: rewrite the explanation as a code comment and **leave the fence standing**.

## Rule of 500

Simplifications that would touch **more than 500 lines** OR **more than 5 files** SHALL NOT be done by hand. Manual large-scale refactors are error-prone, hard to review, and tend to ship regressions in the long tail of edge cases.

When the candidate change exceeds the 500/5 threshold:

- **(a) Automate it.** Use a codemod, AST-based tool (jscodeshift, libcst, ts-morph), or carefully tested `sed`/`grep` script. The automation itself is reviewable, and the diff it produces is mechanical.
- **(b) Split it.** Identify a natural seam (one module, one bounded context, one pattern occurrence) and ship that as a single PR. Repeat across the rest of the surface in subsequent PRs.

If neither (a) nor (b) is feasible, the simplification is too risky for this skill — escalate to a planning step (`/plan-feature`) so the work gets a proposal, design, and review gates.

## Pattern catalog

Six common simplification patterns that this skill is allowed to apply (subject to Chesterton's Fence and Rule of 500):

- **Deep nesting → guard clauses.** Three or more levels of `if`/`for`/`try` nesting is a smell. Invert the conditions and return early. The body of the function then reads top-to-bottom as the happy path.
- **Long functions → extract helpers.** Functions over ~50 lines or with multiple responsibilities should be split into named helpers. Each helper does one thing; the original function becomes a short outline of the algorithm.
- **Nested ternaries → if/else or lookup table.** A ternary inside a ternary is unreadable. Convert to an `if/elif/else` chain, or — if the branching is value-based — a dict/map lookup.
- **Boolean flag parameters → split functions.** A function with a `bool` parameter that switches its behavior is two functions wearing one name. Split into `do_thing()` and `do_thing_with_X()` (or whatever distinguishes the two paths). Bonus: the call sites become self-documenting.
- **Generic names (`data`, `info`, `obj`, `temp`, `result`, `value`) → domain names.** Names that don't say *what kind of thing* the variable is force every reader to re-derive the type. Replace with the domain term: `user_record`, `pending_invoice`, `parsed_request`.
- **Premature abstractions (single-implementation interface, framework-of-one) → inline.** An interface with one implementation, a base class with one subclass, a factory that always returns the same type — these are abstractions paying their cost without earning their keep. Inline them; let the abstraction reappear when a second implementation actually arrives.

## Workflow

1. **Identify candidates.** List the simplification opportunities you see in the target diff/file/module, grouped by pattern from the catalog above.
2. **Apply Chesterton's Fence** to each candidate. Drop any that fail the three-question check; record the reason in a `# CHESTERTON: kept because <reason>` comment if the reasoning isn't already obvious.
3. **Apply Rule of 500.** Group remaining candidates by surface area. If the cumulative diff exceeds 500 lines or 5 files, stop and either automate or split.
4. **Make the changes.** One simplification per commit, with a conventional commit message naming the pattern (e.g., `refactor(parser): extract guard clauses from validate_input`).
5. **Verify behavior preservation.** Run the test suite. If it changes — either tests OR behavior — back out and re-evaluate. The skill never modifies behavior.

## Common Rationalizations

| Rationalization | Why it's wrong |
|---|---|
| "I don't need to read git blame — the code is obviously dead" | "Obviously dead" code is the #1 source of subtle regressions. The blame log frequently reveals a comment like "DO NOT REMOVE — handles legacy clients on /v1". Run blame; it's free. |
| "It's only 600 lines — I can do it by hand carefully" | The Rule of 500 isn't about your skill, it's about reviewer attention. A 600-line manual diff has tail-end edge cases nobody will catch. Automate or split. |
| "This abstraction will pay off when we add the second implementation" | The second implementation may never arrive, and if it does, its requirements will reshape the abstraction anyway. Inline now; abstract later when the shape is real. |
| "Renaming `data` to `user_record` is a stylistic preference, not a simplification" | It's a *cognitive load* simplification: every reader saves a re-derivation step. The pattern catalog lists it because it pays off in proportion to read frequency. |
| "The function is 80 lines but it's all one algorithm — splitting hurts readability" | If it's truly one algorithm, name the steps as helpers — the outline becomes the readable artifact. If splitting hurts readability, the steps weren't really steps; revisit Chesterton's Fence question 1. |

## Red Flags

- A simplification PR that also changes test assertions (tests should pass unchanged; if they don't, behavior shifted).
- A diff over 500 lines or touching more than 5 files with no codemod / automation reference (Rule of 500 violation).
- A removed function with no `git blame` investigation recorded in the PR description (Chesterton's Fence question 1 skipped).
- A renamed-only commit mixed with a behavior change (Rule 1 from `implement-feature` violation — split the commits).
- A "while I'm in here" simplification adjacent to the actual work but outside the original scope (use `NOTICED BUT NOT TOUCHING:` from `implement-feature`).
- An inlined abstraction whose deletion removed a comment explaining a non-obvious invariant (the comment was the fence — losing it is the regression).

## Verification

1. Cite the pattern catalog entry that justifies each simplification in the PR description.
2. For every removed/renamed/inlined construct, link to the `git blame` line(s) or commit that introduced it, demonstrating the Chesterton's Fence check was performed.
3. Confirm the diff size: `git diff main...HEAD --stat | tail -1` shows ≤ 500 lines and ≤ 5 files, OR the PR description names the codemod / automation that produced the diff.
4. Confirm `git diff main...HEAD -- '*test*'` shows no changes to test assertions — only test renames or restructurings consistent with the simplification.
5. Confirm the test suite passes on the simplification commit AND on the immediately preceding commit (behavior preservation, not just final-state correctness).
