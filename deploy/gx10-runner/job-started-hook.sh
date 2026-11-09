#!/usr/bin/env bash
# Runner-side enforcement point (design D4).
#
# The runner executes this hook at the start of EVERY job (ACTIONS_RUNNER_HOOK_JOB_STARTED),
# before any step, `container:` or `services:` setup, with the runner process's environment.
# Workflow YAML is PR-controlled for pull_request runs, so a fork PR can rewrite `runs-on`
# and delete its fork-guard step; this hook lives in the image and cannot be changed by a PR.
#
# It reads the GitHub-written event payload and fails the job (non-zero) unless the run is:
#   - push to refs/heads/main
#   - workflow_dispatch (only users with write access can dispatch)
#   - pull_request whose head repository equals this repository (not a fork)
# Everything else (fork pull_request, merge_group, pull_request_target, any new trigger) is
# refused. The hook fails closed: a missing or unparsable payload is a refusal.
set -euo pipefail

event="${GITHUB_EVENT_NAME:-}"
ref="${GITHUB_REF:-}"
repo="${GITHUB_REPOSITORY:-}"
payload="${GITHUB_EVENT_PATH:-}"

refuse() {
  echo "::error::gx10 runner refused this job: ${1}. Only push to main, workflow_dispatch and same-repository pull_request runs may execute on this runner." >&2
  exit 1
}

case "$event" in
  push)
    [[ "$ref" == "refs/heads/main" ]] || refuse "push to '${ref}' (only refs/heads/main is allowed)"
    ;;
  workflow_dispatch)
    ;;
  pull_request)
    [[ -n "$repo" && -n "$payload" && -r "$payload" ]] || refuse "no readable event payload for pull_request"
    head_repo="$(jq -r '.pull_request.head.repo.full_name // empty' "$payload")" ||
      refuse "unparsable event payload"
    [[ -n "$head_repo" ]] || refuse "pull_request payload has no head repository"
    [[ "${head_repo,,}" == "${repo,,}" ]] ||
      refuse "pull_request from fork '${head_repo}' (base is '${repo}')"
    ;;
  *)
    refuse "event '${event}' is not allowed"
    ;;
esac
exit 0
