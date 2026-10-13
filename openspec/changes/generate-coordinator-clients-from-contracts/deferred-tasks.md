# Deferred tasks: generate-coordinator-clients-from-contracts

## 6.3 Replay the breaking-change gate over the last 20 contract edits

**Why deferred:** the replay needs a runnable oasdiff. oasdiff v1.24 and later require
Go 1.26, and the implementation sandbox has Go 1.24.7 with no route to download a
newer toolchain (proxy.golang.org, sum.golang.org and release-asset hosts are
outside its egress allowlist). The gate runs only in CI, where Go 1.26 is set up.

**What stands in for it in `decision.md`:** the gate's first real CI run on this PR
(run 37898001576, job `contract-breaking-change-gate`), which compared the typed
`features.yaml` against `main` with oasdiff v1.33.0. That is one observed comparison,
not twenty, so the false-positive criterion in design D7 is recorded as
*insufficient evidence*, not as met.

**How to complete it:** a one-off `workflow_dispatch` job (or a local machine with
Go 1.26) running, for each of the last 20 commits touching
`openspec/contracts/**/openapi/*.yaml`:

```bash
python scripts/contract_gate/check_breaking.py --base <commit>~1 --oasdiff <path-to-oasdiff>
```

from a checkout of `<commit>`, recording which findings a reviewer would have
judged non-breaking. Track as a follow-up of the rollout change that `decision.md`
proposes.
