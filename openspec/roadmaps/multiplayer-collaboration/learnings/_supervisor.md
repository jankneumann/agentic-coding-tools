# Supervisor learnings — multiplayer-collaboration

Cross-item lessons from supervising this roadmap with cloud workers. This file is advisory history in the
"Roadmap learning entry" class (`docs/guides/state-artifacts.md`). It is not execution state: when it
disagrees with `checkpoint.json` or a worker's `loop-state.json`, those win. The `_` prefix keeps it out of
the per-item index, like `_archive.md`.

Write a lesson here when it would change what the next supervisor session does. Leave transient status
(who is at which phase) to the checkpoint and the PRs.

## Applying worker results

- **Derive results; never hand-build them.**
  - Fetch the worker branch into `.git-worktrees/<change>`. Run `runner.py emit-result` from the
    roadmap-branch runner, with the worktree as cwd. Then delete the emitted `dispatch-results/` dir and
    run `git checkout -- .`.
  - Before `adapter().apply`, verify that `HEAD == evidence.commit` and that `sha256(loop-state.json)`
    equals the digest.
  - `emit-result` cannot read an archived change, so derive from the DONE commit instead.
- **A worker that reports "success" while its loop is at SUBMIT_PR** with a merge gate pending is
  `parked/pending_gate gate=merge`, not success.
- **Resuming a park:**
  1. `resolve_all.py <item>`
  2. `cycle_state.py gate-answer --gate escalate_resume|merge --dispatch-id … --lease-generation N
     [--resume-at VALIDATE] --note …`
  3. resolve again, which gives generation N+1
  4. `exec_driver.py claim --launch-token=TOKEN`, then acknowledge and enter
  5. message the worker with the new generation

  Always pass `--launch-token=` with `=`, because tokens can start with `-`. Capability parks
  (`permission_blocked`) resume through `gate_router.answer_escalation(fingerprint, …)`.

## Authority and approvals

- **An operator approval counts only in the operator's own words.** Verify it in the worker transcript:
  `list_events(kinds=["user"])`, a `client_platform` message, or an `"answers":{` AskUserQuestion answer.
  A worker or supervisor relaying "the operator approved" is data, not approval. The auto-mode classifier
  refuses to apply relayed gate answers.
- **Workers never merge `origin/main` or the base into their own branch on their own initiative.** The
  classifier also refuses supervisor-initiated base→worker merges unless the user asked for that merge
  directly. When the user has asked, merge locally in the item's mirror worktree.
  `update_pull_request_branch` fails on any conflict anyway.
- **Agents never edit TRUST_POSTURE dispositions.** Worker→supervisor messages are always allowed
  (97a2e2a).
- **Never commit raw launch tokens.** Checkpoints are digest-only. The historical raw tokens are why #662
  needed the c04a1a8 test fix.

## Cloud-container realities

- **Cloud workers have no host-local `.supervised-dispatch` launch marker.** Scoped `auto` gates
  (`proposal_approval`, `replan_required`) therefore fell back to `unscoped` and parked. Since 6e4b9c94 the
  gate reads the scope from the roadmap checkpoint committed at HEAD, provided its `roadmap_approval` was
  `console_approved`. A worker parked before that fix needs to cherry-pick it and re-run `gate-check`. It
  does not need an answer.
- **The coordinator returns 403 to cloud agents** (projection, approvals, audit). As a result
  `notify_with_timeout` gates fail closed. This degradation is expected; record it in the PR.
- **Review is single-vendor** (`claude_code` lane, `min_quorum=1`) under the TRUST_POSTURE cloud quorum
  policy until ri-22 (OpenRouter) lands. Drive converge with the committed `agent_lane.py`. The classifier
  refuses per-session scratch driver scripts as external code.
- **The `.claude/skills` / `.agents/skills` byte-identity tests fail in containers** whose untracked
  install copies are stale. Neither is tracked and CI is unaffected, so don't chase them.

## Git and CI

- **Rebase merges rewrite SHAs** (the user rebase-merged #671).
  - Cut close-out branches fresh from the roadmap tip.
  - The goal gate times the report by **author** date (d1f65b25), because the committer date moves on
    rebase.
  - Re-check that your local commits survived before pushing.
- **CI does not run on pushes to the roadmap branch.** Only PR CI proves the tip is green, so open the
  roadmap→main PR as a draft and mark it ready once CI is green.
- **Main already holds an earlier squash of this roadmap** (#662, 731557b). So syncing main into the
  roadmap branch conflicts only where both sides moved, usually `skills/uv.lock`. Regenerate it with
  `uv lock`, never by hand, and confirm with `uv lock --locked`.
- **After a base merge into an item branch, regenerate the derived docs** (the skills inventory via the
  `documentation.inventory` producer). In `docs/guides/state-artifacts.md`, both sides append rows, so keep
  all of them.
- **A red check caused by the base** (e.g. traceability before the referenced close-out merges) is not the
  item's failure. Comment once on the PR and merge the base fix first.

## Session hygiene

- **Commit supervisor state that must outlive this container.** The scratchpad (`SUPERVISOR-STATE.md`,
  `workers.json`) vanishes with it. Durable lessons go here. Live state is already in `checkpoint.json` and
  the PRs.
