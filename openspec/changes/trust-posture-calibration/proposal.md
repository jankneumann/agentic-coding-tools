# Calibrate trust posture from correction rates

> Parent roadmap: `multiplayer-collaboration`
> Change ID: `trust-posture-calibration`
> Effort: M
> Priority: 5

## Summary

Compute per-gate and per-owner approve-unchanged and override rates from correction records over a window, and generate trust-posture change proposals when a gate crosses a configured threshold, gated to the posture owner and never self-applied.

## Dependencies

- `ri-18`

## Acceptance Outcomes

- A gate report shows approve-unchanged and override rates per gate and owner over a configurable window.
- A trust-posture change proposal is generated when a gate crosses a configured threshold and requires the posture owner's approval to apply.
- No trust-posture change is applied without a recorded decision by the posture owner.

## Rationale

P9 calibrates trust from evidence and P8 reduces interruptions where humans consistently approve unchanged; owner-gated proposals keep authority with humans.
