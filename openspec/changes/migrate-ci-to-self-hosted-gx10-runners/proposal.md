# Migrate CI to self-hosted GX10 runners

> Parent roadmap: `roadmap-always-on-agent-automation`
> Change ID: `migrate-ci-to-self-hosted-gx10-runners`
> Effort: M
> Priority: 2

## Summary

Ephemeral containerized GitHub Actions runners on the GX10 (systemd, arm64) with ci.yml/security.yml moved to self-hosted labels and a GitHub-hosted fallback lane; fork-PR execution requires approval.

## Dependencies

- None

## Acceptance Outcomes

- ci.yml and security.yml complete green on a self-hosted arm64 runner; non-arm64 jobs are explicitly pinned to the hosted lane.
- Median CI wall-clock for a typical PR drops measurably versus hosted runners.
- A fork PR cannot execute a job on the self-hosted runner without explicit approval.
- Runners are ephemeral per job and survive host reboot via systemd.

## Rationale

CI wall-clock directly bounds merge sync-window cadence, and the runner shares the Docker layer cache with validate-feature; aarch64 and fork-PR safety are first-class requirements.
