# Tasks: Widen execution-environment detection to an isolation posture

## 1. Contract and detection (TDD)

- [x] 1.1 Add failing tests for independent dimensions, compatibility, precedence, and exact cloud markers.
- [x] 1.2 Add `IsolationPosture`, widen `EnvironmentProfile`, and map each rung conservatively.
- [x] 1.3 Preserve diagnostics and reject malformed coordinator posture.

## 2. Worktree consumers (TDD)

- [x] 2.1 Test filesystem=true/network=false short-circuit behavior.
- [x] 2.2 Test network=true/filesystem=false does not short-circuit.
- [x] 2.3 Migrate worktree entrypoints and fallback profiles to the filesystem dimension.

## 3. Documentation and verification

- [x] 3.1 Update cloud execution, worktree, and mental-model documentation.
- [x] 3.2 Run focused/full tests, Ruff, and strict OpenSpec validation.
- [x] 3.3 Converge review across configured vendor-panel harnesses.

<!-- CHECKPOINT: implementation-complete -->

## 4. Landing

- [x] 4.1 Record evidence, push, merge, and advance the roadmap checkpoint.
