# Tasks — Seed Sentinel Security-Evaluation Capability

> Seed-only change: the "implementation" is authoring + validating governance and
> spec artifacts and handing off to the roadmap. No role logic is built here.

## Phase 1 — Governing + spec artifacts

- [x] 1.1 Vendor `constitution.md` — 11 adapted principles + Deviations section (D-1 multi-vendor exception with verdict-provenance mitigation)
- [x] 1.2 Author `specs/sentinel-security-eval/spec.md` — 8 roles + lifecycle + evidence gate + fingerprint + exploited flag + verdict-provenance + governance + policy bindings, each with success + failure scenarios
- [x] 1.3 Author `design.md` — role→infrastructure binding table, seed↔roadmap boundary, deviation analysis, deferred-extension preconditions
- [x] Checkpoint: confirm every spec requirement has ≥1 success and ≥1 failure/edge scenario; confirm constitution Deviations names D-1 + mitigation

## Phase 2 — Project integration

- [x] 2.1 Add a reference to `constitution.md` from `openspec/project.md` so the Sentinel principles are discoverable as project context (do NOT inline the full text; link to the change/spec)
- [x] 2.2 Record the 5 deferred extension roles (Deep-Tester, Variant-Hunter, Attack-Mapper, Remediator, Self-Improver) with adopt-when preconditions in `design.md` D4 (already drafted; verify wording matches the foundry playbook)

## Phase 3 — Validation

- [x] 3.1 Run `openspec validate seed-sentinel-security-eval --strict` and fix any delta-format errors
  **Spec scenarios:** all in `sentinel-security-eval`
- [x] 3.2 Verify the diff is confined to `openspec/changes/seed-sentinel-security-eval/` plus the `project.md` reference — no role implementation code
- [x] Checkpoint: validation passes, scope is clean (spec/doc only)

## Phase 4 — Roadmap handoff

- [ ] 4.1 Run `/plan-roadmap` against this seed to decompose the 8 roles + lifecycle + governance into prioritized follow-on implementation changes, binding each to its mapped existing capability per `design.md` D1
- [ ] 4.2 Capture the 5 extension roles as roadmap candidates gated on their adopt-when preconditions (per `design.md` D4)
- [ ] Checkpoint: roadmap workspace created; seed marked ready to archive once roadmap exists
