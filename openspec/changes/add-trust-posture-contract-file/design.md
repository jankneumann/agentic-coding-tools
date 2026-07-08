# Design: Trust Posture Contract File

## Context

The always-on-automation proposal identifies "human gates are prose, not policy" as
the first thing blocking unattended operation. Phase 1 sequences three capabilities:
(1) this trust posture *contract*, (2) the approval gate *service* that consumes it
(ri-05), and (3) encoding the gates in `autopilot.py` (ri-06). This change is (1) only.

The design constraint that dominates everything below: **the absent-file case must be
byte-identical to today**. The repo ships no active contract; the automation must
behave exactly as it does now until an operator deliberately writes `TRUST_POSTURE.md`.
Every other decision is subordinate to keeping that guarantee structural rather than
incidental.

Prior art we align with but do not duplicate:
- The coordinator's `trust_level` (1–5) + `resolve_trust_level` + guardrails
  (`agent-coordinator/src/agents_config.py`, `coordination_api.py:501`) govern *which
  coordinator operations an agent may perform*. Orthogonal to *whether a workflow gate
  needs a human*. We reuse the word "trust" and the fail-closed instinct, not the model.
- `flags.schema.json` + `feature_flags.py`: a repo-root YAML artifact whose JSON schema
  is declarative documentation while a Python module does authoritative runtime
  validation. We copy this split exactly.
- `skills/shared/active_agents.py`: a small, CLI-and-library dual-use shared helper with
  a fail-closed default. Same shape.

## Key Design Decisions

### D1: `TRUST_POSTURE.md` with typed YAML front matter, not `TRUST_POSTURE.yaml`

**Decision**: The contract is a Markdown file whose leading `---`-fenced YAML front
matter carries the typed policy, followed by human-readable prose. Ship the starter as
`TRUST_POSTURE.template.md`; the loader reads `TRUST_POSTURE.md`.

**Why**: This file is a *governance document a human owns and reasons about* — an
operator decides how much autonomy to grant. Front matter lets the machine-readable
policy and the inline documentation of what each gate/disposition means live in one
file, so the operator edits the policy with its explanation directly above it. It also
matches the always-on proposal's explicit phrasing ("`TRUST_POSTURE.md` (typed YAML
front matter)") and the repo's dominant convention — every `SKILL.md` is exactly this
shape (typed frontmatter + prose). A bare `.yaml` would be marginally simpler to parse
but would push all the per-gate documentation into comments or a separate doc that would
drift, and would break from the SKILL.md convention operators already know.

**Trade-off**: Parsing costs a few lines to split the front-matter fence before handing
the block to `yaml.safe_load`. Cheap and fully tested.

### D2: Template at `TRUST_POSTURE.template.md`, active path `TRUST_POSTURE.md`

**Decision**: The repo ships the *template*, not an active contract. The loader's active
path is `TRUST_POSTURE.md`, which does not exist in the repo.

**Why**: This is what makes the backward-compat guarantee real rather than aspirational.
If we shipped an active `TRUST_POSTURE.md`, we would be shipping a posture — and any
non-`block` disposition would change behavior on day one. Shipping only a template means
the live default is "absent → all block," and adoption is an explicit, reviewable
operator act (`cp TRUST_POSTURE.template.md TRUST_POSTURE.md`). The template itself ships
every gate as `block`, so even a blind copy is behavior-identical to today.

### D3: Absent file → all `block`, guaranteed by a single shared constant

**Decision**: `load_posture` returns `TrustPosture(gates={}, present=False)` when the
file is absent. `TrustPosture.disposition_for` is `self.gates.get(gate, BLOCK)` where
`BLOCK` is one module-level frozen `GateDisposition(disposition=Disposition.BLOCK)`.

**Why**: The guarantee is not "the loader remembers to return block in the absent
branch" — it is structural. There is exactly one fallback path (`dict.get` default) and
exactly one fallback value (`BLOCK`), shared by (a) the absent-file case, (b) any gate a
present file omits, and (c) any gate not in the file's `gates` map. There is no code path
by which an unconfigured gate can resolve to anything other than `block`. A test asserts
all eight gates block on an absent file; another asserts an omitted gate blocks in a
present file.

**Trade-off**: A present-but-empty file and a present-but-partial file both silently
fail-closed for the gates they omit rather than erroring. This is intentional (fail
closed, not loud) and distinguished from typos below.

### D4: Unknown gate / disposition is a hard error; omitted gate is a silent block

**Decision**: An **unknown gate key** or **unknown disposition value** raises
`PostureValidationError`. A **gate omitted** from `gates:` resolves to `block`.

**Why**: These are different failure modes. An omitted gate is an operator choosing not
to delegate it — the safe default is correct and silent. A misspelled gate
(`propsal_approval`) or disposition (`autoo`) is an *error the operator did not intend* —
if we fail-closed silently, the operator believes they delegated a gate they actually
typo'd, and the gate blocks forever with no signal. Failing loud on typos while
defaulting silently on omissions is the only combination that is both safe and
debuggable. `disposition_for` likewise raises on an unknown gate *name* (the closed set
means a consumer typo is a bug, not a block).

### D5: `notify_with_timeout` requires `timeout_seconds` + `default_action`; they are
forbidden elsewhere

**Decision**: For `notify_with_timeout`, `timeout_seconds` (positive integer, `bool`
rejected) and `default_action` (`proceed | block`) are required; missing or malformed
fails validation. For `auto` and `block`, both fields are *rejected* if present.

**Why**: A `notify_with_timeout` gate with no timeout has no defined behavior — the whole
point is "wait N seconds then apply the default." Requiring both closes that hole.
Rejecting the fields on `auto`/`block` catches the common mistake of setting a timeout on
a gate whose disposition was left as `block`, which would otherwise be a silent no-op that
looks like it should time out. `bool` is rejected explicitly because `yaml` parses `true`
as `1`-ish in some contexts and a boolean timeout is always a mistake.

### D6: JSON schema mirrors the loader, loader is authoritative

**Decision**: Ship `openspec/schemas/trust-posture.schema.json` encoding the same rules
(restricted gate keys via `additionalProperties: false`, the `notify_with_timeout`
conditional via `if/then/else`). The Python loader performs the authoritative runtime
validation; the schema is declarative documentation and tooling input.

**Why**: Exactly the `flags.schema.json` / `feature_flags.py` split the repo already uses.
The loader must run without a `jsonschema` dependency at gate-evaluation time (it runs
inside autopilot loops), so validation is hand-rolled and collects *all* errors in one
pass — better operator ergonomics than jsonschema's first-error abort. The schema earns
its keep as CI/editor validation and as the single place the shape is documented
declaratively. A cross-check test confirms schema and loader agree on the template and on
the key negative cases.

### D7: New `trust-posture` capability spec, not an extension of `skill-workflow`

**Decision**: The spec delta adds a **new capability** `trust-posture` rather than
extending `skill-workflow`.

**Why**: `skill-workflow` describes *skills* — user-invocable workflow commands and their
phase behavior. The trust posture is neither a skill nor a workflow phase; it is a
repo-owned *artifact + library contract*, in the same family as `flags.yaml`,
`roadmap.yaml`, or the archetypes contract — each of which has its own capability home.
The consumers (ri-05 approval gate service, ri-06 gate encoding, Phase 3 sync windows)
will each amend *their own* specs to say "reads the trust posture"; the contract itself
deserves a stable capability of its own that those specs can reference. Putting it in
`skill-workflow` would bloat an already-large spec with an artifact that no skill owns.

### D8: The API surface ri-05 depends on

ri-05's approval gate service is the reason this API exists. Its call pattern:

```python
from shared.trust_posture import load_posture, Gate, Disposition, DefaultAction

posture = load_posture()                       # fresh read; absent -> all block
gd = posture.disposition_for(Gate.MERGE)       # GateDisposition
if gd.disposition is Disposition.AUTO:
    audit("auto", gate="merge", posture=posture.present); proceed()
elif gd.disposition is Disposition.NOTIFY_WITH_TIMEOUT:
    request_approval(...); notify(...)
    if not wait_for_approval(timeout=gd.timeout_seconds):
        if gd.default_action is DefaultAction.PROCEED: proceed()
        else: park()
else:  # Disposition.BLOCK
    park()
```

Properties ri-05 relies on and this change guarantees:
- `load_posture()` never raises for the *absent* case (the common one) — it returns an
  all-block posture. It raises `PostureValidationError` only for a *present, malformed*
  file, which ri-05 surfaces as "posture unreadable → degrade to block."
- `disposition_for` is total over the eight gates and pure (no I/O, no caching), so ri-05
  can call it per gate without side effects.
- `GateDisposition` is a frozen dataclass with exactly the three fields ri-05 branches on;
  `timeout_seconds`/`default_action` are non-`None` iff the disposition is
  `notify_with_timeout`, so ri-05 needs no defensive `None` checks on the timeout path.
- Enums (`Gate`, `Disposition`, `DefaultAction`) are `str`-valued, so ri-05 can compare,
  log, and serialize them without conversion.

## Alternatives Considered

- **`TRUST_POSTURE.yaml` (pure YAML).** Rejected per D1 — loses inline documentation and
  breaks the SKILL.md frontmatter convention operators know.
- **Ship an active all-block `TRUST_POSTURE.md`.** Rejected per D2 — even an all-block
  active file invites an operator to edit the live file in place with no template to
  return to, and blurs "absent" (the guaranteed default) with "present and all-block"
  (a loaded posture). Keeping them distinct via `present` lets ri-05 log which authorized
  a decision.
- **Depend on `jsonschema` at runtime.** Rejected per D6 — adds a heavy import to the
  autopilot hot path and gives worse (first-error) diagnostics than the one-pass
  collector.
- **Extend `trust_level` (1–5) to encode gates.** Rejected — conflates operation
  authorization with workflow gating; a single integer cannot express per-gate
  `notify_with_timeout` with timeouts and defaults.

## Testing Strategy

`skills/shared/tests/test_trust_posture.py` (29 tests) covers: valid contract loads; all
eight gates enumerated and representable; absent file → every gate blocks; omitted gate →
block; each of the four disposition configurations round-trips; unknown gate fails;
unknown disposition fails; `notify_with_timeout` missing/malformed/`bool`/zero/negative
timeout fails; missing/unknown `default_action` fails; timeout on a `block` gate fails;
wrong `schema_version` fails; missing/unterminated front-matter fence fails; multiple
errors collected in one pass; `disposition_for` raises on unknown gate name; string and
enum gate args are equivalent; explicit `path=` override. A separate cross-check asserts
the JSON schema and loader agree on the template and the key negatives.
