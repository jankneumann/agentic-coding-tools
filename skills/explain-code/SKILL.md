---
name: explain-code
description: Answers a narrow question about how a specific piece of code works or connects with the smallest visual form that makes the point — grounded in the architecture graph when fresh. Use when the user asks how code flows or relates; use codebase-atlas for whole-repository views.
category: Architecture
tags: [architecture, visualization, explanation, mermaid, grounding]
user_invocable: true
related:
  - codebase-atlas
  - explore-feature
  - refresh-architecture
---

# Explain Code

Answer a narrow question about the code with a small picture and a few sentences.
Catalogue and brevity rules are adapted from humanlayer's MIT-licensed `show-me`
skill; grounding and coverage disclosure are this repository's addition.

**Deferred in v1:** no HTML files, no writing any file, no browser.

## Rules

1. Skip the preamble; keep prose brief (≤3 sentences beside the visual).
2. Pick the **smallest** catalogue form that makes the key point.
3. Include only the calls, files, and boundaries the current question needs.
4. Place each visual next to the short text it supports.
5. Every **sketching** reply ends with exactly one `Grounding:` line (see
   `references/grounding.md`). Clarification and whole-repo redirects do not.

## Catalogue

| Form | When | Reference |
|---|---|---|
| Call tree | Control flow / who calls whom | `references/call-tree.md` |
| Component tree | UI / module structure with paths | `references/component-tree.md` |
| File tree | Responsibility layout | `references/file-tree.md` |
| Sequence | Interaction over time (Mermaid) | `references/sequence.md` |
| Structural diff | What changed in shape | `references/structural-diff.md` |
| Why chain | Why code is like this (decision record) | `references/why.md` |

## Grounding (summary)

Before a **call tree**, check freshness with
`python3 "<skill-base-dir>/../refresh-architecture/scripts/run_architecture.py" --check`
(exit `0` only = fresh). When fresh, obtain callers/callees from
`python3 "<skill-base-dir>/../codebase-atlas/scripts/build_atlas.py" --tree …`.
Never run `--ensure` or the analysis pipeline. Full contract, disclosure forms,
ungrounded reasons, and exemptions: `references/grounding.md`.

Whole-repository questions → name `/codebase-atlas` and stop (no `Grounding:` line).

## Why mode

For "why is this code like this?", resolve the target to `<path>:<line>` and run the
read-only trace (blame → commit → PR → change-id → decisions):
`python3 "<skill-base-dir>/scripts/why_trace.py" <path>:<line> [--symbol <name>]`.
Reply with one fenced why chain and at most three claim sentences, each ending in a
bracketed tier tag: **Direct**, **Supported**, **Inferred**, **Speculative** or
**Unknown**. Direct and Supported tags cite a trace `pointer`; a decision explains
*this line* as Direct only when its `mentions_target` is true.

- **Null-result rule:** a non-null `null_result` is the finding. Lead with
  `No decision record covers <path>:<line> (<reason>)` tagged `[Unknown]`; never
  present an inferred rationale as the answer.
- **Embedded-hypothesis rule:** a reason asserted in the question is restated as a
  claim with one verdict (confirmed, contradicted or untested), never a premise.

Tiers, tag format and a worked example: `references/why.md`. The reply ends with
`Grounding: source read, unverified (form not graph-backed)`.

## Common Rationalizations

| Rationalization | Why it's wrong |
|---|---|
| "I'll sketch from memory — the graph is probably fine" | Ungrounded trees look identical to grounded ones; run `--check` and disclose. |
| "A whole-repo atlas page answers a narrow question better" | That is `/codebase-atlas`'s job; this skill stops and redirects. |
| "I'll refresh the graph myself so the answer is grounded" | The skill never runs `--ensure` or the pipeline; disclose ungrounded instead. |
| "No record covers it, but the reason is obvious" | The absence is the answer; lead with it, tagged `[Unknown]`. |

## Red Flags

- A sketching reply with no final `Grounding:` line.
- A call tree that invents symbols not returned by `--tree` after a fresh check.
- The skill invoked `--ensure`, created or modified a file, or opened one for the user.
- A why reply with an untagged claim, or one that adopts the question's hypothesis.

## Verification

1. Confirm the catalogue form matches the question and cites a `references/*.md`.
2. Confirm sketching replies end with exactly one `Grounding:` line (or an exempt clarification/redirect).
3. Confirm sibling invocations use `<skill-base-dir>/../codebase-atlas/` and `<skill-base-dir>/../refresh-architecture/`.
4. Confirm a why reply tags every claim, cites a pointer for Direct and Supported, and leads with any null result.
