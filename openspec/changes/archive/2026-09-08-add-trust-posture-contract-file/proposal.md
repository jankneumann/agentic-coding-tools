# Add Trust Posture Contract File

> Parent roadmap: `roadmap-always-on-agent-automation` (item ri-04)
> Change ID: `add-trust-posture-contract-file`
> Effort: M

## Why

The autopilot and roadmap loops run to terminal states, but their human gates are
**prose, not policy**. Proposal approval lives in `skills/autopilot/SKILL.md` text;
the terminal merge STOP lives in `/cleanup-feature`; ESCALATE and `replan_required`
park forever waiting for a person. There is no machine-readable object an unattended
process can consult to decide "may I proceed through this gate without a human?"

The always-on-automation proposal (`docs/proposals/always-on-agent-automation.md`,
Phase 1) makes this the first brick: *"Every human gate gets a machine-readable
disposition per trust posture: `auto`, `notify_with_timeout` (default action on
expiry), or `block`. Prose instructions stop being the enforcement mechanism."*

This change delivers **only the contract and its loader/validator** — the narrow,
consumable substrate. The approval gate service (ri-05, `skills/shared/approval_gate.py`)
and the in-code gate encoding (ri-06) build on the clean API this change exposes;
they are out of scope here. Shipping the contract first, with an absent-file default
that is byte-identical to today, lets the consumers land behind it with zero behavior
change until an operator opts in.

The symphony roadmap's `trust-posture-binding` item (priority 12) covers a broader,
*deployment-level* posture (sandbox mode, network allowlist, coordinator trust level,
guardrail posture). This change is the narrower **per-gate disposition layer** the
always-on proposal pulls forward to Phase 1. It keeps vocabulary coherent with the
coordinator's existing `trust_level` (1–5) / `resolve_trust_level` / guardrail model
but does not duplicate it: `trust_level` governs *which coordinator operations an
agent may perform*; the trust posture governs *whether a workflow gate needs a human*.
The two are orthogonal and composable.

## What Changes

### New repo-owned contract file (template)

**`TRUST_POSTURE.template.md`** — a documented starter at the repo root. YAML front
matter carries the typed, schema-validated policy; the prose body documents every
gate, disposition, and field with a worked example. Operators opt in by copying it to
`TRUST_POSTURE.md` (the active path the loader reads). The template ships every gate
as `block`, so `cp TRUST_POSTURE.template.md TRUST_POSTURE.md` is behavior-identical
to today until gates are deliberately flipped.

Per gate the contract declares a **disposition** — `auto | notify_with_timeout | block` —
plus, for `notify_with_timeout`, a required `timeout_seconds` (positive integer) and
`default_action` (`proceed | block`) applied when the timer expires.

The **eight gates** are enumerated and representable:
`gatekeeper_escalation` (GATEKEEPER escalation), `proposal_approval` (proposal approval),
`plan_review_convergence_failure` (plan-review convergence failure),
`validation_failure` (validation failure), `escalate_resume` (ESCALATE resume),
`replan_required`, `pr_creation` (PR creation), and `merge`.

### New loader/validator library

**`skills/shared/trust_posture.py`** — a small, side-effect-free API that ri-05 builds
on:

- `load_posture(repo_root=None, *, path=None) -> TrustPosture` — reads the contract
  fresh on every call (hot-reloadable). **Absent file → `present=False` posture whose
  `disposition_for(gate)` returns `block` for every gate.**
- `TrustPosture.disposition_for(gate) -> GateDisposition` — resolves one gate. Unknown
  gate names raise `ValueError` (gates are a closed set); known-but-unconfigured gates
  and the absent-file case return `block` (fail-closed).
- `GateDisposition(disposition, timeout_seconds, default_action)` — a frozen dataclass.
- `Gate`, `Disposition`, `DefaultAction` — enums.
- `validate_posture_file(path) -> list[str]` — returns all errors in one pass (empty ==
  valid); never raises for validation problems, for CLI/CI use.
- `PostureValidationError` — raised by `load_posture` when a present file is invalid.
- CLI: `python -m shared.trust_posture validate|show [PATH]`.

Mirrored (by `skills/install.sh`) into `.claude/skills/shared/` and
`.agents/skills/shared/` alongside the other shared helpers.

### New JSON schema

**`openspec/schemas/trust-posture.schema.json`** — the declarative mirror of the front
matter, restricting gate keys to the eight names and encoding the
`notify_with_timeout ⇒ timeout_seconds + default_action` conditional. Follows the
established `flags.schema.json` / `feature_flags.py` pattern where the JSON schema is
the declarative contract and the Python module performs authoritative runtime
validation.

### New capability spec

Adds a new `trust-posture` capability spec (see *Out of scope* for why not
`skill-workflow`).

## Out of scope

- **The approval gate service (ri-05).** Consulting the posture, filing approvals,
  polling `check_approval`, applying defaults, and coordinator-down degradation all
  live in `skills/shared/approval_gate.py` in the next change. This change only makes
  the disposition *readable*.
- **Encoding gates in `autopilot.py` / SKILL.md (ri-06).** Moving the prose gates into
  code and the goal-gate check at DONE are downstream.
- **Deployment-level posture** (sandbox mode, network allowlist, coordinator trust
  level, guardrail posture) — that is symphony `trust-posture-binding`, bound to
  `profiles.py` / `policy_engine.py`, not this per-gate layer.
- **Scheduled sync windows / auto-merge ceilings** (Phase 3) — those read this contract
  but are separate changes.
- **Hot-reload machinery beyond "read fresh each call."** No file watcher; consumers
  call `load_posture()` at each gate.

## Success Criteria

- `openspec validate add-trust-posture-contract-file --strict` passes.
- A valid contract loads; an unknown gate name fails validation; an unknown disposition
  fails validation; a `notify_with_timeout` gate missing or with a malformed
  `timeout_seconds` fails validation.
- With **no** `TRUST_POSTURE.md` present, `load_posture().disposition_for(g)` returns
  `block` for every one of the eight gates — byte-identical to today's behavior.
- Each of the four disposition configurations (`auto`, `block`,
  `notify_with_timeout`+`proceed`, `notify_with_timeout`+`block`) round-trips through
  the loader.
- All eight gates are present in the template and representable through the API.
