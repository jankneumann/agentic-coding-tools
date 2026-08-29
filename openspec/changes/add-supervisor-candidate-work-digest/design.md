# Design — add supervisor candidate-work digest

## Context

The cycle's digest is prose with no memory; stubs have no home; approval hands over a
proposal path a stub does not have. The design gives stubs a tracked store, splits ranking
into model judgment (schema-constrained) and script arithmetic (weights, signals, caching),
and routes approval through `refine-roadmap`'s transaction. Approach 1 (Gate 1).

## D1 — Stub store: one tracked file per stub, lifecycle elsewhere

**Decision.** `openspec/supervise/candidates/<stub_key>.json`, written by SENSE after
dedupe with `indent=2, sort_keys=True` and a trailing newline. The file is the stub payload
exactly as validated against `candidate-work.schema.json`; nothing else. Lifecycle
(`pending | approved | deferred | rejected`) is in `back_edge.digested_stubs`.

**Why files, not the handoff.** The handoff is a transport (change 2, D4); carrying every
stub in it makes each handoff grow with the backlog. Files are git-truth, diffable in PRs,
and already inside `_ALLOWED_WRITE_PREFIXES`. **Why lifecycle elsewhere.** A decision is a
supervisor fact, not a finding fact; keeping the file byte-identical to the validated stub
lets `stub_key` stay stable and lets ri-12's generators overwrite a stub without clobbering
a decision.

**`stub_key` as filename.** `change:<id>` and `prov:<hex32>` are filesystem-safe after
replacing `:` with `--`; the mapping is reversible and tested.

## D2 — Ranking: rubric sub-agent scores, script ranks

**Decision.** Five factors, each an integer 1–5 with a ≤200-char justification:

| Factor | Question the sub-agent answers | Evidence it is given |
|---|---|---|
| `relevance` | Is the finding still true on the current tree? | stub + provenance artifact excerpt |
| `value` | What changes for users/operators if this lands? | stub, roadmap proposals it maps to |
| `readiness` | Could an implementer start today? | ready set, active changes |
| `scope_fit` | Is it one change, or several, or a fragment? | stub `effort`, sibling stubs |
| `risk` | Blast radius if it goes wrong | stub `tags`, provenance generator |

`digest.py rank` validates the scores (`rubric-score.schema.json`), computes mechanical
signals itself — `dependency_ready` (every `depends_on` resolves to a completed item or an
archived change), `staleness_days` (age of the provenance artifact's last commit),
`prior_decision` — and orders by `score = Σ w_f · factor_f − staleness_penalty`, with
`deferred` stubs sunk below every `pending` one and `rejected` excluded. Weights are module
constants, documented in the digest output so a reader can recompute any rank by hand.

**Why not deterministic-only.** A formula over `priority`/`effort`/readiness/staleness
cannot judge relevance or value — it would rank a stale-but-high-priority finding above a
fresh, important one. **Why not model-only.** The skill promises that an unchanged tree
re-runs identically; a free-form ranking cannot keep that promise. The split keeps each
half where it is strong and makes the join point (the score file) inspectable.

**Reproducibility.** Scores are cached at `<stub_key>.rubric.json` with the cycle
fingerprint they were produced under. Unchanged fingerprint ⇒ no dispatch, identical
digest. Changed fingerprint ⇒ re-score only stubs whose provenance artifact or dependency
set changed (others keep their cached scores), so a small tree change does not re-judge the
whole backlog.

**Where the model is called.** From `SKILL.md`, by the host, as a sub-agent with the
`templates/rubric-prompt.md` prompt and the batch as input, returning JSON only. Never from
`scripts/` — `TestHostAssistedInvariant` covers `digest.py` automatically because it walks
the whole directory.

## D3 — `digest.py` is a new module; `cycle_state.py` keeps its surface

**Decision.** `store`, `rank`, `digest`, `stub-to-request`, `decide` live in
`skills/supervise/scripts/digest.py`, importing `stub_key`, `ready_across_roadmaps`,
`compute_fingerprint`, `load_ledger`, `classify_write` from `cycle_state`.

**Why.** `cycle_state.py` is 586 lines of idempotency machinery with its own CLI; adding
five subcommands and a rubric model would double it. A second module also lets the two
implementation packages of this change run in parallel (module vs prompt template) and
keeps change 2's `supervisor-record` additions to `cycle_state.py` from colliding with this
change's work.

## D4 — Approval goes through `refine-roadmap`, never a supervise-side roadmap write

**Decision.** `digest.py stub-to-request` renders a request YAML; the host runs
`refiner.py preview` then `apply --expect-base-sha256`. Field mapping:

| Stub | Roadmap item |
|---|---|
| `title` | `title` |
| `description` + `\n\nProvenance: <source_artifact> (<finding_ids>)` | `description` |
| `rationale` | `rationale` |
| `effort` | `effort` |
| `priority` | `priority` (refiner renumbers) |
| `depends_on` (change-ids) | `depends_on` (resolved to item ids where they match; unresolved ones go to the description) |
| `suggested_change_id` | `change_id` (refiner rejects collisions) |
| — | `item_id`: next free `ri-NN` |
| — | `acceptance_outcomes`: from `--acceptance`, required |

**Why the host drafts acceptance outcomes.** They are the one roadmap field a stub cannot
supply and the one `refine-roadmap` refuses to accept empty. Drafting them in conversation
is the operator's confirmation step — the "yes" is a yes to specific outcomes.

**Why not `plan-roadmap --force`.** `refine-roadmap/SKILL.md:122` says it plainly: `--force`
replaces the artifact and erases statuses and provenance. The transaction is the point.

## D5 — `decide` writes the supervisor record's `back_edge`; the cycle prunes

**Decision.** `digest.py decide` appends/replaces the `digested_stubs` entry in the
non-derivable mirror (change 2's `openspec/supervise/supervisor-record.json`) and the
handoff write at cycle end carries it. The next CYCLE removes `approved`/`rejected` stub
files and their `.rubric.json`; `deferred` files stay and return to `pending` after `until`.

**Why prune next cycle, not immediately.** `decide` may run several times in one
conversation; deferring deletion to the cycle keeps every mutation of
`openspec/supervise/` inside the audited `snapshot-writes` / `audit-since` window.

## D6 — Digest artifact and the unchanged-fingerprint path

`digest.json` (`digest.schema.json`): `{schema_version, fingerprint, generated_at,
sections: {needs_decision[], ready_now[], new_this_cycle[], blocked[], degraded[]},
ranked[]: {stub_key, rank, score, factors{...}, signals{...}, decision, suggested_change_id}}`.
When `cycle_state.py fingerprint` reports `unchanged`, the skill re-presents the prior
`digest.json` (and says so) rather than re-ranking — the existing stop rule, now with an
artifact to re-present.

## D7 — Sequencing

- Depends on change 2's `back_edge` slot and mirror; until it lands, `decide` writes to a
  `back_edge` key in the mirror file only (same shape), so this change is testable alone.
- ri-12 (generators emit stubs) is the real producer; fixtures stand in until then.
- `TestWorkflowContract` string assertions move with the reworded CYCLE sections.

## Task sizing notes

No task is L or XL. The rank task (1.4) is M because scoring validation, signals, weights,
caching, and ordering are one function's worth of logic that only makes sense tested
together.
