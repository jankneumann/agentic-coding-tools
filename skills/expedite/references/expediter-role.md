# Expediter role

The expediter is the read-only station between validation and a sync point. It
combines three readiness signals that were previously scattered across merge
workflows:

1. no active agents still own work on the change;
2. required validation phases pass their hard gates; and
3. the rework report does not require iteration or block cleanup.

The role returns `READY` or `BLOCKED`; it does not merge, push, update specs,
tear down worktrees, rerun validation, or fix findings. This separation keeps
the refusal decision independent from the operation it guards.

One residual remains: pending multi-vendor disagreements are not yet a fourth
check because the coordinator audit result shape for review events has not
stabilized. Add that check only after the public audit contract can provide a
portable, deterministic signal.
