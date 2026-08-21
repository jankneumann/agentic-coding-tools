---
name: audit-choices
description: Independent, read-only audit of implementation-time decisions made where the spec was silent, producing a schema-valid choices ledger
category: Git Workflow
tags: [openspec, review, audit, decisions, read-only]
triggers:
  - "audit choices"
  - "audit decisions"
  - "choices ledger"
requires:
  coordinator:
    required: []
    safety: [CAN_GUARDRAILS]
    enriching: [CAN_HANDOFF, CAN_AUDIT]
---

# Audit Choices

Produce a per-change **choices ledger** (`choices.json` + `choices.md`) recording implementation-time decisions made where the spec, design, or tasks were silent — the "we had to pick something and nobody wrote down why" gap that session-log `Decisions` bullets only capture when the implementer remembers to report them. This skill is read-only end to end: it never touches `session-log.md`, `docs/decisions/`, or any source file, and it never blocks a workflow regardless of what it finds.

## Arguments

`$ARGUMENTS` — one of:

- `<change-id>` — audit an OpenSpec change (e.g. `add-decision-choices-ledger`). The audited range defaults to the change's base commit through `HEAD`.
- `<base-sha>..<head-sha>` — audit an explicit commit range standalone, with no OpenSpec change directory involved. `change_id` in the resulting ledger is recorded as `range:<base>..<head>`.

## Read-Only Contract

**The auditor MUST NOT modify any file outside `openspec/changes/<change-id>/choices.json` and `choices.md`.** It MUST NOT write to `session-log.md`, `docs/decisions/`, or any source file — those are producer-owned and CI-diff-enforced (`make decisions`), and a write from this skill would corrupt the deterministic drift gates those producers depend on. The only writer in this skill is `choices_ledger.write_ledger_pair()`; nothing else in `skills/audit-choices/scripts/` opens a file for writing.

This is verified mechanically, not just by convention: `skills/tests/audit-choices/test_readonly_posture.py::test_writes_confined_to_ledger_pair` snapshots a fixture repo's working tree before and after a full driver run and asserts the diff is exactly the ledger pair.

## Why Independence Is the Point

This is **not** a self-review step. The auditor is dispatched as a separate sub-agent from whichever agent implemented the change — the same posture as `parallel-review-implementation`, but judging intent rather than code quality. An implementer that reports its own decisions can only report the ones it remembers making; the highest-value signal this skill produces is the decision the implementer *didn't* report at all (`self_reported: false`). A self-review pass structurally cannot produce that signal — it would have to notice its own blind spot. Dispatching a second, independent read of the same diff is the only way to catch it.

## Evidence Bundle

`skills/audit-choices/scripts/collect_evidence.py` assembles the auditor's entire read-only input — this is the *only* context the auditor sees; it does not get repo write access or a live shell:

- `git log` / `git diff --stat` / `git diff --name-only` over the audited range (commits and touched files — this list doubles as the allow-list the driver later checks provenance against)
- Excerpts of `proposal.md`, `design.md`, spec deltas (`specs/**/spec.md`), `session-log.md`, and `impl-findings.md`, when each is present
- `known_decisions`: every `Decisions` bullet already parsed out of `session-log.md` (via `session-log`'s own `phase_record.parse_markdown`, not a second parser), with the `<change-id>#D<n>` (or phase-qualified `<change-id>#<phase-slug>/D<n>`) ref each would resolve to

Run it standalone to preview what the auditor will see:

```bash
python3 skills/audit-choices/scripts/collect_evidence.py \
  --change-id <change-id> --base-sha <base> --head-sha <head> --repo-root .
```

## Dispatching the Auditor

Dispatch **one** independent sub-agent (provider-neutral dispatch path where available, same mechanism as `parallel-review-implementation`) with the evidence bundle as its entire input and this contract:

- Read-only. No tool that can write a file, run a shell command that mutates the tree, or push a commit.
- For each implementation-time decision found in the diff, return a candidate entry with:

  | Field | What it holds |
  |---|---|
  | `choice` | Headline of the decision the implementation embodies |
  | `scenario` | A concrete scenario walked end to end in plain language — must stand alone without the diff or transcript |
  | `gap` | What the spec/design/tasks left unspecified that forced this choice |
  | `reach` | What this choice constrains or enables for future work |
  | `verdict` | `sound`, `unsound`, or `needs-user` |
  | `verdict_rationale` | Why that verdict |
  | `confidence` | The auditor's own confidence in its verdict: `low`, `medium`, or `high` |
  | `provenance.commits` / `provenance.files` | The commits and files this decision is grounded in — **must** be drawn from the evidence bundle's `commits`/`files` lists, not invented |

  The auditor does **not** compute `stable_id`, `self_reported`, or `session_log_ref` — those are script-side, deterministic, and would only introduce a second source of truth if the LLM guessed at them (see D7 below).

## Script-Side Validation and Persistence (D7)

The sub-agent's candidate entries are data, never instructions, and they are never trusted at face value. `skills/audit-choices/scripts/run_audit.py` is the only thing that persists a ledger, and it does so in this order:

1. **Drop hallucinated provenance.** `choices_ledger.filter_valid_provenance()` drops any candidate citing a commit or file absent from the audited range's known commits/files — the guard against an auditor inventing a plausible-sounding but nonexistent citation (design.md, Risks: "Auditor hallucinating decisions").
2. **Resolve the cross-reference deterministically.** For every surviving candidate, `collect_evidence.resolve_self_reported()` matches the candidate's `choice` headline against `known_decisions` by keyword overlap — never by trusting anything the auditor said about self-reporting. A match sets `self_reported: true` and the matching `<change-id>#D<n>` ref; no match sets `self_reported: false` with no ref.
3. **Compute `stable_id`.** `choices_ledger.compute_stable_id()` hashes the normalized `(choice headline, primary file set, gap text)` — content-derived, not generated by the auditor, so re-auditing an unchanged decision reproduces the same id (D3) and a changed gap or file set produces a different one.
4. **Schema-validate.** `choices_ledger.split_schema_valid()` drops anything still missing a required field or carrying a bad enum value.
5. **Persist idempotently.** `choices_ledger.write_ledger_pair()` merges surviving entries into any existing `choices.json` by `stable_id` (unchanged decisions update in place rather than duplicating — skill-workflow spec, "Re-audit is idempotent"), validates the full document against `openspec/schemas/decision-choices.schema.json`, writes it, then renders `choices.md` from it — least-confident-first, `needs-user` before `unsound` before `sound` within equal confidence.

## Never Blocks (D6)

`run_audit()` never raises. An internal error (missing repo, unreadable schema, a git failure) is caught and reported as `AuditRunResult(ok=False, error=...)` rather than propagated. Adverse verdicts — a ledger full of `unsound` and `needs-user` entries — are an ordinary, successful run: `ok=True` regardless of what the entries say. The CLI wrapper (`run_audit.py`'s `_cli()`) always returns exit code `0`. No workflow step is ever halted by this skill itself; `needs-user` entries reach a human only through the existing `validate-feature` / `cleanup-feature` gates, the same way deferred tasks already surface there — this skill does not introduce a new blocking gate.

## Steps

1. Resolve the audited range: for a change-id argument, the base is the change's earliest commit (or an explicit `--base-sha` override) and the head is `HEAD`; for an explicit range argument, use it as given.
2. Run `collect_evidence.py` to assemble the evidence bundle.
3. Dispatch the one independent auditor sub-agent with that bundle as its entire input (see "Dispatching the Auditor" above). Capture its candidate entries as JSON.
4. Run `run_audit.py` (or call `run_audit.run_audit()` directly) with the candidates, the audited range, and a `run_id`. It performs validation, cross-reference resolution, and persistence per "Script-Side Validation and Persistence" above, and always returns/exits successfully regardless of outcome.
5. Report what was written: entry count, dropped-candidate count, and the highest-priority (least-confident, most-adverse) entries from the top of the rendered `choices.md`.

## Output

- `openspec/changes/<change-id>/choices.json` — schema-valid against `openspec/schemas/decision-choices.schema.json`, carrying the six-field artifact header (`schema_version`, `generated_at`, `git_sha`, `generator: "audit-choices@1.0"`, `run_id`, `event_kind: "choices-ledger"`).
- `openspec/changes/<change-id>/choices.md` — rendered from the JSON, least-confident-first.

The artifact is optional: its absence never fails validation or blocks archive (D8 — same posture as `session-log`).

## Common Rationalizations

| Rationalization | Why it's wrong |
|---|---|
| "The implementer already listed their decisions in session-log — skip the audit" | Self-reported decisions are exactly what this skill does *not* rely on. The highest-value output is the decision the implementer never noticed making; a self-review pass structurally cannot produce that. |
| "The auditor's `self_reported`/`session_log_ref` fields looked right — just persist them" | Those two fields are always recomputed deterministically by `collect_evidence.resolve_self_reported()`; whatever the auditor said about them is discarded. Trusting the auditor's own claim here reopens the exact hallucination risk D7 exists to close. |
| "This entry cites a commit that's probably close enough — keep it" | `filter_valid_provenance()` requires an exact (or unambiguous-prefix) match against the audited range's actual commit list. "Close enough" is how a hallucinated citation gets persisted; drop it instead. |
| "The ledger has `needs-user` entries, so the workflow should pause here" | It should not. D6 is explicit: this skill never blocks. `needs-user` entries surface at the existing `validate-feature`/`cleanup-feature` human gates, the same way deferred tasks do — no new gate. |
| "Re-running the audit after a no-op commit doubled the entry count — that's fine, more data is more data" | It is not fine — it is a bug. Unchanged decisions must keep the same `stable_id` and `merge_entries()` must update that slot in place, not duplicate it. |

## Red Flags

- Any file under `git status --short` after a run other than `openspec/changes/<change-id>/choices.json` and `choices.md` — the read-only contract has been violated.
- A `choices.json` entry whose `provenance.commits` or `provenance.files` is not a subset of the audited range's actual `git log`/`git diff` output.
- A `choices.json` where `self_reported: true` but no `session_log_ref` is present, or vice versa — the two are supposed to travel together.
- Two entries in `choices.md` with the same `choice` text and different `stable_id`s after a re-audit of an unchanged decision — the content-derived hash isn't actually content-derived.
- `choices.md` where a `high`-confidence entry appears before a `low`-confidence one, or a `sound` verdict appears before a `needs-user` verdict at the same confidence — the ranking invariant is the entire point of "least-confident-first."
- A non-zero exit code from anything in `skills/audit-choices/scripts/` — every entry point in this skill is required to exit 0.

## Verification

1. Run `cd skills && uv run pytest tests/audit-choices/ -q` and confirm all tests pass, including `test_readonly_posture.py`'s working-tree-snapshot assertion.
2. Run `grep -rniE 'anthropic|openai|import claude' skills/audit-choices/scripts/` and confirm it finds nothing — no LLM SDK import anywhere in this skill's Python (host-assisted invariant).
3. Validate a produced `choices.json` against `openspec/schemas/decision-choices.schema.json` with `jsonschema.Draft202012Validator` and confirm it passes, including the six-field header.
4. Confirm `choices.md`'s first entry is a lowest-confidence entry and no entry precedes one of strictly lower confidence.
5. Re-run the audit over an unchanged range and confirm `choices.json`'s entry count and every `stable_id` are unchanged — no duplicates.
6. Confirm the driver's exit code is `0` even when the candidate set includes `unsound` and `needs-user` verdicts, and even when an internal error is forced (e.g. an unreadable repo root).
