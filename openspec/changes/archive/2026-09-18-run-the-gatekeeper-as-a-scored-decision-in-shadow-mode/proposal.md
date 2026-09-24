# Run the GATEKEEPER as a scored decision in shadow mode

> Parent roadmap: `roadmap-jev-system-one-integration-assessment`
> Change ID: `run-the-gatekeeper-as-a-scored-decision-in-shadow-mode`
> Roadmap item: `ri-06`
> Effort: L
> Priority: 1

## Why

`_phase_gatekeeper` in `skills/autopilot/scripts/autopilot.py` decides whether
an autopilot run may proceed autonomously by dispatching a premium-tier
sub-agent that free-text judges `state.gate_signals` and returns
`proceed` / `proceed_with_review` / `escalate`. This is exactly the class of
brittle, expensive, unmeasured LLM-prompt classification the
`jev-system-one-integration-assessment` roadmap targets: there is no
calibrated confidence, no per-run cost visibility, and no way to know how
often the judge would disagree with itself if evaluated a different way,
before betting behavior on it.

The fix is not to flip the switch yet — it is to measure first. This item
adds a second, calibrated judgment (two `Score` rubrics plus a `Choice`
cross-check, via `system_one_decisions.decide()`) that runs **alongside** the
existing judge on every GATEKEEPER run, computes a candidate verdict in code
from the two `Score` distributions against configured thresholds, and records
it — acting verdict, candidate verdict, and both distributions — without
acting on it. That gives `ri-08` a real, run-by-run disagreement rate to
gate the eventual promotion on, rather than a guess.

## What Changes

- `_phase_gatekeeper` gains one additive step: after computing the acting
  verdict exactly as today, it calls a new `_shadow_gatekeeper_judgment`
  helper that asks `Score(verifiability, 4 levels)`, `Score(risk, 4 levels)`,
  and `Choice(verdict, {proceed, proceed_with_review, escalate})` over
  `state.gate_signals` plus `proposal.md`, `tasks.md`, and a work-packages
  summary, computes a candidate verdict from the two `Score` answers against
  configured thresholds, and appends a `"GATEKEEPER_SHADOW"` entry to
  `state.phase_history` carrying both verdicts and both score distributions.
- `_run_phase` threads `change_dir` into `_phase_gatekeeper` so the shadow
  judge's state payload can read the plan artifacts.
- New `skills/autopilot/scripts/gatekeeper_shadow.py`: the shadow-judgment
  helper, the code-computed-verdict thresholding function, and the
  config-sourced thresholds (default layer + optional sidecar JSON,
  mirroring `ri-05`'s `review_rules.py` precedent).
- New `skills/autopilot/scripts/gatekeeper_shadow_report.py`: a deterministic
  reporting CLI that reads recorded `loop-state.json` files and emits the
  GATEKEEPER shadow-period disagreement rate.
- No change to the acting verdict, `--force`, the scope-safety floor, or the
  existing premium-tier judge dispatch — see design.md's Non-goals.

## Impact

- **Affected specs**: `skill-workflow` (adds a shadow-recording requirement
  to the GATEKEEPER phase; does not modify the existing GATEKEEPER
  requirements this item leaves untouched).
- **Affected code**: `skills/autopilot/scripts/autopilot.py` (additive change
  to `_phase_gatekeeper` and `_run_phase`'s GATEKEEPER dispatch line), new
  `skills/autopilot/scripts/gatekeeper_shadow.py` and
  `gatekeeper_shadow_report.py`.
- **Risk**: low — every new code path is additive and defensively no-ops on
  any unavailability branch; the acceptance outcomes require a byte-identical
  acting verdict, proven by a replay test over two real recorded
  `gate_signals` fixtures.

## Non-Functional Requirements

| Attribute | Metric | Target | Verifying phase |
|---|---|---|---|
| Cost | Shadow `decide()` calls per GATEKEEPER run | Exactly 1 | Unit test on `_shadow_gatekeeper_judgment` call count |
| Safety | Acting verdict divergence from today's behavior | Zero, for every run in the shadow period | Fixture-replay test over recorded `gate_signals` |
| Observability | GATEKEEPER shadow disagreement rate | Emitted by `gatekeeper_shadow_report.py` | Manual/CI report run over recorded `loop-state.json` files |

## Dependencies

- `ri-05` (establishes the merge-model / config-threshold precedent this item
  follows for D3, and is the most recently completed roadmap item this one
  depends on per the roadmap DAG).

## Non-Goals

- Promoting the shadow verdict to the acting decision — `ri-08`'s job.
- Retiring the premium-tier `gatekeeper_fn` dispatch — `ri-08`'s job.
- A project-override config layer for shadow thresholds beyond one
  default-plus-sidecar file.
- Vindication attribution (which side a later review round agreed with) —
  `ri-07`'s job for its own shadow record.
