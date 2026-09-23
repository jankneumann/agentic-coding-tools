# Session Log: add-isolation-posture-detection

## Phase: Plan Reconciliation (2026-09-23)

**Agent**: codex | **Session**: N/A

### Decisions

1. Use nested factual booleans with legacy read/construction compatibility.
2. Define filesystem as per-session workspace isolation, not security containment.
3. Recognize conservative exact Claude/Codex markers and independent network evidence.

### Alternatives Considered

- Router/trust enums: rejected because requests and asserted containment are different facts.
- Generic `CI`: rejected due to local-CI false positives.

### Trade-offs

- Preserve the coordinator surface but leave endpoint repair outside dg-03.
- Missing network evidence remains unrestricted even when filesystem isolation is known.

### Completed Work

- Reconciled the scaffold into an implementation-ready TDD plan.
- Reproduced the detection gap and pinned exact signals.

### Context

dg-03 is the only ready roadmap item. Its direction and continued execution are approved.

---

## Phase: Implementation and Review (2026-09-23)

**Agent**: codex | **Session**: N/A

### Decisions

1. Resolve precedence independently for filesystem and network through every layer.
2. Reject malformed canonical coordinator posture instead of consulting a legacy field
   from the same response.
3. Match empirical Codex/Claude harness markers only at their documented exact values.
4. Make local-worktree test preconditions explicit rather than weakening cloud detection.

### Review

- Round 1 dispatched to all five configured vendor harnesses.
- Antigravity returned zero findings; Claude, Codex Sol, and Grok identified precedence,
  spec-delta, hermeticity, exact-marker, and provenance gaps that were fixed.
- Pi failed with `auth_required`; no Pi finding was used.

### Validation

- Expanded dg-03 affected gate: 238 passed, 5 skipped.
- Configured shared skills suite: 5,200 passed, 17 skipped.
- CI-equivalent isolated per-skill loop: passed.
- Ruff: passed.
- Strict OpenSpec validation: 114 passed, 0 failed.

### Context

The first full gate exposed ambient Codex markers in tests that implicitly assumed local
execution. Regression fixtures now state local mode explicitly, and detector tests clear
all input signals before arranging each scenario. Vendor review then drove the
per-dimension precedence refactor and canonical MODIFIED requirement.

### Convergence

Round 5 completed with zero findings from all five configured harnesses:
Antigravity (`gemini-3.8-flash-high`), Claude Code (`fable`), Codex
(`gpt-5.6-sol`), Grok (`grok-4.5`), and Pi
(`nvidia/nemotron-3-ultra-550b-a55b`). The final affected gate passed 243 tests
with 5 skips; Ruff and 114/114 strict OpenSpec validations passed.
