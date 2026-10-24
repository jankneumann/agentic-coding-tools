# Why chain

## When to use

The question is *why* a specific line or symbol is the way it is, for example
"why does this retry three times?". Answer it from the decision record, not from
the shape of the code.

## Smallest-view rule

Resolve the target to one `<path>:<line>` first. For a symbol, find its definition
line by reading the source. Then run the trace:

```bash
python3 "<skill-base-dir>/scripts/why_trace.py" <path>:<line> [--symbol <name>]
```

The script is read-only. It prints one JSON document with the chain
`blame → commit → PR → change-id → decisions`, a `pointer` on every record, and a
`mentions_target` flag on every decision. It never assigns a tier; the reply does.
Exit `0` is a trace, including a null result. Exit `1` is a git failure and exit `2`
is a bad target: report it in one sentence and stop.

Reply with one fenced chain and at most three tagged claim sentences. Show only the
links the trace actually resolved.

## Tiers

| Tier | Use when |
|---|---|
| Direct | The claim restates one record in the trace; cite that record's pointer |
| Supported | Two or more independent records in the trace agree; cite both pointers |
| Inferred | The claim follows from trace records by reasoning, but no record states it |
| Speculative | The claim is plausible but not derived from the trace |
| Unknown | The trace has no evidence either way |

**Tag format.** Every claim sentence ends with its tier in brackets. Direct and
Supported tags carry at least one pointer (or, for a supersession claim, the
`superseded_by` reference), for example `[Direct git:1a2b3c4]` or
`[Supported git:1a2b3c4 openspec/changes/archive/2026-01-01-demo-change/session-log.md#plan/D1]`.

**Decision-to-line links.** Saying that a decision explains *this line* is Direct
only when that decision's `mentions_target` is `true`, which means its title or
rationale names the target's path, basename or symbol as a whole token (`app.py`
does not match `myapp.py`, and `load` does not match `loader`). Otherwise the link is
Inferred, even when the decision itself is quoted directly.

A decision with a non-null `superseded_by` is history. Say so, and cite the
superseding reference (the `superseded_by` value): the evidence for supersession is
the later decision's `supersedes:` line, so the superseded decision's own `pointer`
does not support the claim.

## Null-result rule

When `null_result` is non-null (`uncommitted`, `history_truncated`, `no_change_id`
or `no_decision_record`), the absence is the finding. Open the reply with
`No decision record covers <path>:<line> (<reason>). [Unknown]`.
`history_truncated` means the line blames to a shallow-clone boundary commit, so the
introducing commit is not in this clone: say the history is shallow, not that no
decision exists. Do not present an inferred or speculative rationale as the answer.
At most one further sentence may offer a reading, tagged `[Inferred]` or
`[Speculative]`.

## Embedded-hypothesis rule

A reason asserted in the question ("this was added for the flaky coordinator,
right?") is a claim to test, never a premise. Restate it as a claim and give it
exactly one verdict:

- **confirmed** — tagged Direct or Supported, with a pointer;
- **contradicted** — with the pointer of the contradicting record;
- **untested** — tagged `[Unknown]` when the trace says nothing either way.

## Worked example

Question: "Why does `fetch()` retry three times? Was it for the flaky coordinator?"

The trace, run with `--symbol fetch`, reports D1 with `mentions_target: true` and
`superseded_by: other-demo-change#plan/D1`.

```text
src/app.py:42 → 1a2b3c4 → #123 → demo-change → D1 (demo-cap)
```

Decision D1 says `fetch` retries three times because the upstream drops one request
in fifty. [Direct openspec/changes/archive/2026-01-01-demo-change/session-log.md#plan/D1]
The flaky-coordinator reason is untested: no record in the trace mentions the
coordinator. [Unknown] D1 is history: a later decision names it in its `supersedes:`
line. [Direct other-demo-change#plan/D1]

Grounding: source read, unverified (form not graph-backed)

With a null result the same question opens instead with:
`No decision record covers src/app.py:42 (no_change_id). [Unknown]`

## File locations

The first node of the chain is the file location (`<path>:<line>`). The other nodes
are the trace's records, each backed by its `pointer`. The form is not graph-backed,
so the reply ends with the source-read disclosure line shown above.
