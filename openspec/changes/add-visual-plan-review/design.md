# Design — add-visual-plan-review

## Context

`plan-feature` produces markdown OpenSpec proposals. Human objections to a plan are best expressed
by pointing at a specific requirement/task, but markdown review forces prose descriptions of
location. We are adding a derived HTML review surface with element-anchored annotation capture,
borrowing the interaction model from `lavish-axi` but implementing it natively in Python.

## Key Decisions

### D1 — Module placement: `skills/shared/plan_review/`

Lives under `skills/shared/` (like `environment_profile.py`) so both `plan-feature` and
`parallel-review-plan` import it without cross-skill coupling. Three files: `render.py` (md → html),
`server.py` (serve + gate + poll), `annotations.py` (schema + persistence).

### D2 — Annotation schema (wire-compatible with lavish-axi)

```json
{
  "uid": "a1b2c3",
  "selector": "#req-3 > li:nth-child(2)",
  "tag": "li",
  "text": "assumes the coordinator is reachable",
  "prompt": "This is false in cloud runs — see environment_profile.detect()",
  "target": { "startOffset": 12, "endOffset": 41 },
  "anchor": "req-3",
  "resolved": false
}
```

`uid`, `selector`, `tag`, `text`, `prompt`, `target` mirror lavish-axi exactly. We add `anchor`
(the stable `data-plan-anchor` id, robust to re-render when the CSS selector shifts) and `resolved`
(so folded-in annotations can be marked handled). `text` is truncated to 240 chars like lavish-axi.

### D3 — Stable anchors survive re-render

Every proposal requirement, every **spec-delta requirement and scenario** (from `specs/**/spec.md`),
and every task gets a deterministic `data-plan-anchor` derived from its heading slug / task id, so an
annotation still resolves after the agent edits the plan and the artifact is re-rendered. Scenarios
are anchored too, since a reviewer often objects at the scenario level. Selectors are a fallback for
free-text range selections that have no anchor.

### D4 — Layout gate

The gate audits the rendered artifact for horizontal overflow, element clipping, and text overlap,
emitting `{selector, kind, overflowPx, viewportWidth, severity}` findings (lavish-axi's shape).
`error`-severity findings mask the human view until fixed; `warning`-severity render normally.

Because an `error`-severity finding **masks the human view**, it necessarily blocks review — the human
cannot annotate or signal completion on a masked artifact. So error severity is **not** subject to a
soft/hard toggle: `plan-feature` MUST run the remediation loop (regenerate → re-audit) until no
`error`-severity finding remains before it waits for human completion, else the run deadlocks (see the
skill-workflow "Plan Review Layout Gate" requirement). The only genuinely soft class is
`warning`-severity, which renders normally and is surfaced as an annotation without blocking.

### D5 — Long-poll, no timeout

The agent calls the poll endpoint and blocks; queued annotations survive disconnects (persisted to
`plan-annotations.json` on every queue). A `--timeout-ms` escape hatch exists for tests only.
Sessions are keyed by canonical change-id (like lavish-axi's file-path identity), so no opaque IDs.

### D6 — Environment awareness (interactive-capability, not just isolation)

A dedicated interactive-review capability check gates the interactive loop — not
`environment_profile.detect()` alone, whose `isolation_provided` describes worktree filesystem
isolation, not whether a human can drive a browser review. The check combines the cloud/headless
profile, a `CI` signal, and display/browser availability, plus an explicit override flag; a local CI
job or SSH session (isolation=false but no human at a browser) must still short-circuit. When it
does: render the artifact to disk, skip the server and poll, log `visual review skipped: <reason>`.
This mirrors how mutating skills short-circuit worktree ops in cloud harnesses.

### D7 — Security posture

Binding `127.0.0.1` is necessary but **not sufficient**: any page in the user's browser can still
POST to a localhost port via a cross-site request, and the artifact renders untrusted proposal/
annotation text. So the server also (a) embeds a per-session random token in the artifact and
requires it on every poll/annotation-write request, (b) validates `Host` and `Origin` and does not
enable permissive CORS, and (c) escapes/sanitizes rendered markdown (no raw HTML execution) under a
restrictive Content-Security-Policy. The artifact is self-contained (inlined CSS/JS) so it can be
opened directly from disk or attached to a PR without a running server — the CSP forbids external
and inline-script injection from proposal content while still permitting the artifact's own inlined
assets via a nonce.

### D8 — Explicit session completion, not an implicit one

A no-timeout long-poll needs a positive "review is done" signal, otherwise the agent either blocks
forever (reviewer with no feedback) or races ahead after the first annotation batch. The artifact
carries a "done / continue" control that emits a terminal `complete` event over the poll channel;
`plan-feature` folds annotations and advances only on that event or an operator abort. This makes the
zero-annotation case a first-class outcome rather than an indefinite hang.

## Risks

- **Anchor drift** if the agent rewrites a requirement heading between renders — mitigated by
  slug-based anchors and the selector fallback, but a heavily reworded plan may orphan an annotation
  (surfaced as `anchor: null, resolved: false` rather than silently dropped).
- **Scope creep toward a general artifact editor** — explicitly bounded: this change renders *OpenSpec
  proposals only*, not arbitrary HTML. General artifacts are a separate future capability.
