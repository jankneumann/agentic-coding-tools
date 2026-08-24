# Tasks: Clamp effective trust by isolation posture

> Change ID: `clamp-trust-by-isolation-posture`

## Status

- [ ] Planning
- [ ] Implementation
- [ ] Testing
- [ ] Review
- [ ] Done

## Tasks

- [ ] 1.1 Define the posture model (`fs` × `net` enums) in one module shared by
      config loading, the clamp, and the enrollment script's validation lists
- [ ] 1.2 Add the posture→cap mapping to policy YAML with the documented
      defaults; loader falls back to the most conservative cap for unknown or
      partial postures
- [ ] 2.1 Compute `effective_trust = min(vendor_ceiling, posture_cap)` at
      profile resolution, reading posture from the key's identity entry;
      missing posture ⇒ `fs=none, net=open`
- [ ] 2.2 Thread `effective_trust` (and raw posture, for Cedar/native rules)
      into the policy-engine context; trust-gated grants (merge queue,
      verification skips) compare against the clamped value
- [ ] 3.1 Accept a self-reported posture on `register_session` / heartbeat;
      apply `min(asserted_cap, reported_cap)` per session
- [ ] 3.2 Emit a `posture_mismatch` audit event whenever reported ≠ asserted,
      carrying both postures and the winning cap
- [ ] 4.1 Tests: clamp arithmetic across the cap table, conservative default
      for legacy identities, downgrade-only session semantics, mismatch audit
      payload against the audit contract
- [ ] 4.2 Documentation: trust-scale doc gains the ceiling/cap distinction;
      enrollment README section cross-links `--isolation`
