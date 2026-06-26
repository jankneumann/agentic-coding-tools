# HTML Artifacts as a Human↔Agent Feedback Channel (lavish-axi analysis)

**Status**: Draft / research
**Created**: 2026-06-26
**Source repos analyzed**: [`kunchenguid/lavish-axi`](https://github.com/kunchenguid/lavish-axi), [`kunchenguid/axi`](https://github.com/kunchenguid/axi)
**Theme**: agent-ergonomic tooling, human-in-the-loop review, OpenSpec plan review

## Executive synthesis

`lavish-axi` is a reference implementation of the bet this repo has been making informally:
**HTML is becoming the interchange format between coding agents and humans.** Its tagline —
"HTML is the new markdown" — names the same intuition behind our own interest in using rich
HTML artifacts as a language of communication with the agent.

The tool is actually two separable contributions, and we can adopt either independently:

1. **AXI** — a design philosophy for *agent-facing CLIs* that treats token budget as a
   first-class constraint (TOON output, minimal default schemas, pre-computed aggregates,
   ambient SessionStart context, next-step disclosure). Published benchmarks claim ~50% lower
   cost and roughly half the turns versus MCP for browser/GitHub tasks. This is directly
   applicable to our existing agent-facing CLIs (coordinator bridge, `vendor-status`,
   `agent-metrics`, the `validate-*` family) with **no HTML involved**.

2. **Lavish** — a local-first browser review loop where an agent writes an HTML artifact, the
   human **annotates specific DOM elements / text ranges**, and feedback drains back to the
   agent through a **long-poll**. The key innovation is *targeted* feedback: instead of the
   human describing where a problem is in prose ("the third bullet under approach B…"), they
   click the element and the agent receives surgical coordinates
   `{selector, tag, text, prompt, target}`.

The strategic fit is high because our most expensive human-facing artifact — the OpenSpec
proposal (`plan-feature` → `iterate-on-plan` → `parallel-review-plan`) — is exactly the
"wall of markdown plan" Lavish was built to replace, and our `prototype-feature` skill already
implements "human pick-and-choose feedback for convergence-aware refinement" but lacks the UI
surface that Lavish provides.

## How lavish-axi works

```
agent writes .lavish/plan.html
  → npx -y lavish-axi <file>        # opens browser, runs in-iframe layout audit
  → npx -y lavish-axi poll <file>   # agent long-polls; "leave it running, never kill it"
  → human clicks an element, types a comment, sends (or uses native controls)
  → poll returns annotations + layout_warnings
  → agent edits HTML, re-polls with --agent-reply "<message>"
  → repeat → npx -y lavish-axi end <file>
```

Mechanisms worth studying:

| Mechanism | What it does | Why it is reusable here |
|---|---|---|
| **Element annotation** | Human selects element/text range → `{uid, selector, tag, text(≤240), prompt, target}` | Surgical feedback coordinates instead of prose; a clean structured-feedback schema |
| **Long-poll protocol** | Agent blocks on `poll`; queued feedback survives disconnects | Clean async human↔agent handoff that fits our coordinator's message model |
| **Layout gate** | In-browser audit (horizontal overflow, clipping, text overlap) masks the artifact until it renders cleanly; `{selector, kind, overflowPx, viewportWidth, severity}` warnings go back to the agent | Self-correcting render quality *before* the human ever looks |
| **`data-lavish-action` + native controls** | Radios/checkboxes/inputs/buttons interactive automatically; custom actions via data-attrs; `window.lavish.queuePrompt()`; `data-lavish-question`/`queueKey` deduplicate answers | Structured *input collection*, not just free-text comments |
| **Playbooks** | Per-artifact-type guidance (`diagram`, `table`, `comparison`, `plan`, `code`, `input`, `slides`) loaded before generation | Teaches the agent *good* visualization; avoids AI-slop HTML |
| **File-path session identity** | Sessions keyed by canonical file path, no opaque IDs | Portable, git-compatible, agent-friendly |
| **SessionStart hook** | `lavish-axi setup hooks` feeds open sessions + playbooks as ambient context | Slots into our existing heavy SessionStart-hook usage |

### The AXI principles (CLI design, no HTML required)

1. Token-efficient output (TOON, ~40% savings vs JSON)
2. Minimal default schemas (3–4 fields/item, not 10) with a `--full` escape hatch
3. Content truncation with size hints
4. Pre-computed aggregates (counts/statuses) to eliminate round-trips
5. Definitive empty states ("0 results", never ambiguous silence)
6. Structured errors & exit codes; idempotent mutations; no interactive prompts
7. Ambient context (opt-in SessionStart) before on-demand skills
8. Content-first (live data when run with no args, not a help wall)
9. Contextual disclosure (next-step suggestions after each output)
10. Consistent, concise per-subcommand help

## What our repo already covers

We are unusually well positioned: we already emit structured artifacts and have the review
scaffolding Lavish assumes.

- **Plan/review loop**: `plan-feature`, `iterate-on-plan`, `parallel-review-plan` produce and
  critique OpenSpec proposals — today as markdown.
- **Variant feedback**: `prototype-feature` already dispatches N variants and captures
  human pick-and-choose feedback — but without an annotation surface.
- **Browser tooling**: `browser-testing-with-devtools` already drives Chrome DevTools MCP and
  `playwright-validator` already runs deployed frontends — we can run a layout/render gate today.
- **UI authoring**: `frontend-ui-engineering` already encodes accessible, non-AI-slop HTML
  patterns — the same goal as Lavish's playbooks.
- **Ambient context**: heavy SessionStart-hook usage already in place.

What we do *not* have is (a) a *targeted* feedback primitive (click-an-element → structured
comment) and (b) HTML treated as a first-class review surface for plans rather than prose.

## Opportunities, ranked by leverage

1. **Visual OpenSpec proposals (highest leverage).** Add an HTML-artifact rendering step to
   `plan-feature` so a proposal ships as both `proposal.md` and a reviewable
   `.lavish/proposal.html` (goal → current state → approach → task DAG). The human annotates
   the specific wrong task/claim *before* `implement-feature` runs — shortening our most
   expensive loop (re-planning after implementation has begun). The Lavish "plan" playbook's
   directive ("verify each claim against the codebase before presenting it as fact… self-
   contained enough that another developer can fully implement it") already restates our
   OpenSpec philosophy.

2. **Annotation as a coordinator message type.** Adopt `{selector, tag, text, prompt, target}`
   as a `human_annotation` message so targeted feedback flows through the coordinator the same
   way structured tasks do. `parallel-review-*` could then consume element-anchored feedback
   instead of free-form text.

3. **AXI output audit of our agent-facing CLIs (no HTML).** Apply the 10-point AXI rubric to
   the coordinator bridge, `vendor-status`, `agent-metrics`, and `validate-*`. Pure
   token-cost/accuracy win, independent of the artifact loop; a `bug-scrub`-style sweep.

4. **Render/layout gate for HTML we already emit.** Pair the audit-before-show pattern with
   `browser-testing-with-devtools` so reporting skills (`agent-metrics`, `bug-scrub` reports)
   never ship broken-rendering artifacts to a human.

5. **Structured-input artifacts for complex decisions.** For `explore-feature` /
   `prioritize-proposals`, render a comparison surface with native radios/checkboxes and a
   single submit, as a richer alternative to one-shot `AskUserQuestion` prompts when the human
   is choosing among many options with tradeoffs.

## Adopt vs. borrow

Two viable strategies; the spike below defers the choice until we have felt the loop.

- **Adopt the tool directly** — `npx -y lavish-axi` is zero-install and MIT-licensed; fastest
  path to the annotation loop. Cost: an external Node dependency in the skill runtime and a
  protocol we do not own.
- **Borrow the patterns natively** — reimplement the annotation schema, layout gate, and AXI
  output principles inside our coordinator/skills. More work, fully owned, integrates with the
  Postgres coordinator.

## Recommended next step

Run a **throwaway spike**: wire `lavish-axi` into `plan-feature` for one real proposal and
feel the round-trip, rather than designing the protocol up front. It is near-zero cost
(`npx -y`, MIT) and ships a Claude Code SessionStart hook that fits our existing setup. Capture
findings, then choose adopt-vs-borrow and (if we proceed) promote opportunity #1 into a real
OpenSpec change via `plan-feature` / `plan-roadmap`.

The single most portable idea, even if we adopt nothing else, is standardizing on the
annotation tuple `{selector, tag, text, prompt, target}` as a coordinator feedback primitive —
it gives every review skill a structured "the human pointed at *this* and said *that*."

## Sources

- README, `SKILL.md`, `src/` — https://github.com/kunchenguid/lavish-axi
- AXI design principles — https://github.com/kunchenguid/axi
- "Use visual plans, not walls of markdown" (Peter Yang) —
  https://www.threads.com/@petergyang/post/DZU_B_9lCGM/
- Trendshift stats — https://trendshift.io/repositories/28108
