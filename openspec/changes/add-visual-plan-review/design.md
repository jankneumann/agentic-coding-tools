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

Every requirement and task gets a deterministic `data-plan-anchor` derived from its heading slug /
task id, so an annotation still resolves after the agent edits the proposal and the artifact is
re-rendered. Selectors are a fallback for free-text range selections that have no anchor.

### D4 — Layout gate

The gate audits the rendered artifact for horizontal overflow, element clipping, and text overlap,
emitting `{selector, kind, overflowPx, viewportWidth, severity}` findings (lavish-axi's shape).
`error`-severity findings mask the human view until fixed; `warning`-severity render normally.

**Gate-1 operator decision (Decision D in proposal):** does an `error`-severity gate also *block the
agent* from proceeding to `iterate-on-plan` (hard gate), or only annotate the artifact and let the
flow continue (soft gate)? Default proposed: **soft gate** — record the finding, let iteration
continue, surface it in the annotation artifact. Operator confirms at Gate 1.

### D5 — Long-poll, no timeout

The agent calls the poll endpoint and blocks; queued annotations survive disconnects (persisted to
`plan-annotations.json` on every queue). A `--timeout-ms` escape hatch exists for tests only.
Sessions are keyed by canonical change-id (like lavish-axi's file-path identity), so no opaque IDs.

### D6 — Environment awareness

`environment_profile.detect()` gates the interactive loop. In cloud/headless: render the artifact to
disk, skip the server and poll, log `visual review skipped: <profile>`. This mirrors how mutating
skills short-circuit worktree ops in cloud harnesses.

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
