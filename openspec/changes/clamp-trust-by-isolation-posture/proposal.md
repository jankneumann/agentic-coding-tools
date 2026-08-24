# Clamp effective trust by isolation posture

> Change ID: `clamp-trust-by-isolation-posture`
> Effort: M
> Priority: 2

## Summary

Make an agent's *effective* trust level the minimum of two inputs: the vendor
trust ceiling already declared in `agents.yaml`, and a cap derived from the
runtime's **isolation posture** (filesystem containment × network egress).
Posture is an operator assertion recorded at enrollment
(`scripts/add_agent_keys.py --isolation fs=<mode>,net=<mode>`, already landed
as recorded-but-not-enforced metadata on each key's identity entry); this
change adds the enforcement:

```
effective_trust = min(vendor_ceiling, posture_cap)
```

The posture→cap mapping lives in YAML policy configuration, not code. Session
self-reports of detected posture may only lower the effective cap, never raise
it, and a mismatch against the operator assertion emits an audit event.

## Why

Vendor identity answers *who is acting*; isolation answers *how contained a
mistake or compromise is*. The Unified Trust Scale (`src/trust_levels.py`)
currently conflates them: `claude_code_local` carries trust 3 whether the
binary runs inside an isolated VM, an OS-level sandbox, or directly on the
operator's filesystem with open egress. An agent in a cloud VM or sandbox can
safely *earn* its vendor ceiling; the same agent raw on the filesystem should
be clamped to Standard — keeping automated verification and losing the
trust≥3 grants (merge-queue operations, verification skips) — no matter how
good the vendor is.

The `min()` formulation keeps the existing scale as the only scale: policy
thresholds, action tiers, and the `agent_profiles` CHECK constraint are
untouched. Isolation enters as a clamp on the input, not a new dimension every
enforcement point must learn.

## Design constraints

- **Posture is a fact, not a grant.** The coordinator cannot give a local
  agent isolation; it can only learn the posture and condition policy on it.
- **Assertion hierarchy.** (1) Operator assertion at enrollment is
  authoritative for *raising* the cap — the operator is the trust root.
  (2) Harness-implied posture (a `*-remote` agent runs in the vendor's cloud
  by construction of its transport) needs no assertion. (3) Session
  self-reports (`EnvironmentProfile.detect()`, see
  `add-isolation-posture-detection`) are **downgrade-only**: an honest agent
  reporting "actually I'm raw on the fs" tightens its own leash; a lying agent
  gains nothing.
- **Fail conservative.** Identity entries with no recorded posture (all keys
  minted before this change) are treated as `fs=none, net=open`.
- **Thresholds in YAML, not code** (established review policy): the
  posture→cap table ships as policy configuration with documented defaults.
- **Workspace hygiene is not containment.** `worktree` is a merge-conflict
  strategy granting full filesystem access; it is not a value of the fs
  dimension.

## Default posture→cap mapping (shipping configuration)

| fs containment | network | cap | rationale |
|---|---|---|---|
| vm / container | restricted | 4 | blast radius contained both ways |
| vm / container | open | 3 | fs contained, exfiltration possible |
| sandbox | open | 3 | fs contained, exfiltration possible |
| none | open | 2 | full blast radius — automated verification stays on |
| none | restricted | 2 | fs damage possible; egress limits help little locally |

## Dependencies

- `add-isolation-posture-detection` (fs × net split in
  `skills/shared/environment_profile.py`) — required only for the
  session-downgrade signal; the enrollment-asserted clamp works without it.
- Enrollment posture recording — landed with `scripts/add_agent_keys.py`
  (`isolation` field on identity-map entries).

## Out of scope

- Attestation of posture claims (verifying the sandbox actually exists).
- Moving keys/identities from Railway env vars into a DB-backed `agent_keys`
  table — separate end-state change; the clamp reads posture from wherever
  the identity record lives.
- Enforcing network egress itself — the coordinator conditions *its own*
  authorization decisions on posture; it does not implement the sandbox.

## Acceptance outcomes

- Policy decisions and profile resolution consume `effective_trust`, computed
  in exactly one place.
- The cap table is YAML-loaded; an unknown or missing posture resolves to the
  most conservative applicable cap.
- A session self-report below the asserted posture lowers the effective cap
  for that session and emits a `posture_mismatch` audit event naming both
  postures.
- A self-report above the asserted posture changes nothing and emits the same
  audit event.
- Identity entries without an `isolation` field behave exactly as
  `fs=none, net=open`.
